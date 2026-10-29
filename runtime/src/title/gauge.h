#pragma once

// The gauge of an added Tekken 7 2D fighter (Akuma's Super Combo gauge,
// Eliza's): what its EX moves, supers and cancels cost, filled as it deals
// and takes damage, shown at the bottom of the screen with Tekken 7's own
// pictures, the fighter lit up yellow as it spends it. See gauge.cpp.

#include <cstdint>
#include <filesystem>
#include <string>

namespace cafe::title::gauge {

// The moveset's ids for it (the importer's convert/gauge.py): requirements
// no TTT2 moveset uses and the title's requirement function takes as false
// (sub_0404FF30's default case; below 643, as the cancel rows' loader
// sub_040D2300 marks rows with 643 and above as its special ones, which
// it never tests for a player), properties its interpreter passes over
// (sub_03AE86A0's table sends them to its end).
constexpr uint32_t kAtLeast = 190; // the gauge holds `param` or more
constexpr uint32_t kBelow = 191;   // the gauge holds less than `param`
constexpr uint32_t kAdd = 0x8220;   // the gauge += value (signed; a cost is negative)
constexpr uint32_t kNoGain = 0x8222; // value 1: the move builds no gauge for its attacks
constexpr uint32_t kFlash = 0x8223;  // the fighter lights up (an EX move, a cancel)

// character.ini's `gauge` line: the most it holds, a stock, then the
// gains in percent of the damage: a blocked attack's (the defender's, the
// attacker's), a hit's (the defender's, the attacker's), e.g.
// `gauge = 1000 500 37 75 112 225` (Akuma's).
struct Config {
    int32_t max = 0, stock = 500;
    int32_t gain[4] = {50, 100, 150, 300};
};
bool parse(const std::string& value, Config& config);

// The added fighter `slot` has this gauge; its pictures are its pack's
// gauge/ (gauge.ini, gauge.nut), if it has them.
void configure(int slot, const Config& config, const std::filesystem::path& pack);

// The moveset's (the added fighter `slot`'s; -1: another fighter's). True
// when the id is the gauge's (the requirement's result in `result`).
bool requirement(uint32_t player, int slot, uint32_t kind, uint32_t param, bool& result);
bool property(uint32_t player, int slot, uint32_t id, uint32_t value);

// The title's situation set-up (sub_039C2DB0's kind): a match's start
// empties every gauge; a round's keeps them, as Tekken 7 does.
void situation(uint32_t kind);

// After the fighters' frame: the gains, the flashes' time, the HUD.
void fighters_frame(uint8_t* base, const uint32_t fighters[2]);

// The colour the title draws `fighter` in while it flashes (a guest
// address of four floats, the fighter's own times yellow), else 0.
uint32_t colour(uint32_t fighter);

} // namespace cafe::title::gauge
