# Paul Phoenix costume test (Windows)

Open **Start Costume Test.cmd** from this project folder. The Characters section
has **Paul Phoenix · Tekken 7 presets → Choose presets…**. Choose one to six
outfits and click **Import / update presets**. Close the game before importing,
then restart it. In character select, open Paul's normal **CHANGE COSTUME**
chooser: his three original entries are followed by the imported presets, then
all five customisation slots. Paul retains his Tag 2 identity, moveset, voice
and roster cell. A match can choose a different outfit for each player slot.

Ten source sets are offered. The six-at-once limit keeps the native 14-entry
chooser within capacity while preserving original and customisation slots.
Reimport a different selection to test other outfits. This experiment supports
Tekken 7 Paul only; Tekken 8 requires a separate adapter.

The matching runtime is required. The launcher checks the installed executable
for native-Paul support and disables import when it is absent. On another PC,
build/update this modified source before importing. The regular release launcher
and an unmodified game executable do not implement these new slots.

Packs are in the configured fighter folder, under `native/pau/`. They contain
game assets and are ignored by Git. Each update retains its previous directory
as `native/.pau-backup-<id>/`. **Remove imported presets** disables only this
pack by retaining it as a backup; native game files and saves are untouched.
Do not copy the generated body files over Paul's original game assets.

Implementation: `tools/characters/import_native_costumes.py`,
`ttt2char/native_costumes.py`, launcher Windows UI/backend, and native body
recipe/chooser hooks in `runtime/src/title/roster.cpp` and `native_costumes.inc`.
No animation-tool code is changed.

The development build can be compiled into a folder outside Dropbox to avoid
sync locks on compiler dependency files. The launcher still uses the configured
installed game. A test build and pack validation do not replace visual testing:
check both default colour variants, mirror matches, tag swaps, native outfits,
customisation and returning from matches. Cloth outfits need particular attention.

Validation includes 20 launcher backend tests, five native pack tests, all 13
Windows runtime checks and a launcher UI smoke test. The in-game chooser and
body-loading test pack contains the two default Tekken 7 Paul presets; the 1P
body was verified rendering in an arcade match with Paul's original identity
and motion row. Mirror matches and the remaining outfits still need hands-on
testing. Native costume
texture IDs retain the game's `0x10` class; using another high byte can produce
a working chooser preview followed by an assertion when loading the 3D body.

On this PC, the matching test runtime and the two defaults are installed in
`F:/Tag2Recomp/Game` and the configured character-pack folder. The previous game
executable is retained beside it as `TTT2 Ultimate.before-native-costumes.exe`.
