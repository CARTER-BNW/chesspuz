@echo off
rem Build a Windows release: dist\chesspuz\chesspuz.exe and dist\chesspuz-<version>-windows.zip
cd /d "%~dp0"
for /f %%v in ('python -c "import chesspuz; print(chesspuz.__version__)"') do set VERSION=%%v
echo Building chesspuz %VERSION%
python tools\make_icon.py || exit /b 1
python -m PyInstaller --noconfirm --clean chesspuz.spec || exit /b 1
if exist dist\chesspuz-%VERSION%-windows.zip del dist\chesspuz-%VERSION%-windows.zip
powershell -NoProfile -Command "Compress-Archive -Path dist\chesspuz -DestinationPath dist\chesspuz-%VERSION%-windows.zip"
if errorlevel 1 exit /b 1
echo Done: dist\chesspuz-%VERSION%-windows.zip
