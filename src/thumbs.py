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
import json, os
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


LAST_THUMB = None  # asset actually used by the latest make_thumbnail call


def _recent_thumb_assets():
    """Hero assets used by the last 2 published episodes, so a thumbnail
    never repeats the picture the previous episodes just showed. Reads
    state.json (the machine's own record); episodes published before the
    'thumb' field existed fall back to their banked authored asset."""
    recent = []
    try:
        state = json.load(open(os.path.join(ROOT, "state.json")))
        for entry in state.get("published", [])[-2:]:
            asset = entry.get("thumb")
            if not asset and entry.get("script"):
                prev = json.load(open(os.path.join(ROOT, "bank", entry["script"])))
                asset = (prev.get("thumb") or {}).get("asset")
            if asset:
                recent.append(asset)
    except Exception:
        pass
    return recent


def make_thumbnail(meta, out_path):
    """GAP 9 thumbnail discipline (measured on Rep Theory): black
    background, ONE huge bright pose, at most 2 lines of huge tease
    text (white, then red), ONE hand-drawn red arrow. No number, no
    badge chip, no brand bar - one idea only."""
    global LAST_THUMB
    spec = derive_spec(meta)
    # Anti-repeat: if the authored hero was the thumbnail of one of the
    # last 2 episodes, take the episode's next own picture instead.
    recent = _recent_thumb_assets()
    if spec.get("asset") in recent:
        cands = []
        for sc in meta.get("scenes", []):
            for a in (sc.get("poses") or []) + ([sc["asset"]] if sc.get("asset") else []):
                if a not in cands:
                    cands.append(a)
        for a in cands:
            if a not in recent and os.path.exists(os.path.join(ROOT, "assets", a)):
                spec["asset"] = a
                break
    LAST_THUMB = spec.get("asset")
    RED = (255, 59, 48)
    img = Image.new("RGB", (W, H), (5, 5, 7))

    # --- hero art: large, BRIGHT, right side, left edge faded out ---
    art_path = os.path.join(ROOT, "assets", spec.get("asset", ""))
    if spec.get("asset") and os.path.exists(art_path):
        art = Image.open(art_path).convert("RGB")
        scale = (H * 1.04) / art.height
        art = art.resize((int(art.width * scale) + 1, int(art.height * scale) + 1))
        art = ImageEnhance.Brightness(art).enhance(1.28)
        art = ImageEnhance.Color(art).enhance(1.12)
        ax = W - art.width + 60
        if ax < W // 3:  # very wide art: anchor right edge instead
            ax = W - art.width
        img.paste(art, (ax, -8))
        import numpy as np
        fx = max(ax, 0)
        fw = min(200, W - fx)
        if fw > 0:
            alpha = np.tile(np.linspace(255, 0, fw, dtype=np.uint8), (H, 1))
            img.paste(Image.new("RGB", (fw, H), (5, 5, 7)), (fx, 0),
                      Image.fromarray(alpha, "L"))
    d = ImageDraw.Draw(img, "RGBA")

    # --- tease text: max 2 lines, huge; line 1 white, line 2 red ---
    hook = (spec.get("hook") or "THE TEST").upper()
    words = hook.split()
    if len(words) <= 2:
        lines = [" ".join(words)]
    else:
        half = (len(words) + 1) // 2
        lines = [" ".join(words[:half]), " ".join(words[half:])]
    size = 196
    while size > 60:
        f = _font(size)
        if all(d.textlength(ln, font=f) <= 700 for ln in lines):
            break
        size -= 8
    f = _font(size)
    lh = int(size * 1.04)
    y = (H - lh * len(lines)) // 2 - 10
    for i, ln in enumerate(lines):
        d.text((52, y), ln, font=f, fill=(255, 255, 255) if i == 0 else RED,
               stroke_width=7, stroke_fill=(0, 0, 0))
        y += lh

    # --- one hand-drawn red arrow: text -> character ---
    ay = H // 2 + lh // 2 + 64
    pts = [(150, ay + 26), (300, ay + 6), (452, ay + 18)]
    d.line(pts, fill=RED, width=15, joint="curve")
    hx, hy = 452, ay + 18
    d.polygon([(hx, hy - 30), (hx + 58, hy + 8), (hx - 6, hy + 40)], fill=RED)

    img.save(out_path, "JPEG", quality=90)
    return out_path


if __name__ == "__main__":
    import json, sys
    meta = json.load(open(sys.argv[1]))
    print(make_thumbnail(meta, sys.argv[2] if len(sys.argv) > 2 else "out/thumbnail.jpg"))
