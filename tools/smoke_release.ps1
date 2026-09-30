# Smoke test of a built Windows release zip, offscreen:
#     powershell -NoProfile -File tools\smoke_release.ps1 0.4.2
# Unzips dist\chesspuz-<version>-windows.zip into %TEMP%, starts the exe with an empty data
# folder (CHESSPUZ_DATA_DIR) and the offscreen Qt platform, then checks that the app is still
# running after 12 s, created user.sqlite (it got as far as opening its databases), made no copy
# of the puzzle database, and holds the shipped puzzles.sqlite open (SQLite keeps an open file
# locked against a rename on Windows). It cannot tell a crash dialog from a running app.
param([Parameter(Mandatory = $true)][string]$Version)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$zip = Join-Path $root "dist\chesspuz-$Version-windows.zip"
$work = Join-Path $env:TEMP "chesspuz-smoke-$Version"
$unz = Join-Path $work 'unz'
$data = Join-Path $work 'data'
if (Test-Path $work) { Remove-Item -Recurse -Force $work }
foreach ($d in @($unz, $data)) { New-Item -ItemType Directory $d | Out-Null }
Expand-Archive -Path $zip -DestinationPath $unz
$exe = Join-Path $unz 'chesspuz\chesspuz.exe'
$db = Join-Path $unz 'chesspuz\puzzles.sqlite'
"zip: {0:N1} MB, bundled puzzles.sqlite: {1:N1} MB" -f ((Get-Item $zip).Length / 1MB), ((Get-Item $db).Length / 1MB)
$env:CHESSPUZ_DATA_DIR = $data
$env:QT_QPA_PLATFORM = 'offscreen'
$env:QT_QPA_FONTDIR = 'C:\Windows\Fonts'
$p = Start-Process -FilePath $exe -PassThru
Start-Sleep -Seconds 12
"process alive after 12 s: $(-not $p.HasExited)"
"user.sqlite created: $(Test-Path (Join-Path $data 'user.sqlite'))"
"no copy of puzzles.sqlite in the data folder: $(-not (Test-Path (Join-Path $data 'puzzles.sqlite')))"
try {
    Rename-Item -Path $db -NewName 'puzzles.moved' -ErrorAction Stop
    Rename-Item -Path (Join-Path $unz 'chesspuz\puzzles.moved') -NewName 'puzzles.sqlite'
    "bundled database open in the app: False (the rename went through)"
} catch {
    "bundled database open in the app: True"
}
if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
Start-Sleep -Seconds 1
Remove-Item -Recurse -Force $work
