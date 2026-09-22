# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: a one-folder, windowed build in dist/chesspuz (run build_release.bat)."""

from pathlib import Path

UI_MODULES = [
    "chesspuz.ui.app",
    "chesspuz.ui.board",
    "chesspuz.ui.demo",
    "chesspuz.ui.engine",
    "chesspuz.ui.home_page",
    "chesspuz.ui.leaderboard_page",
    "chesspuz.ui.mistakes_page",
    "chesspuz.ui.pieces",
    "chesspuz.ui.played_page",
    "chesspuz.ui.puzzle_window",
    "chesspuz.ui.review_page",
    "chesspuz.ui.run_page",
    "chesspuz.ui.settings_page",
    "chesspuz.ui.stats_page",
    "chesspuz.ui.theme",
    "chesspuz.ui.workers",
]

icon = Path("assets/chesspuz.ico")

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=[*UI_MODULES, "winsound", "zstandard", "chess.engine", "chess.svg"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuickWidgets",
        "PySide6.QtQuickControls2",
        "PySide6.QtNetwork",
        "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets",
        "PySide6.QtPrintSupport",
        "PySide6.QtSql",
        "PySide6.QtTest",
        "PySide6.QtXml",
        "PySide6.QtDBus",
        "PySide6.QtConcurrent",
        "PySide6.QtHelp",
        "PySide6.QtDesigner",
        "PySide6.QtUiTools",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="chesspuz",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(icon) if icon.exists() else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="chesspuz",
)
