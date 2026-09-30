# Security

Please report security issues privately through [GitHub security advisories](https://github.com/Ijtihed/flow-local/security/advisories/new), once private vulnerability reporting is enabled. Do not put credentials or personal recordings in public issues.

Flow stores recordings in memory during dictation. History, dictionary and model files stay in the user's data directory, outside the installation and repository. API speech sends audio to the provider only after explicit consent. Update requests send app version and download requests to GitHub; they do not include dictation history.

Updates use HTTPS and verify the GitHub release asset's SHA-256 digest and byte count before installation. Credentials go only to GitHub's API and are removed from requests to signed download storage URLs. The Windows installer is currently unsigned, so Windows may show a publisher warning. A checksum does not replace publisher code signing.

Automatic installation waits for dictation and processing to finish, then reserves the recorder before handing off to the installer. Windows preserves user data and startup preferences; Linux keeps the previous AppImage as a backup.
