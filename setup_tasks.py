"""Download optional on-device models and GPU libraries. API speech is configured separately.

  speech model   Whisper from Hugging Face into %APPDATA%\\Flow\\models (reuses an existing HF cache)
  GPU pack       NVIDIA cuBLAS/cuDNN libraries from PyPI wheels, only when an NVIDIA GPU is present
  cleanup model  qwen3:1.7b through a locally installed Ollama (optional)
"""
import ctypes
import getpass
import io
import json
import os
import shutil
import tempfile
import threading
import zipfile
from pathlib import Path

import paths

MODEL_REPOS = {"large-v3": "Systran/faster-whisper-large-v3", "small": "Systran/faster-whisper-small",
               "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo"}
MODEL_SIZE_GB = {"large-v3": 3.1, "small": 0.5, "large-v3-turbo": 1.6}
CUDA_WHEELS = [("nvidia-cublas-cu12", "12.9.2.10"), ("nvidia-cudnn-cu12", "9.26.0.51"), ("nvidia-cuda-nvrtc-cu12", "12.9.86")]
OLLAMA = "http://127.0.0.1:11434"
LLM = "qwen3:1.7b"

state = {"task": None, "label": "", "done": 0, "total": 0, "error": None, "finished": []}
_lock = threading.Lock()


# ------------------------------------------------------------ detection

from system import nvidia_gpu, cuda_dirs, cuda_ready

def find_model(name):
    """Local path of a Whisper model if it's already on this PC."""
    local = paths.MODELS / name
    if all((local / filename).is_file() for filename in ("model.bin", "config.json", "tokenizer.json")):
        return str(local)
    # an existing Hugging Face cache (e.g. from another Whisper app): look for the files directly, since
    # newer huggingface_hub rejects snapshots missing README/.gitattributes even though the model is complete
    try:
        from huggingface_hub.constants import HF_HUB_CACHE
        repo_dir = Path(HF_HUB_CACHE) / ("models--" + MODEL_REPOS[name].replace("/", "--")) / "snapshots"
        for snap in sorted(repo_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
            if all((snap / filename).is_file() for filename in ("model.bin", "config.json", "tokenizer.json")):
                return str(snap)
    except Exception:
        pass
    return None


def ollama_status():
    import requests
    try:
        tags = requests.get(f"{OLLAMA}/api/tags", timeout=1.5).json()
    except Exception:
        return {"running": False, "model": False}
    return {"running": True, "model": any(m["name"].startswith(LLM) for m in tags.get("models", []))}


def guess_name():
    import vault
    from system import display_name
    return vault.find_name(vault.vault_paths()) or display_name()

def recommended_model(gpu):
    return "large-v3" if gpu and gpu[1] >= 4 else "small"


def system_info():
    import vault
    gpu = nvidia_gpu()
    s = paths.load_settings()
    model = s.get("model") or recommended_model(gpu)
    from system import IS_WIN
    return {"platform": "windows" if IS_WIN else "linux", "recommended_model": recommended_model(gpu),
            "models": [{"id": k, "gb": v, "ready": bool(find_model(k))} for k, v in MODEL_SIZE_GB.items()],
            "gpu": gpu, "cuda": cuda_ready() if gpu else None, "model": model, "model_gb": MODEL_SIZE_GB.get(model),
            "model_ready": bool(find_model(model)), "ollama": ollama_status(),
            "vaults": [str(p) for p in vault.vault_paths()], "name": s.get("name") or guess_name()}


# ------------------------------------------------------------ tasks

def _set(**kw):
    with _lock:
        state.update(kw)


def run(task, *args):
    fn = {"model": _download_model, "cuda": _download_cuda, "llm": _pull_llm}.get(task)
    if not fn or (task == "model" and (not args or args[0] not in MODEL_REPOS)):
        raise ValueError("Choose a supported setup task and model.")
    with _lock:
        if state["task"]:
            return False
        state.update(task=task, error=None, done=0, total=0, label="Starting…")

    def go():
        try:
            fn(*args)
            with _lock:
                state["finished"].append(task)
        except Exception as e:
            _set(error=f"{type(e).__name__}: {e}")
        finally:
            _set(task=None)
    threading.Thread(target=go, daemon=True).start()
    return True


def _download_model(name):
    import requests
    from huggingface_hub import hf_hub_url
    repo = MODEL_REPOS[name]
    # The tray sets HF_HUB_OFFLINE for inference. Setup must still download the user's chosen model.
    meta = requests.get(f"https://huggingface.co/api/models/{repo}/tree/main", timeout=30)
    meta.raise_for_status()
    allowed = {"config.json", "model.bin", "tokenizer.json", "vocabulary.txt", "vocabulary.json", "preprocessor_config.json"}
    files = [f for f in meta.json() if f.get("size") and f.get("path") in allowed and f.get("type") == "file"]
    if not {"model.bin", "config.json", "tokenizer.json"}.issubset({f["path"] for f in files}):
        raise RuntimeError("The speech model repository is missing required files. Please try again later.")
    total = sum(f["size"] for f in files)
    _set(label=f"Downloading the {name} speech model", total=total)
    out = paths.MODELS / name
    out.mkdir(parents=True, exist_ok=True)
    base = 0
    for f in files:
        # stream so the UI gets real progress
        with requests.get(hf_hub_url(repo, f["path"]), stream=True, timeout=30) as r:
            r.raise_for_status()
            tmp = out / (f["path"] + ".part")
            with open(tmp, "wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    fh.write(chunk)
                    base += len(chunk)
                    _set(done=base)
            tmp.replace(out / f["path"])


def _download_cuda():
    import requests
    wheels = []
    for pkg, ver in CUDA_WHEELS:
        meta = requests.get(f"https://pypi.org/pypi/{pkg}/{ver}/json", timeout=20).json()
        from system import IS_WIN
        w = next(u for u in meta["urls"] if (u["filename"].endswith("win_amd64.whl") if IS_WIN
                 else "manylinux" in u["filename"] and u["filename"].endswith("x86_64.whl")))
        wheels.append(w)
    total = sum(w["size"] for w in wheels)
    _set(label="Downloading GPU acceleration (NVIDIA libraries)", total=total)
    paths.CUDA.mkdir(parents=True, exist_ok=True)
    done = 0
    for w in wheels:
        with tempfile.TemporaryFile() as tmp:
            with requests.get(w["url"], stream=True, timeout=30) as r:
                r.raise_for_status()
                for chunk in r.iter_content(1 << 20):
                    tmp.write(chunk)
                    done += len(chunk)
                    _set(done=done)
            tmp.seek(0)
            with zipfile.ZipFile(tmp) as z:
                for info in z.infolist():
                    if ((info.filename.lower().endswith(".dll") and "/bin/" in info.filename) if IS_WIN
                        else "/lib/" in info.filename and ".so" in Path(info.filename).name):
                        with z.open(info) as src, open(paths.CUDA / Path(info.filename).name, "wb") as dst:
                            shutil.copyfileobj(src, dst)


def _pull_llm():
    import requests
    _set(label="Downloading the smart cleanup model", total=0)
    with requests.post(f"{OLLAMA}/api/pull", json={"model": LLM, "stream": True}, stream=True, timeout=30) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            j = json.loads(line)
            if j.get("error"):
                raise RuntimeError(j["error"])
            if j.get("total"):
                _set(total=j["total"], done=j.get("completed", 0))
