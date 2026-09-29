# Flow

A free, local replacement for Wispr Flow on Windows. Hold a key, talk, let go, and your words are typed wherever your cursor is. Nothing leaves your PC.

![Flow](docs/home.png)

## Download

[Download FlowSetup.exe](https://github.com/Ijtihed/flow-local/releases/latest/download/FlowSetup.exe) (Windows 10 and 11, no admin needed)

The first time it opens, Flow downloads the speech model once (about 3 GB). After that it works offline.

## Use it

- Hold `Ctrl` + `Win`, talk, let go. The text is pasted where you're typing.
- Double tap `Ctrl` + `Win` (or tap `Space` while holding) for hands free. Press again to finish.
- `Esc` cancels.
- Click the tray icon to open your history, dictionary and settings.

## What it does

- **Runs on your PC.** Whisper large-v3 for speech, a small local model for cleanup. No account, no cloud.
- **Learns you.** Names, jargon and project names get spelled right. It reads your Obsidian vault (optional) and learns from every word you fix.
- **Matches the app.** Casual in Discord, formal in email, your own style everywhere. Texting shortcuts like idk and tbh in chats if you want them.
- **Cleans up.** Removes ums and handles "at 2, actually 3". It can only delete words, never invent them.
- **Many languages.** Switch between languages mid conversation.
- **Voice notes.** Optionally saves every dictation to a daily note in Obsidian.

An NVIDIA GPU makes it fast (about 1 to 2 seconds per dictation). It also runs on the CPU with a smaller model. Smart cleanup needs [Ollama](https://ollama.com) installed; Flow downloads the model it uses for you.

## Build from source

```powershell
git clone https://github.com/Ijtihed/flow-local
cd flow-local
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

To build the installer yourself: install [Inno Setup](https://jrsoftware.org/isinfo.php), then run `.\build.ps1`.

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

Your data lives in `%APPDATA%\Flow`.

## License

MIT
