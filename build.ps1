# Builds dist\Flow\Flow.exe and installer\FlowSetup.exe
# Needs: the venv from the README, plus Inno Setup 6 (winget install JRSoftware.InnoSetup)
param([switch]$Signed)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
.\.venv\Scripts\python tools\release_version.py --check
if ($LASTEXITCODE -ne 0) { throw "Application and installer versions differ" }
if ($Signed) {
    Import-Module (Join-Path $PSScriptRoot 'tools\signing.psm1') -Force
    Assert-FlowSigningConfiguration
}
.\.venv\Scripts\pip install pyinstaller | Out-Null
.\.venv\Scripts\python -c "import icons; from pathlib import Path; icons.ensure_app_ico(Path('assets/flow.ico'), force=True); icons.app_icon(256).save('assets/logo.png')"
.\.venv\Scripts\pyinstaller flow.spec --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
if ($Signed) { Invoke-FlowSigning -Path 'dist\Flow\Flow.exe' | Out-Host }
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found. Install it with: winget install JRSoftware.InnoSetup" }
if ($Signed) {
    $flowPowerShell = (Get-Process -Id $PID).Path
    $flowSigner = Join-Path $PSScriptRoot 'tools\sign-windows.ps1'
    $flowSignCommand = '-SFlowSigner=$q' + $flowPowerShell + '$q -NoProfile -NonInteractive -File $q' + $flowSigner + '$q -Path $f'
    & $iscc '/DFlowSigned' $flowSignCommand flow.iss
} else {
    & $iscc flow.iss
}
if ($LASTEXITCODE -ne 0) { throw "Installer build failed" }
if ($Signed) {
    & (Join-Path $PSScriptRoot 'tools\sign-windows.ps1') -Mode Verify -Path 'dist\Flow\Flow.exe','installer\FlowSetup.exe' -Report 'windows-signatures.json'
} else {
    Write-Warning 'Development installer is unsigned. Publish update requires verified signing.'
}
Write-Host "Done: installer\FlowSetup.exe"
