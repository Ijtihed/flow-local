# Publication checklist

The owner has authorized public source, downloads and website hosting. Hosting uses free GitHub Pages. Windows releases are unsigned unless an optional verified signing provider is configured.

1. Run Windows/Linux unit and interface checks, speech regression and the real stdio MCP check. Confirm the packaged Windows `FlowMCP.exe` and Linux AppImage connect successfully.
2. Review the README product GIFs and screenshots. They must use example data. Scan the full Git history for credentials and personal files, not just the latest commit.
3. Disclose unsigned Windows downloads and SmartScreen in the README and release notes. If optional [signing](WINDOWS_SIGNING.md) is configured, verify the GUI app, MCP companion, installer and uninstaller; failed signing must block publication.
4. Choose an unused version with `python tools/release_version.py VERSION`. Push it, run the Publish update workflow, and verify both packages, checksums and MCP entry points before announcing downloads. Never replace existing release assets.
5. Enable GitHub private vulnerability reporting and free public-repository secret scanning where available. Verify downloads and update lookup without authentication.
6. Deploy `site/` with the Publish website workflow. Check download links, desktop OS routing, assets and mobile layout. Check first-run model selection, interactive practice and an upgrade from the prior version on disposable runners; do not modify a maintainer's installed app/profile for release validation.

The MIT license covers Flow's code. Bundled publisher logos retain their owners' rights; asset sources are in `assets/logos/SOURCES.txt`. Product previews illustrate compatibility and do not imply endorsements.
