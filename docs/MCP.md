# Connect Flow with MCP

Flow ships a local stdio MCP server built with the [official Python SDK](https://github.com/modelcontextprotocol/python-sdk). An assistant can configure the app, teach vocabulary, manage spoken shortcuts, inspect history, select engines, download models, check updates and run real dictation. It uses the same implementation as the app. Connecting does not start recording or upload audio.

MCP is included in Flow 1.5.15 and newer. Older downloads through 1.5.11 do not contain it.

## Quick connection

Open **Settings → Connect your assistant → MCP connection**. Copy JSON or TOML, add it to your client's MCP configuration, and restart that client. These buttons generate the correct absolute path for your installation. Choose **Read-only access** before copying to block changes, recording, transcription and downloads.

Clients using `mcpServers` can use this JSON on Windows, replacing the example path with their own:

```json
{
  "mcpServers": {
    "flow": {
      "command": "C:\\Users\\YOUR_NAME\\AppData\\Local\\Programs\\Flow\\FlowMCP.exe",
      "args": []
    }
  }
}
```

FlowMCP.exe is included beside Flow.exe; no separate Python or Node installation is needed. The separate executable supplies the stdio pipes that a Windows GUI executable lacks.

Linux AppImage users:

```json
{
  "mcpServers": {
    "flow": {
      "command": "/absolute/path/Flow-x86_64.AppImage",
      "args": ["--mcp"]
    }
  }
}
```

For TOML clients, use the same command and arguments under `[mcp_servers.flow]`. For source installs, use your virtual environment's Python with the absolute `main.py` path and `--mcp`. Add `--read-only` to the arguments if wanted. Set `FLOW_DATA` in the client's server environment to use a separate Flow profile.

## Things to ask your assistant

- “Teach Flow the names Ijtihed and Kubernetes.”
- “When I say ‘my email’, insert alex@example.com.”
- “Make my work writing formal and personal chats casual.”
- “Show the speech models my computer can run, then help me choose one.”
- “Find my last five Firefox dictations.”
- “Check for an update, but wait before installing.”

Dictionary additions become available to the running engine without a restart. Settings changes take effect after the current dictation; the UI refreshes when you finish editing a field.

## Tools

| Area | Tools |
|---|---|
| Configuration | `flow_get_settings`, `flow_configure`, `flow_get_status`, `flow_finish_setup` |
| Models and speech | `flow_list_models`, `flow_download_component`, `flow_download_status`, `flow_set_speech_engine`, `flow_forget_speech_key`, `flow_transcribe_file` |
| Vocabulary | `flow_get_dictionary`, `flow_add_words`, `flow_add_correction`, `flow_remove_word`, `flow_remove_correction`, `flow_scan_notes` |
| Spoken shortcuts | `flow_list_spoken_shortcuts`, `flow_set_spoken_shortcut`, `flow_remove_spoken_shortcut` |
| History and usage | `flow_get_history`, `flow_edit_dictation`, `flow_delete_dictation`, `flow_clear_history`, `flow_get_insights`, `flow_list_apps` |
| Notes and clipboard | `flow_set_voice_notes`, `flow_copy_text` |
| Health | `flow_get_diagnostics`, `flow_export_diagnostics` |
| Updates | `flow_check_updates`, `flow_update_status`, `flow_install_update`, `flow_set_update_access`, `flow_forget_update_access` |
| Microphone and tutorial | `flow_recording`, `flow_practice` |

Each tool has typed input, a description and MCP annotations identifying reads, changes, destructive actions and external access. The protocol advertises six JSON resources: `flow://settings`, `flow://models`, `flow://dictionary`, `flow://shortcuts`, `flow://apps`, and `flow://diagnostics`. The `flow_setup` and `flow_personalize` prompts guide assisted setup and personalization.

`flow_configure` accepts only documented settings, merges partial style changes, and rejects secret fields and tutorial-completion flags. API speech uses a dedicated tool that requires `consent=true`; that represents the user's explicit agreement to audio uploads, provider policy and possible fees. Keys are saved through Flow's existing credential storage and never returned by reads. Use a client's private credential entry mechanism for secret tool arguments; entering a key as ordinary chat text can leave it in that client's conversation history.

Recording and practice tools capture the real microphone only when called. A session heartbeat keeps their lease alive; disconnecting cancels an active recording belonging to that connection. MCP recording saves its transcript in Recent; it does not paste into the assistant's window. Retrieve it with `flow_get_history`. The usual keyboard shortcut still pastes into your focused app. `flow_transcribe_file` accepts a specific local audio file up to 50 MB / 15 minutes, follows the selected engine and API consent, and applies vocabulary, cleanup, style and spoken shortcuts. It neither pastes nor saves history.

## Add tools without changing the UI

Create a local Python file with `register(server, service)`, then add `--plugin` and its absolute path to the MCP launch arguments. Multiple `--plugin` arguments are supported. See [the working extension example](../examples/mcp_extension.py).

```python
from mcp.types import ToolAnnotations

def register(server, service):
    @server.tool(annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, openWorldHint=False))
    def flow_find_word(query: str) -> list[dict]:
        return [term for term in service.api.memory()["terms"]
                if query.casefold() in term["text"].casefold()]
```

`service.api` is the shared app API; `service.settings()` returns the sanitized configuration. Call `service.require_write()` before changing anything, and use `service.configure()` for settings. Plugins can register standard MCP tools, resources and prompts. They run as ordinary Python code with your user account's permissions, so load only extensions you trust. Read-only mode refuses plugins. No remote extensions are downloaded or auto-loaded. For third-party services, you can also connect their MCP servers alongside Flow in your assistant and let the assistant coordinate them.

The default server exposes no listening port and has no remote HTTP mode. Connected clients can read personal history and invoke enabled tools, so use trusted clients and their approval controls. User text from history, dictionary and transcripts is data, not instructions.

Reconnect your MCP client after updating Flow so it launches the new executable. If Windows reports that the MCP companion is in use during installation, disconnect it in your client, then retry the update.

## Verify a connection

```bash
python tools/check_mcp.py
python tools/check_mcp.py --command /path/to/FlowMCP.exe --args '[]'
python tools/check_mcp.py --command /path/to/Flow-x86_64.AppImage --args '["--appimage-extract-and-run", "--mcp"]'
```

The check launches a real stdio client/server session with a temporary profile, exercises configuration and vocabulary, reads resources and prompts, checks credential redaction, and verifies read-only enforcement. It never captures audio, downloads a model or makes a paid API call. CI runs it through the unit suite and checks packaged entry points during release builds.

Speech CI also runs `python tools/check_mcp_speech.py --model small` after caching the model. That check transcribes the bundled tutorial and business/GitHub audio through the real MCP tool and enforces the same word-error thresholds as the app's speech health check. It uses a temporary profile and makes no microphone recordings or API uploads.
