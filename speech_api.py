"""Optional OpenAI-compatible file transcription. No background audio uploads."""
import ctypes
import io
import os
import re
import wave
from urllib.parse import urlsplit

import numpy as np
import requests

import paths


class SpeechError(RuntimeError):
    pass


def validated_base(value):
    value = str(value).strip().rstrip("/")
    url = urlsplit(value)
    local = url.hostname in ("localhost", "127.0.0.1", "::1")
    if (not url.hostname or url.username or url.password or url.query or url.fragment
            or not (url.scheme == "https" or (local and url.scheme == "http"))):
        raise ValueError("Use an HTTPS API base URL, or HTTP on localhost for a self-hosted engine.")
    return value


def validated_model(value):
    value = str(value).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", value):
        raise ValueError("Enter a valid transcription model ID.")
    return value


def _dpapi(data, decrypt=False):
    from ctypes import wintypes as wt
    class Blob(ctypes.Structure):
        _fields_ = [("size", wt.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    buf = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    out = Blob()
    fn = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wt.BOOL
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(out)):
        raise SpeechError("Windows could not unlock the saved API key. Please enter it again.")
    try:
        return ctypes.string_at(out.data, out.size)
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(out.data)


def save_key(key):
    key = str(key).strip()
    if not key or len(key) > 8192 or any(c.isspace() for c in key):
        raise ValueError("Enter an API key without spaces.")
    paths.DATA.mkdir(parents=True, exist_ok=True)
    data = key.encode()
    if os.name == "nt":
        data = _dpapi(data)
    target = paths.DATA / "speech-key"
    tmp = target.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    if os.name != "nt":
        tmp.chmod(0o600)
    tmp.replace(target)


def get_key():
    target = paths.DATA / "speech-key"
    if not target.exists():
        return ""
    data = target.read_bytes()
    if os.name == "nt":
        data = _dpapi(data, decrypt=True)
    return data.decode()


def configured(settings):
    if settings.get("speech_provider") != "api" or not settings.get("api_consent"):
        return False
    try:
        validated_base(settings["api_base"])
        validated_model(settings["api_model"])
        return bool(get_key())
    except Exception:
        return False


def transcribe(audio, settings):
    if not configured(settings):
        raise SpeechError("Open Settings to enable API speech and accept the data notice.")
    if len(audio) > (25_000_000 - 4096) // 2:
        raise SpeechError("This recording is too long for the API. Try a shorter dictation.")
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(pcm.tobytes())
    data = {"model": validated_model(settings["api_model"]), "response_format": "json"}
    langs = settings.get("languages") or []
    if len(langs) == 1:
        data["language"] = langs[0]
    try:
        response = requests.post(validated_base(settings["api_base"]) + "/audio/transcriptions",
                                 headers={"Authorization": "Bearer " + get_key()}, data=data,
                                 files={"file": ("dictation.wav", buffer.getvalue(), "audio/wav")},
                                 timeout=(10, 90), allow_redirects=False)
    except requests.Timeout:
        raise SpeechError("Speech API timed out. Check your connection and try again.") from None
    except requests.RequestException:
        raise SpeechError("Could not reach the speech API. Check your connection and API URL.") from None
    if response.status_code in (401, 403):
        raise SpeechError("Speech API rejected the key. Check it in Settings.")
    if response.status_code == 429:
        raise SpeechError("Speech API limit reached. Check your provider's quota or billing.")
    if not 200 <= response.status_code < 300:
        raise SpeechError(f"Speech API returned HTTP {response.status_code}. Check the model and API URL.")
    try:
        text = response.json()["text"]
        if not isinstance(text, str):
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise SpeechError("Speech API returned an unexpected response. Use a compatible transcription endpoint.") from None
    # Do not send history, vocabulary or app titles. Memory repairs stay on the device.
    return text.strip(), langs[0] if len(langs) == 1 else ""
