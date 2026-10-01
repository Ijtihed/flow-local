# Public release preparation

The owner has authorized publishing Flow's source, downloads and website without paid signing. The release procedure is documented in [PUBLISHING.md](PUBLISHING.md). Public source includes Git history, past releases and workflow logs.

Before changing visibility:

- Run Gitleaks against all Git history and the tracked working tree, with redacted reports. Investigate every finding before publishing.
- Review screenshots, release attachments and repository discussions for personal data. The bundled screenshots and speech fixtures are synthetic examples.
- Verify Windows/Linux CI, speech regression and the latest packaged runtimes. Document physical Linux/Wayland testing limits.
- Ensure no local history, dictionaries, recordings, model caches or credentials are included in the source or installers.
- Keep the MIT license, font licenses and third-party logo attribution with the distributed assets.
- Confirm that the latest release includes both installers and SHA256SUMS.txt. Windows builds are currently unsigned.

After changing visibility, test release lookup and both asset downloads without a token, enable private vulnerability reporting, and check the mobile GitHub link and desktop direct downloads. Public releases need no GitHub token for automatic app updates; private releases require each user's own repository access.

To publish future updates, bump the version, push the commit and run **Actions → Publish update**. Update checks run at startup, on each window opening and every six hours; offline failures retry after fifteen minutes. An available version shows a popup. Automatic installation can be disabled in Settings without disabling checks. Installation waits until the window is closed and at least sixty seconds have passed without dictation or processing. Linux requires a writable AppImage.
