param(
    [Parameter(Mandatory)][string[]]$Path,
    [ValidateSet('Sign','Verify')][string]$Mode = 'Sign',
    [string]$Report
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'signing.psm1') -Force
$results = @()
foreach ($file in $Path) {
    if ($Mode -eq 'Sign') { $results += Invoke-FlowSigning -Path $file }
    else { $results += Assert-FlowSignature -Path $file }
}
if ($Report) { ConvertTo-Json -InputObject $results -Depth 4 | Set-Content -LiteralPath $Report -Encoding utf8 }
$results | Format-Table file,status,timestamped,publisher
