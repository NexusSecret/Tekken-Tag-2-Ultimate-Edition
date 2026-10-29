// The gauge of an added Tekken 7 2D fighter, as Tekken 7 keeps it (its
// executable's rules; the moveset only names the costs and checks).
//
// - A fighter's gauge (player +0xcc8 in Tekken 7) holds 0 to its most
//   (+0xccc: 1000, two stocks of 500; Geese's 1500). Requirement 629 tests
//   it >= param, 635 < param; property 0x81c2 adds its value (EX moves
//   -500, supers -1000, a parry +300) and clamps it (0x14071d1b4).
// - Every frame (0x140713f72), for each fighter that took damage, both it
//   and its opponent gain gauge in percent of that damage: of a blocked
//   attack's damage (+0x7c8; the defender's +0x754 bit 8 set) 50 for the
//   defender and 100 for the attacker, of the health a hit took (+0x7d4)
//   150 and 300; Akuma 37 / 75 / 112 / 225 (Tekken 7's 2019 patch cut his
//   gain by a quarter), Geese 21 / 85 / 63 / 255. The attacker gains none
//   while its move set 0x8228 (+0x6b4: EX moves, Focus Attack, supers).
// - The gauge empties at a match's start (0x140759a50 for the start kinds
//   0-3, 11-15, 17, 19-21), not at a round's.
// - 0x8229 lights the fighter up (an EX move, a cancel: effect 38 at its
//   body, the fighter drawn yellow a moment).
// The converted moveset uses this file's ids for them (gauge.h); the gains
// follow the title's own state after each fighters' frame: the health a
// fighter lost (+96, 16 bits) and, on the frame it blocked (+1152 bit
// 0x20000000), the blocked attack's damage (+1180).
//
// The HUD is Tekken 7's (its HUD movie SW_UI_HUD_Rage: a panel at each
// bottom corner, a slot per stock that fills from one end and lights up
// when full, EX or SUPER! beside them), baked by the importer into the
// pack's gauge/: gauge.nut its pictures, gauge.ini each clip's frames as
// placed pictures on Tekken 7's 1920 x 1080 screen, the slots' bars and
// their masks (slot 0 the outer one: the gauge fills from the screen's
// edge). The clips play as Tekken 7's HUD code (0x1404c1940 on) plays
// them: a slot that fills plays EX then EX_MAX_01 and stays lit, a
// full gauge plays every slot's EX_MAX_02 and then loops their Super (the
// panel's and the text's too, lightning running), a slot that empties
// shows Normal; EXLight's Start runs as a stock fills, EXFocus's as the
// gauge is spent. A slot's bar is moved along its mask by how full it is
// (0x1404c1b90: 154 pixels a stock).

#include "title/gauge.h"

#include "gpu/overlay.h"
#include "title/framedata.h"
#include "title/image.h"
#include "title/roster.h"

#include "cafe/ppc_ops.h"
#include "cafe/runtime.h"
#include "cafe/sysmem.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <map>
#include <memory>
#include <optional>
#include <sstream>
#include <vector>

namespace cafe::title::gauge {
namespace {

namespace fs = std::filesystem;

constexpr uint32_t kHealth = 96, kHitDamage = 1180, kEvents = 1152, kBlocked = 0x20000000, kMove = 280;
constexpr uint32_t kOwnColour = 7840; // four floats the title multiplies the fighter's colours by
constexpr uint32_t kPhase = 2048; // the fighter's round: 0 before it (its intro), 1 READY, 2 FIGHT (Practice: 2 at once)

// The flash: the fighter's colours times yellow, full for a few frames,
// then fading.
constexpr int kFlashFrames = 18, kFlashHold = 4;
constexpr float kYellow[3] = {2.4f, 2.0f, 0.35f};

constexpr float kScale = gpu::overlay::kWidth / 1920.0f; // Tekken 7's HUD is 1920 x 1080
// Tekken 7 draws it at its screen's bottom, where the title has its own
// texts (Arcade's stage and time, Promotion Chance): a little higher here;
// in Practice above the frame data panels, when they show.
// The left one moves right of Practice's input history while that shows.
constexpr float kRaise = 70, kAbovePanels = 8, kBesideHistory = 6;
float g_raise = kRaise, g_shift = 0; // (this frame's, Tekken 7's units)
constexpr int kMaxSlots = 4;

// ------------------------------------------------------------------------------------- the HUD's data
struct Picture {
    float x0 = 0, y0 = 0, x1 = 0, y1 = 0; // on Tekken 7's screen (x1 < x0: mirrored)
    float u0 = 0, v0 = 0, u1 = 0, v1 = 0; // texels of gauge.nut
    uint32_t mult = 0xFFFFFFFF, add = 0;  // as overlay::Quad's
};
struct Clip {
    std::vector<std::vector<Picture>> frames;
    std::map<std::string, std::pair<int, int>> labels; // first and last frame
    std::pair<int, int> label(const std::string& name) const {
        const auto it = labels.find(name);
        return it == labels.end() ? std::pair{-1, -1} : it->second;
    }
};
struct Bar {
    bool present = false;
    Picture picture;                      // full
    float mask[4] = {};                   // x0 y0 x1 y1
    float slide = 1;                      // the way it moves as it fills
};
struct Side {
    std::map<std::string, Clip> clips;
    Bar bars[kMaxSlots];
};
struct Hud {
    Side sides[2];
    float travel = 154;
    Rgba image;            // gauge.nut's picture
    uint32_t atlas_y = 0;  // where it is in the HUD layer's atlas
};

// What a clip shows: frames `frame` to `last`, then `next` (a range looped;
// -1: the last frame held).
struct Play {
    int frame = 0, last = 0, next_first = -1, next_last = -1;
    bool hidden = false;
    void still(int at) { frame = last = at, next_first = -1, hidden = false; }
    void hide() { hidden = true; }
    void run(std::pair<int, int> from, std::pair<int, int> to, bool loop) {
        if (from.first < 0 || to.first < 0) return;
        frame = from.first, last = to.second, hidden = false;
        next_first = loop ? to.first : -1, next_last = to.second;
    }
    void step() {
        if (hidden) return;
        if (frame < last) ++frame;
        else if (next_first >= 0) frame = next_first, last = next_last;
    }
};

struct Player {
    int32_t value = 0;
    int slot = -1;
    int16_t health = 0;
    bool health_known = false;
    uint32_t no_gain_move = 0; // the move kNoGain was set in (0: none)
    int flash = 0;             // frames of the flash left
    uint32_t colour = 0;       // its colour while it flashes (guest, four floats)
    // the HUD
    int32_t shown = -1;        // the value drawn last (-1: none yet)
    int full = 0;              // its stocks full then
    Play base, slots[kMaxSlots], text, light, lightning, focus;
};
std::map<uint32_t, Player> g_players; // by fighter

struct Fighter {
    Config config;
    std::optional<Hud> hud;
};
std::map<int, Fighter> g_fighters; // by slot
uint32_t g_atlas_width = 0, g_atlas_height = 0;
bool g_atlas_set = false;
// The HUD shows with the title's own, as Tekken 7's shows with its other
// HUD: from READY (the fighters' round phase, not in intros nor the select
// screen's previews), not while a fighter is knocked out.

const Fighter* fighter_of(int slot) {
    const auto it = g_fighters.find(slot);
    return it == g_fighters.end() || it->second.config.max <= 0 ? nullptr : &it->second;
}

bool read_picture(std::istringstream& s, Picture& p) {
    std::string mult, add;
    if (!(s >> p.x0 >> p.y0 >> p.x1 >> p.y1 >> p.u0 >> p.v0 >> p.u1 >> p.v1)) return false;
    if (s >> mult >> add) {
        p.mult = static_cast<uint32_t>(std::strtoul(mult.c_str(), nullptr, 16));
        p.add = static_cast<uint32_t>(std::strtoul(add.c_str(), nullptr, 16));
    }
    return true;
}

std::optional<Hud> read_hud(const fs::path& directory) {
    std::ifstream in(directory / "gauge.ini");
    std::ifstream nut(directory / "gauge.nut", std::ios::binary);
    if (!in || !nut) return std::nullopt;
    const std::vector<uint8_t> file((std::istreambuf_iterator<char>(nut)), std::istreambuf_iterator<char>());
    const auto textures = ntp3::parse(file);
    auto image = textures && !textures->empty() ? ntp3::decode((*textures)[0]) : std::nullopt;
    if (!image) return std::nullopt;
    Hud hud;
    hud.image = std::move(*image);
    std::vector<Picture>* frame = nullptr;
    std::string line;
    while (std::getline(in, line)) {
        line = line.substr(0, line.find('#'));
        std::istringstream s(line);
        std::string kind, side_name, clip;
        if (!(s >> kind)) continue;
        if (kind == "travel") {
            s >> hud.travel;
            continue;
        }
        if (kind == "q") {
            Picture p;
            if (frame && read_picture(s, p)) frame->push_back(p);
            continue;
        }
        if (!(s >> side_name)) continue;
        Side& side = hud.sides[side_name == "R"];
        if (kind == "bar" || kind == "mask") {
            int k;
            if (!(s >> k) || k < 0 || k >= kMaxSlots) continue;
            Bar& bar = side.bars[k];
            if (kind == "bar") bar.present = read_picture(s, bar.picture);
            else s >> bar.mask[0] >> bar.mask[1] >> bar.mask[2] >> bar.mask[3] >> bar.slide;
        } else if (kind == "clip") {
            size_t frames = 0;
            if (s >> clip >> frames) side.clips[clip].frames.resize(std::min<size_t>(frames, 1000));
        } else if (kind == "label") {
            std::string label;
            int first, last;
            if (s >> clip >> label >> first >> last) side.clips[clip].labels[label] = {first, last};
        } else if (kind == "frame") {
            size_t n;
            frame = nullptr;
            if (s >> clip >> n && n < side.clips[clip].frames.size()) frame = &side.clips[clip].frames[n];
        }
    }
    return hud;
}

// Every slot's pictures, one under another, as the HUD layer's atlas.
void set_atlas() {
    uint32_t width = 0, height = 0;
    for (auto& [slot, f] : g_fighters) {
        if (!f.hud) continue;
        f.hud->atlas_y = height;
        width = std::max(width, f.hud->image.width);
        height += f.hud->image.height;
    }
    if (!height) return;
    auto atlas = std::make_shared<gpu::overlay::Atlas>();
    atlas->width = width;
    atlas->height = height;
    atlas->pixels.assign(size_t{width} * height * 4, 0);
    for (auto& [slot, f] : g_fighters) {
        if (!f.hud) continue;
        const Rgba& image = f.hud->image;
        for (uint32_t y = 0; y < image.height; ++y)
            std::memcpy(&atlas->pixels[(size_t{f.hud->atlas_y + y} * width) * 4], image.at(0, y), size_t{image.width} * 4);
    }
    g_atlas_width = width;
    g_atlas_height = height;
    gpu::overlay::set_hud_atlas(std::move(atlas));
}

int32_t clamp(int32_t value, int32_t max) { return std::clamp(value, 0, max); }

// What a gauge holds at a match's start: none (TTT2_GAUGE_START, for tests).
int32_t start_value() {
    const char* v = std::getenv("TTT2_GAUGE_START");
    return v ? std::atoi(v) : 0;
}

Player& entry(uint32_t address) {
    const auto [it, made] = g_players.try_emplace(address);
    if (made) it->second.value = start_value();
    return it->second;
}

Player& player(uint32_t address, int slot) {
    Player& p = entry(address);
    p.slot = slot;
    if (const Fighter* f = fighter_of(slot)) p.value = clamp(p.value, f->config.max);
    return p;
}

// --------------------------------------------------------------------------------------- the flash
void write_colour(uint32_t fighter, Player& p) {
    if (!p.colour) p.colour = system_alloc(16);
    const float t = p.flash >= kFlashFrames - kFlashHold ? 1.0f
                                                         : float(p.flash) / float(kFlashFrames - kFlashHold);
    for (int i = 0; i < 4; ++i) {
        uint32_t bits = ppc::ld32(guest_base(), fighter + kOwnColour + 4 * i);
        float own;
        std::memcpy(&own, &bits, 4);
        const float value = own * (i < 3 ? 1.0f + (kYellow[i] - 1.0f) * t : 1.0f);
        std::memcpy(&bits, &value, 4);
        ppc::st32(guest_base(), p.colour + 4 * i, bits);
    }
}

// ------------------------------------------------------------------------------------------ the HUD
void add_quad(std::vector<gpu::overlay::Quad>& out, const Hud& hud, Picture p, const float* mask = nullptr) {
    if (mask) { // (an unmirrored picture)
        const float x0 = std::max(p.x0, std::min(mask[0], mask[2])), x1 = std::min(p.x1, std::max(mask[0], mask[2]));
        const float y0 = std::max(p.y0, std::min(mask[1], mask[3])), y1 = std::min(p.y1, std::max(mask[1], mask[3]));
        if (x0 >= x1 || y0 >= y1) return;
        const auto at = [](float a, float lo, float hi, float ulo, float uhi) {
            return ulo + (uhi - ulo) * (a - lo) / (hi - lo);
        };
        const Picture q = p;
        p.u0 = at(x0, q.x0, q.x1, q.u0, q.u1), p.u1 = at(x1, q.x0, q.x1, q.u0, q.u1);
        p.v0 = at(y0, q.y0, q.y1, q.v0, q.v1), p.v1 = at(y1, q.y0, q.y1, q.v0, q.v1);
        p.x0 = x0, p.x1 = x1, p.y0 = y0, p.y1 = y1;
    }
    if (p.x1 < p.x0) std::swap(p.x0, p.x1), std::swap(p.u0, p.u1);
    if (p.y1 < p.y0) std::swap(p.y0, p.y1), std::swap(p.v0, p.v1);
    gpu::overlay::Quad q;
    q.x0 = (p.x0 + g_shift) * kScale, q.y0 = (p.y0 - g_raise) * kScale;
    q.x1 = (p.x1 + g_shift) * kScale, q.y1 = (p.y1 - g_raise) * kScale;
    q.u0 = p.u0 / g_atlas_width, q.u1 = p.u1 / g_atlas_width;
    q.v0 = (hud.atlas_y + p.v0) / g_atlas_height, q.v1 = (hud.atlas_y + p.v1) / g_atlas_height;
    q.top = q.bottom = p.mult;
    q.add = p.add;
    out.push_back(q);
}

void add_clip(std::vector<gpu::overlay::Quad>& out, const Hud& hud, const Side& side, const char* name,
              const Play& play) {
    const auto it = side.clips.find(name);
    if (play.hidden || it == side.clips.end() || it->second.frames.empty()) return;
    const auto& frames = it->second.frames;
    for (const Picture& p : frames[std::clamp<size_t>(play.frame, 0, frames.size() - 1)]) add_quad(out, hud, p);
}

void draw(std::vector<gpu::overlay::Quad>& out, const Hud& hud, const Config& config, Player& p, int s) {
    const Side& side = hud.sides[s];
    const int stocks = std::clamp(config.max / std::max(1, config.stock), 1, kMaxSlots);
    const int32_t value = p.value;
    const int full = std::min(stocks, value / std::max(1, config.stock));
    const auto clip = [&](const char* name) -> const Clip& {
        static const Clip none;
        const auto it = side.clips.find(name);
        return it == side.clips.end() ? none : it->second;
    };
    const char* const slot_names[kMaxSlots] = {"slot0", "slot1", "slot2", "slot3"};
    if (p.shown < 0) { // a new fighter or match: the clips as the gauge is
        p.base.still(0), p.text.still(0);
        p.light.hide(), p.focus.hide(), p.lightning.hide(); // (their first frames are their effects)
        for (Play& slot : p.slots) slot.still(0);
        p.full = 0;
    }
    if (full != p.full) {
        if (full == stocks) { // every slot: EX_MAX_02, then Super looped
            for (int k = 0; k < stocks; ++k) {
                const Clip& c = clip(slot_names[k]);
                p.slots[k].run(c.label("EX_MAX_02"), c.label("Super"), true);
            }
            p.base.run(clip("base").label("Super"), clip("base").label("Super"), true);
            p.text.run(clip("text").label("Super"), clip("text").label("Super"), true);
            p.lightning.run(clip("lightning").label("On"), clip("lightning").label("On"), true);
        } else {
            for (int k = 0; k < stocks; ++k) {
                const Clip& c = clip(slot_names[k]);
                if (k >= full) p.slots[k].still(0);
                else if (k >= p.full || p.full == stocks) { // newly full (or no longer every one): lit
                    const auto max1 = c.label("EX_MAX_01");
                    p.slots[k].run(c.label("EX"), max1.first >= 0 ? max1 : c.label("EX"), false);
                }
            }
            p.base.still(0);
            p.lightning.hide();
            if (full == 0) p.text.still(0);
            else p.text.run(clip("text").label("EX"), clip("text").label("EX"), false);
        }
        if (full > p.full) p.light.run(clip("light").label("Start"), clip("light").label("Start"), false);
    }
    if (p.shown >= 0 && value < p.shown) p.focus.run(clip("focus").label("Start"), clip("focus").label("Start"), false);
    p.full = full;
    p.shown = value;

    add_clip(out, hud, side, "base", p.base);
    for (int k = 0; k < stocks; ++k) {
        const Bar& bar = side.bars[k];
        const float fill = std::clamp(float(value - k * config.stock) / float(config.stock), 0.0f, 1.0f);
        if (bar.present && fill > 0) {
            Picture moved = bar.picture;
            const float dx = (fill - 1) * hud.travel * bar.slide;
            moved.x0 += dx, moved.x1 += dx;
            add_quad(out, hud, moved, bar.mask);
        }
        add_clip(out, hud, side, slot_names[k], p.slots[k]);
    }
    add_clip(out, hud, side, "text", p.text);
    add_clip(out, hud, side, "light", p.light);
    add_clip(out, hud, side, "lightning", p.lightning);
    add_clip(out, hud, side, "focus", p.focus);
    for (Play* play : {&p.base, &p.text, &p.light, &p.lightning, &p.focus}) play->step();
    for (Play& play : p.slots) play.step();
    if (p.light.frame >= p.light.last && p.light.next_first < 0) p.light.hide();
    if (p.focus.frame >= p.focus.last && p.focus.next_first < 0) p.focus.hide();
}

} // namespace

bool parse(const std::string& value, Config& config) {
    std::istringstream s(value);
    Config c;
    if (!(s >> c.max >> c.stock)) return false;
    for (int32_t& g : c.gain)
        if (!(s >> g)) break;
    if (c.max <= 0 || c.stock <= 0) return false;
    config = c;
    return true;
}

void configure(int slot, const Config& config, const fs::path& pack) {
    Fighter& f = g_fighters[slot];
    f.config = config;
    f.hud = read_hud(pack / "gauge");
    if (!f.hud) std::fprintf(stderr, "ttt2: %s has a gauge but no gauge/ pictures; it is not shown\n",
                             pack.filename().string().c_str());
    g_atlas_set = false;
}

bool requirement(uint32_t address, int slot, uint32_t kind, uint32_t param, bool& result) {
    if (kind != kAtLeast && kind != kBelow) return false;
    const Fighter* f = fighter_of(slot);
    const int32_t value = f ? player(address, slot).value : 0;
    result = kind == kAtLeast ? value >= static_cast<int32_t>(param) : value < static_cast<int32_t>(param);
    if (std::getenv("TTT2_TRACE_GAUGE")) {
        static uint32_t last_key = 0;
        const uint32_t key = address ^ (kind << 20) ^ param ^ (result << 31) ^ uint32_t(value) << 8;
        if (key != last_key)
            std::fprintf(stderr, "ttt2: gauge: test %08X slot %d %s %u: %d -> %d\n", address, slot,
                         kind == kAtLeast ? ">=" : "<", param, value, result);
        last_key = key;
    }
    return true;
}

bool property(uint32_t address, int slot, uint32_t id, uint32_t value) {
    if (id != kAdd && id != kNoGain && id != kFlash) return false;
    const Fighter* f = fighter_of(slot);
    if (!f) return true;
    Player& p = player(address, slot);
    if (id == kAdd) {
        p.value = clamp(p.value + static_cast<int32_t>(value), f->config.max);
        if (std::getenv("TTT2_TRACE_GAUGE"))
            std::fprintf(stderr, "ttt2: gauge: %08X %+d -> %d\n", address, static_cast<int32_t>(value), p.value);
    } else if (id == kNoGain) {
        p.no_gain_move = value ? ppc::ld32(guest_base(), address + kMove) : 0;
    } else {
        p.flash = kFlashFrames;
    }
    return true;
}

void situation(uint32_t kind) {
    // Tekken 7's start kinds (0x140759a50's table): a round's keep the gauge
    static constexpr uint32_t kKeep[] = {4, 5, 6, 7, 8, 9, 10, 16, 18};
    if (std::getenv("TTT2_TRACE_GAUGE")) std::fprintf(stderr, "ttt2: gauge: situation %u\n", kind);
    if (std::find(std::begin(kKeep), std::end(kKeep), kind) != std::end(kKeep)) return;
    for (auto& [address, p] : g_players) {
        p.value = start_value();
        p.shown = -1;
        p.no_gain_move = 0;
        p.flash = 0;
        p.health_known = false;
    }
}

void fighters_frame(uint8_t* base, const uint32_t fighters[2]) {
    if (g_fighters.empty()) return;
    if (std::getenv("TTT2_TRACE_GAUGE")) { // the moves, as they start
        static uint32_t shown[2] = {};
        static const auto start = std::chrono::steady_clock::now();
        for (int s = 0; s < 2; ++s) {
            const uint32_t move = fighters[s] ? ppc::ld32(base, fighters[s] + kMove) : 0;
            if (move == shown[s]) continue;
            shown[s] = move;
            const uint32_t name = move ? ppc::ld32(base, move) : 0;
            std::fprintf(stderr, "ttt2: gauge: %.2f s side %d %s (gauge %d)\n",
                         std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count(), s,
                         name ? reinterpret_cast<const char*>(base + name) : "?",
                         fighters[s] ? entry(fighters[s]).value : 0);
        }
    }
    // The gains: each fighter that took damage, and its opponent.
    int32_t gains[2] = {0, 0};
    const Fighter* who[2] = {nullptr, nullptr};
    int slots[2] = {-1, -1};
    for (int s = 0; s < 2; ++s) {
        slots[s] = title::added_slot(fighters[s]);
        who[s] = fighter_of(slots[s]);
    }
    for (int s = 0; s < 2; ++s) {
        const uint32_t defender = fighters[s], attacker = fighters[1 - s];
        if (!defender) continue;
        Player& d = entry(defender);
        const int16_t health = static_cast<int16_t>(ppc::ld16(base, defender + kHealth));
        const int32_t lost = d.health_known ? d.health - health : 0;
        d.health = health;
        d.health_known = true;
        const bool blocked = ppc::ld32(base, defender + kEvents) & kBlocked;
        const int32_t damage = blocked ? static_cast<int32_t>(ppc::ld32(base, defender + kHitDamage)) : lost;
        if (damage <= 0) continue;
        const int32_t before[2] = {gains[0], gains[1]};
        if (who[s]) gains[s] += damage * who[s]->config.gain[blocked ? 0 : 2] / 100;
        if (attacker && who[1 - s]) {
            Player& a = entry(attacker);
            const bool no_gain = a.no_gain_move && a.no_gain_move == ppc::ld32(base, attacker + kMove);
            if (!no_gain) gains[1 - s] += damage * who[1 - s]->config.gain[blocked ? 1 : 3] / 100;
        }
        if (std::getenv("TTT2_TRACE_GAUGE"))
            std::fprintf(stderr, "ttt2: gauge: side %d %s %d: defender +%d, attacker +%d\n", s,
                         blocked ? "blocked" : "lost", damage, gains[s] - before[s], gains[1 - s] - before[1 - s]);
    }
    for (int s = 0; s < 2; ++s) {
        if (!who[s] || !gains[s]) continue;
        Player& p = player(fighters[s], slots[s]);
        p.value = clamp(p.value + gains[s], who[s]->config.max);
    }
    // The flashes.
    for (auto& [address, p] : g_players) {
        if (p.flash <= 0) continue;
        write_colour(address, p);
        --p.flash;
    }
    // The HUD.
    if (!fighters[0] || !fighters[1]) return;
    const auto phase = [&](uint32_t f) { return ppc::ld32(base, f + kPhase); };
    const auto down = [&](uint32_t f) { return static_cast<int16_t>(ppc::ld16(base, f + kHealth)) <= 0; };
    if ((phase(fighters[0]) == 0 && phase(fighters[1]) == 0) || down(fighters[0]) || down(fighters[1])) return;
    if (!g_atlas_set) {
        set_atlas();
        g_atlas_set = true;
    }
    if (!g_atlas_height) return;
    std::vector<gpu::overlay::Quad> quads;
    for (int s = 0; s < 2; ++s) {
        if (!who[s] || !who[s]->hud) continue;
        g_raise = kRaise, g_shift = 0;
        const auto& clips = who[s]->hud->sides[s].clips;
        const auto base = clips.find("base");
        float left = 1e9f, bottom = 0; // the panel's left and bottom
        if (base != clips.end() && !base->second.frames.empty())
            for (const Picture& pic : base->second.frames[0])
                left = std::min({left, pic.x0, pic.x1}), bottom = std::max({bottom, pic.y0, pic.y1});
        if (const float top = framedata::panels_top(s); top && bottom > 0)
            g_raise = std::max(kRaise, bottom - (top - kAbovePanels) / kScale);
        if (const float right = framedata::history_right(); right && s == 0 && left < 1e9f)
            g_shift = std::max(0.0f, (right + kBesideHistory) / kScale - left);
        draw(quads, *who[s]->hud, who[s]->config, player(fighters[s], slots[s]), s);
    }
    gpu::overlay::show_hud(std::move(quads), 0.1);
}

uint32_t colour(uint32_t fighter) {
    const auto it = g_players.find(fighter);
    return it != g_players.end() && it->second.flash > 0 && it->second.colour ? it->second.colour : 0;
}

} // namespace cafe::title::gauge

// The title's situation set-up (r3: the situation's kind; Practice's 15 too,
// for its start and its position reset).
PPC_FUNC(sub_039C2DB0_orig);
PPC_FUNC(sub_039C2DB0) {
    cafe::title::gauge::situation(ctx.r[3]);
    sub_039C2DB0_orig(ctx, base);
}
