"""Find your personal vocabulary in your Obsidian vaults: names, places, projects, jargon.

Reads markdown only, on this PC. Skips anything that looks like credentials or finances.
A word qualifies when it's rare in your languages (so Whisper wouldn't know it) and you use it
repeatedly, mostly capitalized for names. Multi-word names ("Ada Lovelace") are kept together.
"""
import json
import math
import os
import re
from collections import Counter
from pathlib import Path

from memory import WORD_RE

SKIP_DIRS = {".obsidian", ".trash", ".git", ".claude", "node_modules", "Images", "attachments", "assets"}
SKIP_FILE = re.compile(r"login|password|passwd|secret|token|credential|api.?key|spending|bank|iban|ssn|passport", re.I)
SECRETISH = re.compile(r"\b(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{20,}\b")


def vault_paths():
    cfg = Path(os.environ.get("APPDATA", "")) / "obsidian" / "obsidian.json"
    try:
        vaults = json.loads(cfg.read_text("utf-8")).get("vaults", {})
        return [Path(v["path"]) for v in vaults.values() if Path(v["path"]).exists()]
    except Exception:
        return []


def _notes(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for f in filenames:
            if f.endswith(".md") and not SKIP_FILE.search(f) and not SKIP_FILE.search(dirpath):
                yield Path(dirpath) / f


def _clean(text):
    text = re.sub(r"\A---.*?\n---\n", "", text, flags=re.S)          # frontmatter
    text = re.sub(r"```.*?```", " ", text, flags=re.S)                  # code
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\[\[([^\]|]+)(\|[^\]]+)?\]\]", r"\1", text)         # [[link|alias]] -> link
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return SECRETISH.sub(" ", text)


def find_name(roots):
    """Your name, if a note has a 'Full legal name' / 'Name' row."""
    pat = re.compile(r"(?:full legal name|full name)\s*\|\s*\**([^|*\n]+?)\**\s*\|", re.I)
    for root in roots:
        for p in _notes(root):
            try:
                m = pat.search(p.read_text("utf-8", errors="ignore"))
            except OSError:
                continue
            if m:
                return m.group(1).strip()
    return None


def scan(memory, roots=None, limit=700):
    roots = roots or vault_paths()
    caps, lower, bigrams = Counter(), Counter(), Counter()
    files = 0
    for root in roots:
        for p in _notes(root):
            try:
                text = _clean(p.read_text("utf-8", errors="ignore"))
            except OSError:
                continue
            files += 1
            for line in text.splitlines():
                prev, prev_cap, prev_end = None, None, 0
                for m in WORD_RE.finditer(line):
                    w, gap = re.sub(r"['’]s$", "", m.group()), line[prev_end:m.start()]
                    if re.search(r"[a-z][A-Z]$", w):      # random IDs like "UlkL"
                        prev, prev_cap, prev_end = w, None, m.end()
                        continue
                    sentence_start = prev is None or re.search(r"[.!?:#>|*\-]\s*$", gap)
                    cap = w[0].isupper()
                    if len(w) >= 3:
                        if cap and not sentence_start:
                            caps[w] += 1
                        elif not cap:
                            lower[w] += 1
                    if cap and prev_cap and gap.isspace():
                        bigrams[f"{prev_cap} {w}"] += 1
                    prev, prev_cap, prev_end = w, (w if cap else None), m.end()

    scored = {}
    for w, c in caps.items():
        total = c + lower[w.lower()]
        if c < 2 or c / total < 0.7:
            continue
        # a name counts if it's rare in ANY of your languages: "Aalto" is everyday Finnish, but English
        # Whisper still mangles it into "Alta"
        z = memory.zipf(w, strict=False)
        if z < 3.4 and memory.zipf(w) < 4.9:
            scored[w] = math.log2(1 + c) * (4.2 - z)
    from rapidfuzz import fuzz, process
    from wordfreq import top_n_list
    common = [x for l in ("en", "fi", "fr") if l in memory.languages for x in top_n_list(l, 30000)]
    for w, c in caps.items():             # people you mention constantly, even with common first names
        total = c + lower[w.lower()]
        if c >= 15 and c / total >= 0.9 and memory.zipf(w) < 4.6 and w not in scored:
            scored[w] = math.log2(1 + c) * 1.6
    for w, c in lower.items():            # lowercase jargon you use a lot, but not typos of common words
        if "_" in w or re.search(r"(.)\1\1", w):
            continue
        if c >= 4 and memory.zipf(w) < 1.8 and len(w) >= 5 and not process.extractOne(w, common, scorer=fuzz.ratio, score_cutoff=86):
            scored.setdefault(w, math.log2(1 + c) * (4.2 - memory.zipf(w)) * 0.7)
    for bg, c in bigrams.items():
        zs = [memory.zipf(x) for x in bg.split()]
        if c >= 2 and max(zs) < 4.5 and min(zs) < 3.0:   # "Ada Lovelace" yes, "Called Ada" no
            scored[bg] = math.log2(1 + c) * 3.5

    top = sorted(scored.items(), key=lambda kv: -kv[1])[:limit]
    for term, s in top:
        memory.add_term(term, "notes", seen=int(s * 10))
    import techvocab
    techvocab.seed(memory)
    name = find_name(roots)
    if name:
        memory.add_term(name, "you")
        for part in name.split():
            if memory.is_rare(part):
                memory.add_term(part, "you")
    import time
    memory.meta("vault_scanned", json.dumps({"at": time.time(), "files": files, "terms": len(top), "name": name,
                                             "vaults": [r.name for r in roots]}))
    return {"files": files, "terms": len(top), "name": name}
