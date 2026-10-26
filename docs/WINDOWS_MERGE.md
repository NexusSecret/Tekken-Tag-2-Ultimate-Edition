# Windows gameplay-branch merge â€” 2026-10-26

## Tested checkpoint — 2026-10-26

Branch: `codex/native-windows-t7-reina`, based on gameplay commit `e3839c9e3c44b187f4ad397186be1b308d4cc3f2`. This checkpoint preserves the existing gameplay customizations and the selectively reviewed Windows fixes from verqion's PR #19 (revision `5269b05777c53db8076d54397c8edeb3aba498a4`). That PR was not merged wholesale.

Both native imports have completed: all 17 T7 packs and Reina's own T8 moveset, plus shared assets for all 18 fighters. The user confirmed a T7 fighter works in Practice, then confirmed Reina works after relaunch. These live results supersede the historical progress notes below. Native Windows install/update is now integrated and validated; see SELECTED_UPSTREAM.md for the follow-up and data-location behavior.

Validation: 11/11 native CTests; earlier importer suite 623 tests with 6 skips; final T8 suite 247 tests with 6 platform/optional skips; Windows importer suite 8 tests. No game assets, generated game code, compiled executables, extracted files, caches, logs, or local compiler dependencies are part of this source checkpoint.

The sections below record the development sequence and include earlier, superseded status reports.

## Historical state

Working source: C:/Users/justi/Desktop/TTT2 Ultimate/Tekken-Tag-2-Ultimate-Edition

The project now has Git history from DeReggie/Tekken-Tag-2-Ultimate-Edition, branch codex/character-updates-main-sync. HEAD is e3839c9e3c44b187f4ad397186be1b308d4cc3f2. The remote branch was checked again after integration and still pointed to that commit. Windows adaptations are local uncommitted changes; nothing was pushed.

The previous snapshot matched gameplay converter revision 8f7877217eb21200a3be8cce7f091c922f65ed9e. A source backup was saved before integration, and the previous working game executable is retained under local/windows-build-before-gameplay-merge. No original game archive, source Steam installation, or saved extraction data was deleted.

## Included gameplay changes

All source changes from the requested branch are integrated, with Windows platform adaptations. This includes Fahkumram's explicit preservation of running 3 (Co_runlk00 / ncss_mach) and d4 (Co_t_srk00 / ncss_2rk), current Akuma/Eliza definitions and converter customizations, and e3839c9's Eliza/Geese assist handling. docs/BUG_TRACKER.md is the branch's authoritative record of gameplay fixes and unresolved issues; source inclusion does not independently prove each move works in-game.

## Selective use of upstream PR 19

Reviewed https://github.com/Petexy/Tekken-Tag-2-Ultimate-Edition/pull/19 at 5269b05777c53db8076d54397c8edeb3aba498a4. It was NOT merged wholesale. Applied its reviewed Windows native-library support, mesh-decimator int64 ABI fix, leverless/analog-to-digital input handling and tests. A native Windows codec implementation and synthetic codec tests were also applied when enabling the compiler exposed the Linux-only codec code. Our tested Windows session manager, cache/save locations and game build remain in use. The PR's installer and full Windows T8 session backend were not adopted.

## Validation

- Updated native Windows game executable builds successfully.
- 11/11 CTests passed, including Eliza/Geese assist, outfit handling, damage scaling, memory, VPAD input and the original game's real combat input routine with all eight directions.
- Selected Python importer suite: 623 tests ran, 6 skipped, no failures (before the subsequent one-test cache-path regression addition).
- Linux GTK launcher/process tests in test_launcher.py were excluded from the Windows run. Symbolic-link tests requiring privileges unavailable to this Windows account were skipped.
- Subsequent cache-path regression: all 6 Windows importer tests pass, including the new test with Git deliberately unavailable.
- Updated game rendered and the user confirmed Practice mode works. The validation launch deliberately used an empty character-pack folder; this is not imported-roster verification.
- git diff --check passed; Git emits only line-ending conversion notices.

## T7 import in progress

User relaunched the native importer at 12:47 PM America/New_York. Log confirmed Steam access and Kazumi conversion with all 17 T7 fighters queued. Saved 18 movesets (including reference Heihachi) and encrypted files are reused. Completion is not yet verified. Do not repeatedly poll the import; inspect when asked or on completion/error.

Run the same restored Import TTT2 Fighters.exe from the user's desktop session. The development command environment cannot see the desktop Steam session. The launcher delegates to tools/characters/import_windows.py, so it uses the current source automatically. Defender previously quarantined the small original launcher; the user restored/allowed it. Do not disable Defender or change exclusions automatically.

A first post-merge run failed because the desktop session lacked the development app's bundled Git. pack.git_ignores now recognizes the explicit /local/ exclusion without Git, requiring canonical containment and refusing negated ignore patterns. Source-directory output remains rejected. A regression test covers this.

Live status: local/windows-import-status.json
Latest log: local/windows-import-latest.log
Archived logs: local/windows-import-logs/
Helper logs: local/windows-userdata/TTT2Ultimate/cache/tekken7/run/<timestamp>/helper.log
Output packs: local/windows-userdata/TTT2Ultimate/characters/
Cached movesets/files: local/windows-userdata/TTT2Ultimate/tekken7/
The readable latest log is also mirrored into this chat's Outputs folder.

After Import complete: restart through the normal Play TTT2 Ultimate launcher, verify all 17 added fighters on character select, and test the updated moves. Do not judge completion from manifests alone; shared/keys is built after the last fighter. The runner's complete status records both manifests and shared-assets presence.

## Reina and other remaining work

Reina's source/conversion support is present from the requested branch. The native Windows runner currently defaults to the 17 T7 fighters only. Full native Windows T8 live extraction is not yet wired or verified; do not claim Reina's genuine T8 moveset can be imported through this launcher. User explicitly chose to finish T7 first.

Windows install/update remains unfinished (explicit stub); launching from the WUA works. Avoid porting the PR's installer wholesale without reviewing shortcut naming against the separate installed Xbox 360 PC port.

Reina Windows import (2026-10-26):
- Native T8 discovery/session/helper added separately from the working T7 backend.
- Installed T8 build 25221600 passes all four existing executable signature checks.
- Helper targets the exact importer-owned process; pre-existing T8 sessions are refused.
- Windows runner extracts and validates Reina's own zbr moveset before conversion; extraction failure stops instead of using Heihachi.
- Existing character packs are backed up under local/character-backups/before-reina-* before conversion. Only Reina is requested; shared assets are rebuilt for the combined roster.
- User-facing launcher: outputs/Import Reina.cmd in the Codex task folder. Close TTT2 and both PC games, keep Steam open, then double-click it.
- Validation: 247 T8 tests passed (6 platform/optional skips), 8 Windows importer tests passed; native t8helper compiled successfully. Live extraction and in-game Reina testing remain pending.
