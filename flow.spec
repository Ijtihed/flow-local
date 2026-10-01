# PyInstaller build for Flow.  Build:  .venv\Scripts\pyinstaller flow.spec --noconfirm
# Output: dist\Flow\Flow.exe (one folder). The speech model and NVIDIA libraries are NOT bundled;
# first-run setup downloads them, so the installer stays small and CPU-only machines don't carry 1.4 GB of CUDA.
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata

datas = [("ui.html", "."), ("assets", "assets")]
for pkg in ("faster_whisper", "wordfreq", "uiautomation", "webview"):
    datas += collect_data_files(pkg)
datas += collect_data_files("mcp")
datas += collect_data_files("mcp_types") + copy_metadata("mcp", recursive=True)
binaries = collect_dynamic_libs("ctranslate2") + collect_dynamic_libs("onnxruntime") + collect_dynamic_libs("uiautomation")
hidden = ["pystray._win32", "webview.platforms.winforms", "clr", "comtypes.stream", "sounddevice", "_sounddevice_data"]
hidden += collect_submodules("uiautomation")

a = Analysis(
    ["main.py", "mcp_entry.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    excludes=["nvidia", "torch", "tensorflow", "matplotlib", "IPython", "pytest", "PyInstaller"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, [script for script in a.scripts if script[0] != "mcp_entry"], [],
    exclude_binaries=True,
    name="Flow",
    icon="assets/flow.ico",
    console=False,
    version="version.txt",
    upx=False,
)
# Windows GUI executables have no stdio. Ship a console companion for MCP pipes.
mcp_exe = EXE(pyz, [script for script in a.scripts if script[0] != "main"], [], exclude_binaries=True,
              name="FlowMCP", icon="assets/flow.ico", console=True, version="version.txt", upx=False)
coll = COLLECT(exe, mcp_exe, a.binaries, a.datas, name="Flow", upx=False)
