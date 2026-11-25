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
import json, math, os, subprocess, sys
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

def card_image4(scene, reveal=99):
    im = Image.new("RGB", (W, H), DARK); d = ImageDraw.Draw(im)
    kind = scene["card"]
    if kind == "bignum":
        d.text((140, 300), scene["big"], font=F(230), fill=CYAN)
        if reveal >= 1: d.text((146, 580), scene["label"], font=F(64), fill=WHITE)
        if reveal >= 2: d.text((146, 680), scene.get("sub", ""), font=F(38, False), fill=GREY)
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
    return {"tr": (W - 48 - w, 128), "br": (W - 48 - w, H - 470),
            "bl": (48, H - 470), "mr": (W - 48 - w, 400),
            "ml": (48, 400)}.get(pos, (W - 48 - w, 128))

def current_swap(beats, j, default_asset):
    """v5: latest swap beat at or before phrase j wins, else the scene asset."""
    asset = default_asset
    for b in beats:
        if b.get("kind") == "swap" and j >= b.get("at", 0):
            asset = b.get("asset", asset)
    return asset

def draw_beats(fr, beats, j):
    d = ImageDraw.Draw(fr, "RGBA")
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    visible = [b for b in beats if b.get("kind") != "swap" and j >= b.get("at", 0)][-2:]
    for b in visible:
        kind = b["kind"]; pos = b.get("pos", "tr")
        if kind == "fact":
            w_, h_ = 860, 300
            x, y = _beat_xy(pos, w_, h_)
            d.rounded_rectangle([x, y, x + w_, y + h_], 18, fill=(18, 18, 18, 240), outline=GOLD, width=3)
            d.text((x + 28, y + 22), b.get("title", ""), font=F(46), fill=GOLD)
            yy = y + 92
            for ln in b.get("lines", [])[:2]:
                d.text((x + 28, yy), ln, font=F(36, False), fill=WHITE); yy += 62
            continue
        if kind == "chip":
            t = b["text"]; w_ = int(probe.textlength(t, font=F(40))) + 56
            x, y = _beat_xy(pos, w_, 84)
            d.rounded_rectangle([x, y, x + w_, y + 84], 18, fill=(18, 18, 18, 235), outline=CYAN, width=3)
            d.text((x + 28, y + 20), t, font=F(40), fill=WHITE)
        elif kind == "stat":
            t = b["text"]; w_ = 430
            x, y = _beat_xy(pos, w_, 190)
            d.rounded_rectangle([x, y, x + w_, y + 190], 18, fill=(18, 18, 18, 235), outline=CYAN, width=3)
            d.text((x + 28, y + 16), t, font=F(84), fill=CYAN)
            d.text((x + 30, y + 122), b.get("label", ""), font=F(30, False), fill=GREY)
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
            d.text((x + 28, y + 18), b.get("title", ""), font=F(34), fill=GOLD)
            yy = y + 76
            for label, pct, colname in b["items"]:
                col = CYAN if colname == "cyan" else ((200, 60, 60) if colname == "red" else GREY)
                d.text((x + 28, yy), label, font=F(32, False), fill=WHITE)
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

def scene_audio(phs, tmp, tag, lead_pause=0.0):
    """Returns (wav_path, phrase_bounds, total). Gaps: 0.22s, +0.3s after sentences."""
    wavs = [tts(ph, os.path.join(tmp, f"{tag}_{j}")) for j, ph in enumerate(phs)]
    durs = []
    for w in wavs:
        durs.append(dur(w))
    gaps = [0.22 + (0.3 if ph.rstrip().endswith((".", "!", "?")) else 0.0) for ph in phs]
    total = lead_pause + sum(durs) + sum(gaps[:-1])
    track = np.zeros(int(total * SR) + SR // 2, dtype=np.float32)
    bounds = [lead_pause]
    t = lead_pause
    for j, w in enumerate(wavs):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", w, "-f", "f32le", "-ac", "1",
                              "-ar", str(SR), "-"], capture_output=True).stdout
        v = np.frombuffer(raw, dtype=np.float32)
        s0 = int(t * SR); track[s0:s0 + len(v)] += v[:max(0, len(track) - s0)]
        t += durs[j] + (gaps[j] if j < len(phs) - 1 else 0.0)
        bounds.append(t)
    out = os.path.join(tmp, f"{tag}_full.wav")
    p = subprocess.run(["ffmpeg", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-",
                        "-c:a", "pcm_s16le", out], input=track.tobytes(), capture_output=True)
    if p.returncode != 0: raise RuntimeError("scene audio failed")
    return out, bounds, total

def narrated_frames(script, scene, tmp, idx):
    phs = phrases5(scene["narration"])
    aud, bounds, total = scene_audio(phs, tmp, f"s{idx}", scene.get("lead_pause", 0.0))
    is_card = scene["type"] == "card"
    base_art = None
    swap_cache = {}
    if not is_card:
        base_art = fit_cover(Image.open(os.path.join(ROOT, "assets", scene["asset"])).convert("RGB"), W, H)
        # v5: pre-load every swap target so the picture can change mid-scene.
        for b in scene.get("beats", []):
            if b.get("kind") == "swap" and b.get("asset"):
                swap_cache[b["asset"]] = fit_cover(
                    Image.open(os.path.join(ROOT, "assets", b["asset"])).convert("RGB"), W, H)
    hud_im = hud(script, scene, scene.get("check", 0))
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
            cur = current_swap(scene.get("beats", []), j, scene["asset"])
            fr.paste(swap_cache.get(cur, base_art), (sway, 0))
            g = glow_cache[fi % 20]; fr.paste(g, (0, 0), g)
        if tt >= scene.get("lead_pause", 0.0):
            pp = pp_cache[j]
            fr.paste(pp, (0, 830), pp)
        draw_beats(fr, scene.get("beats", []), j)
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
    hud_im = hud(script, scene, scene.get("check", 0))
    pp_cache = [phrase_png(ph) for ph in phs]
    fdir = os.path.join(tmp, f"af{idx}"); os.makedirs(fdir, exist_ok=True)
    for fi in range(int(total * FPS_A)):
        tt = fi / FPS_A
        j = max(0, int(np.searchsorted(bounds, tt, side="right") - 1))
        si = (j // every) % len(sets)
        s = sets[si]; sq = seqs[si]
        pose = s[sq[int(tt / (cycle / len(sq))) % len(sq)]]
        fr = pose.copy()
        if tt >= scene.get("lead_pause", 0.0):
            pp = pp_cache[j]; fr.paste(pp, (0, 830), pp)
        draw_beats(fr, scene.get("beats", []), j)
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

def render5(script_path, out_path):
    script = json.load(open(script_path))
    sid = script.get("id", "x")
    tmp = os.path.join(ROOT, "out", f"tmp5_{sid}"); os.makedirs(tmp, exist_ok=True)
    segs, plan = [], []
    for i, sc in enumerate(script["scenes"]):
        cached = os.path.join(tmp, f"seg{i}.mp4")
        if os.path.exists(cached) and os.path.getsize(cached) > 10000:
            segs.append(cached); plan.append((sc.get("music", "calm"), dur(cached)))
            print(f"scene {i} cached"); continue
        if sc["type"] == "timer":
            segs.append(timer_segment(script, sc, tmp, i)); plan.append(("drive", dur(segs[-1])))
        elif sc["type"] == "anim":
            seg, mk, tt = anim_frames(script, sc, tmp, i); segs.append(seg); plan.append((mk, tt))
        else:
            seg, mk, tt = narrated_frames(script, sc, tmp, i); segs.append(seg); plan.append((mk, tt))
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
    return total

if __name__ == "__main__":
    render5(sys.argv[1], sys.argv[2])
