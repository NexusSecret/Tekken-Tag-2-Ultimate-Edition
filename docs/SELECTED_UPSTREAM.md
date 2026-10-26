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


## Installer integration follow-up

The installer is now integrated after the user requested it. Windows uses the shared installer, copies the game and native DLLs, supports resume/update, and creates `TTT2 Ultimate.lnk`. The old Windows stub is removed.

Windows records absolute pack and save paths in `.ttt2-userdata` next to the installed executable. Explicit `TTT2_CHARACTERS` / `TTT2_SAVE_DIR` win; otherwise a development build detects `local/windows-userdata/TTT2Ultimate/characters` and `local/windows-save`, falling back to the native user-data defaults. The installed runtime applies those settings before roster/save lookup, including updating the CRT environment. Existing packs and saves are referenced, never moved or overwritten; the original data folders must stay available. Reinstall/update keeps the recorded locations.

Windows installation records live under `%LOCALAPPDATA%/TTT2Ultimate/installed`. Windows executable and DLL updates use replacement semantics. The Linux installation behavior is retained.

Run `ttt2-ultimate.exe --install GAME FOLDER` (or omit paths for dialogs); `--no-launcher` skips the desktop shortcut. `--update FOLDER` updates the executable and DLLs. Close the installed game before updating it. An unrelated nonempty destination receives a `TTT2 Ultimate` subfolder rather than being reused.

Regression coverage exercises the production installer on synthetic data: wrong-build refusal, binary file copying, incomplete-install resume, preservation of modified files, pack/save bootstrap and explicit overrides, unchanged settings on reinstall, DLL copying, update, invalid-update refusal, and isolated shortcut creation. Real-game installation validation uses an ignored local validation folder; it does not replace the working game or create a desktop shortcut.


Installer validation completed: the full native runtime rebuilt; all 12 native CTests passed (the installer test includes 6 end-to-end scenarios); a real 15.9 GB extracted EU v16 game installed successfully in `local/windows-install-validation`; updating that install succeeded; the installed executable started without game arguments or pack/save environment overrides and loaded all 18 fighters, including Reina, from the original pack folder. This last startup check used the null renderer; prior graphical practice tests remain the rendering/gameplay evidence. No desktop shortcut was created during real-game validation; shortcut creation was exercised inside a temporary test directory.


## Main merge conflict resolution

Merged upstream main at `1cab8c68f39b252757804fc16399ec61802e91f2` into the Windows branch. Main's face/eyelid changes were already selectively integrated. The branch intentionally retains its tested custom bound/screw conversion policy rather than adopting upstream commit `4770e17` (Bound Mod move lists and definition-only bounds). This includes the matching converter, tag behavior, move-list icons, character definitions, tests, and gameplay documentation; auto-merges of those files were reviewed and restored to the branch policy as a coherent group.

The six conflicting character definitions retain the branch's bound settings, free specials, hitbox fixes, Fahkumram d4/wr3 preservation, and other custom rules. The importer keeps a single face-retarget step. Outfit conversion keeps cached-outfit support and face-joint correction. Pack revision advances to 5, above both parents. Windows runtime, importers and installer are retained. Existing installed packs are unchanged.
