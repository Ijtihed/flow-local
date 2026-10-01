# Platforms

## Windows

Windows 10/11 x64, per-user installation, no administrator rights required. The installer includes the runtime and console MCP companion. Choose a speech model during setup; models, optional GPU libraries and optional cleanup are separate downloads. The tray menu opens Settings. Hold Ctrl + Win, or select another shortcut.

## Linux

The x86_64 AppImage targets Ubuntu 22.04 or newer and compatible distributions:

```bash
chmod +x Flow-x86_64.AppImage
./Flow-x86_64.AppImage
```

If AppImage mounting is unavailable, use `./Flow-x86_64.AppImage --appimage-extract-and-run`.

The settings window opens at an authenticated loopback address in your browser. Flow adds application-menu launchers on first start. A desktop system tray is needed for the tray icon; GNOME may need an AppIndicator extension. Open Flow Settings from the application menu if your tray is hidden.

X11 supports global shortcuts, clipboard pasting and active-app detection. Clipboard and paste utilities are bundled; pynput is the shortcut fallback. Ctrl + Super, F8 and Right Ctrl are available.

### Wayland

Wayland support is experimental. Shortcuts need read access to your keyboard's `/dev/input/event*` devices, managed through your distribution. Flow does not grant permissions itself. Space, Esc, F8 and Caps Lock also reach the focused app on Linux; Right Ctrl is often less disruptive.

Clipboard support requires `wl-clipboard`; automatic pasting needs writable `/dev/uinput` or compositor support for `wtype`. Otherwise Flow leaves the result on the clipboard and asks you to press Ctrl+V. Active-app style detection is unavailable for native Wayland windows. Teach corrections by editing Recent in Flow; reading corrections from other apps is Windows-only.

### Source install

```bash
sudo apt install python3-venv python3-tk libportaudio2 libasound2-plugins xclip xdotool
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

### Validation limits

Packaged Linux runtime, assets, speech inference and MCP have been exercised under Ubuntu 22.04 in WSL. Source tests cover X11 key events, clipboard operations and CPU speech. A physical Linux keyboard and native Wayland desktop have not been validated. Other distributions are not certified.
