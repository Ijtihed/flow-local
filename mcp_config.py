"""Portable MCP launch recipes, without importing the protocol or speech runtime."""
import os
import sys
from pathlib import Path

import paths


def connection_config(read_only=False):
    if paths.FROZEN:
        command = str(Path(sys.executable).with_name("FlowMCP.exe")) if sys.platform == "win32" else os.environ.get("APPIMAGE", sys.executable)
        args = [] if sys.platform == "win32" else ["--mcp"]
    else:
        command = str(Path(sys.executable).with_name("python.exe")) if sys.platform == "win32" else sys.executable
        args = [str(paths.APP / "main.py"), "--mcp"]
    if read_only:
        args.append("--read-only")
    return {"mcpServers": {"flow": {"command": command, "args": args}}}


def codex_config(read_only=False):
    import json
    server = connection_config(read_only)["mcpServers"]["flow"]
    return "[mcp_servers.flow]\ncommand = " + json.dumps(server["command"]) + "\nargs = " + json.dumps(server["args"]) + "\n"
