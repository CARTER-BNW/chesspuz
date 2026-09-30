@echo off
rem Build a Windows release: dist\chesspuz\chesspuz.exe and dist\chesspuz-<version>-windows.zip
rem The puzzle database is shipped inside the zip (puzzles.sqlite next to the exe), so nothing
rem is downloaded on the user's machine. It is taken from %CHESSPUZ_DB% when set, else from the
rem app's data folder (build it once with: python main.py import --download).
cd /d "%~dp0"
for /f %%v in ('python -c "import chesspuz; print(chesspuz.__version__)"') do set VERSION=%%v
echo Building chesspuz %VERSION%
if "%CHESSPUZ_DB%"=="" set "CHESSPUZ_DB=%LOCALAPPDATA%\chesspuz\puzzles.sqlite"
python main.py stats --db "%CHESSPUZ_DB%" || exit /b 1
python tools\make_icon.py || exit /b 1
python -m PyInstaller --noconfirm --clean chesspuz.spec || exit /b 1
copy /y "%CHESSPUZ_DB%" dist\chesspuz\puzzles.sqlite >nul || exit /b 1
echo Bundled "%CHESSPUZ_DB%"
if exist dist\chesspuz-%VERSION%-windows.zip del dist\chesspuz-%VERSION%-windows.zip
powershell -NoProfile -Command "Compress-Archive -Path dist\chesspuz -DestinationPath dist\chesspuz-%VERSION%-windows.zip"
if errorlevel 1 exit /b 1
echo Done: dist\chesspuz-%VERSION%-windows.zip
