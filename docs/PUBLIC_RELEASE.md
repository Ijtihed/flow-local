# Public release preparation

The repository remains private while this preparation is reviewed. Changing visibility also exposes Git history, past releases, issue discussions and workflow logs. Public website hosting is a separate action.

Before changing visibility:

- Run Gitleaks against all Git history and the tracked working tree, with redacted reports. Investigate every finding before publishing.
- Review screenshots, release attachments and repository discussions for personal data. The bundled screenshots and speech fixtures are synthetic examples.
- Verify Windows/Linux CI, speech regression and the latest packaged runtimes. Document physical Linux/Wayland testing limits.
- Ensure no local history, dictionaries, recordings, model caches or credentials are included in the source or installers.
- Keep the MIT license, font licenses and third-party logo attribution with the distributed assets.
- Confirm that the latest release includes both installers and SHA256SUMS.txt. Windows builds are currently unsigned.

After the owner approves the visibility change, test release lookup and both asset downloads without a token. Remove the private-access note from the README, enable private vulnerability reporting, and check the mobile GitHub link and desktop direct downloads. Public releases need no GitHub token for automatic app updates; private releases require each user's own repository access.

To publish future updates, bump the version, push the commit and run **Actions → Publish update**. Automatic updates are enabled by default and can be disabled in Settings. They check shortly after startup, every six hours thereafter, and retry offline failures after fifteen minutes. Installation waits for at least sixty seconds without dictation or processing. Linux requires a writable AppImage.
