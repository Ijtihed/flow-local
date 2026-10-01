# These checks inspect real Authenticode files. No signing account or keys are used.
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot '..\tools\signing.psm1') -Force

function Expect-Failure {
    param([scriptblock]$Action, [string]$Message)
    $failed = $false
    try { & $Action | Out-Null } catch {
        if ($_.Exception.Message -notlike "*$Message*") { throw }
        $failed = $true
    }
    if (-not $failed) { throw "Expected failure: $Message" }
}

$saved = @{}
foreach ($name in 'FLOW_SIGNING_PROVIDER','FLOW_SIGNING_ENDPOINT','FLOW_SIGNING_ACCOUNT','FLOW_SIGNING_PROFILE','FLOW_SIGNER_SUBJECT','FLOW_SIGN_CERT_SHA1') {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name)
    [Environment]::SetEnvironmentVariable($name,$null)
}
$fixture = Join-Path ([IO.Path]::GetTempPath()) ('flow-unsigned-' + [guid]::NewGuid().ToString('N') + '.ps1')
try {
    Expect-Failure { Assert-FlowSigningConfiguration } 'not configured'
    $env:FLOW_SIGNING_PROVIDER = 'azure'
    Expect-Failure { Assert-FlowSigningConfiguration } 'FLOW_SIGNING_ENDPOINT'
    $env:FLOW_SIGNING_ACCOUNT = 'fixture'
    $env:FLOW_SIGNING_PROFILE = 'fixture'
    foreach ($endpoint in 'http://eus.codesigning.azure.net','https://example.com','https://eus.codesigning.azure.net.example.com','https://user@eus.codesigning.azure.net','https://eus.codesigning.azure.net?token=fixture') {
        $env:FLOW_SIGNING_ENDPOINT = $endpoint
        Expect-Failure { Assert-FlowSigningConfiguration } 'HTTPS regional'
    }
    $env:FLOW_SIGNING_ENDPOINT = 'https://eus.codesigning.azure.net/'
    Assert-FlowSigningConfiguration
    $env:FLOW_SIGNING_PROVIDER = 'certificate'
    Expect-Failure { Assert-FlowSigningConfiguration } 'FLOW_SIGN_CERT_SHA1'
    $env:FLOW_SIGN_CERT_SHA1 = '0' * 40
    Assert-FlowSigningConfiguration

    '# An unsigned fixture' | Set-Content -LiteralPath $fixture
    Expect-Failure { Assert-FlowSignature -Path $fixture } 'Trusted embedded signature required'
    # The hosted Windows runner uses Microsoft's signed PowerShell executable.
    $trusted = (Get-Process -Id $PID).Path
    $report = Assert-FlowSignature -Path $trusted
    if ($report.status -ne 'Valid' -or -not $report.timestamped) { throw 'Trusted signature was not accepted' }
    Expect-Failure { Assert-FlowSignature -Path $trusted -ExpectedSubject 'CN=Unrelated publisher' } 'Unexpected signing identity'
    Write-Output 'Signing checks passed: missing configuration, endpoint validation, unsigned-file rejection, trusted timestamped signature, publisher mismatch.'
} finally {
    Remove-Item -LiteralPath $fixture -ErrorAction SilentlyContinue
    foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name,$saved[$name]) }
}
