"""Notice when you fix a word Flow got wrong, the way Wispr does.

A few seconds after pasting, Flow reads the focused text box through Windows UI Automation, finds the
text it pasted, and diffs it. Only misrecognitions are learned (short, sound-alike replacements toward a
rare or capitalized word), never rewording. Password fields are skipped. Nothing leaves this PC.
"""
import re
import threading
import time

from rapidfuzz import fuzz

CHECKS = (6, 20)   # seconds after paste


def focused_text():
    from system import IS_WIN
    if not IS_WIN:
        return None, None   # Linux learns corrections made in Flow's history editor.
    import uiautomation as auto
    with auto.UIAutomationInitializerInThread(debug=False):
        c = auto.GetFocusedControl()
        if c is None or c.IsPassword:
            return None, None
        try:
            runtime_id = tuple(c.GetRuntimeId())
        except Exception:
            runtime_id = None
        key = (c.ProcessId, runtime_id, c.ControlTypeName, c.AutomationId, c.Name[:40] if c.Name else "")
        try:
            vp = c.GetValuePattern()
            if vp and vp.Value:
                return key, vp.Value[-20000:]
        except Exception:
            pass
        try:
            tp = c.GetTextPattern()
            if tp:
                return key, tp.DocumentRange.GetText(20000)
        except Exception:
            pass
    return key, None


def find_edited(pasted, field):
    """The part of the field that corresponds to what we pasted (possibly edited), or None."""
    if not field or pasted in field:
        return None
    al = fuzz.partial_ratio_alignment(pasted, field, score_cutoff=55)
    if al is None:
        return None
    # widen to word boundaries plus some slack, since edits change the length
    slack = max(8, len(pasted) // 4)
    a = max(0, al.dest_start - slack)
    b = min(len(field), al.dest_end + slack)
    while a > 0 and not field[a - 1].isspace():
        a -= 1
    while b < len(field) and not field[b].isspace():
        b += 1
    region = field[a:b].strip()
    return region if fuzz.ratio(pasted, region) >= 55 else None


def watch(pasted, memory, on_learned):
    def run():
        try:
            key0, initial = focused_text()
        except Exception:
            return
        if key0 is None or not initial or pasted not in initial:
            return
        observed = time.monotonic()
        for delay in CHECKS:
            time.sleep(max(0, observed + delay - time.monotonic()))
            try:
                key, field = focused_text()
            except Exception:
                return
            if field is None or key != key0:
                return                     # focus moved on: not our text box any more
            region = find_edited(pasted, field)
            if region:
                learned = memory.learn_correction(pasted, region, auto=True)
                if learned:
                    on_learned(learned)
                    return
    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    return worker
