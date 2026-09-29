"""Flow's waveform mark: pixel-snapped tray glyphs and a multi-size app .ico."""
from pathlib import Path

from PIL import Image, ImageDraw

BARS = (0.38, 0.72, 1.0, 0.72, 0.38)
RED = (255, 69, 88, 255)


def _bars(d, x0, y_mid, bar_w, gap, max_h, color, ss):
    for i, h in enumerate(BARS):
        bh = max(bar_w, round(max_h * h / ss) * ss)
        x = x0 + i * (bar_w + gap)
        d.rounded_rectangle((x, y_mid - bh / 2, x + bar_w - 1, y_mid + bh / 2 - 1), bar_w / 2, fill=color)


def tray(state, size, light_taskbar=False):
    """state: idle | recording | loading. Drawn at the exact tray pixel size so bars land on whole pixels."""
    ss = 8
    S = size * ss
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fg = (20, 20, 22, 255) if light_taskbar else (255, 255, 255, 255)
    color = {"recording": RED, "loading": (*fg[:3], 110)}.get(state, fg)
    bar = max(2, round(size / 8)) * ss
    gap = max(1, round(size / 16)) * ss
    total = 5 * bar + 4 * gap
    _bars(d, (S - total) // 2 // ss * ss, S / 2, bar, gap, S * 0.86, color, ss)
    return img.resize((size, size), Image.LANCZOS)


def app_icon(size):
    """White squircle, black waveform: the inverse of the tray glyph."""
    ss = 4
    S = size * ss
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    pad = S * 0.04
    body = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(body)
    for y in range(S):                                # barely-there top-to-bottom sheen
        c = int(255 - 9 * y / S)
        gd.line((0, y, S, y), fill=(c, c, c + 1 if c < 255 else 255, 255))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((pad, pad, S - pad, S - pad), S * 0.23, fill=255)
    img.paste(body, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((pad, pad, S - pad, S - pad), S * 0.23, outline=(0, 0, 0, 38), width=max(1, S // 96))
    bar = S * 0.085
    gap = S * 0.06
    total = 5 * bar + 4 * gap
    _bars(d, (S - total) / 2, S / 2, bar, gap, S * 0.52, (17, 17, 19, 255), 1)
    return img.resize((size, size), Image.LANCZOS)


def ensure_app_ico(path: Path):
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    imgs = [app_icon(s) for s in sizes]
    imgs[-1].save(path, format="ICO", sizes=[(s, s) for s in sizes], append_images=imgs[:-1])
    return path
