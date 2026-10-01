#!/usr/bin/env bash
# Ubuntu 22.04+ x86_64. Needs python3-venv, python3-tk, libportaudio2, xclip, xdotool.
set -euo pipefail
cd "$(dirname "$0")"
if [[ $(uname -m) != x86_64 ]]; then echo 'This build targets Linux x86_64.' >&2; exit 1; fi
VENV="${FLOW_BUILD_VENV:-.venv-linux}"
if [[ ! -x "$VENV/bin/python" ]]; then
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --upgrade pip
    "$VENV/bin/pip" install -r requirements.txt pyinstaller
fi
"$VENV/bin/python" tools/collect_licenses.py
"$VENV/bin/pyinstaller" flow-linux.spec --noconfirm --log-level WARN --distpath build/linux-dist --workpath build/linux-pyinstaller
APPDIR="$PWD/build/Flow.AppDir"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/lib" installer build/tools
cp -a build/linux-dist/Flow/. "$APPDIR/usr/bin/"
for tool in xclip xdotool; do
    cp "$(command -v "$tool")" "$APPDIR/usr/bin/"
done
cp -L /usr/lib/x86_64-linux-gnu/libxdo.so.3 "$APPDIR/usr/lib/"
cp assets/logo.png "$APPDIR/flow.png"
cat > "$APPDIR/flow.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Flow
Comment=Voice dictation
Exec=Flow
Icon=flow
Terminal=false
Categories=Utility;Accessibility;
DESKTOP
cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
FLOW_APPDIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PATH="$FLOW_APPDIR/usr/bin:$PATH"
export LD_LIBRARY_PATH="$FLOW_APPDIR/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$FLOW_APPDIR/usr/bin/Flow" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"
TOOL="${APPIMAGETOOL:-$PWD/build/tools/appimagetool-x86_64.AppImage}"
if [[ ! -x "$TOOL" ]]; then
    curl -fL --retry 3 -o "$TOOL" https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x "$TOOL"
fi
ARCH=x86_64 "$TOOL" --appimage-extract-and-run "$APPDIR" "$PWD/installer/Flow-x86_64.AppImage"
(cd installer && sha256sum Flow-x86_64.AppImage) > installer/Flow-x86_64.AppImage.sha256
echo 'Built installer/Flow-x86_64.AppImage'
