# First-party Windows executables only. Third-party runtime files retain their publishers.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-FlowSignature {
    param([Parameter(Mandatory)][string]$Path, [string]$ExpectedSubject = $env:FLOW_SIGNER_SUBJECT)
    $file = Get-Item -LiteralPath $Path -ErrorAction Stop
    $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
    if ($signature.Status -ne 'Valid' -or $signature.SignatureType -ne 'Authenticode') {
        throw "Trusted embedded signature required for $($file.Name): $($signature.Status)"
    }
    if (-not $signature.TimeStamperCertificate) { throw "Timestamp required for $($file.Name)" }
    $codeSigning = @($signature.SignerCertificate.EnhancedKeyUsageList | Where-Object { $_.ObjectId -eq '1.3.6.1.5.5.7.3.3' })
    if (-not $codeSigning) { throw "Code-signing certificate required for $($file.Name)" }
    if ($ExpectedSubject -and $signature.SignerCertificate.Subject -ne $ExpectedSubject) {
        throw "Unexpected signing identity for $($file.Name)"
    }
    [pscustomobject]@{
        file = $file.Name
        status = [string]$signature.Status
        publisher = $signature.SignerCertificate.Subject
        timestamped = $true
        sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

function Assert-FlowSigningConfiguration {
    param([string]$Provider = $env:FLOW_SIGNING_PROVIDER)
    switch ($Provider) {
        'azure' {
            foreach ($name in 'FLOW_SIGNING_ENDPOINT','FLOW_SIGNING_ACCOUNT','FLOW_SIGNING_PROFILE') {
                if (-not [Environment]::GetEnvironmentVariable($name)) { throw "Signing requires $name. See docs/WINDOWS_SIGNING.md." }
            }
            $endpoint = [uri]$env:FLOW_SIGNING_ENDPOINT
            if ($endpoint.Scheme -ne 'https' -or $endpoint.Host -notmatch '^[a-z0-9]+\.codesigning\.azure\.net$' -or $endpoint.UserInfo -or $endpoint.Query -or $endpoint.Fragment) {
                throw 'Use the HTTPS regional Artifact Signing endpoint from your Azure account.'
            }
        }
        'certificate' {
            if ($env:FLOW_SIGN_CERT_SHA1 -notmatch '^[a-fA-F0-9]{40}$') { throw 'FLOW_SIGN_CERT_SHA1 must identify a trusted code-signing certificate in CurrentUser/My.' }
        }
        default { throw 'Verified code signing is not configured. Set FLOW_SIGNING_PROVIDER after completing docs/WINDOWS_SIGNING.md; releases will not fall back to unsigned files.' }
    }
}

function Invoke-FlowSigning {
    param([Parameter(Mandatory)][string]$Path)
    Assert-FlowSigningConfiguration
    $file = Get-Item -LiteralPath $Path -ErrorAction Stop
    if ($env:FLOW_SIGNING_PROVIDER -eq 'azure') {
        if ($file.FullName.Contains(',')) { throw 'Artifact Signing file paths cannot contain commas.' }
        Import-Module ArtifactSigning -RequiredVersion 0.1.20 -ErrorAction Stop
        $signing = @{
            Endpoint = $env:FLOW_SIGNING_ENDPOINT
            CodeSigningAccountName = $env:FLOW_SIGNING_ACCOUNT
            CertificateProfileName = $env:FLOW_SIGNING_PROFILE
            Files = $file.FullName
            FileDigest = 'SHA256'
            TimestampRfc3161 = 'http://timestamp.acs.microsoft.com'
            TimestampDigest = 'SHA256'
            ExcludeEnvironmentCredential = $true
            ExcludeWorkloadIdentityCredential = $true
            ExcludeManagedIdentityCredential = $true
            ExcludeSharedTokenCacheCredential = $true
            ExcludeVisualStudioCredential = $true
            ExcludeVisualStudioCodeCredential = $true
            ExcludeAzureCliCredential = $false
            ExcludeAzurePowerShellCredential = $true
            ExcludeAzureDeveloperCliCredential = $true
            ExcludeInteractiveBrowserCredential = $true
        }
        Invoke-ArtifactSigning @signing | Out-Host
    } else {
        $certificate = Get-Item -LiteralPath ('Cert:\CurrentUser\My\' + $env:FLOW_SIGN_CERT_SHA1) -ErrorAction Stop
        if (-not $certificate.HasPrivateKey) { throw 'The signing certificate has no accessible private key.' }
        $sdkRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
        $signTool = Get-ChildItem -Path (Join-Path $sdkRoot '*\x64\signtool.exe') -ErrorAction SilentlyContinue |
            Sort-Object { [version]$_.Directory.Parent.Name } -Descending | Select-Object -First 1
        if (-not $signTool) { throw 'Install the Windows SDK signing tools before signing.' }
        & $signTool.FullName sign /sha1 $env:FLOW_SIGN_CERT_SHA1 /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /d Flow $file.FullName | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "SignTool failed for $($file.Name)" }
    }
    Assert-FlowSignature -Path $file.FullName
}

Export-ModuleMember -Function Assert-FlowSignature,Assert-FlowSigningConfiguration,Invoke-FlowSigning
