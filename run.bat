@echo off
rem Launch chesspuz. Double-click for no console window; "run.bat --console" keeps a console open so errors stay visible.
cd /d "%~dp0"
if "%~1"=="--console" (
    python main.py
    if errorlevel 1 pause
) else (
    start "" pythonw main.py
)
