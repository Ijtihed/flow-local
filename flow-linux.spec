"""Build the Linux payload with Python, Tcl/Tk, audio, speech and X11 libraries."""
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata
from pathlib import Path

datas = [("ui.html", "."), ("assets", "assets"), ("LICENSE", "."), ("build/THIRD_PARTY_NOTICES.txt", ".")]
for package in ("faster_whisper", "wordfreq"):
    datas += collect_data_files(package)
datas += collect_data_files("mcp")
datas += collect_data_files("mcp_types") + copy_metadata("mcp", recursive=True)
binaries = collect_dynamic_libs("ctranslate2") + collect_dynamic_libs("onnxruntime")
binaries += [("/usr/lib/x86_64-linux-gnu/libportaudio.so.2", ".")]
hidden = ["pystray._xorg", "pynput.keyboard._xorg", "evdev", "Xlib.ext.shape", "ui_linux",
          "PIL._tkinter_finder", "PIL._imagingtk"]
hidden += collect_submodules("Xlib")
a = Analysis(["main.py"], pathex=["."], binaries=binaries, datas=datas, hiddenimports=hidden,
             excludes=["webview", "uiautomation", "comtypes", "clr", "nvidia", "torch", "tensorflow",
                       "matplotlib", "IPython", "pytest", "PyInstaller"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Flow", console=True, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="Flow", upx=False)
