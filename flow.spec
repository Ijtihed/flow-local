# PyInstaller build for Flow.  Build:  .venv\Scripts\pyinstaller flow.spec --noconfirm
# Output: dist\Flow\Flow.exe (one folder). The speech model and NVIDIA libraries are NOT bundled;
# first-run setup downloads them, so the installer stays small and CPU-only machines don't carry 1.4 GB of CUDA.
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

datas = [("ui.html", "."), ("assets", "assets")]
for pkg in ("faster_whisper", "wordfreq", "uiautomation", "webview"):
    datas += collect_data_files(pkg)
binaries = collect_dynamic_libs("ctranslate2") + collect_dynamic_libs("onnxruntime") + collect_dynamic_libs("uiautomation")
hidden = ["pystray._win32", "webview.platforms.winforms", "clr", "comtypes.stream", "sounddevice", "_sounddevice_data"]
hidden += collect_submodules("uiautomation")

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    excludes=["nvidia", "torch", "tensorflow", "matplotlib", "IPython", "pytest", "PyInstaller"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Flow",
    icon="assets/flow.ico",
    console=False,
    version="version.txt",
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Flow", upx=False)
