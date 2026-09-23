# STATUS - chesspuz
last_updated: 2026-09-23
phase: 0.2.0 released (Windows zip + Android APK on GitHub, both verified by John on the Pixel 9a); next is John's change list

## Next action
- John has a few changes in mind (not yet described): take his list, treat it as feedback round 3 (spec note in docs/specs if bigger than a fix), implement, run `python -m pytest -q` and `ruff check . && ruff format .`, then `python android\sync.py all` to put it on the phone (about 2 minutes; the phone must be on USB with debugging allowed; no uninstall needed now that the phone has the release-signed build). Bump `chesspuz.__version__` / pyproject / `--version` for the next release.

## Blockers
- none

## Android build (2026-09-23)
- `android/bin/chesspuz-0.2.0-arm64-v8a-release.apk`: 70.5 MB (40 MB puzzle database), signed with our key (APK signature scheme v2), targetSdk 36, not debuggable, 19 native libraries (Qt Core/Gui/Widgets/Svg + platform plugin, PySide6 modules for them, shiboken, CPython 3.11 + sqlite/openssl/libffi, the Python bundle with only those modules). Build time after a code change about 1 minute.
- John installed the release APK from GitHub on the Pixel 9a (Android 16) and confirmed it all works: no compatibility dialog, portrait layout, scrolling, sounds through AAudio, Back key. The earlier debug builds had been checked over adb during development.
- Release key: `~/chesspuz-release.keystore` + `~/chesspuz-release.env` in the box, backup in `D:\Claude\secrets\chesspuz-android` (never in the repo; `android/wsl/keystore.sh` restores it from the backup). Losing it means uninstall-before-update for every user.
- Toolchain: WSL box `dd-android` (shared with Digit Defender) + `~/chesspuz-venv` (Python 3.11, PySide6 6.11.2 host tools, buildozer 1.6.0, pip, tqdm), Qt Android wheels 6.11.2 aarch64 in `~/wheels`, our python-for-android checkout `~/p4a-chesspuz` at `3762c88c` (last CPython 3.11 revision) with the Back-key Java patch, NDK r28c, API 36. Reproducible from `android/wsl/setup.sh` + `build.sh`.
- Desktop emulation: `python android\app\main.py --desktop` (412x915 window); 161 tests green, ruff clean. Rules of thumb for UI changes: keep every page's minimum width under ~380 px (word-wrap labels, stack rows when compact), touch has no right button, dialogs cancel on Back.

## Puzzle database (rebuilt 2026-09-23)
- `python main.py import --download` rebuilt it: 288,504 puzzles in `%LOCALAPPDATA%\chesspuz\puzzles.sqlite` (109 MB), the 300 MB Lichess file kept next to it. Scholar's Mate is now capped (8,342). The APK bundles this file (`sync.py sync` copies it; `--db PATH` for another).

## Last session
- Done (2026-09-23, Android): `android/` pipeline (sync.py, wsl/setup.sh, build.sh, patch_spec.py, patch_java.py, patch_recipe.py, keystore.sh, mobile/entry.py, mobile/aaudio.py, README), responsive pages (`chesspuz/ui/responsive.py`, `device.py`; every page), Back-key handling, phone theme, bundled database, tests/test_android.py, docs. On-device fixes: pages shaped from the screen before the window is shown (else the desktop minimum width clamps the window to 574 px), QScroller touch scrolling with hidden scrollbars, fault handler writing to a file (p4a's stderr has no fileno), python-for-android's PythonActivity patched so Back is not swallowed by its "click again to close" rule. Then: Qt trimmed via a patched recipe (197 -> 70 MB), signed release build (no debug compatibility dialog), AAudio sounds, version 0.2.0, Windows zip rebuilt with the venv's Python 3.13, GitHub release v0.2.0 with both assets, confirmed on the phone by John.
- Done (2026-09-23, earlier): feedback rounds 1-2, release tooling, v0.1.0 on GitHub. Done (2026-09-22): Phases 0-7.
- Failed / dead ends (do not retry): pyside6-android-deploy refuses Python 3.12+ (use the 3.11 venv); a uv venv has no pip, and buildozer needs `python -m pip`; the deploy tool needs tqdm (its `requirements-android.txt`); `buildozer init` prompts "running as root" before a spec exists (`BUILDOZER_WARN_ON_ROOT=0`); buildozer `git reset --hard`s its own p4a clone every build (patch a `p4a.source_dir` checkout instead); buildozer's `android release` makes an .aab unless `android.release_artifact = apk`; `build_release.bat` must run with the venv activated (the PATH python is 3.12 without chess); PySide6's Android build has no QJniObject; libshiboken6 is 4 KB-aligned (debug builds always get the compatibility dialog); a page's minimum width above ~380 px clips on the phone; do not drive the phone with blind `adb shell input tap` while John is using it (a tap landed on Clear stats). Earlier: Bash tool truncates commands over ~8 KB (use the Write tool); pytest-qt `mouseMove` is unreliable offscreen; a shell pipeline hides pytest's exit code; winsound cannot play asynchronously from memory.

## Verify with
- `python -m pytest -q`
- `ruff check . && ruff format .`
- `run.bat` (GUI from source), `build_release.bat` (release zip, venv activated), `python android\sync.py build` (APK), `python android\sync.py status`
