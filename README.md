# Flow

Free voice dictation for Windows and Linux. Hold a key, talk, let go, and your words are typed wherever your cursor is. Choose on-device speech or an optional transcription API. Your vocabulary and history stay on your device.

## Download

[Download FlowSetup.exe](https://github.com/Ijtihed/flow-local/releases/latest/download/FlowSetup.exe) (Windows 10 and 11, no admin needed)

[Download Flow-x86_64.AppImage](https://github.com/Ijtihed/flow-local/releases/latest/download/Flow-x86_64.AppImage) (Linux x86_64, Ubuntu 22.04 or newer / compatible distributions)

The repository and downloads are private until the owner chooses to publish them. Sign into GitHub with an account that has repository access to download.

Setup detects your OS and offers a speech engine and model choice. Local options are Whisper small (0.5 GB), large-v3-turbo (1.6 GB) and large-v3 (3.1 GB). Flow recommends a model for your hardware; GPU acceleration and cleanup are optional downloads. On-device dictation works offline after setup. The first-use tutorial asks you to record a short sentence with your selected speech engine. It shows what Flow heard and accepts the step only when the phrase matches. Retry or change speech options if needed. Practice recordings stop after 15 seconds and are not saved in history. Replay the practice in Settings.

### Optional API speech

Choose API in setup or Settings, select a transcription model, enter your API base URL and key, and accept the data notice. The default is OpenAI; services implementing the same `POST /audio/transcriptions` multipart contract are also supported. Choose Custom model for another provider's model ID. HTTPS is required except for a self-hosted service on localhost.

Each dictation uploads the microphone recording to the selected provider. An internet connection is required, fees may apply, and the provider's data policy applies. Flow sends the recording, model and a single-language hint when applicable; it does not send history, dictionary, app titles or notes. Read [OpenAI's data controls](https://developers.openai.com/api/docs/guides/your-data), or your own provider's policy. Nothing is uploaded until you explicitly enable API speech and dictate.

Keys are kept outside settings and history: Windows uses account-bound DPAPI encryption; Linux uses a user-readable-only file (mode 0600). Forget API key removes it and switches back to local speech. Switching models takes effect after the current dictation; no restart is needed. Re-selecting an engine also retries a failed model load.

API request formatting, consent, key storage, timeouts and quota errors are tested against an isolated local server. No real paid API account was used for release validation.

### Linux setup

Download the AppImage, then run:

```bash
chmod +x Flow-x86_64.AppImage
./Flow-x86_64.AppImage
```

If your distribution does not support mounting AppImages, run `./Flow-x86_64.AppImage --appimage-extract-and-run` instead.

Use `Ctrl` + `Super` (the Windows/logo key), or choose F8 / Right Ctrl in settings. The settings window opens in your browser at an authenticated loopback address on your own computer. Flow adds launchers to your application menu after its first start.

X11 supports global shortcuts, clipboard pasting and active-app detection. It uses bundled clipboard/paste tools, with pynput as a shortcut fallback. The tray needs a desktop with a system tray (GNOME may require an AppIndicator extension). Open Flow Settings from the application menu if your desktop hides the tray.

Wayland support is experimental. Global shortcuts require read access to your keyboard's `/dev/input/event*` devices (for example, distribution-managed input group access). Flow never grants these permissions itself. `Space`, `Esc`, F8 and Caps Lock also reach the focused app on Linux, so Right Ctrl is often the least disruptive shortcut. Wayland clipboard support needs `wl-clipboard`; automatic pasting needs writable `/dev/uinput` or a compositor that supports `wtype`. Without automatic pasting, Flow leaves the text on the clipboard and asks you to press Ctrl+V. Active-app style detection is unavailable for native Wayland windows.

On Linux, teach corrections by editing dictations in Flow's History. Reading corrections automatically from other apps remains Windows-only. Speech recognition, dictionary learning, local cleanup and voice notes are shared across both platforms.

The AppImage was built and smoke-tested in Ubuntu 22.04 under WSL, including the packaged speech libraries, audio device detection and overlay. Source checks also exercised X11 keyboard events, clipboard pasting and speech transcription on the CPU. A physical Linux keyboard and the native Wayland path were not available for validation. Other distributions are not yet certified.

## Use it

- Hold `Ctrl` + `Win`, talk, let go. The text is pasted where you're typing.
- Double tap `Ctrl` + `Win` (or tap `Space` while holding) for hands free. Press again to finish.
- `Esc` cancels.
- Click the tray icon to start or stop hands-free dictation. Use its Open Flow menu item for history, dictionary and settings.
- The floating pill shows Recording, live microphone levels and elapsed time. Thinking and Polishing animate while Flow processes your words; after 12 seconds it says Still working. The Home screen's Record button saves a thought to Recent, where you can copy or edit it.

## What it does

- **Your engine choice.** Run Whisper locally, or use an API with your own key. Cleanup stays local.
- **Learns you.** Names, jargon and project names get spelled right. It reads your Obsidian vault (optional) and learns from every word you fix.
- **65 familiar app logos.** Writing and notes, email, chats, AI tools, code editors and browsers share one bundled app catalog. Desktop process names and branded browser-tab titles identify the app for history and writing style. The website automatically cycles through all 65 previews; use the app picker to jump directly to one. These are illustrative previews, not endorsements or provider integrations. Dictation works in other apps too, wherever the OS can paste text.
- **Matches the app.** Casual in Discord, formal in email, your own style everywhere. Texting shortcuts like idk and tbh in chats if you want them.
- **Cleans up.** Removes ums and handles "at 2, actually 3". It can only delete words, never invent them.
- **Many languages.** Switch between languages mid conversation.
- **Voice notes.** Optionally saves every dictation to a daily note in Obsidian.
- **Spoken shortcuts.** Save “my email” → your full email address, then say that phrase while dictating.
- **A home screen that changes.** Greetings follow your local time, recent use and selected mood. Mood is your choice; Flow does not infer emotions from your recordings.

An NVIDIA GPU accelerates local speech. Flow also runs on the CPU and falls back to it if GPU inference cannot start. Smart cleanup needs [Ollama](https://ollama.com) installed; Flow downloads the model it uses for you.

## Build from source

```powershell
git clone https://github.com/Ijtihed/flow-local
cd flow-local
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

To build the installer yourself: install [Inno Setup](https://jrsoftware.org/isinfo.php), then run `.\build.ps1`.

On Linux:

```bash
sudo apt install python3-venv python3-tk libportaudio2 libasound2-plugins xclip xdotool
python3 -m venv .venv-linux
.venv-linux/bin/pip install -r requirements.txt
.venv-linux/bin/python main.py
bash build-linux.sh
```

`build-linux.sh` builds `installer/Flow-x86_64.AppImage` with PyInstaller and the official [AppImage packaging tools](https://docs.appimage.org/packaging-guide/manual.html). Speech models and NVIDIA libraries are downloaded during setup. For source installs, GPU libraries can also be installed with `pip install -r requirements-gpu.txt`.

Run `python -m unittest discover -s tests -v` for platform and settings-server checks. Run `Flow.exe --self-test` or `./Flow-x86_64.AppImage --self-test` on a desktop to verify the bundled speech runtime, audio devices, assets and overlay without modifying your personal data.

`--self-test-headless` checks the packaged runtime and assets without opening a window or inspecting audio/GPU devices. Add `--test-report report.json` for a saved result (useful with the Windows GUI executable).

For isolated interface checks, run `npm install` and `npm test` inside `tests/`. This uses a simulated DOM and clock, without controlling a browser or accessing the desktop. It covers setup on both OSes, the first-use tutorial, model/API selection, greetings, spoken shortcuts and the website's automatic app cycle.

## Use the engine in your own code

The speech engine and the personal memory are plain Python, with no UI needed:

```python
from pathlib import Path
from faster_whisper import decode_audio
from engine import Engine
from memory import Memory
import setup_tasks

memory = Memory(Path("memory.db"), languages=["en"])
memory.add_term("Kubernetes", "you")

engine = Engine(memory)
engine.load(setup_tasks.find_model("large-v3"))
text, lang = engine.transcribe(decode_audio("meeting.wav", sampling_rate=16000), {"languages": ["en"]})
```

See [examples/transcribe_file.py](examples/transcribe_file.py) for a complete script.

## How it stays accurate

1. Whisper listens to your audio once with no hints.
2. Flow looks for words in your dictionary that sound like what it heard, and listens again with those words in mind. Only those words change, so the rest of your sentence stays exactly as you said it.
3. Fixes you have taught it are applied.
4. A small local model removes filler words. Its output is thrown away if it adds a word you did not say.

## Files

| File | What it is |
|---|---|
| `flow.py` | Tray app, shortcut and overlay |
| `engine.py` | Speech to text, cleanup, style per app |
| `memory.py` | Your personal vocabulary (SQLite) |
| `hotkeys.py` | Push to talk keyboard hook |
| `vault.py` | Reads your Obsidian vault for names and terms |
| `learn.py` | Notices when you fix a word |
| `ui.html`, `ui.py` | The settings window |

Your data lives in `%APPDATA%\Flow` on Windows and `$XDG_DATA_HOME/flow` (normally `~/.local/share/flow`) on Linux. Set `FLOW_DATA` to override it.

## License

MIT

After editing `assets/apps.json`, run `python tools/sync_apps.py` to sync the website catalog and logos. Publisher asset sources are recorded in `assets/logos/SOURCES.txt`.
