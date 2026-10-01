# Windows code signing

Flow releases through 1.5.11 are unsigned. The release workflow now requires signing configuration and stops when it is missing or verification fails. The existing downloads are unchanged; this preparation does not turn them into signed files.

The signed build signs `Flow.exe` before packaging, then lets Inno Setup sign both the installer and its generated uninstaller. It checks for a trusted embedded Authenticode signature, code-signing usage and a timestamp. Release checksums are generated afterward. Third-party runtime files retain their original publishers. `windows-signatures.json` records the final app and installer signatures and hashes in the Windows build artifact.

Signing identifies the publisher, but a new publisher can still receive SmartScreen warnings while reputation builds. Microsoft Store MSIX distribution is the most reliable route for avoiding the download warning. [Microsoft's SmartScreen guidance](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation)

## Finish account setup

The owner must supply a verified signing identity. Neither a self-signed certificate nor the installer’s `AppPublisher` label establishes a trusted publisher. The private key, account credentials and identity documents must not be put in the repository or this document.

The prepared hosted workflow uses Azure Artifact Signing. Its Public Trust service supports individuals in the US and Canada; organizations have a wider supported country list. Confirm eligibility before purchasing anything. Identity validation requires the Azure portal and the owner's accurate legal and billing details. Use a **PublicTrust** certificate profile; test/private trust profiles do not establish consumer trust. [Account setup and eligibility](https://learn.microsoft.com/en-us/azure/artifact-signing/quickstart)

Once the account and profile are approved:

1. Create a GitHub environment named `windows-signing`, restrict deployment branches/tags to release tags `v*` (and `main` if manually publishing from that branch), and review who can change its configuration. Create an Entra application/service principal for release signing. Add a GitHub federated credential with subject `repo:Ijtihed/flow-local:environment:windows-signing`, issuer `https://token.actions.githubusercontent.com` and audience `api://AzureADTokenExchange`. This stays valid across release versions. Only the Windows release job requests a signing token; Linux and ordinary CI do not.
2. Grant **Artifact Signing Certificate Profile Signer** on the intended profile only. The signing identity does not need subscription Owner or Contributor. Creating this access is an owner/account-administrator action.
3. In GitHub **Settings → Secrets and variables → Actions → Variables**, enter:

   | Variable | Value |
   |---|---|
   | `FLOW_SIGNING_PROVIDER` | `azure` |
   | `FLOW_SIGNING_ENDPOINT` | Your account's HTTPS regional endpoint |
   | `FLOW_SIGNING_ACCOUNT` | Approved signing account name |
   | `FLOW_SIGNING_PROFILE` | Approved PublicTrust profile name |
   | `AZURE_CLIENT_ID` | Entra application ID |
   | `AZURE_TENANT_ID` | Directory ID |
   | `AZURE_SUBSCRIPTION_ID` | Subscription ID |
   | `FLOW_SIGNER_SUBJECT` | Optional exact certificate subject to enforce |

These are identifiers, not passwords. GitHub uses short-lived OIDC authentication; no client secret or certificate private key is stored in GitHub. The release job uses Microsoft's pinned Azure login action and the official ArtifactSigning PowerShell module version 0.1.20, also used by its signing action. [Microsoft's signing integration](https://github.com/Azure/artifact-signing-action)

4. Bump to an unused version, commit and push its matching tag. Verify both signatures in the Windows artifact before distributing the new installer. The old unsigned release is never overwritten. SmartScreen reputation cannot be guaranteed immediately.

## Existing certificate or another provider

For a local trusted certificate with its private key available in **CurrentUser/My**, set `FLOW_SIGNING_PROVIDER=certificate` and `FLOW_SIGN_CERT_SHA1` to its thumbprint, then run `./build.ps1 -Signed`. The Windows SDK's SignTool signs with SHA-256 and an RFC 3161 timestamp. Hardware/cloud key-provider certificates must be usable through that certificate's configured Windows provider. Do not export a non-exportable key or upload a private key to this repository.

The hosted release workflow currently supports Azure. Using a local certificate in CI requires an appropriately managed signing runner or the certificate vendor's service integration. SignPath Foundation offers signing for approved open-source projects; acceptance is not automatic and its policy requires verifiable project reputation and manual approval of releases. Flow remains private until the owner approves publication. [SignPath conditions](https://signpath.org/terms.html)

An ordinary `./build.ps1` creates an explicitly unsigned development installer. It is not accepted by the release workflow. To verify signed outputs independently:

```powershell
./tools/sign-windows.ps1 -Mode Verify -Path dist/Flow/Flow.exe,installer/FlowSetup.exe -Report windows-signatures.json
```

Inno Setup invokes the same signer for its temporary uninstall executable during compilation. [Inno signing](https://jrsoftware.org/ishelp/topic_setup_signtool.htm)
