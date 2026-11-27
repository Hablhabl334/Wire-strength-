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

_THEME_FAMS = {
    "ankle": {"calf", "shin", "balance"},
    "balance": {"calf", "shin", "balance"},
    "grip": {"grip", "hang"},
    "hang": {"hang", "grip"},
    "knee": {"calf", "hip", "jump"},
    "shoulder": {"pushup", "hang"},
    "elbow": {"grip", "pushup"},
}


def _recent_thumb_assets():
    """(recent_art, hero_history) from state.json. recent_art = every
    picture shown by the last 3 episodes (their in-video art + their
    thumbnail heroes) - a new thumbnail must never repeat any of it.
    hero_history = every thumbnail hero ever used - a hero that already
    sold a click once is only a last resort."""
    recent, heroes = set(), set()
    try:
        state = json.load(open(os.path.join(ROOT, "state.json")))
        pubs = state.get("published", [])
        for entry in pubs:
            hero = entry.get("thumb")
            if not hero and entry.get("script"):
                prev = json.load(open(os.path.join(ROOT, "bank", entry["script"])))
                hero = (prev.get("thumb") or {}).get("asset")
            if hero:
                heroes.add(hero)
        for entry in pubs[-3:]:
            if entry.get("thumb"):
                recent.add(entry["thumb"])
            recent.update(entry.get("art") or [])
            if entry.get("script"):
                prev = json.load(open(os.path.join(ROOT, "bank", entry["script"])))
                a = (prev.get("thumb") or {}).get("asset")
                if a:
                    recent.add(a)
    except Exception:
        pass
    return recent, heroes


def _pick_hero(meta, spec):
    """Choose the thumbnail hero under Habl's HARD RULE (2026-11-27):
    NEVER a repeated picture. The hero must not appear anywhere in the
    last 3 episodes (thumbnail or in-video) while any fresh picture
    exists, and a picture that was already a thumbnail hero once is a
    last resort. Chain: the authored picture, the episode's own Ren
    poses, same-family poses, subject-theme poses, any own picture.
    Anatomy plates sit at the end of the chain - the character sells
    the click, exactly like the model channel."""
    authored = spec.get("asset")
    recent, heroes = _recent_thumb_assets()
    try:
        man = {it["file"]: it for it in
               json.load(open(os.path.join(ROOT, "assets", "manifest.json")))["images"]}
    except Exception:
        man = {}

    def is_pose(f):
        return f in man and man[f].get("role") in ("still", "cycle", "closeup")

    own = []
    for sc in meta.get("scenes", []):
        for a in (sc.get("poses") or []) + ([sc["asset"]] if sc.get("asset") else []):
            if a not in own:
                own.append(a)
    chain = []
    def add(f):
        if f and f not in chain and os.path.exists(os.path.join(ROOT, "assets", f)):
            chain.append(f)
    add(authored)
    for a in own:
        if is_pose(a):
            add(a)
    fams = {man[a].get("family") for a in own if a in man}
    for f in man:
        if man[f].get("family") in fams and is_pose(f):
            add(f)
    theme_fams = set()
    text = (meta.get("title", "") + " " + meta.get("badge", "")).lower()
    for token, fs in _THEME_FAMS.items():
        if token in text:
            theme_fams.update(fs)
    for f in man:
        if man[f].get("family") in theme_fams and is_pose(f):
            add(f)
    for a in own:
        add(a)
    if not chain:
        return authored
    clean = [f for f in chain if f not in recent]
    if clean:
        for f in clean:
            if f not in heroes:
                return f
        return clean[0]
    for f in chain:
        if f not in heroes:
            return f
    return chain[0]


def make_thumbnail(meta, out_path):
    """GAP 9 thumbnail discipline (measured on Rep Theory): black
    background, ONE huge bright pose, at most 2 lines of huge tease
    text (white, then red), ONE hand-drawn red arrow. No number, no
    badge chip, no brand bar - one idea only."""
    global LAST_THUMB
    spec = derive_spec(meta)
    spec["asset"] = _pick_hero(meta, spec)
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

    # --- tease text: EXACTLY the model channel's grammar - at most 2
    # words (the hook's punch lands last, so the last 2 words), ONE
    # line, first word white, second word red ---
    hook = (spec.get("hook") or "THE TEST").upper()
    words = hook.split()[-2:]
    size = 196
    while size > 60:
        f = _font(size)
        if d.textlength(" ".join(words), font=f) <= 700:
            break
        size -= 8
    f = _font(size)
    y = (H - int(size * 1.04)) // 2 - 10
    x = 52
    for i, w in enumerate(words):
        d.text((x, y), w, font=f, fill=(255, 255, 255) if i == 0 else RED,
               stroke_width=7, stroke_fill=(0, 0, 0))
        x += d.textlength(w + " ", font=f)
    lh = int(size * 1.04)

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
