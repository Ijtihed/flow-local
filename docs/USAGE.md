# Using Flow

Setup asks what to call you, which languages you use, and which speech engine and model you prefer. It does not infer your preferred name from your OS account. A local model downloads before practice begins. Hold Ctrl + Win (Ctrl + Super on Linux), say the sentence, and release. The empty field fills with the actual transcript; Continue appears only when it matches. Practice stops after 15 seconds and is not saved in history. Replay it in Settings.

## Everyday dictation

- Hold your shortcut, speak, then release to stop recording and paste the result.
- Tap Space while holding for hands-free mode; press the shortcut again to finish.
- Press Esc to cancel.
- Click the tray icon to toggle hands-free recording. Its menu opens history, Dictionary and Settings.
- The floating pill shows microphone levels while recording, then Thinking or Polishing while processing. After 12 seconds, it says Still working.

Dictionary stores names, terms and confirmed corrections. Edit a mistaken dictation in Recent to teach its spelling. Spoken shortcuts expand phrases: “my email” can insert your full address. Writing styles follow the app category. Optional daily voice notes save dictations to Obsidian.

Corrections are saved in your local dictionary and reused by future dictations, including after restarting. Windows can notice edits in the same accessible text field at six and twenty seconds after a successful paste; switching fields or using a password field cancels that observation. Repeated automatic spelling repairs are confirmed after separate observations. Editing a dictation in Recent explicitly teaches the correction on both Windows and Linux, including capitalization of unfamiliar names.

## Speech engines

### Local speech

Choose Whisper small (about 0.5 GB), large-v3-turbo (1.6 GB) or large-v3 (3.1 GB). Model recommendations use available RAM and NVIDIA VRAM. Models that exceed available RAM are disabled. Models that do not fit the GPU can run on CPU if RAM allows; unknown memory is marked unverified. GPU inference failures fall back to CPU. Models and GPU libraries download during setup; local speech works offline afterward.

Optional cleanup requires a local Ollama installation. Flow can download its cleanup model. It removes filler words and rejects cleanup output that adds words. Recognition is not infallible; teach unfamiliar names and review important text.

### API speech

Choose API in setup or Settings, select a transcription model, enter the provider's base URL and your key, and accept the data notice. Services implementing the OpenAI-compatible `POST /audio/transcriptions` multipart contract are supported. Choose Custom model for another model ID. HTTPS is required except for a local self-hosted service.

Each dictation uploads its recording to the selected provider. Internet access is required, fees may apply, and that provider's data policy applies. Flow sends audio, the model ID and an optional single-language hint; it does not send history, dictionary, app titles or notes. Review [OpenAI's data controls](https://developers.openai.com/api/docs/guides/your-data) if using OpenAI, or your provider's policy.

Keys stay outside settings and history. Windows uses account-bound DPAPI encryption; Linux uses a mode-0600 credential file. Forget API key removes the credential and switches to local speech. Switching engines takes effect after the current dictation. Selecting an engine again retries a failed load.

## Downloads and updates

Download only from [Flow's GitHub releases](https://github.com/Ijtihed/flow-local/releases). Windows installers are unsigned; Windows may show SmartScreen or Unknown publisher. SHA256SUMS.txt and GitHub asset digests let you verify the downloaded bytes. Checksums establish integrity, not a trusted Windows publisher. [Optional signing setup](WINDOWS_SIGNING.md)

To verify on Windows, compare `Get-FileHash .\FlowSetup.exe -Algorithm SHA256` with the corresponding SHA256SUMS.txt entry. On Linux, download both files into one folder and run `sha256sum --ignore-missing -c SHA256SUMS.txt`.

Flow checks immediately at startup, every time you open its window, and every six hours. A newer release shows a popup with Update and Later; it waits until setup, practice and active dictation have finished. Offline checks stay quiet and retry after fifteen minutes. Checks continue with Automatic updates disabled, so the popup can still offer a manual update.

Automatic installation is enabled by default. It verifies the download digest and waits until the window is closed and sixty seconds have passed without dictation or processing. Settings, names, history, dictionaries, speech keys and models remain in the data folder. Linux keeps the previous AppImage beside the new one and requires a writable location. Reconnect your MCP client after an update.

Public downloads and updates need no GitHub account or token. GitHub access in Settings is for private repositories and release management only. Tokens are protected separately from speech keys and sent only to GitHub's API.

## Speech health

Each local engine start transcribes bundled synthetic audio, including GitHub, business and download vocabulary. Inference failures or word errors show a warning with a report you can review, copy or save. Reports contain bundled test transcripts and runtime metadata, not personal recordings, history or keys. Nothing is sent automatically. API engines use the interactive spoken practice without automatic paid test requests.

## Your files

Profiles live in `%APPDATA%\Flow` on Windows and `$XDG_DATA_HOME/flow` (normally `~/.local/share/flow`) on Linux. Set `FLOW_DATA` to use another profile. App uninstall leaves your profile and downloaded models available for reinstalling. Delete that specific profile yourself only if you intend to remove your saved data.
