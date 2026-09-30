# Builds dist\Flow\Flow.exe and installer\FlowSetup.exe
# Needs: the venv from the README, plus Inno Setup 6 (winget install JRSoftware.InnoSetup)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
.\.venv\Scripts\pip install pyinstaller | Out-Null
.\.venv\Scripts\python -c "import icons; from pathlib import Path; icons.ensure_app_ico(Path('assets/flow.ico')); icons.app_icon(256).save('assets/logo.png')"
.\.venv\Scripts\pyinstaller flow.spec --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found. Install it with: winget install JRSoftware.InnoSetup" }
& $iscc flow.iss
if ($LASTEXITCODE -ne 0) { throw "Installer build failed" }
Write-Host "Done: installer\FlowSetup.exe"
