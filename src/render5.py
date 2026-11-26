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

def card_image4(scene, reveal=99):
    im = Image.new("RGB", (W, H), DARK); d = ImageDraw.Draw(im)
    kind = scene["card"]
    if kind == "bignum":
        d.text((140, 300), scene["big"], font=F(230), fill=CYAN)
        if reveal >= 1: d.text((146, 580), scene["label"], font=F(64), fill=WHITE)
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

def _draw_focus(fr, part, px, py, tt):
    d = ImageDraw.Draw(fr)
    r = 36 + int(5 * math.sin(tt * 5.0))
    d.ellipse([px - r, py - r, px + r, py + r], outline=RED, width=6)
    d.ellipse([px - r - 13, py - r - 13, px + r + 13, py + r + 13], outline=WHITE, width=2)
    d.ellipse([px - 5, py - 5, px + 5, py + 5], fill=RED)
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
        d.line([xa, ya, xb, yb], fill=WHITE, width=3)
    d.rounded_rectangle([lx, ly, lx + tw + 36, ly + 48], 8, fill=(8, 10, 12), outline=CYAN, width=2)
    d.text((lx + 18, ly + 8), label, font=fnt, fill=WHITE)
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
    if _USED[asset] == 0:
        _USED[asset] += 1
        return asset
    role, fam = man[asset].get("role"), man[asset].get("family")
    order = {f: i for i, f in enumerate(man)}
    cands = [f for f, im in man.items() if im.get("role") == role and f != asset]
    fresh = [f for f in cands if _USED[f] < 2]
    if fresh:
        cands = fresh
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
    cands.sort(key=lambda f: (_USED[f], 0 if man[f].get("family") == fam else 1, order[f]))
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

_POOL_ROLES = {"still", "anatomy", "closeup"}
def _best_match(tagset, exclude, context=None):
    """Best picture for these words (never `exclude`). Habl's rules:
    something NEW beats a repeat -- a picture already shown this episode
    only comes back if it matches clearly better (by 2+) and has not
    already appeared twice; a picture the last episodes used is penalised
    so cross-episode repeats stay RARE. Returns (file, effective score):
    the raw word-match score minus the recent-episode penalty."""
    man = _manifest()
    order = {f: i for i, f in enumerate(man)}
    cur_fam = man.get(exclude, {}).get("family")
    pool = [f for f, im in man.items()
            if im.get("role") in _POOL_ROLES and f != exclude]
    if not pool:
        return None, 0
    def eff(f):
        return _score(f, tagset) - (2 if f in _RECENT else 0)
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

def _prev_opener():
    if _EP_NUM <= 1:
        return None
    try:
        prev = json.load(open(os.path.join(ROOT, "bank", f"{_EP_NUM - 1:03d}.json")))
        sc0 = prev["scenes"][0]
        return sc0.get("asset") or sc0.get("art")
    except Exception:
        return None

def draw_beats(fr, beats, j, scene_idx=None):
    d = ImageDraw.Draw(fr, "RGBA")
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    visible = [b for b in beats if b.get("kind") != "swap" and j >= b.get("at", 0)][-2:]
    for b in visible:
        kind = b["kind"]; pos = b.get("pos", "tr")
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
            continue
        if kind == "chip":
            t = b["text"]; w_ = int(probe.textlength(t, font=F(40))) + 56
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
                w_ = 430
                x, y = _beat_xy(pos, w_, 190)
                d.rounded_rectangle([x, y, x + w_, y + 190], 18, fill=(18, 18, 18, 235), outline=CYAN, width=3)
                d.text((x + 28, y + 16), t, font=F(fit_size(t, 84, w_ - 56)), fill=CYAN)
                _lbl = b.get("label", "")
                d.text((x + 30, y + 122), _lbl, font=F(fit_size(_lbl, 30, w_ - 58, False), False), fill=GREY)
        elif kind == "mark":
            sym = "✓" if b.get("ok", True) else "✗"
            col = CYAN if b.get("ok", True) else RED
            t = b.get("text", ""); w_ = int(probe.textlength(t, font=F(40))) + 170
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
            img = Image.open(os.path.join(ROOT, "assets", b["asset"])).convert("RGB")
            img = fit_cover(img, 500, 290)
            x, y = _beat_xy(pos, 500, 290)
            fr.paste(img, (x, y))
            d.rectangle([x, y, x + 500, y + 290], outline=CYAN, width=4)
            if b.get("label"):
                d.rectangle([x, y + 244, x + 500, y + 290], fill=(0, 0, 0))
                d.text((x + 16, y + 250), b["label"], font=F(30), fill=WHITE)
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
    """Progress furniture (Rep Theory gap 1): TL = red bar + section
    title; TR = SECTION n/N + progress dots (cyan = done, ringed =
    current, grey = upcoming) instead of the episode-title badge;
    bottom = the checklist bar with the channel name corrected."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rectangle([36, 30, 46, 78], fill=RED + (255,))
    d.text((60, 34), scene.get("section", ""), font=F(34), fill=WHITE + (255,))
    items = script.get("checklist", [])
    n = len(items)
    if n:
        cur = max(0, min(done_upto, n - 1))
        label = f"SECTION {cur + 1}/{n}"
        tw = d.textlength(label, font=F(26))
        r, gap = 11, 16
        dots_w = n * (2 * r) + (n - 1) * gap
        x0 = W - 36 - dots_w
        d.text((x0 - tw - 24, 40), label, font=F(26), fill=WHITE + (255,))
        cy = 54
        for i in range(n):
            cx = x0 + r + i * (2 * r + gap)
            if i < cur:
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=CYAN + (255,))
            elif i == cur:
                d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=WHITE + (255,), width=3)
                d.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=CYAN + (255,))
            else:
                d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=GREY + (255,), width=3)
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

def narrated_frames(script, scene, tmp, idx):
    phs = phrases5(scene["narration"])
    aud, bounds, total = scene_audio(phs, tmp, f"s{idx}", scene.get("lead_pause", 0.0))
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
            cands = [f for f, im in man.items() if im.get("role") in ("still", "closeup")]
            def _okey(f):
                s = _score(f, open_tags) - (1 if f == prev_o else 0) - (2 if f in _RECENT else 0)
                return (-s, 1 if f == prev_o else 0, _USED[f], order[f])
            pick = min(cands, key=_okey) if cands else opener
            if _score(pick, open_tags) <= 0 and pick != opener:
                pick = opener  # nothing matches the words: keep the author's
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
                if pre.get(opener, opener) != cur:
                    pick = pre.get(opener, opener)
                else:
                    pick = _auto_pick(cur, shown)
                if pick:
                    beats.append({"at": j, "kind": "swap", "asset": pick})
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
    fdir = os.path.join(tmp, f"ff{idx}"); os.makedirs(fdir, exist_ok=True)
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
            cur = current_swap(beats, j, scene["asset"])
            fr.paste(swap_cache.get(cur, base_art), (sway, 0))
            g = glow_cache[fi % 20]; fr.paste(g, (0, 0), g)
        draw_beats(fr, draw_beat_list, j, scene_idx=idx)
        if j in focus:
            _part, _px, _py = focus[j]
            _draw_focus(fr, _part, _px + (0 if is_card else sway), _py, tt)
        if tt >= scene.get("lead_pause", 0.0):
            pp = pp_cache[j]
            fr.paste(pp, (0, phrase_y), pp)
        fr.paste(hud_im, (0, 0), hud_im)
        d = ImageDraw.Draw(fr)
        d.rectangle([60, 92, 60 + int(300 * min(1.0, tt / total)), 100], fill=CYAN)
        fr.save(os.path.join(fdir, f"f{fi:04d}.png"))
    seg = os.path.join(tmp, f"seg{idx}.mp4")
    run(["ffmpeg", "-y", "-framerate", str(FPS_A), "-i", os.path.join(fdir, "f%04d.png"),
         "-i", aud, "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-c:a", "aac",
         "-shortest", seg])
    print(f"scene {idx} ({scene['type']}) {total:.1f}s {len(phs)} phrases")
    return seg, scene.get("music", "calm"), total

def anim_frames(script, scene, tmp, idx):
    phs = phrases5(scene["narration"])
    aud, bounds, total = scene_audio(phs, tmp, f"a{idx}", scene.get("lead_pause", 0.0))
    angle_sets = scene.get("angles") or [scene["poses"]]
    sets = [[fit_cover(Image.open(os.path.join(ROOT, "assets", a)).convert("RGB"), W, H) for a in s]
            for s in angle_sets]
    seqs = []
    for s in sets:
        idxs = list(range(len(s)))
        seqs.append(idxs + idxs[-2:0:-1] if len(s) > 2 else idxs + idxs[::-1])
    cycle = scene.get("cycle", 2.4); every = scene.get("angle_every", 3)
    hud_im = hud5(script, scene, scene.get("check", 0))
    pp_cache = [phrase_png(ph) for ph in phs]
    fdir = os.path.join(tmp, f"af{idx}"); os.makedirs(fdir, exist_ok=True)
    for fi in range(int(total * FPS_A)):
        tt = fi / FPS_A
        j = max(0, int(np.searchsorted(bounds, tt, side="right") - 1))
        si = (j // every) % len(sets)
        s = sets[si]; sq = seqs[si]
        pose = s[sq[int(tt / (cycle / len(sq))) % len(sq)]]
        fr = pose.copy()
        draw_beats(fr, scene.get("beats", []), j)
        if tt >= scene.get("lead_pause", 0.0):
            pp = pp_cache[j]; fr.paste(pp, (0, 830), pp)
        fr.paste(hud_im, (0, 0), hud_im)
        fr.save(os.path.join(fdir, f"f{fi:04d}.png"))
    seg = os.path.join(tmp, f"seg{idx}.mp4")
    run(["ffmpeg", "-y", "-framerate", str(FPS_A), "-i", os.path.join(fdir, "f%04d.png"),
         "-i", aud, "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-c:a", "aac",
         "-shortest", seg])
    print(f"scene {idx} (anim) {total:.1f}s angles={len(sets)}")
    return seg, scene.get("music", "drive"), total

def music_track(plan, total, tmp):
    """plan: list of (kind, seconds). Build a ducked bed: consecutive same-kind
    sections merged, each trimmed + faded, joined with the concat filter."""
    files = {"dark": "bed_dark.mp3", "calm": "bed_calm.mp3", "drive": "bed_drive.mp3"}
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
    """Gap 2: the episode roadmap -- the checklist as a chain of stop
    cards. Done stops get a cyan check, the current stop glows, future
    stops are padlocked. final=True stamps MAP COMPLETE in gold."""
    items = script.get("checklist", [])
    n = len(items)
    im = Image.new("RGB", (W, H), DARK); d = ImageDraw.Draw(im)
    t = "TODAY'S MAP"
    d.text(((W - d.textlength(t, font=F(66))) / 2, 96), t, font=F(66), fill=WHITE)
    t2 = "FINISH EVERY STOP. EARN YOUR NEW NUMBER."
    d.text(((W - d.textlength(t2, font=F(30))) / 2, 186), t2, font=F(30), fill=GOLD)
    y0, y1 = 350, 690
    cw = min(370, (1760 - (n - 1) * 36) // max(1, n))
    total_w = n * cw + (n - 1) * 36
    x0 = (W - total_w) // 2
    cy = (y0 + y1) // 2
    d.line([x0 + cw // 2, cy, x0 + total_w - cw // 2, cy], fill=(70, 80, 88), width=6)
    for k, name in enumerate(items):
        x = x0 + k * (cw + 36)
        done = final or k < current
        cur = (not final) and k == current
        if cur:
            for g in range(3):
                d.rounded_rectangle([x - 6 + g * 2, y0 - 6 + g * 2, x + cw + 6 - g * 2, y1 + 6 - g * 2],
                                    18, outline=CYAN)
        d.rounded_rectangle([x, y0, x + cw, y1], 16, fill=(16, 20, 24),
                            outline=CYAN if cur else (90, 100, 108), width=4 if cur else 2)
        num = str(k + 1)
        ncol = CYAN if (done or cur) else GREY
        d.text((x + (cw - d.textlength(num, font=F(84))) / 2, y0 + 22), num, font=F(84), fill=ncol)
        size = 34
        while size > 18 and d.textlength(name, font=F(size)) > cw - 28:
            size -= 2
        words = name.split()
        lines, ln = [], ""
        for w_ in words:
            cand = (ln + " " + w_).strip()
            if d.textlength(cand, font=F(size)) <= cw - 28 or not ln:
                ln = cand
            else:
                lines.append(ln); ln = w_
        if ln: lines.append(ln)
        ly = y0 + 138
        for L in lines[:2]:
            d.text((x + (cw - d.textlength(L, font=F(size))) / 2, ly), L, font=F(size), fill=WHITE)
            ly += size + 8
        sy = y1 - 78
        if done:
            d.ellipse([x + cw / 2 - 62, sy, x + cw / 2 - 10, sy + 52], fill=CYAN)
            d.text((x + cw / 2 - 62 + (52 - d.textlength("✓", font=F(36))) / 2, sy + 4), "✓", font=F(36), fill=(0, 0, 0))
            d.text((x + cw / 2 + 2, sy + 10), "DONE", font=F(30), fill=CYAN)
        elif cur:
            t3 = "YOU ARE HERE"
            d.text((x + (cw - d.textlength(t3, font=F(29))) / 2, sy + 10), t3, font=F(29), fill=GOLD)
        else:
            lx = x + cw / 2 - 66
            d.arc([lx + 8, sy - 12, lx + 36, sy + 22], start=180, end=360, fill=GREY, width=5)
            d.rounded_rectangle([lx, sy + 8, lx + 44, sy + 46], 6, fill=GREY)
            d.ellipse([lx + 19, sy + 20, lx + 25, sy + 26], fill=DARK)
            d.text((lx + 54, sy + 8), "LOCKED", font=F(28), fill=GREY)
    if final:
        layer = Image.new("RGBA", (1240, 300), (0, 0, 0, 0)); ld = ImageDraw.Draw(layer)
        ld.rounded_rectangle([36, 36, 1204, 264], 26, outline=GOLD + (255,), width=8)
        t4 = "MAP COMPLETE"
        ld.text(((1240 - ld.textlength(t4, font=F(92))) / 2, 92), t4, font=F(92), fill=GOLD + (255,))
        layer = layer.rotate(10, resample=Image.BICUBIC, expand=True)
        im.paste(layer, ((W - layer.width) // 2, 872 - layer.height // 2), layer)
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

def route_image(script, bands, check, section):
    """GAP 7 personal routing: the payoff card before the verdict -
    every band of the viewer's number routed to its starting point."""
    im = Image.new("RGB", (W, H), DARK)
    d = ImageDraw.Draw(im)
    t = "YOUR ROUTE"
    d.text(((W - d.textlength(t, font=F(64))) / 2, 140), t, font=F(64), fill=CYAN)
    y = 300
    for rng, lab, route, col in _route_rows(script, bands):
        d.rounded_rectangle([220, y, W - 220, y + 128], 16,
                            fill=(22, 22, 27), outline=col, width=3)
        d.text((260, y + 18), rng, font=F(44), fill=col)
        d.text((260, y + 74), lab, font=F(30), fill=GREY)
        rt = "-> " + route
        d.text((W - 260 - d.textlength(rt, font=F(38)), y + 42), rt, font=F(38), fill=WHITE)
        y += 162
    t = "EVERY ROUTE ENDS AT THE RETEST"
    d.text(((W - d.textlength(t, font=F(30))) / 2, y + 40), t, font=F(30), fill=GREY)
    hud_im = hud5(script, {"section": section, "check": check}, check)
    im.paste(hud_im, (0, 0), hud_im)
    return im

def route_segment(script, bands, check, section, tmp):
    ip = os.path.join(tmp, "route.png")
    route_image(script, bands, check, section).save(ip)
    parts = []
    for rng, _lab, route, _c in _route_rows(script, bands):
        parts.append(f"{rng.lower()}: {route.lower()}")
    line = "Here is your route. " + ". ".join(parts) + "."
    wav = tts(line, os.path.join(tmp, "route"))
    dd = dur(wav) + 0.6
    seg = os.path.join(tmp, "route.mp4")
    run(["ffmpeg", "-y", "-loop", "1", "-framerate", "30", "-i", ip, "-i", wav,
         "-t", f"{dd:.2f}", "-vf", "format=yuv420p", "-c:v", "libx264", "-c:a", "aac", seg])
    print(f"route segment: {dd:.1f}s")
    return seg, dd

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

def render5(script_path, out_path):
    global _EP_NUM
    # Timer segments are drawn inside render2.timer_segment, which pastes
    # render2.hud; point that call at hud5 so every frame type carries
    # the same progress furniture.
    import render2 as _r2
    _r2.hud = hud5
    script = json.load(open(script_path))
    _pick_citation(script)
    _USED.clear()
    # Cross-episode memory: pictures the last 3 episodes used (recorded in
    # state.json by main.py) -- the matcher penalises them so a picture
    # from an old video comes back only rarely, when it clearly matches.
    _RECENT.clear()
    try:
        st = json.load(open(os.path.join(ROOT, "state.json")))
        for e in st.get("published", [])[-3:]:
            _RECENT.update(e.get("art", []))
    except Exception:
        pass
    try:
        _EP_NUM = int(script.get("id", 0))
    except (TypeError, ValueError):
        _EP_NUM = 0
    sid = script.get("id", "x")
    tmp = os.path.join(ROOT, "out", f"tmp5_{sid}"); os.makedirs(tmp, exist_ok=True)
    segs, plan = [], []
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
    for i, sc in enumerate(scenes):
        if ep_bands and bignum_idx is not None and i == bignum_idx + 1 and i != 1:
            seg, dd = tease_segment(script, ep_bands,
                                    scenes[bignum_idx].get("check", 0), tmp)
            segs.append(seg); plan.append(("calm", dd))
        # Gap 2: the roadmap returns between sections with updated state.
        if i == 1 and n_items >= 2:
            names = ", ".join(nm.lower() for nm in script["checklist"])
            cw_ = {2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six",
                   7: "Seven", 8: "Eight"}.get(n_items, str(n_items))
            seg, dd = roadmap_segment(script, sc.get("check", 1),
                f"Here is the map. {cw_} stops: {names}. Finish the map, and you finish with a new number.",
                tmp, "intro")
            segs.append(seg); plan.append(("calm", dd))
        elif timer_idx is not None and i == timer_idx and i > 1 and sc.get("check", 0) >= 2:
            seg, dd = roadmap_segment(script, sc.get("check", 0),
                "Map check. The first stops are done. Now the real work.", tmp, "mid")
            segs.append(seg); plan.append(("calm", dd))
        elif i == len(scenes) - 1 and i >= 3 and i != timer_idx:
            seg, dd = roadmap_segment(script, sc.get("check", max(0, n_items - 1)),
                "The map is complete. Every stop checked. One thing left: your new number.",
                tmp, "final", final=True)
            segs.append(seg); plan.append(("calm", dd))
        if ep_bands and i == len(scenes) - 1 and i >= 3 and i != timer_idx:
            seg, dd = route_segment(script, ep_bands, sc.get("check", 0),
                                    sc.get("section", ""), tmp)
            segs.append(seg); plan.append(("calm", dd))
        cached = os.path.join(tmp, f"seg{i}.mp4")
        cached_ok = False
        if os.path.exists(cached) and os.path.getsize(cached) > 10000:
            try:
                cd_ = dur(cached); cached_ok = True
            except Exception:
                os.remove(cached)  # truncated by an interrupted run: re-render
        if cached_ok:
            segs.append(cached); plan.append((sc.get("music", "calm"), cd_))
            print(f"scene {i} cached"); continue
        if sc["type"] == "timer":
            segs.append(timer_segment(script, sc, tmp, i)); plan.append(("drive", dur(segs[-1])))
        elif sc["type"] == "anim":
            seg, mk, tt = anim_frames(script, sc, tmp, i); segs.append(seg); plan.append((mk, tt))
        else:
            seg, mk, tt = narrated_frames(script, sc, tmp, i); segs.append(seg); plan.append((mk, tt))
    es = end_segment(script, tmp)
    if es:
        segs.append(es[0]); plan.append(("calm", es[1]))
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
    mus = music_track(plan, total, tmp)
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
