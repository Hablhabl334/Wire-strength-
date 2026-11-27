"""Mobile-legibility QA (v6.2 item 4). NO AI/LLM calls anywhere.

Report tool, not a render blocker: samples frames from a rendered
video, downscales them to 640x360 (a phone in the Shorts/feed world),
and checks the two things that decide whether text survives a phone:

- HEIGHT: the frame's main text element must be >= 1/6 of frame
  height (>= 60px at 360p). Measured from the renderer's KNOWN draw
  sizes (the same font sizes render5/render3 draw with), scaled -
  never OCR.
- CONTRAST: key text vs background >= 4.5:1 (WCAG AA), measured from
  the frame's own pixels: text luminance = 98th percentile, ground
  luminance = 10th percentile of the downscaled frame.

Usage:
  .venv/bin/python src/qa_mobile.py out/ep4_v62.mp4 \
      --script out/_ep4_resolved.json \
      --probe 0.7:title --probe 200:beats --probe 640:route
Kinds: title | beats | route | bignum.
Prints one PASS/FAIL line per probe; always exits 0.
"""
import argparse, json, os, subprocess, sys
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render2 import W, H
import render5

SMALL_W, SMALL_H = 640, 360
MIN_TEXT_PX = SMALL_H // 6          # 60px at 360p
MIN_CONTRAST = 4.5


def main_draw_size(kind, script):
    """The frame kind's main text element, at its 1920x1080 draw size -
    the same numbers the renderer itself draws with."""
    if kind == "title":
        word = ""
        for sc in script.get("scenes", []):
            if sc.get("type") == "timer" and sc.get("exercise"):
                word = sc["exercise"].upper()
                break
        if not word:
            word = (script.get("checklist") or ["THE TEST"])[0]
        return f"title word '{word}'", render5.fit_size(word, 300, W - 120)
    if kind == "bignum":
        return "bignum big number", 230        # card_image4: F(230)
    if kind == "route":
        return "route card title 'YOUR RESULT'", 64   # route_image: F(64)
    if kind == "beats":
        return "phrase strip", 56              # render3.phrase_png: F(56)
    raise ValueError(f"unknown probe kind {kind!r}")


def _lum(rgb):
    v = rgb.astype(np.float32) / 255.0
    v = np.where(v <= 0.03928, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * v[..., 0] + 0.7152 * v[..., 1] + 0.0722 * v[..., 2]


def check_frame(video, t, kind, script, tmpd):
    raw = os.path.join(tmpd, f"qa_{kind}_{t}.png")
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", video,
                        "-frames:v", "1", raw], capture_output=True)
    if r.returncode != 0 or not os.path.exists(raw):
        return f"QA {kind} @{t}s: FRAME EXTRACT FAILED"
    im = Image.open(raw).convert("RGB").resize((SMALL_W, SMALL_H), Image.BICUBIC)
    label, size1080 = main_draw_size(kind, script)
    h360 = size1080 * SMALL_H / H
    h_ok = h360 >= MIN_TEXT_PX
    lum = _lum(np.asarray(im))
    lt, lb = np.percentile(lum, 98), np.percentile(lum, 10)
    ratio = (lt + 0.05) / (lb + 0.05)
    c_ok = ratio >= MIN_CONTRAST
    return (f"QA {kind} @{t}s: {label} {size1080}px@1080p = {h360:.0f}px@360p "
            f"(need >={MIN_TEXT_PX}) {'PASS' if h_ok else 'FAIL'}; "
            f"contrast {ratio:.1f}:1 (need >={MIN_CONTRAST}) "
            f"{'PASS' if c_ok else 'FAIL'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--script", required=True)
    ap.add_argument("--probe", action="append", required=True,
                    help="T:KIND, e.g. 0.7:title (repeatable)")
    a = ap.parse_args()
    script = json.load(open(a.script))
    tmpd = os.path.join(os.path.dirname(os.path.abspath(a.video)), "qa_frames")
    os.makedirs(tmpd, exist_ok=True)
    for p in a.probe:
        t, kind = p.split(":", 1)
        print(check_frame(a.video, float(t), kind, script, tmpd))
    return 0


if __name__ == "__main__":
    sys.exit(main())
