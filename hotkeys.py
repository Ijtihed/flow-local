"""Push-to-talk: hold the shortcut to talk, release to paste. Picks the Windows or Linux implementation."""
from system import IS_WIN, paste as send_ctrl_v

if IS_WIN:
    from hotkeys_win import Hotkeys  # noqa: F401
else:
    from hotkeys_linux import Hotkeys  # noqa: F401
