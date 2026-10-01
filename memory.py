"""Flow's personal memory: the words, names and phrases that make your dictation yours.

Everything lives in data/memory.db (SQLite, this PC only).

How it's used for every dictation
  1. prompt()      core terms (your name, words you added) prime Whisper's personal pass
  2. candidates()  personal terms that *sound like* something in the first-pass text are looked up
                   with a sound-alike key ("Ishtihad" and "Ijtihed" share one), then fed to a second,
                   primed pass; the audio still has the final say
  3. correct()     learned fixes (heard -> meant), sound-alike repairs of rare words, canonical casing
  4. learn_*()     every dictation and every correction you make updates the memory

Sources, strongest first: you (added by hand) > learned (from your corrections) >
history (you keep saying it) > notes (found in your Obsidian vaults).
"""
import difflib
import math
import re
import sqlite3
import threading
import time
from pathlib import Path

from rapidfuzz import fuzz
from unidecode import unidecode
from wordfreq import zipf_frequency

WEIGHT = {"you": 3.0, "learned": 2.5, "project": 2.0, "history": 1.6, "notes": 1.0, "tech": 0.9, "slang": 0.9}
WORD_RE = re.compile(r"[^\W\d_](?:[\w'’-]*[^\W\d_])?", re.UNICODE)
RARE = 3.0          # max Zipf frequency across your languages below which a word counts as "yours"
PROMOTE_AFTER = 3   # a rare word you say this many times joins your vocabulary

_SOUND_RULES = [(r"dzh|dj|tch|sch|sh|ch|zh", "j"), (r"ph", "f"), (r"th", "t"), (r"dh", "d"), (r"kh", "h"),
                (r"gh", "g"), (r"ck|qu|q", "k"), (r"x", "ks"), (r"c(?=[eiy])", "s"), (r"c", "k"), (r"w", "v"),
                (r"z", "s"), (r"y", "i"), (r"[aeiou]+", "a"), (r"(.)\1+", r"\1")]


def sound_key(s):
    """Rough cross-language sound-alike key: consonant skeleton, vowels collapsed."""
    s = re.sub(r"[^a-z]", "", unidecode(s).lower())
    for pat, rep in _SOUND_RULES:
        s = re.sub(pat, rep, s)
    return s


def norm(s):
    return re.sub(r"[^\w]", "", s.lower())


def words(text):
    return WORD_RE.findall(text)


class Memory:
    def __init__(self, path: Path, languages=("en",)):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False, timeout=5)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS terms (text TEXT PRIMARY KEY COLLATE NOCASE, source TEXT, uses INT DEFAULT 0,
                                              seen INT DEFAULT 0, last_used REAL, created REAL, hidden INT DEFAULT 0);
            CREATE TABLE IF NOT EXISTS variants (heard TEXT COLLATE NOCASE, term TEXT COLLATE NOCASE, count INT DEFAULT 1,
                                                 confirmed INT DEFAULT 0, updated REAL, PRIMARY KEY (heard, term));
            CREATE TABLE IF NOT EXISTS words (word TEXT PRIMARY KEY COLLATE NOCASE, count INT, last_used REAL);
            CREATE TABLE IF NOT EXISTS recent (ts REAL, lang TEXT, text TEXT);
            CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
        """)
        self.db.commit()
        self.languages = list(languages) or ["en"]
        self._cache = None
        self._data_version = None

    # ------------------------------------------------------------ basics

    def set_languages(self, langs):
        self.languages = [l for l in langs if l] or ["en"]

    def zipf(self, word, strict=True):
        """Word frequency across your languages: the max (strict, "common anywhere") or the min."""
        latin = ("en", "fi", "fr", "sv", "de", "es", "it", "nl", "pt", "tr")
        script = latin if re.match(r"[A-Za-zÀ-ɏ]", word) else ("ar", "ru")
        langs = [l for l in self.languages if l in script] or (["en"] if script is latin else [])
        vals = [zipf_frequency(word, l) for l in langs] or [0.0]
        return max(vals) if strict else min(vals)

    def is_rare(self, phrase):
        return all(self.zipf(w) < RARE for w in words(phrase)) if words(phrase) else False

    def meta(self, k, v=None):
        with self.lock:
            if v is None:
                row = self.db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
                return row[0] if row else None
            self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (k, str(v)))
            self.db.commit()

    def terms(self):
        """[(text, source, weight, key)] cached until the table changes."""
        with self.lock:
            data_version = self.db.execute("PRAGMA data_version").fetchone()[0]
            if data_version != self._data_version:
                self._cache = None
                self._data_version = data_version
            if self._cache is None:
                rows = self.db.execute("SELECT text, source, uses FROM terms WHERE hidden=0").fetchall()
                self._cache = [(t, s, WEIGHT.get(s, 1.0) + min(1.0, math.log1p(u) / 3), sound_key(t)) for t, s, u in rows]
            return self._cache

    def _dirty(self):
        self._cache = None

    def add_term(self, text, source="you", seen=0, update_case=False):
        text = re.sub(r"\s+", " ", text).strip()
        if not text or len(text) > 60:
            return
        with self.lock:
            row = self.db.execute("SELECT source FROM terms WHERE text=?", (text,)).fetchone()
            if row is None:
                self.db.execute("INSERT INTO terms (text, source, seen, created) VALUES (?,?,?,?)", (text, source, seen, time.time()))
            elif WEIGHT.get(source, 0) > WEIGHT.get(row[0], 0):
                # a stronger source wins; also adopt its exact casing
                self.db.execute("UPDATE terms SET text=?, source=?, hidden=0 WHERE text=?", (text, source, text))
            elif update_case:
                self.db.execute("UPDATE terms SET text=? WHERE text=?", (text, text))
            elif source == row[0] and seen:
                self.db.execute("UPDATE terms SET seen=? WHERE text=?", (seen, text))
            self.db.commit()
            self._dirty()

    def remove_term(self, text):
        with self.lock:
            # notes terms are hidden rather than deleted so a rescan doesn't bring them back
            self.db.execute("UPDATE terms SET hidden=1 WHERE text=? AND source='notes'", (text,))
            self.db.execute("DELETE FROM terms WHERE text=? AND source!='notes'", (text,))
            self.db.execute("DELETE FROM variants WHERE term=?", (text,))
            self.db.commit()
            self._dirty()

    def add_variant(self, heard, term, confirmed=True):
        heard, term = heard.strip(), term.strip()
        if not heard or not term or norm(heard) == norm(term):
            return
        with self.lock:
            self.db.execute("""INSERT INTO variants (heard, term, count, confirmed, updated) VALUES (?,?,1,?,?)
                               ON CONFLICT(heard, term) DO UPDATE SET count=count+1, updated=excluded.updated,
                               confirmed=MAX(confirmed, excluded.confirmed)""", (heard, term, int(confirmed), time.time()))
            # auto-noticed fixes become active once seen twice
            self.db.execute("UPDATE variants SET confirmed=1 WHERE heard=? AND term=? AND count>=2", (heard, term))
            self.db.commit()

    def remove_variant(self, heard, term):
        with self.lock:
            self.db.execute("DELETE FROM variants WHERE heard=? AND term=?", (heard, term))
            self.db.commit()

    # ------------------------------------------------------------ recognition

    def core_terms(self, preferred=()):
        """Primes every dictation: your own words, then the names you mention most in notes and speech."""
        with self.lock:
            q = lambda src, n, order: [r[0] for r in self.db.execute(
                f"SELECT text FROM terms WHERE hidden=0 AND source=? ORDER BY {order} LIMIT ?", (src, n))]
            return list(dict.fromkeys([t for t in preferred if t] + q("you", 24, "uses DESC, created DESC")
                    + q("learned", 8, "uses DESC, created DESC")
                    + q("history", 4, "uses DESC") + q("notes", 5, "uses DESC, seen DESC")))

    def candidates(self, hypothesis, limit=16):
        """Personal terms that sound like a span of the hypothesis but aren't spelled that way in it."""
        toks = words(hypothesis)
        if not toks:
            return []
        spans = set()
        for n in (1, 2, 3):
            for i in range(len(toks) - n + 1):
                spans.add(" ".join(toks[i:i + n]))
        present = {norm(s) for s in spans}
        span_keys = [(s, sound_key(s), norm(s)) for s in spans]
        best = {}
        for text, source, weight, key in self.terms():
            if len(key) < 3 or norm(text) in present:
                continue
            tn = norm(text)
            for s, sk, sn in span_keys:
                if not (0.6 <= len(sn) / max(1, len(tn)) <= 1.6):
                    continue
                if source == "notes" and text.islower() and not self.is_rare(s):
                    continue  # never pull a common word you said toward a notes spelling
                score = max(fuzz.ratio(sk, key), fuzz.ratio(sn, tn)) / 100
                if score >= 0.78:
                    best[text] = max(best.get(text, 0), score * weight)
        return [t for t, _ in sorted(best.items(), key=lambda kv: -kv[1])[:limit]]

    def exemplar(self, lang):
        """A recent dictation of yours in this language; primes Whisper with your own phrasing and mixing."""
        with self.lock:
            row = self.db.execute("SELECT text FROM recent WHERE lang=? ORDER BY ts DESC LIMIT 1", (lang,)).fetchone()
        if not row:
            return ""
        return " ".join(row[0].split()[:30])

    def prompt(self, terms, lang=None):
        terms = list(dict.fromkeys(terms))
        text = ", ".join(terms)
        while len(text) > 520 and terms:
            terms.pop()
            text = ", ".join(terms)
        ex = self.exemplar(lang) if lang else ""
        return (text + ". " if text else "") + ex

    def correct(self, text):
        """Deterministic, conservative repairs using what Flow knows about you."""
        with self.lock:
            fixes = self.db.execute("SELECT heard, term FROM variants WHERE confirmed=1 ORDER BY length(heard) DESC").fetchall()
        for heard, term in fixes:
            text = re.sub(rf"(?<!\w){re.escape(heard)}(?!\w)", term, text, flags=re.IGNORECASE)

        strong = {}
        for t, source, weight, key in self.terms():
            if (source in ("you", "learned") or weight >= 2.2) and len(key) >= 4:
                strong.setdefault(key, (weight, t))
        if strong:
            toks = list(re.finditer(WORD_RE, text))
            out, i, last = [], 0, 0
            while i < len(toks):
                hit = None
                for n in (3, 2, 1):
                    if i + n > len(toks):
                        continue
                    a, b = toks[i].start(), toks[i + n - 1].end()
                    span = text[a:b]
                    k = sound_key(span)
                    if k in strong and norm(span) != norm(strong[k][1]) and self.is_rare(span):
                        hit = (a, b, strong[k][1], n)
                        break
                if hit:
                    out.append(text[last:hit[0]] + hit[2])
                    last = hit[1]
                    i += hit[3]
                else:
                    i += 1
            text = "".join(out) + text[last:]

        # spacing: "Schemav 3" -> "schemav3", "Horizon Lab" -> "HorizonLab" for your own words and projects
        for t, source, weight, key in self.terms():
            if source not in ("you", "learned", "project", "history"):
                continue
            flat = re.sub(r"[^\w]", "", t.lower())
            if len(flat) < 5 or " " in t:
                continue
            parts = re.findall(r"[a-z]+|\d+", flat)
            if len(parts) < 1:
                continue
            pat = r"(?<!\w)" + r"[\s\-_]*".join(re.escape(ch) for ch in flat) + r"(?!\w)"
            text = re.sub(pat, t, text, flags=re.IGNORECASE)

        return self.canonical_case(text)

    def canonical_case(self, text):
        """Restore personal spellings after a writing style lowercases ordinary text."""
        # canonical casing for rare personal terms ("github" -> "GitHub", "ijtihed" -> "Ijtihed")
        for t, source, weight, key in self.terms():
            if t != t.lower() and self.is_rare(t):
                text = re.sub(rf"(?<!\w){re.escape(t)}(?!\w)", t, text, flags=re.IGNORECASE)
        return text

    # ------------------------------------------------------------ learning

    def learn_dictation(self, final, lang):
        now = time.time()
        with self.lock:
            self.db.execute("INSERT INTO recent VALUES (?,?,?)", (now, lang or "", final))
            self.db.execute("DELETE FROM recent WHERE ts NOT IN (SELECT ts FROM recent ORDER BY ts DESC LIMIT 200)")
            present = norm(final)
            for t, *_ in self.terms():
                if re.search(rf"(?<!\w){re.escape(t)}(?!\w)", final, flags=re.IGNORECASE):
                    self.db.execute("UPDATE terms SET uses=uses+1, last_used=? WHERE text=?", (now, t))
            promote = []
            for w in set(words(final)):
                if len(w) >= 3 and self.zipf(w) < RARE:
                    self.db.execute("""INSERT INTO words VALUES (?,1,?) ON CONFLICT(word) DO UPDATE
                                       SET count=count+1, last_used=excluded.last_used""", (w, now))
                    if self.db.execute("SELECT count FROM words WHERE word=?", (w,)).fetchone()[0] >= PROMOTE_AFTER:
                        promote.append(w)
            self.db.commit()
        for w in promote:
            self.add_term(w, "history")
        self._dirty()

    def learn_correction(self, before, after, auto=False):
        """Diff what Flow wrote against what you changed it to; remember misheard -> meant."""
        a, b = words(before), words(after)
        sm = difflib.SequenceMatcher(a=[w.lower() for w in a], b=[w.lower() for w in b], autojunk=False)
        learned = []
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == 'equal':
                for original, corrected in zip(a[i1:i2], b[j1:j2]):
                    if original != corrected and corrected != corrected.lower() and self.is_rare(corrected):
                        self.add_term(corrected, 'learned', update_case=True)
                        learned.append((original, corrected))
                continue
            if op != "replace" or not (1 <= i2 - i1 <= 3 and 1 <= j2 - j1 <= 3):
                continue
            heard, meant = " ".join(a[i1:i2]), " ".join(b[j1:j2])
            similar = fuzz.ratio(sound_key(heard), sound_key(meant)) >= 60
            if auto and not (similar and (self.is_rare(meant) or meant[:1].isupper())):
                continue  # a rewording, not a misrecognition
            if not auto and not similar and not self.is_rare(meant):
                continue
            self.add_term(meant, "learned")
            self.add_variant(heard, meant, confirmed=not auto)
            learned.append((heard, meant))
        return learned

    # ------------------------------------------------------------ listing for the UI

    def listing(self):
        with self.lock:
            terms = self.db.execute("""SELECT text, source, uses FROM terms WHERE hidden=0
                                       ORDER BY CASE source WHEN 'you' THEN 0 WHEN 'learned' THEN 1 WHEN 'history' THEN 2 ELSE 3 END,
                                       uses DESC, seen DESC, created DESC""").fetchall()
            fixes = self.db.execute("SELECT heard, term, count, confirmed FROM variants ORDER BY updated DESC").fetchall()
        return {"terms": [{"text": t, "source": s, "uses": u} for t, s, u in terms],
                "fixes": [{"heard": h, "term": t, "count": c, "active": bool(k)} for h, t, c, k in fixes],
                "scanned": self.meta("vault_scanned")}
