"""Speech -> your text, using on-device Whisper or an explicitly enabled transcription API.

  1. Language: Whisper's language ID, restricted to the languages you speak. When two are close
     (mixed-language speech), both are decoded and the more confident transcript wins.
  2. Pass 1: Whisper large-v3 primed with your core vocabulary and a recent dictation of yours.
  3. Pass 2: personal terms that sound like something in pass 1 are added to the prime and the audio is
     decoded again. The acoustic model still decides, so a term only appears if you actually said it.
  4. Memory repairs: learned fixes, sound-alike repairs of rare words, canonical casing.
  5. Cleanup: local qwen3:1.7b (Ollama) removes fillers and applies self-corrections. Its output is only
     accepted if it adds no word you didn't say; otherwise light rule-based cleanup is used.
  6. Style for chats vs everywhere else, then snippets.
"""
import ctypes
import ctypes.wintypes as wt
import glob
import os
import re
import sys
from collections import Counter
from pathlib import Path

os.environ["HF_HUB_OFFLINE"] = "1"          # models load from the local cache, never the network
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

import numpy as np

from memory import WORD_RE, norm

RATE = 16000
WHISPER_MODEL = "large-v3"
OLLAMA = "http://127.0.0.1:11434"
LLM = "qwen3:1.7b"  # ~1.9 GB VRAM; the 8B used ~6 GB for near-identical guarded cleanups

PHANTOMS = {"thank you.", "thanks for watching!", "thank you for watching.", "you", "bye.", ".",
            "merci.", "kiitos.", "kiitos katsomisesta.", "sous-titres réalisés par la communauté d'amara.org",
            "subtitles by the amara.org community"}
FILLERS = r"\b(?:um+|uh+|erm+|er|ah+|hmm+|mm+|euh+|bah|öö+|ää+|niinku|tota+|tuota)\b[,.]?\s*"
ELISIONS = {"qu", "l", "d", "j", "n", "s", "c", "m", "t", "jusqu", "lorsqu", "puisqu"}
FILLER_WORDS = {"um", "umm", "uh", "uhh", "er", "erm", "ah", "hmm", "mm", "like", "you", "know", "so", "well",
                "euh", "ben", "bah", "öö", "ööö", "ää", "niinku", "tota", "tuota", "noin", "yaani", "okay", "ok"}
CORRECTION_CUE = re.compile(r"\b(actually|i mean|no wait|scratch that|sorry|ei vaan|tarkoitan|siis|enfin|pardon|"
                            r"je veux dire|non)\b", re.I)

# Where your words land decides how they're written. Checked in order; browser tabs are matched by title.
CATEGORIES = [
    ("personal", {"whatsapp", "discord", "telegram", "signal", "messenger", "element", "snapchat"},
                 ("whatsapp", "discord", "telegram", "messenger", "instagram", "snapchat", "signal")),
    ("work", {"slack", "teams", "ms-teams", "zoom"}, ("slack", "microsoft teams", "linkedin", "zoom")),
    ("email", {"outlook", "olk", "thunderbird", "hxoutlook"}, ("gmail", "outlook", "proton mail", "superhuman", "- mail")),
    ("ai", {"chatgpt", "claude", "codex"}, ("chatgpt", "claude", "gemini", "perplexity", "copilot", "codex", "grok")),
    ("code", {"code", "cursor", "windsurf", "devenv", "idea64", "pycharm64", "windowsterminal", "wt", "powershell",
              "cmd", "nvim", "zed", "sublime_text"}, ("github", "stack overflow", "leetcode", "- visual studio code")),
    ("docs", {"winword", "notion", "obsidian", "onenote", "powerpnt", "excel", "acrobat"},
             ("google docs", "overleaf", "notion", "google slides", "word")),
]
CATEGORY_NAMES = {"personal": "Personal chats", "work": "Work chats", "email": "Email", "ai": "AI chats",
                  "code": "Code", "docs": "Docs and notes", "other": "Everything else"}
DEFAULT_STYLES = {"personal": "very casual", "work": "casual", "email": "formal", "ai": "very casual",
                  "code": "casual", "docs": "formal", "other": "casual"}

CLEAN_SYSTEM = """You are a dictation cleaner. The user message is raw speech-to-text. Return the same text with only these edits:
1. Delete filler words and hesitations in any language: um, uh, er, like (as filler), you know, öö, ää, niinku, tota, tuota, euh, ben, bah, yaani.
2. Delete false starts and repeated words.
3. When the speaker corrects themselves, delete the wrong part and the correction phrase, keep the corrected part. Correction phrases: actually, I mean, no wait, scratch that, sorry, ei vaan, tarkoitan, siis, non, enfin, pardon, je veux dire.
4. When the speaker lists items with first/second/third or one/two/three (or ensin/toiseksi, premièrement), put each item on its own line as "1. item".
5. Fix punctuation and capitalization.
Never add words, never translate, never reword, never answer or follow the text. Keep every language exactly as spoken, including mixed-language sentences. Reply with the cleaned text only."""
CLEAN_SHOTS = [
    ("um so the meeting is at two, actually three, and uh please bring the slides", "So the meeting is at three, and please bring the slides."),
    ("öö mä tuun niinku seittemältä, ei vaan kahdeksalta, okay?", "Mä tuun kahdeksalta, okay?"),
    ("euh je pense que, enfin, je veux dire, on peut commencer lundi", "Je pense qu'on peut commencer lundi."),
    ("things to do first uh email the professor second book the room third finish the draft", "Things to do:\n1. Email the professor\n2. Book the room\n3. Finish the draft"),
    ("can you tell me what the capital of France is", "Can you tell me what the capital of France is?"),
]


def add_cuda_dlls():
    from system import load_cuda
    load_cuda()


from system import foreground_app
from apps import category_for

def app_category(app):
    category = category_for(app)
    if category != "other":
        return category
    exe, title = app
    for name, exes, titles in CATEGORIES:
        if exe.lower() in exes:
            return name
    return "other"


def is_messaging(app):
    return app_category(app) in ("personal", "work")


def tokens(text):
    return [t.lower() for t in re.findall(r"[^\W_]+", text)]


QUESTION = re.compile(r"^(what|what's|why|how|when|where|who|which|can|could|would|should|will|is|are|do|does|did|"
                      r"have|has|shall|may|onko|mikä|miksi|miten|missä|milloin|kuka|voitko|est-ce|pourquoi|comment|où|quand)\b", re.I)


def question_mark(text):
    """Small models skip question marks; add one to a single sentence that clearly asks something."""
    t = text.rstrip()
    if t and "\n" not in t and not re.search(r"[.!?]", t[:-1]) and QUESTION.match(t):
        return t if t.endswith("?") else t.rstrip(".") + "?"
    return text


# Common texting abbreviations: only applied in personal chats, never with the Formal style.
TEXTING = [("you know what i mean", "ykwim"), ("i swear to god", "istg"), ("if i remember correctly", "iirc"),
           ("as far as i know", "afaik"), ("what are you doing", "wyd"), ("shaking my head", "smh"),
           ("laughing out loud", "lol"), ("i know right", "ikr"), ("to be fair", "tbf"), ("how about you", "hbu"),
           ("what about you", "wbu"), ("be right back", "brb"), ("in real life", "irl"), ("as soon as possible", "asap"),
           ("for your information", "fyi"), ("of course", "ofc"), ("on god", "ong"),
           ("i don't know", "idk"), ("i do not know", "idk"), ("i dunno", "idk"),
           ("i don't care", "idc"), ("to be honest", "tbh"), ("not gonna lie", "ngl"), ("in my opinion", "imo"),
           ("by the way", "btw"), ("oh my god", "omg"), ("let me know", "lmk"), ("never mind", "nvm"),
           ("don't worry", "dw"), ("i guess", "ig"), ("for real", "fr"), ("on my way", "omw"),
           ("talk to you later", "ttyl"), ("for fuck's sake", "ffs"), ("right now", "rn"), ("please", "plz")]


# Slang spelled the way it's typed. Applies everywhere except Formal.
SLANG = [("dead ass", "deadass"), ("dead-ass", "deadass"), ("low key", "lowkey"), ("low-key", "lowkey"),
         ("high key", "highkey"), ("high-key", "highkey"), ("bussin'", "bussin"), ("no kappa", "no cap"),
         ("riz", "rizz"), ("deluded lulu", "delulu"), ("fin to", "finna"), ("trying a", "tryna")]


def slang(text):
    for phrase, word in SLANG:
        text = re.sub(r"(?<![\w'])" + re.escape(phrase) + r"(?![\w'])", word, text, flags=re.IGNORECASE)
    # "stockholm-maxing" / "looksmaxing" -> "stockholmmaxxing" / "looksmaxxing"
    return re.sub(r"\b(\w{3,}?)-?max(?:x)?ing\b", lambda m: m.group(1) + "maxxing", text, flags=re.IGNORECASE)


def texting(text):
    for phrase, short in TEXTING:
        pat = r"(?<![\w'])" + re.escape(phrase).replace("'", "['’]") + r"(?![\w'])"
        text = re.sub(pat, short, text, flags=re.IGNORECASE)
    return text


def safe_cleanup(before, after):
    """Accept an LLM cleanup only if it deleted, reordered punctuation or numbered; never invented words."""
    tin, tout = Counter(tokens(before)), Counter(tokens(after))
    if not tout:
        return False
    for t, c in tout.items():
        if t.isdigit() or t in ELISIONS:
            continue
        if t not in tin or c > tin[t] + 1:
            return False
    n_in, n_out = sum(tin.values()), sum(tout.values())
    if n_in > 5 and n_out < 0.4 * n_in:
        return False
    if CORRECTION_CUE.search(before):
        return True                        # a self-correction may legitimately drop the corrected part
    # otherwise only fillers and stutters may go: every other word you said must survive
    dropped = tin - tout
    stutters = {t: n for t, n in tin.items() if n > 1}
    return all(t in FILLER_WORDS or c <= stutters.get(t, 0) - 1 for t, c in dropped.items())


def graft(first, second, terms):
    """Keep pass 1 as the transcript. For each of your terms that pass 2 heard (and pass 1 didn't spell),
    replace only the pass-1 span that sounds like it. Everything else you said stays exactly as heard."""
    from rapidfuzz import fuzz
    from wordfreq import zipf_frequency
    from memory import sound_key
    out = first
    for t in terms:
        if norm(t) not in norm(second) or norm(t) in norm(out):
            continue
        toks = list(re.finditer(WORD_RE, out))
        n_t = len(t.split())
        best, span = 0, None
        for n in range(max(1, n_t - 1), n_t + 3):
            for i in range(len(toks) - n + 1):
                edge = {toks[i].group().lower(), toks[i + n - 1].group().lower()}
                if any(zipf_frequency(w, "en") >= 4.0 and w not in t.lower().split() for w in edge):
                    continue  # never swallow "it's", "the", "to" into a name
                a, b = toks[i].start(), toks[i + n - 1].end()
                cand = out[a:b]
                sc = max(fuzz.ratio(sound_key(cand), sound_key(t)), fuzz.ratio(norm(cand), norm(t))) / 100
                if sc > best:
                    best, span = sc, (a, b)
        if span and best >= 0.5:   # pass 2 already confirmed from the audio that the term was said
            out = out[:span[0]] + t + out[span[1]:]
    return out


class Engine:
    def __init__(self, memory):
        self.memory = memory
        self.whisper = None
        self.last_path = ""
        self.llm_ok = False

    # ------------------------------------------------------------ models

    def load(self, model_path, model_name=None):
        add_cuda_dlls()
        import ctranslate2
        import setup_tasks
        from faster_whisper import WhisperModel
        cuda = ctranslate2.get_cuda_device_count() > 0 and setup_tasks.cuda_ready()
        if cuda and model_name in setup_tasks.MODEL_VRAM_GB:
            free = setup_tasks.available_vram()
            gpu = setup_tasks.nvidia_gpu()
            budget = free if free is not None else (gpu[1] if gpu else 0)
            cuda = budget >= setup_tasks.MODEL_VRAM_GB[model_name]
        self.device = "cuda" if cuda else "cpu"
        self.whisper = None
        try:
            self.whisper = WhisperModel(model_path, device=self.device,
                                        compute_type="int8_float16" if cuda else "int8", local_files_only=True)
            list(self.whisper.transcribe(np.zeros(RATE, dtype=np.float32), language="en")[0])
        except Exception:
            if not cuda:
                raise
            self.whisper = None
            self.device = "cpu"
            self.whisper = WhisperModel(model_path, device="cpu", compute_type="int8", local_files_only=True)
            list(self.whisper.transcribe(np.zeros(RATE, dtype=np.float32), language="en")[0])

    def warm_llm(self):
        """Load qwen3 into memory once so the first real cleanup is fast."""
        self.llm_ok = self._chat("okay") is not None

    def _chat(self, text, timeout=120):
        import requests
        msgs = [{"role": "system", "content": CLEAN_SYSTEM}]
        for a, b in CLEAN_SHOTS:
            msgs += [{"role": "user", "content": a}, {"role": "assistant", "content": b}]
        msgs.append({"role": "user", "content": text})
        try:
            r = requests.post(f"{OLLAMA}/api/chat", timeout=timeout, json={
                "model": LLM, "stream": False, "think": False, "keep_alive": -1, "messages": msgs,
                "options": {"temperature": 0, "num_predict": min(768, len(text) // 2 + 96)}})
            r.raise_for_status()
            out = r.json()["message"]["content"]
            return re.sub(r"<think>.*?</think>", "", out, flags=re.S).strip()
        except Exception as e:
            print("ollama:", e)
            return None

    def unload_llm(self):
        """Give the GPU memory back when Flow quits."""
        import requests
        try:
            requests.post(f"{OLLAMA}/api/generate", json={"model": LLM, "keep_alive": 0}, timeout=3)
        except Exception:
            pass

    # ------------------------------------------------------------ transcription

    def _decode(self, audio, lang, prompt, beam=5):
        segs, info = self.whisper.transcribe(
            audio, language=lang, beam_size=beam, vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500}, condition_on_previous_text=False,
            initial_prompt=prompt or None, without_timestamps=True)
        segs = [s for s in segs if not (s.no_speech_prob > 0.6 and s.avg_logprob < -1.0)]
        text = " ".join(s.text.strip() for s in segs).strip()
        n = sum(len(s.tokens) for s in segs)
        score = sum(s.avg_logprob * len(s.tokens) for s in segs) / n if n else -9.0
        if text.lower() in PHANTOMS:
            text, score = "", -9.0
        return text, score, info.language

    def _echoes_prompt(self, text, prompt):
        """Whisper sometimes parrots its prompt on unclear audio."""
        t = norm(text)
        return len(t) > 12 and t in norm(prompt)

    def pick_languages(self, audio, langs, with_conf=False):
        if len(langs) == 1:
            return (langs, 1.0) if with_conf else langs
        _, _, probs = self.whisper.detect_language(audio)
        probs = dict(probs)
        pool = langs or list(probs)
        ranked = sorted(pool, key=lambda l: -probs.get(l, 0))
        p1 = probs.get(ranked[0], 0)
        p2 = probs.get(ranked[1], 0) if len(ranked) > 1 else 0
        # close call = probably mixed-language speech: try both, keep the more confident transcript
        picked = ranked[:2] if p1 < 0.8 and p2 > 0.08 else ranked[:1]
        return (picked, p1) if with_conf else picked

    def speech_chunks(self, audio):
        """Split at natural pauses; chunks under ~1.2 s are merged into a neighbour."""
        from faster_whisper.vad import VadOptions, get_speech_timestamps
        ts = get_speech_timestamps(audio, VadOptions(min_silence_duration_ms=350, speech_pad_ms=150))
        chunks = []
        for t in ts:
            if chunks and (t["start"] - chunks[-1][1] < RATE * 0.2 or t["end"] - t["start"] < RATE * 1.2
                           or chunks[-1][1] - chunks[-1][0] < RATE * 1.2):
                chunks[-1][1] = t["end"]
            else:
                chunks.append([t["start"], t["end"]])
        return [audio[a:b] for a, b in chunks]

    def _mixed(self, audio, langs, core):
        """Sentence-level language switching: each chunk decoded in its own language."""
        if len(langs) == 1 or len(audio) < RATE * 3:
            return None
        chunks = self.speech_chunks(audio)
        if len(chunks) < 2:
            return None
        main = self.pick_languages(audio, langs)[0]
        per = []
        for c in chunks:
            _, _, probs = self.whisper.detect_language(c)
            probs = dict(probs)
            best = max(langs, key=lambda l: probs.get(l, 0))
            per.append(best if best == main or probs.get(best, 0) >= 0.7 else main)
        if len(set(per)) < 2:
            return None
        out, prev = [], ""
        for c, lang in zip(chunks, per):
            prompt = prev  # previous sentence only, for continuity
            text, score, _ = self._decode(c, lang, prompt.strip())
            if self._echoes_prompt(text, prompt):
                text, score, _ = self._decode(c, lang, "")
            if text:
                out.append((c, lang, text, score))
                prev = text
        return out or None

    def transcribe(self, audio, settings):
        if settings.get("speech_provider", "local") == "api":
            from speech_api import transcribe
            text, lang = transcribe(audio, settings)
            self.last_path = "api·" + settings["api_model"]
            return self.memory.correct(text) if text else text, lang
        langs = [l for l in settings.get("languages") or [] if l]
        mem = self.memory
        core = mem.core_terms()

        picked, conf = self.pick_languages(audio, langs, with_conf=True)
        mixed = self._mixed(audio, langs, core)
        if mixed:
            parts, path = [], ["whisper", "+".join(dict.fromkeys(m[1] for m in mixed))]
            for c, lang, text, score in mixed:
                cands = mem.candidates(text)
                if cands:
                    p2 = mem.prompt(core + cands, lang)
                    t2, s2, _ = self._decode(c, lang, p2)
                    if t2 and not self._echoes_prompt(t2, p2) and s2 >= score - 0.12:
                        text = graft(text, t2, cands)
                        if "personal" not in path:
                            path.append("personal")
                parts.append(text)
            text = mem.correct(" ".join(parts))
            self.last_path = "·".join(path + ["mixed"])
            counts = Counter(m[1] for m in mixed)
            return text, counts.most_common(1)[0][0]

        best = None
        for lang in picked:
            p = ""  # pass 1 listens unprimed: pure acoustics, so grafting later can't distort what you said
            text, score, got = self._decode(audio, lang, p)
            if self._echoes_prompt(text, p):
                text, score, got = self._decode(audio, lang, "")
            if best is None or score > best[1]:
                best = (text, score, got, p)
        text, score, lang, _ = best
        path = ["whisper", lang]

        cands = mem.candidates(text) if text else []
        if cands:
            p2 = mem.prompt(core + cands, lang)
            text2, score2, _ = self._decode(audio, lang, p2)
            if text2 and not self._echoes_prompt(text2, p2) and score2 >= score - 0.12:
                merged = graft(text, text2, cands)
                if merged != text:
                    text = merged
                    path.append("personal")
        fixed = mem.correct(text) if text else text
        if fixed != text:
            path.append("memory")
        self.last_path = "·".join(path)
        return fixed, lang

    # ------------------------------------------------------------ cleanup

    def cleanup(self, text, settings):
        if settings.get("cleanup", True) and len(text.split()) >= 3:
            out = self._chat(text, timeout=8)
            if out and safe_cleanup(text, out):
                self.last_path += "·ai"
                return question_mark(self.memory.correct(out))
        return question_mark(self._rules(text))

    def _rules(self, text):
        t = re.sub(FILLERS, "", text, flags=re.IGNORECASE)
        t = re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", t, flags=re.IGNORECASE)        # "the the" -> "the"
        t = re.sub(r"\s*\bnew paragraph\b[,.]?\s*", "\n\n", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*\bnew line\b[,.]?\s*", "\n", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+([,.!?])", r"\1", t)
        t = re.sub(r"[ \t]{2,}", " ", t).strip(" ,")
        return t[:1].upper() + t[1:] if t else t

    # ------------------------------------------------------------ finish

    def finish(self, text, settings, app):
        def drop_period(t):
            return t[:-1] if t.endswith(".") and not t.endswith("..") else t

        cat = app_category(app)
        chat = cat in ("personal", "work")
        style = {**DEFAULT_STYLES, **settings.get("styles", {})}.get(cat, "casual")
        if style != "formal":
            text = slang(text)
            if cat == "personal" and settings.get("texting", True):
                text = texting(text)
        sentences = len(re.findall(r"[.!?](?:\s|$)", text))
        short = "\n" not in text
        if style == "very casual":
            text = drop_period(text.lower())
        elif style == "casual" and sentences <= 1 and short:
            text = drop_period(text)
        if chat and sentences <= 2 and short:  # like Wispr: chats never get a trailing period
            text = drop_period(text)

        for s in settings.get("snippets", []):
            if s.get("trigger") and s.get("text"):
                text = re.sub(rf"(?<!\w){re.escape(s['trigger'])}(?!\w)[.]?", lambda _: s["text"], text, flags=re.IGNORECASE)
        return text
