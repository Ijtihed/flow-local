# Development

See [CONTRIBUTING.md](../CONTRIBUTING.md) and the [platform setup](PLATFORMS.md). Use Python 3.10 or newer and a virtual environment. Keep personal profiles and credentials out of source control.

## Build

Windows: install [Inno Setup](https://jrsoftware.org/isinfo.php), install PyInstaller in `.venv`, then run `./build.ps1`. Outputs are `dist/Flow/Flow.exe`, `dist/Flow/FlowMCP.exe`, and `installer/FlowSetup.exe`. Builds are unsigned unless `-Signed` is explicitly requested with a verified identity.

Linux: run `bash build-linux.sh`. It bundles Python, speech/audio libraries and X11 utilities into `installer/Flow-x86_64.AppImage`, using the official AppImage packaging tools. Models and NVIDIA libraries remain separate downloads. Source users can install GPU dependencies from `requirements-gpu.txt`.

## Checks

```bash
python tools/release_version.py --check
python -m unittest discover -s tests -v
npm ci --prefix tests
node tests/interface.cjs
python tools/check_mcp.py
python tools/check_speech.py --model small --download --report speech-regression.json
python tools/check_mcp_speech.py --model small --report mcp-speech-regression.json
```

Interface checks use an isolated DOM and clock, covering setup, the spoken tutorial, engine selection, greetings, shortcuts, updates and website OS routing. Speech checks use bundled synthetic audio and a cached model; they do not capture a microphone or use a paid API.

Packaged builds support `--self-test-headless --test-report report.json` to inspect runtime/assets without opening a window or inspecting hardware. On a desktop, `--self-test` also checks audio devices and the overlay. Windows `--self-test-window` opens and closes the actual tutorial using an empty temporary profile. `./tests/signing.ps1` verifies optional signing safeguards without signing credentials. Release CI additionally installs, upgrades and uninstalls the Windows app on an isolated runner.

## Architecture

| File | Purpose |
|---|---|
| `flow.py`, `hotkeys.py`, `pill.py` | Tray, shortcut state, recording and overlay |
| `engine.py` | Recognition, vocabulary hints, cleanup and style |
| `memory.py` | SQLite personal vocabulary and corrections |
| `ui.py`, `ui.html`, `ui_linux.py` | Shared API and platform settings UI |
| `mcp_server.py`, `mcp_config.py` | MCP tools, resources, prompts and connection configs |
| `updates.py` | GitHub release selection, digest verification and replacement |
| `vault.py`, `voicenotes.py`, `learn.py` | Optional notes and learning |

Recognition first decodes without hints, selects sound-alike dictionary candidates, then selectively retries recognition. Confirmed repairs apply afterward. Optional local cleanup can remove words but cannot add them. See [examples/transcribe_file.py](../examples/transcribe_file.py) to use the engine without the UI, and [MCP extensions](MCP.md#add-tools-without-changing-the-ui) for assistant integrations.

Edit `assets/apps.json` and run `python tools/sync_apps.py` to synchronize the website catalog and logos. Preserve publisher attribution. GIFs use example data; [capture instructions](media/README.md).

## Release

Run `python tools/release_version.py VERSION`, commit and push the matching `vVERSION` tag, or dispatch **Publish update** from Actions. Windows/Linux checks and speech regression must pass. Both packages and checksums are uploaded to a draft before it becomes latest. Existing versions are never overwritten. The website deploys from `site/` through GitHub Pages on changes to main.

Releases are unsigned while no signing provider is configured. Setting `FLOW_SIGNING_PROVIDER=azure` enables the prepared verified-signing pipeline; failures then block publishing rather than falling back to unsigned files. See [signing](WINDOWS_SIGNING.md) and the [publication checklist](PUBLISHING.md).
