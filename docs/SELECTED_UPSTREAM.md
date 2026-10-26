# Selected upstream improvements

Reviewed verqion PR #19 at 5269b05777c53db8076d54397c8edeb3aba498a4 against the tested Windows checkpoint 8f770f3. No wholesale merge.

## Accepted: face animation corrections

Original implementation: Petexy / Linexy, upstream commit 1cab8c68f39b252757804fc16399ec61802e91f2 (also present in the fork). Face animations and preset facial joints follow the imported fighter; eyelid turns are scaled from the T7 source animations. Skin gain avoids turning non-skin eyelid texels blue. Existing cached-outfit support and all character/gameplay definitions are preserved. Pack revision increases so previously imported packs can be identified for update.

These conversion changes apply on reimport. Existing working packs were not modified. In-game visual validation of newly converted faces is still pending; the previous T7/Reina practice results apply to the saved checkpoint packs.

## Accepted: build automation, adapted

The fork's cross-platform workflow is adapted to our existing CMake paths rather than replacing the working Windows build with its MSYS2-specific build script. Linux builds use GCC and Clang; Windows CI builds portable tools, the runtime core, and synthetic host tests with CLANG64, then runs asset-free importer tests. Full generated game code and real-game input tests require the user's game and remain local checks. GitHub-hosted Linux and MSYS2 jobs have not yet run for this branch.

A shared test entry point omits the Linux GTK/process launcher tests only on Windows. Compiler tests now account for the Windows compiler override and actually run mesh-decimator checks with Clang.

Validation locally: 633 importer tests, 9 platform/optional skips, no failures; all 11 existing native CTests; clean portable Windows tools build and its 3 CTests. No game files are required by the new CI workflow.

## Deferred: Windows installer

The fork has a real installer; ours still has an explicit Windows installer stub. Its shortcut directly launches the installed runtime, bypassing our development launcher's custom save and pack locations. Its executable/shortcut naming also overlaps the user's separate Xbox port. Integrating it safely requires a deliberate installed-data migration and distinct shortcut naming, plus install/update tests. It is not needed for the already working launch/import path, so it was not adopted in this change.
