"""Wire Strength renderer v5. NO AI/LLM calls anywhere.
v5 = v4 + Habl's 95% note on sample #010: in the TALKING scenes, a NEW
piece of content must appear every 5-10 seconds - not just a label on
the same static picture. Two new beat kinds do that, code-only:
- "swap": {"at": phrase, "kind": "swap", "asset": "..."} swaps the
  main picture for the rest of the scene (art scenes). The picture
  itself changes, so the scene is never one static image.
- "fact": {"at": phrase, "kind": "fact", "title": ..., "lines": [...]}
  a large content card (headline + 2 lines) - a new fact/diagram
  block, not a chip.
Everything else (voice, music, cadence, HUD, one side per workout)
is inherited from v4 unchanged.
Upgrades over v3, from Habl's review + the deep top-8 measurements:
- VOICE: Kokoro-82M offline (near-human) is now the primary engine (render.tts),
  Edge second, Piper last-resort. Voice bus EQ + compression, -14 LUFS master.
- MUSIC: three real Creative Commons tracks banked in assets/music/
  (Kevin MacLeod, CC BY 4.0 - attribution auto-added to descriptions).
  Scenes pick dark/calm/drive; the bed is built per video with crossfades
  and ducked under the voice. No more synth loop.
- CADENCE: phrases are <=5 words (~1.5s each), card lines REVEAL as they are
  spoken about, a glow pulse + micro-sway keep every frame alive, and a
  section progress bar fills. Target: something new at least every ~2s.
- PAUSES: 0.22s between phrases, +0.3s after sentences, and a scene can set
  lead_pause (music-only breathing room at section changes, like theirs).
- ANGLES: anim scenes can carry several pose sets ("angles") and switch
  camera angle every few phrases (side / front / back / 45 degrees).
HUD, cards and TIMER scenes are inherited from render2/render3."""
import json, math, os, re, subprocess, sys
from collections import Counter
import numpy as np
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render import tts, dur, run, ROOT
from render2 import hud, fit_cover, timer_segment, F
from render2 import CYAN, GOLD, RED, WHITE, GREY, DARK, W, H
from render3 import phrase_png

SR = 44100
FPS_A = 8

def phrases5(text):
    if "|" in text:
        return [p.strip() for p in text.split("|") if p.strip()]
    import re
    out = []
    for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
        words = sent.split()
        while len(words) > 5:
            cut = 5
            for i in range(5, 2, -1):
                if words[i - 1].endswith((",", ";", ":")):
                    cut = i; break
            out.append(" ".join(words[:cut])); words = words[cut:]
        if words: out.append(" ".join(words))
    return out

def _parse_bands(sub):
    """Parse a bignum card's sub line into scale bands, e.g.
    'under 15: untrained ankles - over 60: elite control' or the 3-band
    'under 5: untrained - 5 to 15: building - over 15: wired'.
    Returns [(lo, hi_or_None, label), ...] or None when the line does
    not carry a usable scale (the chart is then simply not drawn)."""
    if not sub:
        return None
    bands = []
    for seg in sub.split(" - "):
        m = re.match(r"\s*under\s+(\d+)\s*:\s*(.+)", seg, re.I)
        if m:
            bands.append((0, int(m.group(1)), m.group(2).strip())); continue
        m = re.match(r"\s*(\d+)\s*to\s*(\d+)\s*:\s*(.+)", seg, re.I)
        if m:
            bands.append((int(m.group(1)), int(m.group(2)), m.group(3).strip())); continue
        m = re.match(r"\s*over\s+(\d+)\s*:\s*(.+)", seg, re.I)
        if m:
            bands.append((int(m.group(1)), None, m.group(2).strip())); continue
        return None
    return bands if len(bands) >= 2 else None

def _draw_band_steps(d, bands, big_text):
    """GAP 4 instrument: an ascending step-chart of the card's own scale
    bands (Rep Theory's 2->5->10s staircase) with a slider track under
    it and a gold marker where the card's big number - THE LINE - falls.
    Geometry stays above y=990: the hud checklist bar owns y>=1016."""
    x0, x1, base = 140, W - 140, 950
    n = len(bands)
    cols = [(200, 60, 60), GOLD, CYAN] if n == 3 else [(200, 60, 60), CYAN]
    sw = (x1 - x0) // n
    m = re.match(r"\s*~?(\d+)", big_text or "")
    line_v = int(m.group(1)) if m else None
    for i, (lo, hi, label) in enumerate(bands):
        hgt = 64 + i * 58
        xa, xb = x0 + i * sw + 6, x0 + (i + 1) * sw - 6
        d.rounded_rectangle([xa, base - hgt, xb, base], 10, fill=(26, 26, 26), outline=cols[i], width=4)
        rng = f"UNDER {hi}" if lo == 0 else (f"OVER {lo}" if hi is None else f"{lo}-{hi}")
        d.text((xa + 22, base - hgt + 14), rng, font=F(fit_size(rng, 40, sw - 44)), fill=cols[i])
        lab = label.upper()
        lf = F(fit_size(lab, 30, sw - 44, False), False)
        if hgt >= 120:
            d.text((xa + 22, base - hgt + 66), lab, font=lf, fill=WHITE)
        else:
            # short step: the label rides above the box instead of inside
            d.text((xa + 22, base - hgt - 40), lab, font=lf, fill=cols[i])
        if line_v is not None and lo <= line_v and (hi is None or line_v < hi):
            tag = "THE LINE"
            tw = d.textlength(tag, font=F(28))
            d.text((xb - tw - 20, base - hgt + 16), tag, font=F(28), fill=GOLD)
    # slider track under the steps, gold triangle at THE LINE's value
    top = bands[-1][0]
    scale_max = max(top * 1.3, 1)
    ty = base + 22
    d.rounded_rectangle([x0, ty, x1, ty + 14], 7, fill=(40, 40, 40))
    for i, (lo, hi, label) in enumerate(bands):
        xa = x0 + (x1 - x0) * lo / scale_max
        xb = x1 if hi is None else x0 + (x1 - x0) * hi / scale_max
        d.rounded_rectangle([int(xa), ty, int(xb), ty + 14], 7, fill=cols[i])
    if line_v is not None and 0 <= line_v <= scale_max:
        mx = int(x0 + (x1 - x0) * line_v / scale_max)
        d.polygon([(mx - 11, ty - 18), (mx + 11, ty - 18), (mx, ty - 3)], fill=GOLD)

def _draw_stopwatch(d, cx, cy, r):
    """v6 device (L-sit video): a stopwatch face for a number that is
    a time - white ring, tick marks, red hand, red crown button."""
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=WHITE, width=9)
    d.rectangle([cx - 15, cy - r - 30, cx + 15, cy - r + 2], fill=GREY)
    d.rounded_rectangle([cx - 36, cy - r - 54, cx + 36, cy - r - 28], 6, fill=(200, 60, 60))
    for k in range(12):
        a = math.radians(k * 30)
        d.line([cx + (r - 18) * math.sin(a), cy - (r - 18) * math.cos(a),
                cx + (r - 38) * math.sin(a), cy - (r - 38) * math.cos(a)], fill=GREY, width=5)
    a = math.radians(50)
    d.line([cx, cy, cx + (r - 46) * math.sin(a), cy - (r - 46) * math.cos(a)], fill=(200, 60, 60), width=9)
    d.ellipse([cx - 13, cy - 13, cx + 13, cy + 13], fill=WHITE)

def card_image4(scene, reveal=99):
    im = Image.new("RGB", (W, H), DARK); d = ImageDraw.Draw(im)
    kind = scene["card"]
    if kind == "bignum":
        d.text((140, 300), scene["big"], font=F(230), fill=CYAN)
        if reveal >= 1: d.text((146, 580), scene["label"], font=F(64), fill=WHITE)
        if reveal >= 1 and re.search(r"\bSEC\b|\bSECONDS?\b",
                                     (scene.get("big", "") + " " + scene.get("label", "")).upper()):
            _draw_stopwatch(d, W - 350, 350, 140)
        if reveal >= 2:
            d.text((146, 680), scene.get("sub", ""), font=F(38, False), fill=GREY)
            bands = _parse_bands(scene.get("sub", ""))
            if bands:
                _draw_band_steps(d, bands, scene.get("big", ""))
    elif kind == "study":
        d.rounded_rectangle([240, 200, W - 240, 820], 24, fill=(24, 24, 24), outline=GREY, width=2)
        d.rectangle([240, 200, W - 240, 290], fill=RED)
        d.text((290, 224), scene["head"], font=F(40), fill=WHITE)
        y = 350
        for ln in scene["lines"][:reveal]:
            d.text((290, y), ln, font=F(44, False), fill=WHITE); y += 74
        if reveal >= len(scene["lines"]):
            d.text((290, 740), scene.get("foot", ""), font=F(32, False), fill=GOLD)
    elif kind == "layers":
        d.text((140, 130), scene["title"], font=F(64), fill=WHITE)
        y = 300
        for name, note, pct, colname in scene["layers"][:reveal]:
            col = CYAN if colname == "cyan" else (WHITE if colname == "white" else GREY)
            bw = int(1300 * pct / 100)
            d.rounded_rectangle([140, y, 140 + bw, y + 110], 16, fill=(30, 30, 30), outline=col, width=4)
            d.text((170, y + 18), name, font=F(52), fill=col)
            d.text((170, y + 122), note, font=F(32, False), fill=GREY)
            y += 220
    return im

def glow_overlay(t):
    a = int(10 + 8 * math.sin(2 * math.pi * t / 2.4))
    im = Image.new("RGBA", (W, H), (0, 229, 255, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([W // 2 - 700, H // 2 - 500, W // 2 + 700, H // 2 + 500], fill=(0, 229, 255, max(0, a)))
    return im

# ---------- visual BEATS: a new content element every 5-10s ----------
# Scene field "beats": [{"at": phrase_index, "kind": ..., ...}] - each beat
# appears when its phrase starts and stays. Kinds: chip (label), stat (big
# number + label), bars (comparison), pip (inset picture), mark (check/cross),
# swap (v5: change the main picture), fact (v5: large content card).
def _beat_xy(pos, w, h):
    return {"tr": (W - 48 - w, 128), "br": (W - 48 - w, min(H - 470, 812 - h)),
            "bl": (48, min(H - 470, 812 - h)), "mr": (W - 48 - w, 400),
            "ml": (48, 400)}.get(pos, (W - 48 - w, 128))

_fit_probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
def fit_size(text, size, max_w, bold=True):
    """Shrink the font until the text fits max_w (cards have fixed widths,
    so an unmeasured label would paint past the card edge or under a bar)."""
    s = size
    while s > 12 and _fit_probe.textlength(text, font=F(s, bold)) > max_w:
        s -= 2
    return s

def current_swap(beats, j, default_asset):
    """v5: latest swap beat at or before phrase j wins, else the scene asset."""
    asset = default_asset
    for b in beats:
        if b.get("kind") == "swap" and j >= b.get("at", 0):
            asset = b.get("asset", asset)
    return asset

# ---------- episode art rotation ----------
# Bank scripts lean on a few favourite plates per episode (median 3 distinct
# images). The first use of any picture is the author's choice and stays;
# every REPEAT use inside the same episode is rotated to the least-used
# picture of the same role (anatomy -> anatomy, still -> still, ...),
# preferring the same family. Deterministic: manifest order breaks ties.
_MANIFEST = None
_USED = Counter()
_RECENT = set()   # pictures used by the last few episodes (from state.json)
LAST_USED = []    # pictures this episode used (main.py records them)
LAST_CHAPTERS = []  # [(start_sec, section)] on the real assembled timeline
                    # (main.py turns them into YouTube chapters)
LAST_MUSIC = []   # music titles this episode used, in order of first use
                  # (main.py passes them to upload.py for the CC BY credit)

# Music rotation (MUSIC_EXPANSION.md): a pool of 5 tracks per mood, the
# original bed at slot 0. Deterministic by episode id - every mood resolves
# to pool[int(id) % 5], the same slot across moods within one episode, so
# consecutive episodes never share a bed and a track repeats only every
# 5 episodes. Stateless: re-renders reproduce the same episode sound.
# The mix downstream is LOCKED (0.16 volume, per-scene auto-cut,
# -stream_loop -1 + atrim + 0.8s fades, -14 LUFS master) - only the file
# each mood resolves to changes.
MUSIC_POOLS = {
    "calm": ["bed_calm.mp3", "calm_sovereign.mp3", "calm_clean-soul.mp3",
             "calm_sincerely.mp3", "calm_beauty-flow.mp3"],
    "drive": ["bed_drive.mp3", "drive_funkorama.mp3", "drive_loopster.mp3",
              "drive_style-funk.mp3", "drive_got-funk.mp3"],
    "dark": ["bed_dark.mp3", "dark_crypto.mp3", "dark_stay-the-course.mp3",
             "dark_lightless-dawn.mp3", "dark_oppressive-gloom.mp3"],
}
MUSIC_TITLES = {
    "bed_calm.mp3": "Wallpaper", "calm_sovereign.mp3": "Sovereign",
    "calm_clean-soul.mp3": "Clean Soul", "calm_sincerely.mp3": "Sincerely",
    "calm_beauty-flow.mp3": "Beauty Flow",
    "bed_drive.mp3": "Cold Funk", "drive_funkorama.mp3": "Funkorama",
    "drive_loopster.mp3": "Loopster", "drive_style-funk.mp3": "Style Funk",
    "drive_got-funk.mp3": "Got Funk",
    "bed_dark.mp3": "Deep and Dirty", "dark_crypto.mp3": "Crypto",
    "dark_stay-the-course.mp3": "Stay the Course",
    "dark_lightless-dawn.mp3": "Lightless Dawn",
    "dark_oppressive-gloom.mp3": "Oppressive Gloom",
}

# Gap 3: annotation ON the picture. assets/anchors.json (authored at
# build time) maps asset file -> body part -> [fx, fy] in SOURCE-image
# fractions. At render time the point is mapped through the same
# cover-crop the picture itself gets, so the ring lands on the joint in
# frame space; points the crop hides are skipped automatically.
_ANCHORS = None
_PART_ALIAS = {"toes": "toe", "fingers": "finger", "grip": "hand",
               "grips": "hand", "tendon": "achilles", "tendons": "achilles",
               "feet": "foot", "hands": "hand", "ankles": "ankle",
               "knees": "knee", "wrists": "wrist", "elbows": "elbow",
               "shoulders": "shoulder", "hips": "hip", "calves": "calf",
               "heels": "heel", "arms": "arm"}
_PART_LABEL = {"achilles": "ACHILLES TENDON", "back": "LOWER BACK",
               "toe": "TOES", "finger": "FINGERS"}

def _anchors():
    global _ANCHORS
    if _ANCHORS is None:
        try:
            _ANCHORS = json.load(open(os.path.join(ROOT, "assets", "anchors.json")))
        except Exception:
            _ANCHORS = {}
    return _ANCHORS

# ---------- GAP 5: study citations (Rep Theory's receipt format) -------
# assets/citations.json holds REAL, verified studies (authors, year,
# journal, sample - checked against the published records at build
# time). Once per episode, the fact card whose scene best matches a
# study's topic keys grows a citation block: red STUDY pill, the cite,
# the journal, the sample pill and the study's own finding. Nothing is
# invented at render time - if no study matches, no card is extended.
_CITATIONS = None
_EP_CITE = None
_EP_CITE_SCENE = -1
_EP_CITE_AT = -1
_EP_CITE_TITLE = None

def _citations():
    global _CITATIONS
    if _CITATIONS is None:
        try:
            _CITATIONS = json.load(open(os.path.join(ROOT, "assets", "citations.json")))
        except Exception:
            _CITATIONS = []
    return _CITATIONS

def _pick_citation(script):
    global _EP_CITE, _EP_CITE_SCENE, _EP_CITE_AT, _EP_CITE_TITLE
    _EP_CITE, _EP_CITE_SCENE, _EP_CITE_AT, _EP_CITE_TITLE = None, -1, -1, None
    scenes = [sc for sc in script.get("scenes", []) if sc.get("type") != "anim"]
    # Stage 1: the EPISODE's topic picks the study - a citation must
    # belong to what the whole video is about, not win on one stray
    # word in one scene.
    best_cite, best_ep = None, 2  # require >= 3 episode-level key hits
    for cite in _citations():
        keys = set(cite.get("keys", []))
        if not keys:
            continue
        hits = 0
        for sc in scenes:
            nw = set(re.findall(r"[a-z]+", sc.get("narration", "").lower()))
            hits += len(keys & nw)
            for b in sc.get("beats", []):
                if b.get("kind") == "fact":
                    fw = set(re.findall(r"[a-z]+", (b.get("title", "") + " " +
                                 " ".join(b.get("lines", []))).lower()))
                    hits += 2 * len(keys & fw)
        if hits > best_ep:
            best_cite, best_ep = cite, hits
    if best_cite is None:
        return
    # Stage 2: inside that study's topic, the fact card whose scene
    # matches it best carries the citation.
    keys = set(best_cite.get("keys", []))
    best = None  # (score, -scene_idx, scene_idx, beat)
    for si, sc in enumerate(script.get("scenes", [])):
        if sc.get("type") == "anim":
            continue
        facts = [b for b in sc.get("beats", []) if b.get("kind") == "fact"]
        if not facts:
            continue
        narr_words = set(re.findall(r"[a-z]+", sc.get("narration", "").lower()))
        for b in facts:
            fact_words = set(re.findall(r"[a-z]+", (b.get("title", "") + " " +
                                 " ".join(b.get("lines", []))).lower()))
            score = 2 * len(keys & fact_words) + len(keys & narr_words)
            if score >= 1:
                cand = (score, -si, si, b)
                if best is None or cand[:2] > best[:2]:
                    best = cand
    if best:
        _EP_CITE = best_cite
        _EP_CITE_SCENE = best[2]
        _EP_CITE_AT = best[3].get("at", 0)
        _EP_CITE_TITLE = best[3].get("title")

def _fact_visible(beats, j):
    """True when a fact card is among the beats on screen at phrase j.
    Mirrors draw_beats exactly: swap beats are never drawn, and the 2
    most recent remaining beats stay visible. A focus ring must never
    fire under a card - the annotation would land on the card's text
    instead of the joint."""
    vis = [b for b in beats if b.get("kind") != "swap" and b.get("at", 0) <= j][-2:]
    return any(b.get("kind") == "fact" for b in vis)

def _focus_plan(phrase_tags, beats, scene, resolved, sizes, bounds):
    """phrase index -> (part, frame_x, frame_y): when the narration names
    a body part that has an anchor on the picture currently on screen,
    that joint gets annotated. At most one focus per part per scene and
    at least 5s between focuses, so it never turns into clutter."""
    plan = {}
    last_t, seen = -10.0, set()
    for j, tags in enumerate(phrase_tags):
        if bounds[j] - last_t < 5.0:
            continue
        if _fact_visible(beats, j):
            continue
        cur = resolved.get(current_swap(beats, j, scene["asset"]), scene["asset"])
        anch = _anchors().get(cur)
        if not anch:
            continue
        iw, ih = sizes.get(cur, (W, H))
        s = max(W / iw, H / ih)
        ox, oy = (iw * s - W) / 2, (ih * s - H) / 2
        for w in sorted(tags):
            part = _PART_ALIAS.get(w, w)
            if part in anch and part not in seen:
                fx, fy = anch[part]
                px, py = fx * iw * s - ox, fy * ih * s - oy
                if 60 <= px <= W - 60 and 130 <= py <= H - 210:
                    plan[j] = (part, int(px), int(py))
                    seen.add(part); last_t = bounds[j]
                    break
    return plan

def _draw_focus(fr, part, px, py, tt, age=9.0):
    # v6.1: the model's target rings brighten in over ~1s, they do not
    # snap on - scale the ink up from the dark ground while age < 0.8s.
    f = 1.0 if age >= 0.8 else max(0.15, age / 0.8)
    def C(c):
        return tuple(int(v * f) for v in c)
    d = ImageDraw.Draw(fr)
    r = 36 + int(5 * math.sin(tt * 5.0))
    d.ellipse([px - r, py - r, px + r, py + r], outline=C(RED), width=6)
    d.ellipse([px - r - 13, py - r - 13, px + r + 13, py + r + 13], outline=C(WHITE), width=2)
    d.ellipse([px - 5, py - 5, px + 5, py + 5], fill=C(RED))
    label = _PART_LABEL.get(part, part.upper())
    fnt = F(30)
    tw = d.textlength(label, font=fnt)
    left_side = px < W / 2
    lx = px + 130 if left_side else px - 130 - int(tw) - 36
    ly = max(120, py - 120)
    x0, y0 = px + (62 if left_side else -62), py - 18
    x1, y1 = lx + (0 if left_side else int(tw) + 36), ly + 24
    steps = 26
    for k in range(0, steps, 2):
        xa = x0 + (x1 - x0) * k / steps; ya = y0 + (y1 - y0) * k / steps
        xb = x0 + (x1 - x0) * (k + 1) / steps; yb = y0 + (y1 - y0) * (k + 1) / steps
        d.line([xa, ya, xb, yb], fill=C(WHITE), width=3)
    # v6: the model's annotations end in an arrow, not a bare line -
    # a bold orange arrowhead where the leader meets the ring.
    ang = math.atan2(y0 - y1, x0 - x1)
    ah = 27
    d.polygon([(x0, y0),
               (x0 - ah * math.cos(ang - 0.42), y0 - ah * math.sin(ang - 0.42)),
               (x0 - ah * math.cos(ang + 0.42), y0 - ah * math.sin(ang + 0.42))],
              fill=C((255, 140, 0)))
    d.rounded_rectangle([lx, ly, lx + tw + 36, ly + 48], 8, fill=(8, 10, 12), outline=C(CYAN), width=2)
    d.text((lx + 18, ly + 8), label, font=fnt, fill=C(WHITE))
def _manifest():
    global _MANIFEST
    if _MANIFEST is None:
        m = json.load(open(os.path.join(ROOT, "assets", "manifest.json")))
        _MANIFEST = {im["file"]: im for im in m["images"]}
    return _MANIFEST

def _rotate(asset, context=None):
    man = _manifest()
    if asset not in man:
        return asset
    if _USED[asset] == 0 and asset not in _RECENT:
        _USED[asset] += 1
        return asset
    if _USED[asset] == 0 and asset in _RECENT:
        # HARD RULE (Habl, 2026-11-27): even a FIRST use this episode is
        # a repeat if the last episodes showed it -- rotate away to a
        # fresh same-role picture, else a fresh same-family one. Only
        # when the whole family/role pool is recent does it stay.
        role, fam = man[asset].get("role"), man[asset].get("family")
        order = {f: i for i, f in enumerate(man)}
        preds = (lambda im: im.get("role") == role,
                 lambda im: im.get("family") == fam
                 and im.get("role") in ("still", "closeup", "anatomy", "cycle"),
                 lambda im: im.get("role") in ("still", "closeup", "cycle")
                 and context is not None and _score(im["file"], context) >= 2)
        for pred in preds:
            cands = [f for f, im in man.items()
                     if pred(im) and f != asset and f not in _RECENT and _USED[f] < 2]
            if cands:
                cands.sort(key=lambda f: (-((_score(f, context) if context else 0)),
                                          _USED[f],
                                          0 if man[f].get("family") == fam else 1,
                                          order[f]))
                pick = cands[0]
                _USED[pick] += 1
                print(f"art rotation (recent): {asset} -> {pick}")
                return pick
        _USED[asset] += 1
        return asset
    role, fam = man[asset].get("role"), man[asset].get("family")
    order = {f: i for i, f in enumerate(man)}
    cands = [f for f, im in man.items() if im.get("role") == role and f != asset]
    fresh = [f for f in cands if _USED[f] < 2]
    if fresh:
        cands = fresh
    # HARD RULE: never rotate onto a picture the last episodes showed
    # while a fresh alternative exists.
    nonrecent = [f for f in cands if f not in _RECENT]
    if nonrecent:
        cands = nonrecent
    if not cands:
        _USED[asset] += 1
        return asset
    # Repeats rotate to the picture that best matches what the scene is
    # SAYING (context = the scene's word tags); pictures the last episodes
    # already used are penalised, least-used breaks ties.
    cands.sort(key=lambda f: (-((_score(f, context) if context else 0) - (2 if f in _RECENT else 0)),
                              _USED[f], 0 if man[f].get("family") == fam else 1, order[f]))
    pick = cands[0]
    _USED[pick] += 1
    print(f"art rotation: {asset} already used -> {pick}")
    return pick

# ---------- opening-frame variety across episodes ----------
# Consecutive episodes often author the same scene-0 picture (episodes 1 and
# 2 both opened on the balance-test plate). If the PREVIOUS episode (by
# number) opened on the same picture, this episode's opener shifts to the
# next picture of the same family (else same role) in manifest order.
_EP_NUM = 0
def _opener_shift(asset):
    if _EP_NUM <= 1 or not asset:
        return asset
    prev_path = os.path.join(ROOT, "bank", f"{_EP_NUM - 1:03d}.json")
    if not os.path.exists(prev_path):
        return asset
    try:
        prev = json.load(open(prev_path))
        psc = prev["scenes"][0]
        prev_asset = psc.get("asset") or psc.get("art")
    except Exception:
        return asset
    if prev_asset != asset:
        return asset
    man = _manifest()
    if asset not in man:
        return asset
    role, fam = man[asset].get("role"), man[asset].get("family")
    order = list(man)
    pool = [f for f in order if man[f].get("family") == fam and f != asset] or \
           [f for f in order if man[f].get("role") == role and f != asset]
    if not pool:
        return asset
    i = order.index(asset)
    pick = min(pool, key=lambda f: (order.index(f) - i) % len(order))
    print(f"opener shift: ep {_EP_NUM} would repeat ep {_EP_NUM - 1}'s opener {asset} -> {pick}")
    return pick

def _base_resolve(asset, context=None):
    """Scene BASE pictures obey the cross-episode rule too (Habl,
    2026-11-26): if the authored base was shown by a recent episode,
    open the scene on the best-matching same-role picture that was NOT
    in a recent episode; if every alternative is recent too, keep the
    authored base (the repeat stays rare, never forced)."""
    man = _manifest()
    if asset in _RECENT and asset in man:
        role, fam = man[asset].get("role"), man[asset].get("family")
        order = {f: i for i, f in enumerate(man)}
        cands = [f for f, im in man.items()
                 if im.get("role") == role and f != asset and f not in _RECENT]
        if cands:
            cands.sort(key=lambda f: (-(_score(f, context) if context else 0),
                                      _USED[f],
                                      0 if man[f].get("family") == fam else 1,
                                      order[f]))
            pick = cands[0]
            _USED[pick] += 1
            print(f"base obey-recent: {asset} -> {pick}")
            return pick
        # Same-role pool exhausted (e.g. every anatomy plate aired in the
        # last episodes): a fresh picture from the same FAMILY in another
        # role still beats repeating the authored base.
        fams = [f for f, im in man.items()
                if im.get("family") == fam
                and im.get("role") in ("still", "closeup", "anatomy", "cycle")
                and f != asset and f not in _RECENT and _USED[f] < 2]
        if fams:
            fams.sort(key=lambda f: (-(_score(f, context) if context else 0),
                                     _USED[f], order[f]))
            pick = fams[0]
            _USED[pick] += 1
            print(f"base obey-recent (family): {asset} -> {pick}")
            return pick
    return _rotate(asset, context)

def _auto_pick(cur, shown):
    """Least-used same-role picture != cur and not yet shown this scene
    (auto-refresh target). Same family preferred, manifest order breaks ties."""
    man = _manifest()
    if cur not in man:
        return None
    role, fam = man[cur].get("role"), man[cur].get("family")
    order = {f: i for i, f in enumerate(man)}
    cands = [f for f, im in man.items()
             if im.get("role") == role and f != cur and f not in shown]
    if not cands:
        return None
    nonrecent = [f for f in cands if f not in _RECENT]
    if nonrecent:
        cands = nonrecent
    else:
        # HARD RULE: every same-role candidate is a repeat from the last
        # episodes (the anatomy role runs dry exactly like this - all 11
        # plates appeared in eps 1-3). Widen to ANY fresh picture before
        # ever repeating a recent one; plates stay last resort inside the
        # widened pool.
        wide = [f for f, im in man.items()
                if im.get("role") in ("still", "closeup", "cycle", "anatomy")
                and f != cur and f not in shown and f not in _RECENT]
        if wide:
            wide.sort(key=lambda f: (_USED[f],
                                     0 if man[f].get("family") == fam else 1,
                                     1 if man[f].get("role") == "anatomy" else 0,
                                     order[f]))
            return wide[0]
    cands.sort(key=lambda f: (1 if f in _RECENT else 0, _USED[f], 0 if man[f].get("family") == fam else 1, order[f]))
    return cands[0]

# ---------- semantic picture matching ----------
# Every picture carries word tags (from its filename + family + a small hand
# map for the anatomy plates and key poses). Narration is tagged with the
# same vocabulary, and the picture on screen follows the words: when the
# narration moves to a topic another picture describes better, the picture
# swaps to it. Pure keyword scoring -- deterministic, code only, no AI.
_EXTRA_TAGS = {
    "nerve_pathway_plate.webp": {"signal", "brain", "message", "fire", "firing", "electric", "pathway"},
    "ankle_ligament_plate.webp": {"ankle", "stability", "stable", "sprain", "balance", "ligament"},
    "plantar_fascia_plate.webp": {"foot", "sole", "heel", "arch", "fascia"},
    "tibialis_plate.webp": {"shin", "ankle", "foot", "tibialis"},
    "achilles_anatomy_plate.webp": {"ankle", "heel", "tendon", "calf", "achilles"},
    "ren_achilles_profile.webp": {"ankle", "heel", "tendon", "achilles"},
    "ren_eccentric_drop.webp": {"heel", "calf", "ankle", "tendon", "drop"},
    "ren_grip_closeup.webp": {"forearm", "grip", "tendon", "hand", "fingers"},
    "ren_pinch_hold.webp": {"grip", "pinch", "fingers", "forearm"},
    "ren_balance_test.webp": {"ankle", "foot", "stand", "standing", "leg", "balance"},
    "ren_calf_raise.webp": {"ankle", "heel", "foot", "calf"},
    "ren_calf_raise_front.webp": {"ankle", "heel", "foot", "calf"},
    "ren_toe_raise.webp": {"foot", "toe", "shin", "ankle", "tibialis"},
    "ren_horse_stance.webp": {"stand", "standing", "leg", "stance"},
    "ren_jump_peak.webp": {"jump", "vertical", "power", "explosive"},
    "ren_sprint.webp": {"run", "speed", "fast", "leg"},
    "ren_leg_swing.webp": {"leg", "swing", "hip"},
    "knee_anatomy_plate.webp": {"knee", "joint", "leg"},
    "ren_split_squat_top.webp": {"knee", "leg", "lunge", "squat"},
    "ren_split_squat_bottom.webp": {"knee", "leg", "lunge", "squat"},
    "hip_joint_plate.webp": {"hip", "joint"},
    "ren_grip_closeup.webp": {"hand", "finger", "grip"},
    "ren_finger_hang.webp": {"finger", "hand", "hang", "grip"},
    "ren_finger_spread.webp": {"finger", "hand"},
    "ren_thumb_press.webp": {"thumb", "hand", "finger"},
    "ren_pinch_hold.webp": {"finger", "thumb", "hand", "grip"},
    "ren_farmer_carry.webp": {"grip", "hand", "carry", "walk"},
    "ren_grip_squeeze.webp": {"hand", "grip", "squeeze"},
    "forearm_anatomy_plate.webp": {"forearm", "arm", "grip", "wrist"},
    "ren_wrist_lever.webp": {"wrist", "forearm", "hand"},
    "ren_tabletop_press.webp": {"wrist", "hand", "press"},
    "spine_anatomy_plate.webp": {"spine", "back", "posture"},
    "ren_forward_fold.webp": {"back", "hamstring", "fold", "stretch"},
    "shoulder_anatomy_plate.webp": {"shoulder", "joint"},
    "ren_wall_slide.webp": {"shoulder", "arm", "wall"},
    "elbow_anatomy_plate.webp": {"elbow", "joint", "arm"},
    "ren_neck_turn.webp": {"neck", "turn", "head"},
    "ren_neck_hold.webp": {"neck", "head"},
}
_SYN = {"feet": "foot", "ankles": "ankle", "nerves": "nerve", "signals": "signal",
        "calves": "calf", "knees": "knee", "toes": "toe", "fingers": "finger",
        "legs": "leg", "arms": "arm", "hands": "hand", "heels": "heel",
        "pushing": "pushup", "push": "pushup", "pushups": "pushup",
        "hanging": "hang", "jumps": "jump", "jumping": "jump",
        "running": "run", "stands": "stand", "stood": "stand",
        "gripping": "grip", "squeezing": "squeeze", "holding": "hold",
        "holds": "hold", "raises": "raise", "raising": "raise",
        "tendons": "tendon", "ligaments": "ligament", "muscles": "muscle"}
_WEAK = {"forward", "back", "front", "top", "mid", "bottom", "side", "peak",
         "active", "relaxed", "tuck", "weak", "sag", "up", "down"}
_IMG_TAGS = None
def _img_tags():
    global _IMG_TAGS
    if _IMG_TAGS is None:
        tags = {}
        for f, im in _manifest().items():
            primary = set(f.replace(".webp", "").split("_")) - {"ren"} - _WEAK
            secondary = set(_EXTRA_TAGS.get(f, set()))
            if im.get("family"):
                secondary.add(im["family"])
            tags[f] = (primary, secondary)
        _IMG_TAGS = tags
    return _IMG_TAGS

def _text_tags(text):
    return {_SYN.get(w, w) for w in re.findall(r"[a-z]+", text.lower())}

def _score(asset, tagset):
    """Weighted overlap: a word in the picture's own NAME (nerve in
    nerve_pathway_plate) counts double vs a hand-added association
    (ankle on a calf-raise picture) -- so 'ankle nerves' picks the nerve
    plate, not the calf picture."""
    if not tagset:
        return 0
    primary, secondary = _img_tags().get(asset, (set(), set()))
    return 2 * len(primary & tagset) + len(secondary & tagset)

_POOL_ROLES = {"still", "anatomy", "closeup", "cycle"}
def _match_in_pool(pool, tagset, exclude, context=None):
    """The within-episode selection over one candidate pool: an unseen
    picture wins when it matches the words (score >= 2); a picture shown
    this episode may return only if it clearly out-matches (by 2+) and
    has not already appeared twice."""
    man = _manifest()
    order = {f: i for i, f in enumerate(man)}
    cur_fam = man.get(exclude, {}).get("family")
    if not pool:
        return None, 0
    def eff(f):
        return _score(f, tagset)
    def key(f):
        return (-eff(f), -(_score(f, context) if context else 0),
                0 if man[f].get("family") == cur_fam else 1, _USED[f], order[f])
    unseen = sorted((f for f in pool if _USED[f] == 0), key=key)
    seen = sorted((f for f in pool if 0 < _USED[f] < 2), key=key)
    if unseen and eff(unseen[0]) >= 2:
        return unseen[0], eff(unseen[0])
    if seen and eff(seen[0]) >= 2 and (not unseen or eff(seen[0]) >= eff(unseen[0]) + 2):
        return seen[0], eff(seen[0])
    if unseen:
        return unseen[0], eff(unseen[0])
    if seen:
        return seen[0], eff(seen[0])
    return None, 0

def _best_match(tagset, exclude, context=None):
    """Best picture for these words (never `exclude`). HARD RULE (Habl,
    2026-11-27): a picture shown by any of the last 5 episodes NEVER
    comes back while a fresh picture exists -- the fresh pool is matched
    first, and a recent picture can only win when the fresh pool is
    completely empty."""
    man = _manifest()
    pool = [f for f, im in man.items()
            if im.get("role") in _POOL_ROLES and f != exclude]
    if not pool:
        return None, 0
    fresh = [f for f in pool if f not in _RECENT]
    if fresh:
        return _match_in_pool(fresh, tagset, exclude, context)
    return _match_in_pool(pool, tagset, exclude, context)

def _prev_opener():
    if _EP_NUM <= 1:
        return None
    try:
        prev = json.load(open(os.path.join(ROOT, "bank", f"{_EP_NUM - 1:03d}.json")))
        sc0 = prev["scenes"][0]
        return sc0.get("asset") or sc0.get("art")
    except Exception:
        return None

def _beat_fade(age):
    """v6.1 (measured from the model by pixel analysis): elements do
    NOT grow from small and never bounce - they fade in fast, in place
    (small widgets ~0.25s, pills/cards ~0.7s; 0.35s is our middle)."""
    if age is None or age >= 0.35:
        return 1.0
    return max(0.0, age / 0.35)

def _pop_paste(fr, layer, box, fade):
    x, y, w, h = box
    crop = layer.crop((x, y, x + w, y + h))
    if fade < 1.0:
        a = crop.split()[3].point(lambda v: int(v * fade))
        crop.putalpha(a)
    fr.paste(crop, (x, y), crop)

def draw_beats(fr, beats, j, scene_idx=None, tt=None, bounds=None):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer, "RGBA")
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    visible = [b for b in beats if b.get("kind") != "swap" and j >= b.get("at", 0)][-2:]
    for b in visible:
        kind = b["kind"]; pos = b.get("pos", "tr")
        age = (tt - bounds[b.get("at", 0)]) if (tt is not None and bounds is not None) else None
        if kind == "fact":
            cited = (_EP_CITE is not None and scene_idx == _EP_CITE_SCENE
                     and b.get("at", 0) == _EP_CITE_AT and b.get("title") == _EP_CITE_TITLE)
            w_ = 860
            h_ = 452 if cited else 300
            x, y = _beat_xy(pos, w_, h_)
            d.rounded_rectangle([x, y, x + w_, y + h_], 18, fill=(18, 18, 18, 240), outline=GOLD, width=3)
            d.text((x + 28, y + 22), b.get("title", ""), font=F(fit_size(b.get("title", ""), 46, w_ - 56)), fill=GOLD)
            yy = y + 92
            for ln in b.get("lines", [])[:2]:
                d.text((x + 28, yy), ln, font=F(fit_size(ln, 36, w_ - 56, False), False), fill=WHITE); yy += 62
            if cited:
                # GAP 5: the receipt - red STUDY pill, cite, journal,
                # sample pill and the study's own finding, in the card.
                cy = y + 296
                d.line([x + 28, cy, x + w_ - 28, cy], fill=GREY, width=2)
                d.rounded_rectangle([x + 28, cy + 16, x + 158, cy + 56], 8, fill=RED)
                tw = probe.textlength("STUDY", font=F(26))
                d.text((x + 93 - tw / 2, cy + 23), "STUDY", font=F(26), fill=WHITE)
                d.text((x + 176, cy + 21), _EP_CITE["cite"], font=F(30), fill=WHITE)
                sub = f"{_EP_CITE['journal']} · {_EP_CITE['pill']}"
                d.text((x + 28, cy + 68), sub, font=F(fit_size(sub, 25, w_ - 56, False), False), fill=GREY)
                d.text((x + 28, cy + 100), _EP_CITE["finding"],
                       font=F(fit_size(_EP_CITE["finding"], 28, w_ - 56, False), False), fill=GOLD)
            _pop_paste(fr, layer, (x, y, w_, h_), _beat_fade(age))
            continue
        if kind == "chip":
            t = b["text"]; w_ = int(probe.textlength(t, font=F(40))) + 56; h_ = 84
            x, y = _beat_xy(pos, w_, 84)
            d.rounded_rectangle([x, y, x + w_, y + 84], 18, fill=(18, 18, 18, 235), outline=CYAN, width=3)
            d.text((x + 28, y + 20), t, font=F(40), fill=WHITE)
        elif kind == "stat":
            t = b["text"]
            gm = re.match(r"\s*[~+]?(\d+)%\s*\+?\s*$", t)
            if gm:
                # GAP 4 instrument: a percentage stat becomes a gauge -
                # a ring filled to the value, the % in the middle.
                pct = min(int(gm.group(1)), 100)
                w_, h_ = 430, 300
                x, y = _beat_xy(pos, w_, h_)
                d.rounded_rectangle([x, y, x + w_, y + h_], 18, fill=(18, 18, 18, 235), outline=CYAN, width=3)
                cx, cy, rad = x + w_ // 2, y + 128, 84
                d.arc([cx - rad, cy - rad, cx + rad, cy + rad], start=0, end=360, fill=GREY, width=18)
                if pct:
                    d.arc([cx - rad, cy - rad, cx + rad, cy + rad], start=-90, end=-90 + 3.6 * pct, fill=CYAN, width=18)
                pt = f"{pct}%"
                tw = probe.textlength(pt, font=F(48))
                d.text((cx - tw / 2, cy - 32), pt, font=F(48), fill=WHITE)
                _lbl = b.get("label", "")
                if _lbl:
                    lf = F(fit_size(_lbl, 28, w_ - 48, False), False)
                    tw = probe.textlength(_lbl, font=lf)
                    d.text((x + (w_ - tw) / 2, y + 240), _lbl, font=lf, fill=GREY)
            else:
                w_ = 430; h_ = 190
                x, y = _beat_xy(pos, w_, 190)
                d.rounded_rectangle([x, y, x + w_, y + 190], 18, fill=(18, 18, 18, 235), outline=CYAN, width=3)
                d.text((x + 28, y + 16), t, font=F(fit_size(t, 84, w_ - 56)), fill=CYAN)
                _lbl = b.get("label", "")
                d.text((x + 30, y + 122), _lbl, font=F(fit_size(_lbl, 30, w_ - 58, False), False), fill=GREY)
        elif kind == "mark":
            sym = "✓" if b.get("ok", True) else "✗"
            col = CYAN if b.get("ok", True) else RED
            t = b.get("text", ""); w_ = int(probe.textlength(t, font=F(40))) + 170; h_ = 110
            x, y = _beat_xy(pos, w_, 110)
            d.rounded_rectangle([x, y, x + w_, y + 110], 18, fill=(18, 18, 18, 235), outline=col, width=3)
            d.text((x + 26, y + 14), sym, font=F(72), fill=col)
            d.text((x + 118, y + 32), t, font=F(40), fill=WHITE)
        elif kind == "bars":
            w_, h_ = 600, 240
            x, y = _beat_xy(pos, w_, h_)
            d.rounded_rectangle([x, y, x + w_, y + h_], 18, fill=(18, 18, 18, 235), outline=GREY, width=2)
            d.text((x + 28, y + 18), b.get("title", ""), font=F(fit_size(b.get("title", ""), 34, w_ - 56)), fill=GOLD)
            yy = y + 76
            for label, pct, colname in b["items"]:
                col = CYAN if colname == "cyan" else ((200, 60, 60) if colname == "red" else GREY)
                d.text((x + 28, yy), label, font=F(fit_size(label, 32, 148, False), False), fill=WHITE)
                bw = int(330 * pct / 100)
                d.rounded_rectangle([x + 190, yy + 4, x + 190 + bw, yy + 34], 8, fill=col)
                d.text((x + 200 + bw, yy), f"{pct}", font=F(32), fill=col)
                yy += 66
        elif kind == "pip":
            img = Image.open(os.path.join(ROOT, "assets", b["asset"])).convert("RGBA")
            img = fit_cover(img, 500, 290)
            w_, h_ = 500, 290
            x, y = _beat_xy(pos, 500, 290)
            layer.paste(img, (x, y))
            d.rectangle([x, y, x + 500, y + 290], outline=CYAN, width=4)
            if b.get("label"):
                d.rectangle([x, y + 244, x + 500, y + 290], fill=(0, 0, 0))
                d.text((x + 16, y + 250), b["label"], font=F(30), fill=WHITE)
        _pop_paste(fr, layer, (x, y, w_, h_), _beat_fade(age))
    return fr

def _speech_units(phs):
    """Group display phrases into SPEECH units. A human talking does not
    stop in the middle of a sentence -- least of all while explaining --
    so the voice is synthesised per complete sentence, never per display
    chunk. A very long sentence may split once, at a clause edge (comma,
    semicolon, colon) past 16 words. Returns [(text, [phrase indices])]."""
    units, cur_text, cur_idx = [], [], []
    def flush():
        if cur_text:
            units.append((" ".join(cur_text), list(cur_idx)))
            cur_text.clear(); cur_idx.clear()
    for j, ph in enumerate(phs):
        cur_text.append(ph.strip()); cur_idx.append(j)
        words = sum(len(t.split()) for t in cur_text)
        if ph.rstrip().endswith((".", "!", "?")):
            flush()
        elif words >= 16 and ph.rstrip().endswith((",", ";", ":")):
            flush()
    flush()
    return units

def scene_audio(phs, tmp, tag, lead_pause=0.0):
    """Returns (wav_path, phrase_bounds, total). The VOICE speaks in
    complete sentences (see _speech_units) with one real pause between
    sentences; the display-phrase bounds are interpolated inside each
    sentence by word share, so on-screen text, beats and picture swaps
    keep their timing while the narration never stops mid-sentence."""
    units = _speech_units(phs)
    uwavs = [tts(t, os.path.join(tmp, f"{tag}_u{k}")) for k, (t, _) in enumerate(units)]
    udurs = [dur(w) for w in uwavs]
    UGAP = 0.5
    total = lead_pause + sum(udurs) + UGAP * max(0, len(units) - 1)
    track = np.zeros(int(total * SR) + SR // 2, dtype=np.float32)
    bounds = [0.0] * (len(phs) + 1)
    bounds[0] = lead_pause
    t = lead_pause
    for k, ((utext, idxs), w) in enumerate(zip(units, uwavs)):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", w, "-f", "f32le", "-ac", "1",
                              "-ar", str(SR), "-"], capture_output=True).stdout
        v = np.frombuffer(raw, dtype=np.float32)
        s0 = int(t * SR); track[s0:s0 + len(v)] += v[:max(0, len(track) - s0)]
        wcounts = [max(1, len(phs[j].split())) for j in idxs]
        wtot = sum(wcounts); acc = 0
        for m, j in enumerate(idxs):
            bounds[j] = t + udurs[k] * acc / wtot
            acc += wcounts[m]
        t += udurs[k] + (UGAP if k < len(units) - 1 else 0.0)
        bounds[idxs[-1] + 1] = t
    out = os.path.join(tmp, f"{tag}_full.wav")
    p = subprocess.run(["ffmpeg", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-",
                        "-c:a", "pcm_s16le", out], input=track.tobytes(), capture_output=True)
    if p.returncode != 0: raise RuntimeError("scene audio failed")
    return out, bounds, total

def hud5(script, scene, done_upto):
    """Progress furniture: TL = the chapter banner in the model's exact
    grammar (white bold caps on a dark bar, red stripe at the bar's left
    edge); TR = the step ladder (ascending bars, current lit, last one
    gold, YOUR STEP under it); bottom = the checklist bar + brand."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    sec = scene.get("section", "")
    if sec:
        tw0 = d.textlength(sec, font=F(34))
        d.rounded_rectangle([30, 24, 66 + tw0 + 26, 88], 10, fill=(14, 14, 14, 238))
        d.rectangle([30, 24, 44, 88], fill=RED + (255,))
        d.text((62, 38), sec, font=F(34), fill=WHITE + (255,))
    items = script.get("checklist", [])
    n = len(items)
    if n:
        cur = max(0, min(done_upto, n - 1))
        # The ladder: n ascending bars at top-right. Done = cyan,
        # current = white, upcoming = grey outline, the final bar gold.
        bw_, bgap = 30, 12
        total_w = n * bw_ + (n - 1) * bgap
        x0 = W - 36 - total_w
        base_y = 84
        for i in range(n):
            bh = 18 + int(34 * (i + 1) / n)
            x = x0 + i * (bw_ + bgap)
            last = i == n - 1
            if i < cur:
                d.rounded_rectangle([x, base_y - bh, x + bw_, base_y], 5, fill=CYAN + (255,))
            elif i == cur:
                d.rounded_rectangle([x, base_y - bh, x + bw_, base_y], 5, fill=WHITE + (255,))
            else:
                d.rounded_rectangle([x, base_y - bh, x + bw_, base_y], 5,
                                    outline=GOLD + (255,) if last else GREY + (255,), width=3)
            if last and i <= cur:
                d.rounded_rectangle([x, base_y - bh, x + bw_, base_y], 5, fill=GOLD + (255,))
        lab = "YOUR STEP"
        tw = d.textlength(lab, font=F(22))
        d.text((W - 36 - tw, base_y + 10), lab, font=F(22), fill=WHITE + (255,))
        d.rectangle([0, H - 64, W, H], fill=(0, 0, 0, 190))
        x = 40
        for i, it in enumerate(items):
            mark = "✓ " if i < done_upto else ("▸ " if i == done_upto else "• ")
            col = CYAN if i < done_upto else (WHITE if i == done_upto else GREY)
            t = mark + it
            d.text((x, H - 48), t, font=F(26), fill=col + (255,))
            x += d.textlength(t, font=F(26)) + 46
        t = "THE STRENGTH TEST"
        d.text((W - d.textlength(t, font=F(26)) - 40, H - 48), t, font=F(26), fill=GOLD + (255,))
        # GAP 8: Rep Theory's permanent safety strip - a small gold
        # pill above the checklist bar, on from the second section.
        if done_upto >= 1:
            st = "BE SAFE - STOP IF IT HURTS"
            sw = d.textlength(st, font=F(22)) + 36
            d.rounded_rectangle([36, H - 106, 36 + sw, H - 72], 8,
                                fill=(32, 27, 8, 225), outline=GOLD + (255,), width=2)
            d.text((54, H - 100), st, font=F(22), fill=GOLD + (255,))
    return im

def narrated_frames(script, scene, tmp, idx, tag=None, scene_idx=None):
    ftag = idx if tag is None else tag
    phs = scene.get("_phrases") or phrases5(scene["narration"])
    aud, bounds, total = scene_audio(phs, tmp, f"s{ftag}", scene.get("lead_pause", 0.0))
    is_card = scene["type"] == "card"
    base_art = None
    swap_cache = {}
    sizes = {}
    focus = {}
    beats = list(scene.get("beats", []))
    resolved = {}
    pre = {}
    if not is_card:
        opener = scene["asset"]
        scene_tags = _text_tags(scene["narration"])
        phrase_tags = [_text_tags(ph) for ph in phs]
        # Opening frame: the picture that best matches the opening words
        # (first ~5 phrases). The previous episode's opener is penalised so
        # consecutive episodes never open on the same picture when a close
        # alternative matches the words just as well.
        if idx == 0:
            open_tags = set()
            for t in phrase_tags[:5]:
                open_tags |= t
            prev_o = _prev_opener()
            man = _manifest()
            order = {f: i for i, f in enumerate(man)}
            # The opener is a hero frame: a Ren picture, never an anatomy
            # plate (plates enter later, when the words go anatomical).
            cands = [f for f, im in man.items() if im.get("role") in ("still", "closeup", "cycle")]
            def _okey(f):
                s = _score(f, open_tags) - (1 if f == prev_o else 0)
                return (-s, 1 if f == prev_o else 0, _USED[f], order[f])
            # HARD RULE: the opener comes from pictures the last episodes
            # did NOT show, whenever such a picture exists.
            fresh_c = [f for f in cands if f not in _RECENT]
            pick = min(fresh_c, key=_okey) if fresh_c else (min(cands, key=_okey) if cands else opener)
            if _score(pick, open_tags) <= 0 and pick != opener and opener not in _RECENT:
                pick = opener  # nothing fresh matches the words: keep the author's (if it is not itself a repeat)
            if pick == opener and opener == prev_o:
                pick = _opener_shift(opener)  # no match anywhere + a repeat: shift
            if pick != opener:
                pre[opener] = pick
                _USED[pick] += 1
                print(f"opener match ep {_EP_NUM}: {opener} -> {pick}")
        # The picture follows the words: when the narration's topic moves to
        # a picture that matches better, swap to it (min hold 6s so it never
        # flickers). If a picture still holds past the cap (15s hook scene,
        # 25s later) with no better match in the words, fall back to the
        # authored picture, else the least-used same-family picture.
        # HARD RULE: resolve the scene's base picture NOW, through the
        # no-repeat rotation, so the cap fallback below returns to the
        # RESOLVED (fresh) base - never to the authored file when the
        # last episodes already showed it.
        if opener not in resolved:
            resolved[opener] = pre[opener] if opener in pre else _base_resolve(opener, scene_tags)
        cap = 15 if idx == 0 else 25
        cur = pre.get(opener, opener)
        shown = {cur}
        last = 0.0
        authored = {b.get("at", 0): b for b in beats if b.get("kind") == "swap"}
        for j in range(len(phs)):
            if j in authored:
                cur = authored[j].get("asset", cur); shown.add(cur); last = bounds[j]
            held = bounds[j] - last
            # GAP 6 (hook density): Rep Theory cuts a new still every
            # 2-3s across the first seconds. In the opening scene's
            # first 12s the semantic swap may fire after 2.5s instead
            # of 6s, and if the words offer no match for 5s a
            # same-family refresh fires anyway - the hook never sits
            # on one picture. After 12s the normal rules return.
            sprint = idx == 0 and bounds[j] < 12
            if held >= (2.5 if sprint else 6):
                best, sc_ = _best_match(phrase_tags[j], exclude=cur, context=scene_tags)
                if best and sc_ >= 2:
                    beats.append({"at": j, "kind": "swap", "asset": best})
                    pre[best] = best
                    _USED[best] += 1
                    shown.add(best); cur = best; last = bounds[j]
                    print(f"match scene {idx} @{bounds[j]:.0f}s: '{phs[j][:44]}' -> {best} (score {sc_})")
                    continue
            if sprint and held >= 5:
                pick = _auto_pick(cur, shown)
                if pick:
                    beats.append({"at": j, "kind": "swap", "asset": pick})
                    pre[pick] = pick
                    _USED[pick] += 1
                    shown.add(pick); cur = pick; last = bounds[j]
                    print(f"sprint refresh scene {idx} @{bounds[j]:.0f}s -> {pick}")
                    continue
            if held >= cap:
                pick = None
                if cur != opener:
                    pick = opener  # back to the base (drawn via its resolved, fresh image)
                else:
                    pick = _auto_pick(cur, shown)
                if pick:
                    beats.append({"at": j, "kind": "swap", "asset": pick})
                    if pick != opener:
                        pre[pick] = pick
                        _USED[pick] += 1
                    shown.add(pick); cur = pick; last = bounds[j]
                    print(f"auto-refresh (no match) scene {idx} @{bounds[j]:.0f}s -> {pick}")
        beats.sort(key=lambda b: b.get("at", 0))
        # Resolve every picture this scene will show through the episode
        # rotation ONCE (first use in the episode stays, repeats rotate to
        # the best-matching picture for the scene's words).
        for a in [scene["asset"]] + [b.get("asset") for b in beats
                                     if b.get("kind") in ("swap", "pip") and b.get("asset")]:
            if a not in resolved:
                resolved[a] = pre[a] if a in pre else (
                    _base_resolve(a, scene_tags) if a == scene["asset"]
                    else _rotate(a, scene_tags))
        _bim = Image.open(os.path.join(ROOT, "assets", resolved[scene["asset"]]))
        sizes[resolved[scene["asset"]]] = _bim.size
        base_art = fit_cover(_bim.convert("RGB"), W, H)
        # v5: pre-load every swap target so the picture can change mid-scene.
        # Cache is keyed by the AUTHORED name; the image is the resolved one.
        for b in beats:
            if b.get("kind") == "swap" and b.get("asset"):
                _sim = Image.open(os.path.join(ROOT, "assets", resolved[b["asset"]]))
                sizes[resolved[b["asset"]]] = _sim.size
                swap_cache[b["asset"]] = fit_cover(_sim.convert("RGB"), W, H)
        focus = _focus_plan(phrase_tags, beats, scene, resolved, sizes, bounds)
    # GAP 4 layout: on a bignum card WITH a parsed scale, the step-chart
    # owns the bottom of the frame, so the phrase strip moves to the
    # card's empty top band instead of crossing the steps - and any
    # top-right beat drops to mid-right so the two never collide.
    phrase_y = 830
    if is_card and scene.get("card") == "bignum" and _parse_bands(scene.get("sub", "")):
        phrase_y = 108
    draw_beat_list = [dict(b, asset=resolved[b["asset"]])
                      if b.get("kind") == "pip" and b.get("asset") in resolved else b
                      for b in beats]
    if phrase_y == 108:
        draw_beat_list = [dict(b, pos="mr") if b.get("pos") == "tr" else b
                          for b in draw_beat_list]
    hud_im = hud5(script, scene, scene.get("check", 0))
    fdir = os.path.join(tmp, f"ff{ftag}"); os.makedirs(fdir, exist_ok=True)
    pp_cache = [phrase_png(ph) for ph in phs]
    glow_cache = [glow_overlay(k / FPS_A) for k in range(20)]
    n_items = len(scene.get("lines", scene.get("layers", []))) or 3
    for fi in range(int(total * FPS_A)):
        tt = fi / FPS_A
        j = max(0, int(np.searchsorted(bounds, tt, side="right") - 1))
        if is_card:
            reveal = 1 + int((j / max(1, len(phs))) * (n_items + 1))
            fr = card_image4(scene, reveal)
        else:
            sway = int(3 * math.sin(2 * math.pi * tt / 3.2))
            fr = Image.new("RGB", (W, H), DARK)
            # v5: the main picture swaps when a swap beat is reached.
            # v6.1: the swap is a HARD CUT - pixel analysis of the model
            # showed no blur, no flash, no fade between poses, ever.
            cur = current_swap(beats, j, scene["asset"])
            fr.paste(swap_cache.get(cur, base_art), (sway, 0))
            g = glow_cache[fi % 20]; fr.paste(g, (0, 0), g)
        if tt < 0.4:
            # v6.1: scenes fade IN from black over ~0.4s (the model's
            # new content fades/scales in, in place - the cut itself
            # stays hard, the arrival is soft).
            fr = Image.blend(Image.new("RGB", (W, H), DARK), fr, max(0.0, tt / 0.4))
        draw_beats(fr, draw_beat_list, j, scene_idx=idx if scene_idx is None else scene_idx,
                   tt=tt, bounds=bounds)
        if j in focus:
            _part, _px, _py = focus[j]
            _draw_focus(fr, _part, _px + (0 if is_card else sway), _py, tt, age=tt - bounds[j])
        if tt >= scene.get("lead_pause", 0.0):
            pp = pp_cache[j]
            fr.paste(pp, (0, phrase_y), pp)
        fr.paste(hud_im, (0, 0), hud_im)
        d = ImageDraw.Draw(fr)
        d.rectangle([60, 92, 60 + int(300 * min(1.0, tt / total)), 100], fill=CYAN)
        fr.save(os.path.join(fdir, f"f{fi:04d}.png"))
    seg = os.path.join(tmp, f"seg{ftag}.mp4")
    run(["ffmpeg", "-y", "-framerate", str(FPS_A), "-i", os.path.join(fdir, "f%04d.png"),
         "-i", aud, "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-c:a", "aac",
         "-shortest", seg])
    print(f"scene {idx} ({scene['type']}) {total:.1f}s {len(phs)} phrases")
    return seg, scene.get("music", "calm"), total

def anim_frames(script, scene, tmp, idx, tag=None):
    ftag = idx if tag is None else tag
    phs = scene.get("_phrases") or phrases5(scene["narration"])
    aud, bounds, total = scene_audio(phs, tmp, f"a{ftag}", scene.get("lead_pause", 0.0))
    angle_sets = scene.get("angles") or [scene["poses"]]
    # HARD RULE: cycle poses obey the cross-episode ban too -- drop the
    # poses the last episodes showed when the set keeps at least 2 fresh
    # ones (a cycle needs motion; a fully-recent set stays whole).
    angle_sets = [[a for a in s if a not in _RECENT] if len([a for a in s if a not in _RECENT]) >= 2 else s
                  for s in angle_sets]
    for s in angle_sets:
        for a in s:
            _USED[a] += 1  # record cycle poses as used, like every picture
    sets = [[fit_cover(Image.open(os.path.join(ROOT, "assets", a)).convert("RGB"), W, H) for a in s]
            for s in angle_sets]
    seqs = []
    for s in sets:
        idxs = list(range(len(s)))
        seqs.append(idxs + idxs[-2:0:-1] if len(s) > 2 else idxs + idxs[::-1])
    cycle = scene.get("cycle", 2.4); every = scene.get("angle_every", 3)
    hud_im = hud5(script, scene, scene.get("check", 0))
    pp_cache = [phrase_png(ph) for ph in phs]
    fdir = os.path.join(tmp, f"af{ftag}"); os.makedirs(fdir, exist_ok=True)
    for fi in range(int(total * FPS_A)):
        tt = fi / FPS_A
        j = max(0, int(np.searchsorted(bounds, tt, side="right") - 1))
        si = (j // every) % len(sets)
        s = sets[si]; sq = seqs[si]
        pose = s[sq[int(tt / (cycle / len(sq))) % len(sq)]]
        fr = pose.copy()
        if tt < 0.4:
            fr = Image.blend(Image.new("RGB", (W, H), DARK), fr, max(0.0, tt / 0.4))
        draw_beats(fr, scene.get("beats", []), j, tt=tt, bounds=bounds)
        if tt >= scene.get("lead_pause", 0.0):
            pp = pp_cache[j]; fr.paste(pp, (0, 830), pp)
        fr.paste(hud_im, (0, 0), hud_im)
        fr.save(os.path.join(fdir, f"f{fi:04d}.png"))
    seg = os.path.join(tmp, f"seg{ftag}.mp4")
    run(["ffmpeg", "-y", "-framerate", str(FPS_A), "-i", os.path.join(fdir, "f%04d.png"),
         "-i", aud, "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-c:a", "aac",
         "-shortest", seg])
    print(f"scene {idx} (anim) {total:.1f}s angles={len(sets)}")
    return seg, scene.get("music", "drive"), total

def music_track(plan, total, tmp, ep_id=0):
    """plan: list of (kind, seconds). Build a ducked bed: consecutive same-kind
    sections merged, each trimmed + faded, joined with the concat filter.
    Each mood resolves to MUSIC_POOLS[kind][int(ep_id) % 5] (rotation by
    episode id); the resolved titles land in LAST_MUSIC for attribution."""
    try:
        slot = int(ep_id) % 5
    except (TypeError, ValueError):
        slot = 0
    files = {kind: pool[slot % len(pool)] for kind, pool in MUSIC_POOLS.items()}
    LAST_MUSIC[:] = []
    for kind, _secs in plan:
        title = MUSIC_TITLES.get(files[kind])
        if title and title not in LAST_MUSIC:
            LAST_MUSIC.append(title)
    merged = []
    for kind, secs in plan:
        if merged and merged[-1][0] == kind:
            merged[-1][1] += secs
        else:
            merged.append([kind, float(secs)])
    inputs, filters = [], []
    for i, (kind, secs) in enumerate(merged):
        inputs += ["-stream_loop", "-1", "-i", os.path.join(ROOT, "assets", "music", files[kind])]
        filters.append(f"[{i}:a]atrim=0:{secs:.1f},asetpts=PTS-STARTPTS,volume=0.16,"
                       f"afade=t=in:st=0:d=0.8,afade=t=out:st={max(0.0, secs - 0.8):.1f}:d=0.8[a{i}]")
    chain = "".join(f"[a{i}]" for i in range(len(merged)))
    fc = ";".join(filters) + f";{chain}concat=n={len(merged)}:v=0:a=1[out]"
    out = os.path.join(tmp, "music.wav")
    run(["ffmpeg", "-y"] + inputs + ["-filter_complex", fc, "-map", "[out]",
         "-t", f"{total:.1f}", "-c:a", "pcm_s16le", out])
    return out

def roadmap_image(script, current, final=False):
    """Gap 2 roadmap, restyled v6 as the model's road signs: three
    signs on posts over a road strip - FIRST / THEN / the last stop,
    which stays a dim "?" until the final appearance reveals it.
    Passed signs earn a check under the post."""
    items = script.get("checklist", [])
    n = len(items)
    im = Image.new("RGB", (W, H), DARK); d = ImageDraw.Draw(im)
    t = "TODAY'S MAP"
    d.text(((W - d.textlength(t, font=F(66))) / 2, 92), t, font=F(66), fill=WHITE)
    t2 = "FINISH EVERY STOP. EARN YOUR NEW NUMBER."
    d.text(((W - d.textlength(t2, font=F(30))) / 2, 182), t2, font=F(30), fill=GOLD)
    d.rectangle([0, 800, W, 900], fill=(24, 24, 28))
    for x in range(40, W - 120, 180):
        d.rectangle([x, 844, x + 100, 856], fill=(200, 200, 200))
    stage = 2 if final else (0 if current <= 0 else 1)
    signs = [
        (items[0] if n > 0 else "", "FIRST", RED, True),
        (items[1] if n > 1 else "", "THEN", (255, 140, 0), stage >= 1),
        (items[-1] if n > 0 else "", "LAST", CYAN, final),
    ]
    sw_, sh_, gap_ = 500, 210, 110
    total_w = 3 * sw_ + 2 * gap_
    x0 = (W - total_w) // 2
    sy = 400
    for k, (name, tag, col, lit) in enumerate(signs):
        x = x0 + k * (sw_ + gap_)
        d.rectangle([x + sw_ // 2 - 9, sy + sh_, x + sw_ // 2 + 9, 806], fill=(110, 110, 116))
        oc = col if lit else (90, 90, 96)
        d.rounded_rectangle([x, sy, x + sw_, sy + sh_], 18, fill=(14, 14, 16),
                            outline=oc, width=5 if lit else 3)
        tw = d.textlength(tag, font=F(30))
        d.text((x + (sw_ - tw) / 2, sy - 52), tag, font=F(30), fill=col if lit else GREY)
        if k == 2 and not final:
            q = "?"
            d.text((x + (sw_ - d.textlength(q, font=F(120))) / 2, sy + 34), q, font=F(120), fill=(90, 90, 96))
        else:
            size = fit_size(name, 54, sw_ - 48)
            words = name.split(); lines, ln = [], ""
            for w_ in words:
                cand = (ln + " " + w_).strip()
                if d.textlength(cand, font=F(size)) <= sw_ - 48 or not ln:
                    ln = cand
                else:
                    lines.append(ln); ln = w_
            if ln: lines.append(ln)
            ly = sy + (sh_ - len(lines[:2]) * (size + 10)) // 2
            for L in lines[:2]:
                d.text((x + (sw_ - d.textlength(L, font=F(size))) / 2, ly), L,
                       font=F(size), fill=WHITE if lit else GREY)
                ly += size + 10
        if k < 2:
            ch = ">>>"
            d.text((x + sw_ + (gap_ - d.textlength(ch, font=F(44))) / 2, sy + sh_ // 2 - 26),
                   ch, font=F(44), fill=GREY)
        if lit and (final or k < stage):
            d.ellipse([x + sw_ // 2 - 26, sy + sh_ + 118, x + sw_ // 2 + 26, sy + sh_ + 170], fill=CYAN)
            ck = "✓"
            d.text((x + sw_ // 2 - d.textlength(ck, font=F(36)) / 2, sy + sh_ + 124),
                   ck, font=F(36), fill=(0, 0, 0))
    if final:
        t4 = "MAP COMPLETE"
        d.text(((W - d.textlength(t4, font=F(54))) / 2, 936), t4, font=F(54), fill=GOLD)
    fake = {"section": items[current] if 0 <= current < n else "", "check": current}
    h = hud5(script, fake, current)
    im.paste(h, (0, 0), h)
    return im

def roadmap_segment(script, current, line, tmp, tag, final=False):
    ip = os.path.join(tmp, f"rmap{tag}.png")
    roadmap_image(script, current, final).save(ip)
    wav = tts(line, os.path.join(tmp, f"rmap{tag}"))
    d = dur(wav) + 0.6
    seg = os.path.join(tmp, f"rmap{tag}.mp4")
    run(["ffmpeg", "-y", "-loop", "1", "-framerate", "30", "-i", ip, "-i", wav,
         "-t", f"{d:.2f}", "-vf", "format=yuv420p", "-c:v", "libx264", "-c:a", "aac", seg])
    print(f"roadmap {tag}: current={current} final={final} {d:.1f}s")
    return seg, d

def _band_range(b):
    lo, hi, _label = b
    if hi is None:
        return f"OVER {lo:g}"
    if lo == 0:
        return f"UNDER {hi:g}"
    return f"{lo:g}-{hi:g}"

def _route_rows(script, bands):
    """Personal routing from the viewer's own number (GAP 7): each
    scoring band of the episode's number card maps to a starting point.
    The lowest band walks the whole map, the top band maintains and
    retests, a middle band goes straight to the work section."""
    checks = script.get("checklist", [])
    work = "GO STRAIGHT TO THE WORK"
    for sc in script.get("scenes", []):
        if sc.get("type") == "timer":
            ci = sc.get("check", 0)
            if 0 <= ci < len(checks):
                work = f"GO STRAIGHT TO {checks[ci].upper()}"
            break
    rows = []
    n = len(bands)
    for i, b in enumerate(bands):
        if i == 0:
            r = "START AT STOP 1 - THE FULL MAP"
        elif i == n - 1:
            r = "MAINTAIN - RETEST IN 7 DAYS"
        else:
            r = work
        rows.append((_band_range(b), b[2].upper(), r,
                     [(200, 60, 60), GOLD, CYAN][min(i, 2)]))
    return rows

def tease_image(script, bands, check):
    """GAP 7 locked tease: the viewer's full breakdown, shown blurred
    under a padlock right after the number - the payoff is promised,
    withheld, and paid by the route card at the end."""
    from PIL import ImageFilter
    im = Image.new("RGB", (W, H), DARK)
    d = ImageDraw.Draw(im)
    t = "YOUR FULL BREAKDOWN"
    d.text(((W - d.textlength(t, font=F(64))) / 2, 140), t, font=F(64), fill=GOLD)
    rows = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rows)
    y = 300
    for rng, lab, _r, col in _route_rows(script, bands):
        rd.rounded_rectangle([300, y, W - 300, y + 118], 16,
                             fill=(26, 26, 32, 255), outline=col + (255,), width=3)
        rd.text((340, y + 20), rng, font=F(46), fill=col + (255,))
        rd.text((340, y + 72), lab, font=F(32), fill=(230, 230, 230, 255))
        y += 148
    rows = rows.filter(ImageFilter.GaussianBlur(9))
    im.paste(rows, (0, 0), rows)
    d = ImageDraw.Draw(im)
    cx, cy = W // 2, 300 + (y - 300) // 2 - 20
    d.arc([cx - 48, cy - 100, cx + 48, cy + 6], 180, 360, fill=GOLD, width=13)
    d.rounded_rectangle([cx - 74, cy - 12, cx + 74, cy + 88], 14, fill=GOLD)
    d.ellipse([cx - 13, cy + 18, cx + 13, cy + 44], fill=(10, 10, 12))
    d.rectangle([cx - 6, cy + 34, cx + 6, cy + 62], fill=(10, 10, 12))
    t = "LOCKED - YOUR ROUTE UNLOCKS AT THE END"
    d.text(((W - d.textlength(t, font=F(36))) / 2, y + 56), t, font=F(36), fill=GOLD)
    hud_im = hud5(script, {"section": "THE NUMBER", "check": check}, check)
    im.paste(hud_im, (0, 0), hud_im)
    return im

def tease_segment(script, bands, check, tmp):
    ip = os.path.join(tmp, "tease.png")
    tease_image(script, bands, check).save(ip)
    line = ("That number is only the headline. Your full breakdown stays "
            "locked until the end. Finish the map, and I will show you "
            "exactly what your number means - and your first move.")
    wav = tts(line, os.path.join(tmp, "tease"))
    dd = dur(wav) + 0.6
    seg = os.path.join(tmp, "tease.mp4")
    run(["ffmpeg", "-y", "-loop", "1", "-framerate", "30", "-i", ip, "-i", wav,
         "-t", f"{dd:.2f}", "-vf", "format=yuv420p", "-c:v", "libx264", "-c:a", "aac", seg])
    print(f"tease segment: {dd:.1f}s")
    return seg, dd

def _dimc(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)

def route_image(script, bands, check, section, active=None, done=frozenset(),
                glow=1.0, lit_all=True):
    """GAP 7 personal routing, restyled v6 to the model's YOUR RESULT
    card: one row per band of the viewer's number, a coloured border
    down the row's left edge, and the row's own mini step-ladder with
    its step lit - the viewer finds their row and their step at once.
    v6.2: rows carry a narration state - the row the voice is naming
    right now glows (active), rows already named stay lit but calmer
    (done), rows not yet named sit dim. With lit_all=True (the legacy
    static call) every row renders in the calm lit style."""
    im = Image.new("RGB", (W, H), DARK)
    d = ImageDraw.Draw(im)
    t = "YOUR RESULT"
    d.text(((W - d.textlength(t, font=F(64))) / 2, 130), t, font=F(64), fill=GOLD)
    items = script.get("checklist", [])
    n = max(1, len(items))
    y = 280
    for i, (rng, lab, route, col) in enumerate(_route_rows(script, bands)):
        if active is not None and i == active:
            state = "active"
        elif i in done or (active is None and lit_all):
            state = "done"
        else:
            state = "up"
        if state == "active":
            # the glow: a halo ring in the row's own colour, brightening
            # in over ~0.25s (glow 0..1), then the row itself, border
            # thick in the row colour.
            halo = _dimc(col, 0.25 + 0.75 * glow)
            d.rounded_rectangle([212, y - 8, W - 212, y + 158], 22, outline=halo, width=4)
            bord = tuple(int((70 + (c - 70) * glow)) for c in col)
            d.rounded_rectangle([220, y, W - 220, y + 150], 16,
                                fill=(28, 28, 35), outline=bord, width=5)
            bar_c, rng_c, lab_c, rte_c = col, col, WHITE, WHITE
        elif state == "done":
            d.rounded_rectangle([220, y, W - 220, y + 150], 16,
                                fill=(22, 22, 27), outline=_dimc(col, 0.75), width=2)
            bar_c, rng_c, lab_c, rte_c = col, col, GREY, WHITE
        else:
            d.rounded_rectangle([220, y, W - 220, y + 150], 16,
                                fill=(15, 15, 18), outline=(46, 46, 52), width=2)
            bar_c, rng_c, lab_c, rte_c = _dimc(col, 0.35), _dimc(col, 0.5), (95, 95, 95), (115, 115, 115)
        d.rectangle([220, y + 10, 234, y + 140], fill=bar_c)
        d.text((272, y + 16), rng, font=F(46), fill=rng_c)
        d.text((272, y + 76), lab, font=F(30), fill=lab_c)
        d.text((272, y + 110), route, font=F(28), fill=rte_c)
        # the row's mini ladder: n ascending bars, this row's step lit
        bw_, bgap, base = 26, 9, y + 122
        lx = W - 272 - (n * bw_ + (n - 1) * bgap)
        lit = min(i, n - 1)
        for k in range(n):
            bh = 14 + int(26 * (k + 1) / n)
            x = lx + k * (bw_ + bgap)
            if state == "up":
                d.rounded_rectangle([x, base - bh, x + bw_, base], 4,
                                    outline=(70, 70, 76), width=2)
            elif k < lit:
                d.rounded_rectangle([x, base - bh, x + bw_, base], 4,
                                    fill=tuple(c // 2 for c in col))
            elif k == lit:
                d.rounded_rectangle([x, base - bh, x + bw_, base], 4, fill=col)
            else:
                d.rounded_rectangle([x, base - bh, x + bw_, base], 4,
                                    outline=GOLD if k == n - 1 else GREY, width=2)
        y += 176
    t = "EVERY ROUTE ENDS AT THE RETEST"
    d.text(((W - d.textlength(t, font=F(30))) / 2, y + 30), t, font=F(30), fill=GREY)
    hud_im = hud5(script, {"section": section, "check": check}, check)
    im.paste(hud_im, (0, 0), hud_im)
    return im

def route_segment(script, bands, check, section, tmp):
    """v6.2: the route card is an ANIMATED segment, like the model's
    result chapter - the narration is synthesised per band (intro +
    one sentence per row), and each row lights as the voice names it:
    rows start dim, the named row's border glows in over ~0.25s, rows
    already named stay lit but calmer."""
    rows = _route_rows(script, bands)
    units = ["Here is your route."] + \
            [f"{rng.lower()}: {route.lower()}." for rng, _l, route, _c in rows]
    aud, bounds, total = scene_audio(units, tmp, "route")
    tail = 0.6
    fdir = os.path.join(tmp, "routef"); os.makedirs(fdir, exist_ok=True)
    for fi in range(int((total + tail) * FPS_A)):
        tt = fi / FPS_A
        j = max(0, int(np.searchsorted(bounds, tt, side="right") - 1))
        active = j - 1 if j >= 1 else None
        done = frozenset(range(active)) if active else frozenset()
        glow = min(1.0, (tt - bounds[j]) / 0.25) if active is not None else 1.0
        fr = route_image(script, bands, check, section,
                         active=active, done=done, glow=glow, lit_all=False)
        if tt < 0.4:
            fr = Image.blend(Image.new("RGB", (W, H), DARK), fr, max(0.0, tt / 0.4))
        fr.save(os.path.join(fdir, f"f{fi:04d}.png"))
    seg = os.path.join(tmp, "route.mp4")
    run(["ffmpeg", "-y", "-framerate", str(FPS_A), "-i", os.path.join(fdir, "f%04d.png"),
         "-i", aud, "-af", f"apad=pad_dur={tail}", "-vf", "fps=30,format=yuv420p",
         "-c:v", "libx264", "-c:a", "aac", "-t", f"{total + tail:.2f}", seg])
    print(f"route segment: {total + tail:.1f}s rows light at "
          f"{[round(bounds[k + 1], 1) for k in range(len(rows))]}")
    return seg, total + tail

def end_segment(script, tmp):
    """GAP 8 end card: push the NEXT episode by name (read from the
    next bank script) instead of ending on a comment prompt. Returns
    (seg, dur) or None when there is no next episode."""
    try:
        nid = int(script.get("id", 0)) + 1
    except (TypeError, ValueError):
        return None
    nxt = os.path.join(ROOT, "bank", f"{nid:03d}.json")
    if not os.path.exists(nxt):
        return None
    try:
        title = json.load(open(nxt)).get("title", "")
    except Exception:
        return None
    if not title:
        return None
    im = Image.new("RGB", (W, H), DARK)
    d = ImageDraw.Draw(im)
    t = "NEXT ON THE STRENGTH TEST"
    d.text(((W - d.textlength(t, font=F(34))) / 2, 268), t, font=F(34), fill=GOLD)
    words, lines, cur = title.split(), [], ""
    for w_ in words:
        cand = (cur + " " + w_).strip()
        if d.textlength(cand, font=F(58)) <= W - 360 or not cur:
            cur = cand
        else:
            lines.append(cur); cur = w_
    if cur:
        lines.append(cur)
    y = 360
    for ln in lines[:3]:
        d.text(((W - d.textlength(ln, font=F(58))) / 2, y), ln, font=F(58), fill=WHITE)
        y += 76
    ay = y + 44
    d.polygon([(W // 2 - 95, ay), (W // 2 + 35, ay), (W // 2 + 35, ay - 24),
               (W // 2 + 115, ay + 24), (W // 2 + 35, ay + 72), (W // 2 + 35, ay + 48),
               (W // 2 - 95, ay + 48)], fill=CYAN)
    t = "YOUR NEXT NUMBER IS WAITING"
    d.text(((W - d.textlength(t, font=F(30))) / 2, H - 190), t, font=F(30), fill=GREY)
    last = script["scenes"][-1]
    hud_im = hud5(script, {"section": last.get("section", ""), "check": last.get("check", 0)},
                  last.get("check", 0))
    im.paste(hud_im, (0, 0), hud_im)
    ip = os.path.join(tmp, "end.png")
    im.save(ip)
    spoken = re.sub(r"\([^)]*\)", "", title).strip()
    wav = tts(f"Next test: {spoken}.", os.path.join(tmp, "end"))
    dd = dur(wav) + 1.2
    seg = os.path.join(tmp, "end.mp4")
    run(["ffmpeg", "-y", "-loop", "1", "-framerate", "30", "-i", ip, "-i", wav,
         "-t", f"{dd:.2f}", "-vf", "format=yuv420p", "-c:v", "libx264", "-c:a", "aac", seg])
    print(f"end card: next ep {nid} '{title[:50]}' {dd:.1f}s")
    return seg, dd

def title_image(script):
    """v6 opening card (the model's 0:00 frame): the test's name in
    giant white type behind the hero pose - one beat of pure packaging
    before anything is said. No HUD, no other text."""
    word, hero = "", None
    for sc in script.get("scenes", []):
        if sc.get("type") == "timer" and sc.get("exercise"):
            word = sc["exercise"].upper()
            hero = hero or sc.get("asset")
    sc0 = script["scenes"][0] if script.get("scenes") else {}
    hero = hero or sc0.get("asset") or (sc0.get("poses") or [None])[0]
    if not word:
        word = (script.get("checklist") or ["THE TEST"])[0]
    im = Image.new("RGB", (W, H), DARK)
    d = ImageDraw.Draw(im)
    size = fit_size(word, 300, W - 120)
    d.text(((W - d.textlength(word, font=F(size))) / 2, (H - size) // 2 - 30),
           word, font=F(size), fill=WHITE)
    if hero:
        try:
            pic = Image.open(os.path.join(ROOT, "assets", hero)).convert("RGB")
            nh = int(H * 0.92)
            pic = pic.resize((int(pic.width * nh / pic.height), nh), Image.BICUBIC)
            # The art is bright line-work on pure black: key the black
            # out so the giant word stays visible AROUND and BEHIND the
            # figure, the way the model's title card layers it.
            alpha = pic.convert("L").point(lambda v: 0 if v < 14 else min(255, int((v - 14) * 1.6)))
            im.paste(pic, ((W - pic.width) // 2, (H - pic.height) // 2), alpha)
        except Exception:
            pass
    return im, hero

def title_segment(script, tmp):
    ip = os.path.join(tmp, "title.png")
    im, hero = title_image(script)
    im.save(ip)
    wav = os.path.join(tmp, "title.wav")
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "1.5", wav])
    seg = os.path.join(tmp, "title.mp4")
    run(["ffmpeg", "-y", "-loop", "1", "-framerate", "30", "-i", ip, "-i", wav,
         "-t", "1.5", "-vf", "format=yuv420p", "-c:v", "libx264", "-c:a", "aac", seg])
    print("title card: 1.5s")
    return seg, 1.5, hero

def safety_image(script):
    """v6 closing card (the model's last frame): warning triangle,
    SAFETY NOTE pill, the not-licensed lines, ANY PAIN? in orange,
    and the episode's pose in a gold-ringed circle, bottom-right."""
    im = Image.new("RGB", (W, H), DARK)
    d = ImageDraw.Draw(im)
    cx = W // 2
    d.polygon([(cx - 52, 172), (cx + 52, 172), (cx, 84)], outline=GOLD, width=7)
    d.text((cx - d.textlength("!", font=F(56)) / 2, 116), "!", font=F(56), fill=GOLD)
    pill = "SAFETY NOTE"
    pw = d.textlength(pill, font=F(34)) + 56
    d.rounded_rectangle([cx - pw / 2, 214, cx + pw / 2, 272], 29, outline=GOLD, width=3)
    d.text((cx - d.textlength(pill, font=F(34)) / 2, 226), pill, font=F(34), fill=WHITE)
    lines = [("WE'RE NOT LICENSED", 84, WHITE), ("PROFESSIONALS", 84, WHITE),
             ("TRAIN AT YOUR OWN RISK", 64, WHITE), ("ANY PAIN?", 84, (255, 110, 40)),
             ("STOP. SEE A LICENSED PHYSICIAN.", 36, GREY)]
    y = 336
    for txt, size, col in lines:
        d.text((cx - d.textlength(txt, font=F(size)) / 2, y), txt, font=F(size), fill=col)
        y += size + 34
    hero = None
    for sc in script.get("scenes", []):
        if sc.get("type") == "timer" and sc.get("asset"):
            hero = sc["asset"]; break
    if hero:
        try:
            pic = Image.open(os.path.join(ROOT, "assets", hero)).convert("RGB")
            pic = fit_cover(pic, 300, 300)
            mask = Image.new("L", (300, 300), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, 300, 300], fill=255)
            im.paste(pic, (W - 380, H - 380), mask)
            d.ellipse([W - 380, H - 380, W - 80, H - 80], outline=GOLD, width=6)
        except Exception:
            pass
    return im

def safety_segment(script, tmp):
    ip = os.path.join(tmp, "safety.png")
    safety_image(script).save(ip)
    line = ("Safety note. We are not licensed professionals. Train at "
            "your own risk. Any pain? Stop, and see a licensed physician.")
    wav = tts(line, os.path.join(tmp, "safety"))
    dd = dur(wav) + 0.6
    seg = os.path.join(tmp, "safety.mp4")
    run(["ffmpeg", "-y", "-loop", "1", "-framerate", "30", "-i", ip, "-i", wav,
         "-t", f"{dd:.2f}", "-vf", "format=yuv420p", "-c:v", "libx264", "-c:a", "aac", seg])
    print(f"safety card: {dd:.1f}s")
    return seg, dd

def _scene0_parts(scene, tmp):
    """v6.2 (item 2): the intro roadmap must land by ~0:40 like the
    model's (theirs: 0:36), but it is inserted after scene 0 - and a
    long scene 0 pushes it late. When scene 0's narration would run
    past ~45s, split it at the sentence boundary nearest to (never
    after) 40s and return two half-scenes; the caller puts the intro
    roadmap between them. No mid-sentence cuts: the split follows the
    speech units scene_audio itself will use, and beats are remapped
    to the half they belong to. Short scene 0 returns unchanged."""
    if scene.get("type") == "timer" or not scene.get("narration"):
        return [scene]
    phs = phrases5(scene["narration"])
    units = _speech_units(phs)
    if len(units) < 2:
        return [scene]
    ends, t = [], scene.get("lead_pause", 0.0)
    for k, (utext, _idxs) in enumerate(units):
        t += dur(tts(utext, os.path.join(tmp, f"probe0_u{k}")))
        ends.append(t)
        t += 0.5  # scene_audio's inter-sentence gap
    total = ends[-1]
    if total <= 45:
        return [scene]
    k = 1  # units in part A: the last boundary at or before 40s
    for i, e in enumerate(ends):
        if e <= 40 and i < len(units) - 1:
            k = i + 1
    split_phrase = sum(len(idxs) for _t, idxs in units[:k])
    A, B = dict(scene), dict(scene)
    A["narration"] = " ".join(t for t, _ in units[:k])
    B["narration"] = " ".join(t for t, _ in units[k:])
    # Carry the ORIGINAL phrase list into each half: bank narration is
    # author-chunked (often "|" separated), so re-running phrases5 on a
    # half's joined text would re-chunk it differently and knock every
    # beat index out of alignment. narrated_frames/anim_frames honour
    # the "_phrases" override, so each half speaks and times exactly
    # the phrases the probe measured.
    A["_phrases"] = phs[:split_phrase]
    B["_phrases"] = phs[split_phrase:]
    def _remap(beats, part):
        out = []
        for b in beats:
            at = b.get("at", 0)
            if part == "A" and at < split_phrase:
                out.append(dict(b))
            elif part == "B" and at >= split_phrase:
                nb = dict(b); nb["at"] = at - split_phrase; out.append(nb)
        return out
    A["beats"] = _remap(scene.get("beats", []), "A")
    B["beats"] = _remap(scene.get("beats", []), "B")
    B.pop("lead_pause", None)
    print(f"scene 0 split: {total:.1f}s -> A {ends[k - 1]:.1f}s + "
          f"B {total - ends[k - 1] - 0.5:.1f}s (sentence {k}/{len(units)})")
    return [A, B]

def _seg_cached(tmp, tag):
    p = os.path.join(tmp, f"seg{tag}.mp4")
    if os.path.exists(p) and os.path.getsize(p) > 10000:
        try:
            dur(p); return True
        except Exception:
            return False
    return False

def _render_scene(script, sc, tmp, idx, tag, scene_idx=None):
    """One scene segment, with the same cache rule the main loop has
    always used (a cached seg<tag>.mp4 that probes clean is reused).
    Returns (seg_path, music_kind, seconds)."""
    cached = os.path.join(tmp, f"seg{tag}.mp4")
    if os.path.exists(cached) and os.path.getsize(cached) > 10000:
        try:
            cd_ = dur(cached)
            print(f"scene {tag} cached")
            return cached, sc.get("music", "calm"), cd_
        except Exception:
            os.remove(cached)  # truncated by an interrupted run: re-render
    if sc["type"] == "timer":
        seg = timer_segment(script, sc, tmp, idx)
        return seg, "drive", dur(seg)
    if sc["type"] == "anim":
        return anim_frames(script, sc, tmp, idx, tag=tag)
    return narrated_frames(script, sc, tmp, idx, tag=tag, scene_idx=scene_idx)

def render5(script_path, out_path):
    global _EP_NUM, LAST_CHAPTERS
    # Timer segments are drawn inside render2.timer_segment, which pastes
    # render2.hud; point that call at hud5 so every frame type carries
    # the same progress furniture.
    import render2 as _r2
    _r2.hud = hud5
    script = json.load(open(script_path))
    _pick_citation(script)
    _USED.clear()
    LAST_CHAPTERS = []
    # Cross-episode memory: pictures the last 5 episodes used (recorded in
    # state.json by main.py) -- HARD RULE: the matcher never picks them
    # while a fresh picture exists (see _best_match).
    _RECENT.clear()
    try:
        st = json.load(open(os.path.join(ROOT, "state.json")))
        for e in st.get("published", [])[-5:]:
            _RECENT.update(e.get("art", []))
    except Exception:
        pass
    try:
        _EP_NUM = int(script.get("id", 0))
    except (TypeError, ValueError):
        _EP_NUM = 0
    sid = script.get("id", "x")
    tmp = os.path.join(ROOT, "out", f"tmp5_{sid}"); os.makedirs(tmp, exist_ok=True)
    segs, plan, marks = [], [], []
    scenes = script["scenes"]
    timer_idx = next((k for k, s in enumerate(scenes) if s["type"] == "timer"), None)
    n_items = len(script.get("checklist", []))
    # GAP 7: the episode's number card drives the locked tease (after
    # the card) and the personal route card (before the verdict).
    bignum_idx, ep_bands = None, None
    for k, s in enumerate(scenes):
        if s.get("type") == "card" and s.get("card") == "bignum":
            pb = _parse_bands(s.get("sub", ""))
            if pb:
                bignum_idx, ep_bands = k, pb
                break
    tseg, td, thero = title_segment(script, tmp)
    segs.append(tseg); plan.append(("drive", td)); marks.append(None)
    if thero:
        _USED[thero] += 1  # the title card shows it: record it like any picture
    names = ", ".join(nm.lower() for nm in script["checklist"])
    cw_ = {2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six",
           7: "Seven", 8: "Eight"}.get(n_items, str(n_items))
    def _intro_roadmap(check):
        seg, dd = roadmap_segment(script, check,
            f"Here is the map. {cw_} stops: {names}. Finish the map, and you finish with a new number.",
            tmp, "intro")
        segs.append(seg); plan.append(("calm", dd)); marks.append(None)
    # v6.2 item 2: scene 0 renders first - possibly in two halves with
    # the intro roadmap between them, so the map lands by ~0:40 even
    # when the opening narration runs long (see _scene0_parts).
    intro_done = False
    # An unsplit seg0.mp4 in cache means a previous run of this same
    # script already decided no split - skip the probe synthesis.
    parts0 = [scenes[0]] if scenes and _seg_cached(tmp, "0") else \
        (_scene0_parts(scenes[0], tmp) if scenes else [])
    for pi, psc in enumerate(parts0):
        tag = "0" if len(parts0) == 1 else ("0a" if pi == 0 else "0b")
        seg, mk, tt = _render_scene(script, psc, tmp, 0 if pi == 0 else tag, tag,
                                    scene_idx=0)
        segs.append(seg); plan.append((mk, tt)); marks.append(scenes[0].get("section"))
        if len(parts0) == 2 and pi == 0 and n_items >= 2:
            _intro_roadmap((scenes[1] if len(scenes) > 1 else psc).get("check", 1))
            intro_done = True
    for i, sc in enumerate(scenes):
        if i == 0:
            continue
        if ep_bands and bignum_idx is not None and i == bignum_idx + 1 and i != 1:
            seg, dd = tease_segment(script, ep_bands,
                                    scenes[bignum_idx].get("check", 0), tmp)
            segs.append(seg); plan.append(("calm", dd)); marks.append(None)
        # Gap 2: the roadmap returns between sections with updated state.
        if i == 1 and n_items >= 2 and not intro_done:
            _intro_roadmap(sc.get("check", 1))
        elif timer_idx is not None and i == timer_idx and i > 1 and sc.get("check", 0) >= 2:
            seg, dd = roadmap_segment(script, sc.get("check", 0),
                "Map check. The first stops are done. Now the real work.", tmp, "mid")
            segs.append(seg); plan.append(("calm", dd)); marks.append(None)
        elif i == len(scenes) - 1 and i >= 3 and i != timer_idx:
            seg, dd = roadmap_segment(script, sc.get("check", max(0, n_items - 1)),
                "The map is complete. Every stop checked. One thing left: your new number.",
                tmp, "final", final=True)
            segs.append(seg); plan.append(("calm", dd)); marks.append(None)
        if ep_bands and i == len(scenes) - 1 and i >= 3 and i != timer_idx:
            seg, dd = route_segment(script, ep_bands, sc.get("check", 0),
                                    sc.get("section", ""), tmp)
            segs.append(seg); plan.append(("calm", dd)); marks.append(None)
        seg, mk, tt = _render_scene(script, sc, tmp, i, str(i), scene_idx=i)
        segs.append(seg); plan.append((mk, tt)); marks.append(sc.get("section"))
    es = end_segment(script, tmp)
    if es:
        segs.append(es[0]); plan.append(("calm", es[1])); marks.append(None)
    sseg, sd = safety_segment(script, tmp)
    segs.append(sseg); plan.append(("calm", sd)); marks.append(None)
    # v6.2 item 3: YouTube chapters from the REAL assembled timeline -
    # marks[i] is segs[i]'s section (None for inserted segments) and
    # plan[i] its seconds, so title/roadmap/tease/route time is counted
    # (the old scene-only walk in main.py drifted by all of it). The
    # first chapter is pinned to 0:00: YouTube requires exactly 0:00.
    LAST_CHAPTERS = []
    _ct, _clab = 0.0, None
    for _sec, (_mk, _dd) in zip(marks, plan):
        if _sec and _sec != _clab:
            LAST_CHAPTERS.append((_ct, _sec)); _clab = _sec
        _ct += _dd
    if LAST_CHAPTERS:
        LAST_CHAPTERS[0] = (0.0, LAST_CHAPTERS[0][1])
    print("chapters (renderer timeline):",
          [(f"{s:.1f}", l) for s, l in LAST_CHAPTERS])
    body = os.path.join(tmp, "body.mp4")
    inputs = []
    for s in segs: inputs += ["-i", s]
    parts = "".join(f"[{i}:v]fps=30,format=yuv420p,setpts=PTS-STARTPTS[v{i}];"
                    f"[{i}:a]aresample=44100,asetpts=PTS-STARTPTS[a{i}];" for i in range(len(segs)))
    chain = "".join(f"[v{i}][a{i}]" for i in range(len(segs)))
    fc = parts + chain + f"concat=n={len(segs)}:v=1:a=1[v][a]"
    run(["ffmpeg", "-y"] + inputs + ["-filter_complex", fc, "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-c:a", "aac", body])
    total = dur(body)
    mus = music_track(plan, total, tmp, _EP_NUM)
    # Mastering chain measured against the reference channel (-14.1..-14.5 LUFS):
    # hard voice compression first (their narrator has a low crest factor), then
    # mix, make-up gain and a true limiter with level compensation OFF.
    run(["ffmpeg", "-y", "-i", body, "-i", mus,
         "-filter_complex",
         "[0:a]highpass=f=70,equalizer=f=3000:t=q:w=1:g=3,acompressor=threshold=0.35:ratio=4:attack=3:release=100,alimiter=limit=0.7:level=false[vox];"
         "[vox][1:a]amix=inputs=2:duration=first:normalize=0,volume=8dB,alimiter=limit=0.89:level=false[a]",
         "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", out_path])
    print("rendered v5:", out_path, f"{total:.0f}s")
    LAST_USED[:] = sorted(f for f, c in _USED.items() if c > 0)
    return total

if __name__ == "__main__":
    render5(sys.argv[1], sys.argv[2])
