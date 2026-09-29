"""Use Flow's engine in your own code: personalized, local transcription of an audio file.

    python examples/transcribe_file.py meeting.wav "Kubernetes" "Ada Lovelace"

The first run downloads the Whisper model (about 3 GB). After that everything is offline.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import setup_tasks                       # noqa: E402  (before engine, which switches Hugging Face to offline)

MODEL = "large-v3"                       # "small" is faster on machines without an NVIDIA GPU
if not setup_tasks.find_model(MODEL):
    print(f"Downloading {MODEL}...")
    setup_tasks._download_model(MODEL)

from faster_whisper import decode_audio  # noqa: E402
from engine import Engine                # noqa: E402
from memory import Memory                # noqa: E402

audio_path, *words = sys.argv[1:] or [None]
if not audio_path:
    sys.exit(__doc__)

memory = Memory(Path("memory.db"), languages=["en"])   # your vocabulary, stored in a local SQLite file
for w in words:
    memory.add_term(w, "you")                           # names and jargon it should always get right

engine = Engine(memory)
engine.load(setup_tasks.find_model(MODEL))

settings = {"languages": ["en"], "cleanup": False}      # cleanup=True uses Ollama + qwen3:1.7b if installed
text, lang = engine.transcribe(decode_audio(audio_path, sampling_rate=16000), settings)
print(engine.cleanup(text, settings))
