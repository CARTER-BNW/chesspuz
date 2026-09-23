# STATUS - chesspuz
last_updated: 2026-09-23
phase: 0.2.0 released (Windows zip + Android APK on GitHub, pre-release until the trimmed APK has run on the phone); Phase 9 Android done except John's play-test

## Next action
- When the phone is plugged in: `python android\sync.py install run logs` installs the signed release APK 0.2.0 (it uninstalls the debug build first: signature differs, phone runs and settings are lost), then check: no "app compatibility" dialog, home page in portrait, a run starts, sounds audible (log line `chesspuz: sounds through AAudio`, or `phone sound stopped: ...`), Back key. Then `gh release edit v0.2.0 --prerelease=false`. The session's adb watcher does the install automatically if it is still running.
- John's play-test: a whole Survival run, Review, Mistakes practice, a puzzle window from Played, Settings text size, the colour picker. Fix-and-rebuild is `python android\sync.py all` (about 2 minutes).

## Blockers
- none

## Android build (2026-09-23)
- `android/bin/chesspuz-0.2.0-arm64-v8a-release.apk`: 70.5 MB (40 MB puzzle database), signed with our key (APK signature scheme v2), targetSdk 36, not debuggable, 19 native libraries (Qt Core/Gui/Widgets/Svg + platform plugin, PySide6 modules for them, shiboken, CPython 3.11 + sqlite/openssl/libffi, the Python bundle with only those modules). Build time after a code change about 1 minute.
- Verified on the Pixel 9a with the earlier debug builds (0.2.1-0.2.3, untrimmed): install, portrait layout, finger scrolling, a run starts, Back key handled. The trimmed release build and the AAudio sounds are verified offline only (signature, manifest, library closure, bundle contents, unit tests with a fake libaaudio).
- Release key: `~/chesspuz-release.keystore` + `~/chesspuz-release.env` in the box, backup in `D:\Claude\secrets\chesspuz-android` (never in the repo; `android/wsl/keystore.sh` restores it from the backup). Losing it means uninstall-before-update for every user.
- Toolchain: WSL box `dd-android` (shared with Digit Defender) + `~/chesspuz-venv` (Python 3.11, PySide6 6.11.2 host tools, buildozer 1.6.0, pip, tqdm), Qt Android wheels 6.11.2 aarch64 in `~/wheels`, our python-for-android checkout `~/p4a-chesspuz` at `3762c88c` (last CPython 3.11 revision) with the Back-key Java patch, NDK r28c, API 36. Reproducible from `android/wsl/setup.sh` + `build.sh`.
- Desktop emulation: `python android\app\main.py --desktop` (412x915 window); 161 tests green, ruff clean.

## Puzzle database (rebuilt 2026-09-23)
- The database was missing from this machine at session start; `python main.py import --download` rebuilt it: 288,504 puzzles in `%LOCALAPPDATA%\chesspuz\puzzles.sqlite` (109 MB), the 300 MB Lichess file kept next to it. Scholar's Mate is now capped (8,342).

## Last session
- Done (2026-09-23, Android): `android/` pipeline (sync.py, wsl/setup.sh, build.sh, patch_spec.py, patch_java.py, patch_recipe.py, keystore.sh, mobile/entry.py, mobile/aaudio.py, README), responsive pages (`chesspuz/ui/responsive.py`, `device.py`; every page), Back-key handling, phone theme, bundled database, tests/test_android.py, docs. On-device fixes: pages shaped from the screen before the window is shown (else the desktop minimum width clamps the window to 574 px and the right side is cut off), QScroller touch scrolling with hidden scrollbars, fault handler writing to a file (p4a's stderr has no fileno), python-for-android's PythonActivity patched so Back is not swallowed by its "click again to close" rule. Then: Qt trimmed via a patched recipe (197 -> 70 MB), signed release build (no debug compatibility dialog), AAudio sounds, version 0.2.0, Windows zip rebuilt with the venv's Python 3.13, GitHub release v0.2.0 with both assets.
- Done (2026-09-23, earlier): feedback rounds 1-2, release tooling, v0.1.0 on GitHub. Done (2026-09-22): Phases 0-7.
- Failed / dead ends (do not retry): pyside6-android-deploy refuses Python 3.12+ (use the 3.11 venv); a uv venv has no pip, and buildozer needs `python -m pip`; the deploy tool needs tqdm (its `requirements-android.txt`); `buildozer init` prompts "running as root" before a spec exists (`BUILDOZER_WARN_ON_ROOT=0`); buildozer `git reset --hard`s its own p4a clone every build (patch a `p4a.source_dir` checkout instead); buildozer's `android release` makes an .aab unless `android.release_artifact = apk`; `build_release.bat` must run with the venv activated (the PATH python is 3.12 without chess); PySide6's Android build has no QJniObject; libshiboken6 is 4 KB-aligned (debug builds always get the compatibility dialog); a page's minimum width above ~380 px clips on the phone; do not drive the phone with blind `adb shell input tap` while John is using it (a tap landed on Clear stats). Earlier: Bash tool truncates commands over ~8 KB (use the Write tool); pytest-qt `mouseMove` is unreliable offscreen; a shell pipeline hides pytest's exit code; winsound cannot play asynchronously from memory.

## Verify with
- `python -m pytest -q`
- `ruff check . && ruff format .`
- `run.bat` (GUI from source), `build_release.bat` (release zip, venv activated), `python android\sync.py build` (APK), `python android\sync.py status`
