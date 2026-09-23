"""chesspuz on the phone: the APK's ``main.py`` calls :func:`main`.

The desktop app is the master; this file only prepares the phone's environment (private data
directory, the bundled puzzle database, temp dirs for SQLite) and turns on the compact layout.
``python android/app/main.py --desktop`` runs the same code in a phone-sized window on the PC.
"""

from __future__ import annotations

import faulthandler
import os
import sys
import traceback
from pathlib import Path

PHONE_WINDOW = (412, 915)  # logical pixels of a Pixel 9a in portrait


def is_android() -> bool:
    return "ANDROID_PRIVATE" in os.environ or "ANDROID_ARGUMENT" in os.environ


def prepare_environment(private_dir: Path, app_dir: Path) -> dict[str, Path]:
    """Point chesspuz at its phone folders; returns the paths chosen.

    ``private_dir`` is the app's files directory (survives updates), ``app_dir`` the unpacked
    APK payload (replaced on every update: only the read-only puzzle database lives there).
    """
    data = private_dir / "chesspuz"
    cache = private_dir.parent / "cache"
    for folder in (data, cache):
        folder.mkdir(parents=True, exist_ok=True)
    os.environ["CHESSPUZ_DATA_DIR"] = str(data)
    os.environ["CHESSPUZ_MOBILE"] = "1"
    # SQLite and tempfile fall back to "." without these, which is not writable on Android
    os.environ.setdefault("SQLITE_TMPDIR", str(cache))
    os.environ.setdefault("TMPDIR", str(cache))
    return {"data": data, "cache": cache, "puzzles": app_dir / "puzzles.sqlite"}


def _build_info() -> str:
    try:
        from mobile import build_info

        return f"{build_info.VERSION} ({build_info.COMMIT}, built {build_info.BUILT})"
    except Exception:  # noqa: BLE001 (generated file, may be missing when run from source)
        return "dev"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    desktop = "--desktop" in argv
    app_dir = Path(__file__).resolve().parent.parent
    if is_android():
        private = Path(os.environ.get("ANDROID_PRIVATE", str(app_dir)))
    else:
        # emulation on the PC: the normal data dir, a phone-sized window
        from chesspuz import paths

        private = paths.data_dir().parent / "chesspuz-phone"
    where = prepare_environment(private, app_dir)
    faulthandler.enable()
    print(f"chesspuz {_build_info()} starting; data in {where['data']}", flush=True)
    try:
        from chesspuz.ui import app as ui_app

        puzzle_db = where["puzzles"]
        if not puzzle_db.exists():
            puzzle_db = None  # the home page explains that no database is available
        qt_app, ctx, window = ui_app.build(argv=[sys.argv[0]], puzzle_db=puzzle_db)
        window.show()
        if desktop or not is_android():
            # twice: the first resize reshapes the pages, the second is no longer clamped by
            # their landscape minimum size
            for _ in range(2):
                window.resize(*PHONE_WINDOW)
                qt_app.processEvents()
        try:
            return qt_app.exec()
        finally:
            ctx.close()
    except Exception:  # noqa: BLE001 (leave a note where adb can read it, then re-raise)
        (where["data"] / "crash.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    sys.exit(main())
