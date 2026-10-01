# Runs only on a disposable GitHub Actions Windows runner; never on a user's PC.
param([string]$Report = 'windows-install.json')
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or -not $env:RUNNER_TEMP) { throw 'Installer checks require a disposable GitHub Actions runner.' }
$flowTestRoot = Join-Path $env:RUNNER_TEMP ('flow-install-' + [guid]::NewGuid().ToString('N'))
$flowInstallDir = Join-Path $flowTestRoot 'app'
$flowProfileDir = Join-Path $flowTestRoot 'profile'
New-Item -ItemType Directory -Path $flowTestRoot,$flowProfileDir | Out-Null
$flowInstaller = (Resolve-Path -LiteralPath 'installer/FlowSetup.exe').Path
$flowExpected = (& .\.venv\Scripts\python tools/release_version.py --check).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Version check failed' }
$flowSavedData = $env:FLOW_DATA
$env:FLOW_DATA = $flowProfileDir
$flowReport = @{version=$flowExpected; profile='temporary'; audio='not captured'; api='no calls or uploads'}
function Install-FlowFixture([string]$Installer) {
    $process = Start-Process -FilePath $Installer -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/TASKS=',('/DIR="' + $flowInstallDir + '"') -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Installer failed: $($process.ExitCode)" }
}
try {
    # Upgrade from the latest published installer, verified against GitHub's digest.
    $previous = Invoke-RestMethod 'https://api.github.com/repos/Ijtihed/flow-local/releases/latest'
    $asset = $previous.assets | Where-Object name -eq 'FlowSetup.exe' | Select-Object -First 1
    if ($asset -and $previous.tag_name -ne ('v' + $flowExpected)) {
        if ($asset.digest -notmatch '^sha256:[0-9a-f]{64}$') { throw 'Prior release lacks a digest' }
        $priorInstaller = Join-Path $flowTestRoot 'prior.exe'
        Invoke-WebRequest $asset.browser_download_url -OutFile $priorInstaller
        if ((Get-FileHash -LiteralPath $priorInstaller -Algorithm SHA256).Hash.ToLowerInvariant() -ne $asset.digest.Substring(7)) { throw 'Prior installer failed integrity check' }
        Install-FlowFixture $priorInstaller
        $oldVersion = (Get-Item -LiteralPath (Join-Path $flowInstallDir 'Flow.exe')).VersionInfo.ProductVersion
        if ($oldVersion -ne $previous.tag_name.TrimStart('v')) { throw 'Prior installed version differs' }
        $flowReport.upgraded_from = $oldVersion
    } else { $flowReport.upgraded_from = 'fresh install' }
    '{"name":"Alex","languages":["en"],"auto_update":false,"snippets":[{"trigger":"my email","text":"alex@example.com"}]}' | Set-Content -LiteralPath (Join-Path $flowProfileDir 'settings.json') -Encoding utf8NoBOM
    '{"at":"2026-01-01T12:00:00","text":"A synthetic saved dictation.","app":"Firefox"}' | Set-Content -LiteralPath (Join-Path $flowProfileDir 'history.jsonl') -Encoding utf8NoBOM
    $profileHashes = Get-FileHash -LiteralPath (Join-Path $flowProfileDir 'settings.json'),(Join-Path $flowProfileDir 'history.jsonl')
    Install-FlowFixture $flowInstaller
    $flowExecutable = Join-Path $flowInstallDir 'Flow.exe'
    $flowCompanion = Join-Path $flowInstallDir 'FlowMCP.exe'
    foreach ($binary in $flowExecutable,$flowCompanion) {
        if ((Get-Item -LiteralPath $binary).VersionInfo.ProductVersion -ne $flowExpected) { throw 'Installed version differs' }
    }
    foreach ($hash in $profileHashes) {
        if ((Get-FileHash -LiteralPath $hash.Path).Hash -ne $hash.Hash) { throw 'Installer changed the saved profile' }
    }
    foreach ($notice in 'LICENSE','THIRD_PARTY_NOTICES.txt') {
        if (-not (Test-Path -LiteralPath (Join-Path $flowInstallDir ('_internal/' + $notice)))) { throw "Missing packaged notice: $notice" }
    }
    $process = Start-Process -FilePath $flowExecutable -ArgumentList '--self-test-headless','--test-report',(Join-Path $flowTestRoot 'installed-runtime.json') -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw 'Installed runtime check failed' }
    & .\.venv\Scripts\python tools/check_mcp.py --command $flowCompanion --args '[]' --report (Join-Path $flowTestRoot 'installed-mcp.json')
    if ($LASTEXITCODE -ne 0) { throw 'Installed MCP check failed' }
    $flowReport.install = 'passed'; $flowReport.profile_preserved = $true; $flowReport.mcp = 'passed'
    $process = Start-Process -FilePath (Join-Path $flowInstallDir 'unins000.exe') -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART' -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw 'Uninstaller failed' }
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    while ((Test-Path -LiteralPath $flowExecutable) -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 200 }
    if ((Test-Path -LiteralPath $flowExecutable) -or (Test-Path -LiteralPath $flowCompanion)) { throw 'Uninstaller left an executable behind' }
    foreach ($hash in $profileHashes) {
        if ((Get-FileHash -LiteralPath $hash.Path).Hash -ne $hash.Hash) { throw 'Uninstaller changed saved data' }
    }
    $flowReport.uninstall = 'passed'; $flowReport.ok = $true
} finally {
    $env:FLOW_DATA = $flowSavedData
    $flowReport | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Report -Encoding utf8NoBOM
}
