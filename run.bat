@echo off
rem Launch chesspuz. Double-click for no console window; "run.bat --console" keeps a console open so errors stay visible.
rem The repository's own virtual environment (.venv: Python 3.13 with chess and PySide6) is used when it exists;
rem otherwise the python on PATH, which is checked first, because pythonw would fail without a word if a package is missing.
cd /d "%~dp0"
set "PY=python"
set "PYW=pythonw"
if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
    set "PYW=.venv\Scripts\pythonw.exe"
)
if "%~1"=="--console" (
    "%PY%" main.py
    if errorlevel 1 pause
    goto :eof
)
"%PY%" -c "import chess, PySide6" >nul 2>&1
if errorlevel 1 (
    echo chesspuz cannot start: "%PY%" has no chess / PySide6 packages.
    echo Create the virtual environment once, from this folder:
    echo     python -m venv .venv
    echo     .venv\Scripts\python -m pip install -r requirements.txt
    echo or install the packages into the python on PATH:
    echo     python -m pip install -r requirements.txt
    pause
    goto :eof
)
start "" "%PYW%" main.py
