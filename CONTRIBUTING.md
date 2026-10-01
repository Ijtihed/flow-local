# Contributing to Flow

Start with [source setup and platform notes](README.md#build-from-source). Keep Windows and Linux working, preserve the simple UI, and use example data in screenshots and recordings.

The UI and MCP server share `ui.Api`. Put reusable behavior there instead of giving the protocol a different implementation. Runtime commands and recording leases live in `control.py`; recognition and cleanup live in `engine.py`; dictionary changes live in `memory.py`. Settings use `paths.save_settings()` and user data stays outside the application folder.

To add an assistant integration, start with [MCP extensions](docs/MCP.md#add-tools-without-changing-the-ui) and [examples/mcp_extension.py](examples/mcp_extension.py). To add an app identity or logo, edit `assets/apps.json`, record its publisher source, and run `python tools/sync_apps.py`.

Run these checks before submitting a change:

```bash
python tools/release_version.py --check
python -m unittest discover -s tests -v
node tests/interface.cjs
python tools/check_mcp.py
```

Install the interface test dependencies with `npm ci --prefix tests`. Speech-engine changes also need `python tools/check_speech.py --model small --download --report speech-regression.json`.

Do not commit credentials, personal profiles, model downloads or recordings. Test microphone and model work using isolated profiles and bundled fixtures. Explain the user-visible behavior and relevant validation in your pull request. Windows signing changes must retain verification of the GUI app, MCP companion, installer and uninstaller.

For releases, use `python tools/release_version.py VERSION` to align every version field. See [the publication checklist](docs/PUBLISHING.md). Local unsigned builds are previews, not signed releases.
