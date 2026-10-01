# Before making Flow public

The repository remains private until its owner chooses to publish it. Source preparation and a local preview installer do not change GitHub visibility.

1. Run Windows/Linux unit and interface checks, speech regression and the real stdio MCP check. Confirm the packaged Windows `FlowMCP.exe` and Linux AppImage connect successfully.
2. Review the README product GIFs and screenshots. They must use example data. Scan the full Git history for credentials and personal files, not just the latest commit.
3. Configure the verified [Windows signing identity](WINDOWS_SIGNING.md) before publishing a new Windows release. The workflow signs the GUI app, MCP companion, installer and uninstaller, and fails if verification is missing or invalid. A local unsigned preview may still show SmartScreen.
4. Choose an unused version with `python tools/release_version.py VERSION`. Push it, run the Publish update workflow, and verify both packages, checksums and MCP entry points before announcing downloads. Never replace existing release assets.
5. After the owner makes the repository public, enable GitHub private vulnerability reporting and secret scanning where available. Update the README's private-download and private-token paragraphs. Verify downloads and updates from an account without repository access.
6. Publish the website separately when authorized, then check its download links, desktop OS routing and mobile layout. Check the first-run model selection, interactive practice and an update from the prior version on clean profiles.

The MIT license covers Flow's code. Bundled publisher logos retain their owners' rights; asset sources are in `assets/logos/SOURCES.txt`. Product previews illustrate compatibility and do not imply endorsements.
