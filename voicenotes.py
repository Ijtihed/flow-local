"""Every dictation, filed into Obsidian: one note per day, timestamped and labeled with the app."""
import re
from datetime import datetime
from pathlib import Path

INDEX = """---
title: Voice Notes
type: index
updated: {date}
tags:
  - voice
---

# Voice Notes

Everything dictated with Flow, one note per day. Written on this PC only; this folder is gitignored so it never leaves the machine.

```dataview
LIST FROM "{folder}" WHERE type = "voice-notes" SORT file.name DESC
```
"""


def default_folder(vault: Path):
    """Follow the vault's numbering if it has one ("10 Systems" -> "11 Voice Notes")."""
    nums = [int(m.group(1)) for d in vault.iterdir() if d.is_dir() and (m := re.match(r"(\d{2}) ", d.name))
            and int(m.group(1)) < 90]
    return vault / (f"{max(nums) + 1:02d} Voice Notes" if nums else "Voice Notes")


def setup(folder: Path, vault: Path = None):
    folder.mkdir(parents=True, exist_ok=True)
    idx = folder / "Voice Notes.md"
    if not idx.exists():
        rel = folder.relative_to(vault).as_posix() if vault and folder.is_relative_to(vault) else folder.name
        idx.write_text(INDEX.format(date=datetime.now().strftime("%Y-%m-%d"), folder=rel), "utf-8")
    if vault and (vault / ".git").exists():
        gi = vault / ".gitignore"
        rel = folder.relative_to(vault).as_posix() + "/"
        lines = gi.read_text("utf-8").splitlines() if gi.exists() else []
        if rel not in lines:
            gi.write_text("\n".join(lines + ["", "# Flow voice notes: dictations stay on this PC", rel]).lstrip("\n") + "\n", "utf-8")


def save(text, app_label, settings):
    vn = settings.get("voice_notes") or {}
    if not vn.get("enabled") or not vn.get("folder"):
        return
    folder = Path(vn["folder"])
    folder.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    day = folder / f"{now:%Y-%m-%d}.md"
    if not day.exists():
        day.write_text(f"---\ntitle: Voice notes {now:%Y-%m-%d}\ntype: voice-notes\nupdated: {now:%Y-%m-%d}\n---\n\n"
                       f"# {now:%A %d %B %Y}\n\n", "utf-8")
    body = text.strip().replace("\n", "\n  ")
    where = f" · {app_label}" if app_label else ""
    with day.open("a", encoding="utf-8") as f:
        f.write(f"- **{now:%H:%M}**{where} · {body}\n")
