"""Assemble real browser screenshots into a compact GIF with their captured timing.

Input directory: JPEG frames and timing.json containing [{file, at_ms}, ...].
No app text, cursor or waveform is redrawn here; these are rendered UI frames.
"""
import argparse
import json
from pathlib import Path
from PIL import Image

parser = argparse.ArgumentParser()
parser.add_argument("frames", type=Path)
parser.add_argument("output", type=Path)
parser.add_argument("--width", type=int, default=960)
options = parser.parse_args()
timing = json.loads((options.frames / "timing.json").read_text("utf-8"))
samples = []
for item in timing[::max(1, len(timing)//8)]:
    with Image.open(options.frames / item["file"]) as source:
        samples.append(source.convert("RGB").resize((480, 270), Image.Resampling.LANCZOS))
sheet = Image.new("RGB", (480, 270*len(samples)), "white")
for index, sample in enumerate(samples): sheet.paste(sample, (0, 270*index))
palette = sheet.quantize(colors=160, method=Image.Quantize.MEDIANCUT)
frames, durations = [], []
for index, item in enumerate(timing):
    with Image.open(options.frames / item["file"]) as source:
        frame = source.convert("RGB")
        frame = frame.resize((options.width, round(frame.height*options.width/frame.width)), Image.Resampling.LANCZOS)
        frames.append(frame.quantize(palette=palette, dither=Image.Dither.NONE))
    delta = timing[index+1]["at_ms"] - item["at_ms"] if index+1 < len(timing) else 1200
    durations.append(max(20, round(delta/10)*10))
options.output.parent.mkdir(parents=True, exist_ok=True)
frames[0].save(options.output, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True, disposal=1)
print(json.dumps({"file": str(options.output), "frames": len(frames), "duration_ms": sum(durations), "bytes": options.output.stat().st_size}))
