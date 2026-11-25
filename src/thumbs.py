"""Code-only thumbnail composer. NO AI/LLM calls anywhere.

Every episode gets a unique 1280x720 thumbnail built by PIL from the
episode's own banked spec (meta["thumb"]):
  asset  - hero Ren artwork for this episode (fresh per video)
  big    - the giant hook element: the test number ("40s", "x2.3", "3 MIN")
  hook   - 2-4 words max ("HOW LONG?", "NOT MUSCLE", "YOUR NUMBER LIES")
  accent - category color key (see ACCENTS)
Grammar copied from the measured winners of the niche: character large
on one side, one giant number, almost no words, dark background, one
accent color. Fallbacks derive a spec from badge/scenes so even an
episode without an explicit thumb spec still gets a valid thumbnail.
"""
import os
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
W, H = 1280, 720

ACCENTS = {
    "cyan": (0, 229, 255),
    "gold": (255, 196, 0),
    "red": (255, 70, 60),
    "green": (64, 255, 140),
    "violet": (178, 102, 255),
}
CATEGORY_ACCENT = {
    "grip": "cyan", "tendons": "gold", "pain": "red", "healing": "green",
    "nerves": "violet", "isometrics": "violet", "bones": "gold",
    "skinnyfat": "red", "experiment": "green", "whathappens": "cyan",
}


def _font(size):
    try:
        return ImageFont.truetype(FONT, size)
    except Exception:
        return ImageFont.load_default()


def _fit(draw, text, max_w, start):
    """Largest font size (<= start) whose rendered text fits max_w."""
    size = start
    while size > 20:
        f = _font(size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 6
    return _font(20)


def _wrap(draw, text, max_w, size):
    words, lines, cur = text.split(), [], ""
    f = _font(size)
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=f) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def derive_spec(meta):
    spec = dict(meta.get("thumb", {}))
    if not spec.get("asset"):
        for sc in meta.get("scenes", []):
            if sc.get("poses"):
                spec["asset"] = sc["poses"][0]
                break
            if sc.get("asset"):
                spec["asset"] = sc["asset"]
                break
    if not spec.get("hook"):
        spec["hook"] = meta.get("badge", "").split("-", 1)[-1].strip()[:24] or "THE TEST"
    if not spec.get("accent"):
        spec["accent"] = CATEGORY_ACCENT.get(meta.get("category", ""), "cyan")
    return spec


def make_thumbnail(meta, out_path):
    spec = derive_spec(meta)
    accent = ACCENTS.get(spec.get("accent", "cyan"), ACCENTS["cyan"])

    # --- background: hero art, cover-fit, darkened, left side darker ---
    art_path = os.path.join(ROOT, "assets", spec.get("asset", ""))
    if spec.get("asset") and os.path.exists(art_path):
        img = Image.open(art_path).convert("RGB")
        scale = max(W / img.width, H / img.height)
        img = img.resize((int(img.width * scale) + 1, int(img.height * scale) + 1))
        # anchor the character to the right half
        x = max(0, img.width - W)
        img = img.crop((x, 0, x + W, H))
    else:
        img = Image.new("RGB", (W, H), (10, 12, 16))
    img = ImageEnhance.Brightness(img).enhance(0.8)
    # horizontal shade: strong on the left (text side), light on the right
    import numpy as np
    ramp = np.linspace(238, 36, W, dtype=np.uint8)
    mask = Image.fromarray(np.tile(ramp, (H, 1)), "L")
    dark = Image.new("RGB", (W, H), (4, 5, 8))
    img = Image.composite(dark, img, mask)
    d = ImageDraw.Draw(img, "RGBA")

    # --- giant number / big element (top-left block) ---
    big = spec.get("big", "")
    hook_y = 40
    if big:
        f = _fit(d, big, 660, 280)
        d.text((46, 26), big, font=f, fill=accent, stroke_width=6, stroke_fill=(0, 0, 0))
        hook_y = 26 + int(f.size * 1.08) + 18

    # --- hook words: shrink until the whole block clears the brand bar ---
    hook = (spec.get("hook") or "").upper()
    lines, lh = [], 0
    for size in (118, 106, 94, 84, 74, 64):
        lines = _wrap(d, hook, 640, size)[:3]
        lh = int(size * 1.05)
        if hook_y + lh * len(lines) <= H - 96:
            break
    y = hook_y
    for ln in lines:
        f = _fit(d, ln, 640, size)
        d.text((48, y), ln, font=f, fill=(255, 255, 255), stroke_width=5, stroke_fill=(0, 0, 0))
        y += lh

    # --- episode badge chip (top-right) ---
    badge = (meta.get("badge") or "").strip()
    if badge:
        f = _font(34)
        tw = d.textlength(badge, font=f)
        d.rounded_rectangle([W - tw - 56, 26, W - 26, 84], radius=12, fill=(0, 0, 0, 190))
        d.text((W - tw - 41, 38), badge, font=f, fill=accent)

    # --- brand bar (bottom) ---
    d.rectangle([0, H - 64, W, H], fill=(0, 0, 0, 200))
    d.rectangle([0, H - 68, W, H - 64], fill=accent + (255,))
    try:
        import json
        cfg = json.load(open(os.path.join(ROOT, "channel.json")))
        name = cfg.get("name", "")
        tagline = cfg.get("tagline", "")
    except Exception:
        name, tagline = "", ""
    if name:
        f = _font(36)
        d.text((46, H - 52), name.upper(), font=f, fill=(255, 255, 255))
        if tagline:
            f2 = _font(28)
            tw = d.textlength(tagline, font=f2)
            d.text((W - tw - 46, H - 48), tagline, font=f2, fill=accent)

    img.save(out_path, "JPEG", quality=90)
    return out_path


if __name__ == "__main__":
    import json, sys
    meta = json.load(open(sys.argv[1]))
    print(make_thumbnail(meta, sys.argv[2] if len(sys.argv) > 2 else "out/thumbnail.jpg"))
