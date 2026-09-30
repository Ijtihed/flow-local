"""Check the installed payload without opening personal settings or downloading models."""
import json
import tempfile
from pathlib import Path


def run():
    import flow
    import ui
    import setup_tasks
    import system
    import paths
    import numpy as np
    import sounddevice
    import ctranslate2
    import onnxruntime
    import faster_whisper
    from memory import Memory
    from engine import Engine
    import tkinter as tk
    from pill import Pill

    with tempfile.TemporaryDirectory() as folder:
        mem = Memory(Path(folder) / "memory.db", ["en"])
        mem.add_term("Kubernetes", "you")
        assert mem.correct("Kubernetes") == "Kubernetes"
        mem.db.close()
    root = tk.Tk()
    root.withdraw()
    pill = Pill(root)
    for state in ("listening", "transcribing", "message"):
        pill.render(state, 1, [0.5] * 20, "Ready", 1)
        pill.show()
        root.update()
    pill.hide()
    root.destroy()
    assert (paths.APP / "ui.html").is_file()
    assert (paths.APP / "assets/PlexSans-400.woff2").is_file()
    assert (paths.APP / "assets/logos/codex.png").is_file()
    print(json.dumps({"ok": True, "platform": "windows" if system.IS_WIN else "linux",
                      "gpu": system.nvidia_gpu(), "cuda_libraries": system.cuda_ready(),
                      "audio_devices": len(sounddevice.query_devices()), "overlay": "rendered",
                      "assets": "present", "speech_runtime": ctranslate2.__version__}), flush=True)
