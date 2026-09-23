# STATUS - chesspuz
last_updated: 2026-09-23
phase: 0.3.1 released for sharing (Windows zip + APK + README PDF, release page with screenshots of every feature). Waiting for John's phone check and his next change list.

## Next action
- Ask John what came back from sharing and from the phone: the 0.3.1 APK from the Releases page (do Support the Dev and Check for Updates open the browser on the phone? Lives per run, Pause / Resume / Back, the Lives filter on Leaderboard and Stats). Then treat his list as feedback round 4 = Phase 11 in docs/PLAN.md: spec note in docs/specs if bigger than a fix, implement, `.venv\Scripts\python.exe -m pytest -q`, `ruff check . && ruff format .`, screenshots at both shapes if the UI changed, builds, release with the recipe below.

## Blockers
- none

## Where things are
- Code: main, all pushed; version 0.3.1 in `chesspuz/__init__.py`, `pyproject.toml` and `android/VERSION`. 169 tests green, ruff clean.
- Releases (https://github.com/CARTER-BNW/chesspuz/releases): v0.3.1 = zip + APK + `chesspuz-0.3.1-readme.pdf` + a full feature page with screenshots as the notes; v0.3.0 (zip, APK, PDF); v0.2.0 (the last build John confirmed on the Pixel 9a); v0.1.0.
- Phone: John installs from the Releases page himself (same signing key since 0.2.0, data kept). Nothing of 0.3.x has been tried on the device yet, in particular `QDesktopServices.openUrl` behind the two link buttons.
- Screenshots: `docs/screenshots/{desktop,phone}-{home,run,paused,review,leaderboard,stats,mistakes,settings}.png` (16 files, 1.7 MB) from `python tools\release_shots.py docs\screenshots desktop` and `... phone` (offscreen, real database, seeded sample runs). The v0.3.1 release page and the README load them from main via raw.githubusercontent.com: keep the names and the folder, regenerate whenever the UI changes.
- Sharing: John posts about the app. Nothing he shares may contain em dashes. The v0.3.1 release page is the feature list; `gh release view v0.3.1` prints it when a new page needs the template (`build/` is gitignored).

## Built in the 2026-09-23 sessions (all released)
- Round 3 (0.3.0): lives per run (Settings, 1-10, stored on the run row, schema 3), Pause (headless `pause`/`resume`, opaque `PauseOverlay`, Back resumes), boards and stats per number of lives (`UserDB._RUN_AT_SELECT`: a run with more lives also counts on the boards for fewer lives with the score it had at that many mistakes; Lives filter and column on Leaderboard and Stats, History untouched). Spec `docs/specs/lives-and-pause.md`, tests `tests/test_round3.py`.
- 0.3.1: Support the Dev (buymeacoffee.com/carter.bnw) and Check for Updates (Releases page) buttons in their own row above the home menu (`chesspuz.SUPPORT_URL` / `RELEASES_URL`, `home_page.open_link`); the home status line shows the version. README Screenshots section, `tools/release_shots.py`, README PDFs on both releases.
- Earlier that day: Android pipeline and 0.2.0 (confirmed on the phone), rounds 1-2, 0.1.0. 2026-09-22: Phases 0-7.

## How to ship a release
1. Bump `chesspuz.__version__` and `pyproject.toml`; tests + ruff; commit.
2. Windows zip, from PowerShell: `$env:PATH = "$PWD\.venv\Scripts;$env:PATH"; .\build_release.bat` (the PATH python is 3.12 without chess; Git Bash `cmd //c` cannot find the bat). Output `dist\chesspuz-X.Y.Z-windows.zip`. Smoke: run `dist\chesspuz\chesspuz.exe` offscreen for about 12 s with `CHESSPUZ_DATA_DIR` pointing at a scratch dir; a `user.sqlite` appearing there means the bundle started.
3. APK: `.venv\Scripts\python.exe android\sync.py sync build --version X.Y.Z` (about a minute; commit `android/VERSION` afterwards or the build stamp shows "+"). `python android\sync.py install run` only with the phone on USB.
4. Screenshots if the UI changed: `python tools\release_shots.py docs\screenshots desktop` and `... phone`, look at them, commit.
5. Notes in `build\release-notes-X.Y.Z.md` (for a sharing release copy the v0.3.1 page: hero image, download table, every feature with an image, phone trio, what is new, support link; images as `https://raw.githubusercontent.com/CARTER-BNW/chesspuz/main/docs/screenshots/...`; no em dashes). `git push` first (the images must be on main), then `gh release create vX.Y.Z dist\...zip android\bin\...apk --title "chesspuz X.Y.Z" --notes-file build\release-notes-X.Y.Z.md`.
6. README PDF: build `build\README-X.Y.Z.md` from README.md (a "Version X.Y.Z, date. Downloads: [..](..)" line under the H1; relative links made absolute to github.com/CARTER-BNW/chesspuz/blob/main/...; every URL as an explicit `[text](url)` link, because bare URLs break make-pdf's typography pass; the HTML `<img>` blocks turned into `![..](docs/screenshots/..){width=full}` with the screenshots copied to `build\docs\screenshots`; replace the "Created ... template" line by line prefix). Then `GSTACK_BROWSE_BIN=D:\Claude\config\skills\gstack\browse\dist\browse D:\Claude\config\skills\gstack\make-pdf\dist\pdf.exe generate --cover --no-confidential --author "John Carter" --title "chesspuz X.Y.Z" --date "..." build\README-X.Y.Z.md build\chesspuz-X.Y.Z-readme.pdf` (no `--toc`: its page numbers come out empty). Check the pages: the Read tool has no pdftoppm here; PyMuPDF installed with the system Python 3.12 into a scratch `--target` dir renders them to PNG. `gh release upload vX.Y.Z build\chesspuz-X.Y.Z-readme.pdf`.
7. Rewrite this file, tick docs/PLAN.md, commit, push.

## Android facts
- Signed release APKs with our key (scheme v2), targetSdk 36, not debuggable, 19 native libraries, the 40 MB puzzle database inside, 70.5 MB, about a minute per build after a code change. John confirmed 0.2.0 on the Pixel 9a (Android 16): layout, scrolling, AAudio sounds, Back key.
- Release key: `~/chesspuz-release.keystore` + `~/chesspuz-release.env` in the box, backup in `D:\Claude\secrets\chesspuz-android` (never in the repo; `android/wsl/keystore.sh` restores it). Losing it means uninstall-before-update for every user.
- Toolchain: WSL box `dd-android` + `~/chesspuz-venv` (Python 3.11, PySide6 6.11.2 host tools, buildozer 1.6.0), Qt Android wheels 6.11.2 aarch64 in `~/wheels`, python-for-android checkout `~/p4a-chesspuz` at `3762c88c` with the Back-key Java patch, NDK r28c, API 36. Reproducible from `android/wsl/setup.sh` + `build.sh`; pipeline and phone controls in `android/README.md`.
- Desktop emulation: `python android\app\main.py --desktop` (412x915 window). UI rules: keep every page's compact minimum width under ~380 px (word-wrap labels, stack rows when compact) AND its wide-shape minimum under 600 px, the compact threshold, or the emulation window cannot shrink into the phone shape (a third combo box on the leaderboard's filter row hit 671 px; filters now sit on their own rows). Touch has no right button; dialogs and the pause screen cancel on Back.

## Puzzle database
- 288,504 puzzles in `%LOCALAPPDATA%\chesspuz\puzzles.sqlite` (109 MB, rebuilt 2026-09-23 with `python main.py import --download`), the 300 MB Lichess file next to it. `sync.py sync` bundles it into the APK (`--db PATH` for another).

## Failed / dead ends (do not retry)
- 2026-09-23 later sessions: Git Bash `cmd //c build_release.bat` ("not recognized"; use PowerShell); make-pdf with bare URLs (`SMARTPANTS_PRESERVED` tokens and everything after the URL underlined) and with `--toc` (no page numbers); `PySide6.QtPdf` is not in PySide6-Essentials and the uv venv has no pip (PyMuPDF via the system Python 3.12 into a scratch `--target`); the playwright MCP writes screenshots only under the repo (`.playwright-mcp/`, gitignored); a `$`-anchored regex failed on the README's backtick line (replace by line prefix); the offscreen exe smoke test cannot tell a crash dialog from a running app; a third combo box on one filter row (671 px wide-shape minimum).
- Earlier: pyside6-android-deploy refuses Python 3.12+ (use the 3.11 venv); a uv venv has no pip, and buildozer needs `python -m pip`; the deploy tool needs tqdm; `buildozer init` prompts "running as root" before a spec exists (`BUILDOZER_WARN_ON_ROOT=0`); buildozer `git reset --hard`s its own p4a clone every build (patch a `p4a.source_dir` checkout instead); buildozer's `android release` makes an .aab unless `android.release_artifact = apk`; PySide6's Android build has no QJniObject; libshiboken6 is 4 KB-aligned (debug builds always get the compatibility dialog); do not drive the phone with blind `adb shell input tap` while John is using it; Bash tool truncates commands over ~8 KB (use the Write tool); pytest-qt `mouseMove` is unreliable offscreen; a shell pipeline hides pytest's exit code; winsound cannot play asynchronously from memory.

## Verify with
- `.venv\Scripts\python.exe -m pytest -q` (the venv has Python 3.13 with chess, PySide6, pytest-qt, ruff, PyInstaller; the PATH python does not)
- `.venv\Scripts\ruff.exe check . && .venv\Scripts\ruff.exe format .`
- `run.bat` (GUI from source), `build_release.bat` (release zip, venv on PATH), `python android\sync.py build` (APK), `python android\sync.py status`, `python tools\release_shots.py docs\screenshots desktop` (screenshots)
