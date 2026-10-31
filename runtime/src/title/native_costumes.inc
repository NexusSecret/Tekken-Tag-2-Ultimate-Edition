// Included inside roster.cpp's private namespace, after the costume table helpers.
// Native identity and motion rows stay in the title. Only body recipes differ.
void prepare_native_costume(const fs::path& folder, const std::string& target,
                            const std::map<uint32_t, Located>& located,
                            std::map<uint32_t, std::vector<uint8_t>>& overlay) {
    std::ifstream ini(folder / "native.ini");
    if (!ini) return;
    std::map<std::string, std::string> values;
    for (std::string line; std::getline(ini, line);) {
        line = line.substr(0, line.find('#'));
        const auto equal = line.find('=');
        if (equal != std::string::npos) values[trim(line.substr(0, equal))] = trim(line.substr(equal + 1));
    }
    if (values["format"] != "1" || values["target"] != target) return;
    std::vector<std::string> codes;
    std::set<std::string> unique;
    std::stringstream supplied(values["outfits"]);
    for (std::string code; std::getline(supplied, code, ',');) {
        code = trim(code);
        if (code.size() != 3 || !std::all_of(code.begin(), code.end(), [](char c) {
                return (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9'); }) || fighter_id(code) ||
            !unique.insert(code).second) return;
        for (const auto& added : g_added) {
            if (!added.active) continue;
            if (added.code == code || std::any_of(added.outfits.begin(), added.outfits.end(),
                [&](const Outfit& outfit) { return outfit.code == code; })) return;
        }
        for (const auto& [owner, native] : g_native)
            if (std::any_of(native.fighter.outfits.begin(), native.fighter.outfits.end(),
                [&](const Outfit& outfit) { return outfit.code == code; })) return;
        codes.push_back(code);
    }
    const auto id = fighter_id(target);
    if (!id || codes.empty() || codes.size() > 64) return;
    const auto row = motion_row(*id);
    if (!row) return;
    const uint32_t list = load(kCostumeLists + 8 * *id), count = load(kCostumeLists + 8 * *id + 4);
    if (count == 0 || count >= 9 || !list) return;
    const auto previews = read_file(folder / "art/costumes.nut");
    if (!previews || previews->size() < 8 || std::memcmp(previews->data(), "NTP3", 4) != 0 ||
        ((uint32_t((*previews)[6]) << 8) | (*previews)[7]) != count + codes.size()) return;
    std::error_code ec;
    for (const auto& code : codes) {
        for (const char* suffix : {".nud", ".nut", ".bon", ".xml", ".mop"})
            if (!fs::is_regular_file(folder / (code + suffix), ec)) return;
    }
    std::map<uint32_t, std::vector<uint8_t>> entries;
    const uint32_t preview_key = key_of("native/" + target + "/art/costumes.nut");
    for (const auto& item : fs::recursive_directory_iterator(folder, ec)) {
        if (!item.is_regular_file() || item.is_symlink()) continue;
        const std::string name = fs::relative(item.path(), folder).generic_string();
        if (name == "native.ini" || name == "presets.json") continue;
        const bool preview = name == "art/costumes.nut";
        const auto owner = std::find_if(codes.begin(), codes.end(), [&](const std::string& code) {
            return name.rfind(code + ".", 0) == 0 || name.rfind(code + "/alo/", 0) == 0;
        });
        if (!preview && owner == codes.end()) continue;
        const auto bytes = read_file(item.path());
        if (!bytes) return;
        const uint32_t key = preview ? preview_key : key_of(name);
        const uint32_t donor_key = preview ? load(kCostumePreviews + 4 * *id) : key_of(target + name.substr(3));
        uint8_t flags[8] = {};
        if (const auto donor = title_entry(located, donor_key))
            std::copy(donor->second.begin(), donor->second.end(), flags);
        entries[key] = archive::pack(*bytes, key, flags);
    }
    // Commit all native fighters together. Rebuilding a growing archive for
    // each profile repeatedly copies every previously prepared model/texture.
    for (const auto& [key, bytes] : entries) if (overlay.contains(key)) return;
    for (auto& [key, bytes] : entries) overlay.emplace(key, std::move(bytes));
    NativeCostumes native;
    native.fighter.active = true;
    native.fighter.id = *id;
    native.fighter.row = *row;
    native.fighter.code = target;
    native.fighter.code_string = load(kCodes + 4 * *id);
    native.native_count = count;
    native.count = count + static_cast<uint32_t>(outfit_menu::NativePage{count, codes.size()}.visible());
    native.entries = system_alloc(8 * native.count);
    native.key = preview_key;
    std::memcpy(guest_pointer(native.entries), guest_pointer(list), count * 8);
    // Extra bodies use costume 1's native equipment recipe, with their own empty-part XML.
    for (size_t i = 0; i < codes.size(); ++i) {
        const uint32_t registry_id = 0x20000 + static_cast<uint32_t>(g_native_ids.size());
        native.fighter.outfits.push_back({codes[i], registry_id, guest_string(codes[i])});
        g_native_ids[registry_id] = *id;
        if (count + i < native.count)
            std::memcpy(guest_pointer(native.entries + 8 * (count + i)), guest_pointer(list), 8);
    }
    g_native[*id] = std::move(native);
    std::fprintf(stderr, "ttt2: native roster costumes v2: %s: %zu T7 presets; %u native costumes and five custom slots retained\n", target.c_str(), codes.size(), count);
}

// A fixed target allowlist intentionally leaves Kunimitsu, Slim Bob and Forest Law separate.
void prepare_native_costumes(const fs::path& directory) {
    g_native.clear();
    g_native_ids.clear();
    g_native_choosers.clear();
    std::vector<std::string> targets;
    std::error_code ec;
    for (const char* target : {"pau", "law", "yos", "xia", "ask", "jin", "dvj", "lil", "bob", "dra", "bry", "jac", "jul", "kaz", "hei", "nin", "ann", "lar", "asa", "kin", "aki", "edd", "fen", "gan", "hwo", "kum", "pan", "lee", "leo", "lei", "mar", "mig", "ste", "zaf"}) {
        if (fs::is_regular_file(directory / "native" / target / "native.ini", ec)) targets.push_back(target);
    }
    if (targets.empty()) return;
    // Native donors do not change during preparation; read the game's indexes once.
    const auto located = locate_entries();
    std::map<uint32_t, std::vector<uint8_t>> overlay;
    for (const auto& target : targets)
        prepare_native_costume(directory / "native" / target, target, located, overlay);
    if (overlay.empty()) return;
    if (vfs::set_archive_entries("content/hdd/data100", overlay)) {
        g_active = true;
    } else {
        g_native.clear();
        g_native_ids.clear();
        std::fprintf(stderr, "ttt2: native costumes: archive overlay failed; keeping original costumes\n");
    }
}

// Native loader records and identities are never virtualized. Substitute only
// the body code, remembering it by player slot for asynchronous recipe creation.
PPC_FUNC(sub_044BE1EC_orig);
bool load_native_costume(PPCContext& ctx, uint8_t* base) {
    const uint32_t record = ctx.r[5], slot = ctx.r[4];
    if (record >= 139) return false;
    const uint32_t id = load(kRecords + kRecordSize * record + kRecId);
    const auto found = g_native.find(id);
    if (found == g_native.end()) return false;
    const Added& fighter = found->second.fighter;
    const Outfit* selected = nullptr;
    if (slot < 4) {
        const uint32_t pick = g_native_picks[slot & 1][slot / 2];
        for (const auto& outfit : fighter.outfits) if (outfit.id == pick) selected = &outfit;
    }
    const uint32_t code_place = kCodes + 4 * id, old_code = load(code_place);
    const uint32_t code = selected ? selected->code_string : old_code;
    g_outfit_bodies.remember(slot, id, selected ? selected->id : 0);
    static std::map<std::pair<uint32_t, uint32_t>, uint32_t> requested;
    const auto key = std::make_pair(ctx.r[3], slot);
    const uint32_t state = ctx.r[3] + 28 + 56 * slot;
    const bool invalidate = slot < 5 && outfit_menu::needs_reload(requested[key], code,
        load8(state + 1) != 0, load(state + 12), record);
    if (invalidate) store(state + 12, 139);
    store(code_place, code);
    sub_044BE1EC_orig(ctx, base);
    store(code_place, old_code);
    if (slot < 5) {
        if (ctx.r[3]) {
            if (selected && requested[key] != code && std::getenv("TTT2_TRACE_ROSTER"))
                std::fprintf(stderr, "ttt2: native costume: slot %u accepted body %s (fighter %u, native row %u)\n",
                    slot, selected->code.c_str(), id, fighter.row);
            requested[key] = code;
        }
        else if (invalidate && !load8(state + 1)) store(state + 12, record);
    }
    return true;
}
