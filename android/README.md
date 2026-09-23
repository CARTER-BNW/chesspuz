# chesspuz on Android

The phone build is the desktop app plus a thin entry layer (`mobile/`), packaged as an APK by
Qt's `pyside6-android-deploy` + buildozer + python-for-android. The desktop code stays the
master: `sync.py` copies it in. Spec and design decisions: `docs/specs/android.md`.

## Pipeline (all on D:)
| Piece | Where | What |
|---|---|---|
| `sync.py` | this folder | the tool: `python android\sync.py [sync|setup|build|clean|install|run|logs|status|all]` |
| `mobile/entry.py` | this folder | the phone's `main.py`: private data dir, bundled database, temp dirs, phone flag; `--desktop` emulates the phone on the PC |
| `app/` | generated | the synced copy: `chesspuz/`, `mobile/`, `main.py` stub, `puzzles.sqlite`, `icon.png` (gitignored) |
| `VERSION`, `icon.png`, `manifest_application_args.xml` | this folder | version (bumped on every sync), launcher icon, manifest attribute for the Back key |
| `wsl/setup.sh` | this folder | one-time toolchain in the WSL box (idempotent) |
| `wsl/build.sh`, `wsl/patch_spec.py`, `wsl/patch_java.py`, `wsl/patch_recipe.py`, `wsl/keystore.sh`, `wsl/p4a_pin.txt` | this folder | the build inside the box: generate the buildozer project once, patch the spec, the bootstrap's Back-key Java and the PySide6 recipe (Qt trimmed), sign, build |
| `mobile/aaudio.py` | this folder | sound on the phone: the app's WAV clips written to an AAudio stream through ctypes |
| `dd-android` | `D:\WSL\dd-android` | Ubuntu 24.04 WSL distro shared with Digit Defender: buildozer, JDK 17, Android SDK (API 36, build-tools 37), NDK r28c, plus `~/chesspuz-venv` (Python 3.11 + PySide6 6.11.2 host tools), `~/wheels` (Qt Android wheels), `~/chesspuz-android` (build dir) |
| `bin/*.apk`, `build.log` | this folder | outputs (gitignored) |
| adb | `D:\Android\sdk\platform-tools\adb.exe` | install / run / logcat (override with the `ADB` env var) |

Typical update: `python android\sync.py all` (sync, build, install, run, log dump). A build after a
code change takes about a minute; the first build (CPython 3.11, sqlite, openssl, libffi compiled
for arm64) took 9 minutes on this machine. The release APK is about 70 MB (40 MB of it the
puzzle database).

## How the build works
1. `sync` copies the package and `mobile/` into `app/`, writes `app/main.py` (calls
   `mobile.entry.main`), bundles the puzzle database from `%LOCALAPPDATA%\chesspuz` (or
   `--db PATH`; `--no-db` to leave it out), draws `icon.png`, bumps `VERSION`.
2. `build` mirrors the folder to `~/chesspuz-android` in the box (rsync, no spaces in paths)
   and runs `wsl/build.sh`:
   - the first time (or after `clean`): `pyside6-android-deploy --init --keep-deployment-files`
     scans the code for the Qt modules used (Core, Gui, Svg, Widgets), writes the PySide6 and
     shiboken6 python-for-android recipes and the Qt `.jar` files into `app/deployment/`, and
     creates `buildozer.spec`;
   - python-for-android is our own checkout `~/p4a-chesspuz` at commit `3762c88c` (its last
     revision that builds CPython 3.11), set as `p4a.source_dir`: buildozer then runs no git
     commands on it, so `patch_java.py` can rewrite the Qt bootstrap's `PythonActivity.java`,
     which otherwise swallows the first Back press ("Click again to close the app");
   - `patch_spec.py` applies our settings to that spec: package `org.johncarter.chesspuz`,
     version, `requirements` + `sqlite3,chess`, `.sqlite` files included, portrait, fullscreen,
     API 36 / min 28, sources kept as `.py`, the Back-key manifest attribute, the p4a checkout;
   - `patch_recipe.py` appends a pruning step to the generated PySide6 recipe: the deploy
     tool would otherwise pack all 60-odd Qt modules, ffmpeg, QML and headers (a 200 MB APK).
     The step keeps the dependency closure of Core, Gui, Widgets, Svg and the platform plugin
     (computed with the NDK's `llvm-readobj`) and strips the site-packages copy to match;
   - `buildozer android release` builds `bin/chesspuz-<version>-arm64-v8a-release.apk`, signed
     with our key (`wsl/keystore.sh`: `~/chesspuz-release.keystore` + `~/chesspuz-release.env`
     in the box, backed up in `D:\Claude\secrets\chesspuz-android`, never in the repo).
     `android.release_artifact = apk` in the spec, because buildozer's release default is an
     `.aab` bundle that adb cannot install. `--debug` builds a debuggable APK instead; Android
     shows its "app compatibility / 16 KB" dialog for debuggable apps only (`libshiboken6`
     is 4 KB-aligned and cannot be fixed on our side), which is why release is the default.
3. `install` / `run` / `logs` use adb (package `org.johncarter.chesspuz`, activity
   `org.kivy.android.PythonActivity`). Installing a release build over a debug one (or the
   other way round) fails on the signature: `install` then uninstalls the old app first, which
   deletes the runs and settings on the phone.

Build facts: PySide6 6.11.2 Android wheels (aarch64, built for CPython 3.11: they link
`libpython3.11.so`, which is why python-for-android is pinned), python-for-android `develop` at
2025-10-26, buildozer 1.6.0, NDK r28c (16 KB page alignment, required on Android 15+),
targetSdk 36 (Android 16's Play Protect refuses sideloaded APKs that target an old API),
predictive back disabled in the manifest so the Back key reaches Qt. The APK ships 19 native
libraries: Qt Core, Gui, Widgets, Svg and the Android platform plugin, the PySide6 modules for
them, shiboken, CPython 3.11 with sqlite, openssl and libffi, and the Python bundle.

## On the phone
- The app starts in portrait: the board spans the width, the panel below scrolls with a finger
  (no scrollbars on the phone). The layout is decided from the window size, so
  `python android\app\main.py --desktop` shows the same thing in a 412x915 window on the PC
  (after a sync). Before the window is shown the pages are shaped from the screen: their
  desktop minimum width would otherwise clamp Android's fullscreen window wider than the screen.
- Sounds: the clips the desktop plays with winsound go through Android's AAudio C API
  (`mobile/aaudio.py`, ctypes on `libaaudio.so`, one output stream, a worker thread): no extra
  libraries, no permissions. Volume and mute from Settings apply as on the desktop. If AAudio
  fails the app stays silent and logs `chesspuz: phone sound stopped`.
- Data: `/data/data/org.johncarter.chesspuz/files/chesspuz/user.sqlite` (players, runs,
  settings; survives updates), the puzzle database inside the unpacked app folder
  (`files/app/puzzles.sqlite`, replaced on every update). `crash.log` next to `user.sqlite`
  holds the traceback of a failed start:
  `adb shell run-as org.johncarter.chesspuz cat files/chesspuz/crash.log`.
- Back key: closes a puzzle window, asks to end a running run, leaves Settings, otherwise
  returns to the home page; it never quits the app.
- Touch: tap a piece then its target, or drag it. There is no right button, so annotation
  arrows (and the Clear arrows buttons) are absent. Double-tap a row in Played / Mistakes /
  the run overview to open that puzzle.
- Settings: text size (default 14 pt on the phone), board colours, animation, sounds,
  difficulty and Clear stats. The engine and database-rebuild sections are desktop-only.
- Log: `python android\sync.py logs` (Python, Qt and crash lines), `--follow 30` for a live
  stream.
