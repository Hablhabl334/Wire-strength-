"""Wire Strength renderer v3. NO AI/LLM calls anywhere.
Built from the measured top-8 analysis (TOP8_ANALYSIS.md):
- NO zoom/pan. Static framing, like the winners.
- ANIM scenes: the character cycles exercise poses (top->mid->bottom->mid).
- EMPHASIS TEXT: narration is split into phrases; each phrase is voiced on its
  own and shown on screen exactly while it is spoken. ALL-CAPS words render in
  the accent colour. This replaces v1/v2's static caption (the sync bug).
- Glow-pulse overlay option for anatomy scenes.
- Voice bus: high-pass + presence EQ + compression, mastered to -14 LUFS.
HUD, infographic cards and TIMER scenes are inherited from render2."""
import json, math, os, re, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render import tts, dur, run, music_bed, ROOT
from render2 import hud, card_image, fit_cover, timer_segment, F, FONT
from render2 import CYAN, GOLD, RED, WHITE, GREY, DARK, W, H, FPS

ACCENT = CYAN

def phrases(text):
    if "|" in text:
        parts = [p.strip() for p in text.split("|") if p.strip()]
    else:
        parts = []
        for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
            words = sent.split()
            while len(words) > 8:
                cut = 8
                for i in range(8, 3, -1):
                    if words[i - 1].endswith((",", ";", ":")):
                        cut = i; break
                parts.append(" ".join(words[:cut])); words = words[cut:]
            if words: parts.append(" ".join(words))
    return parts

def phrase_png(text, max_w=1560):
    words = text.split()
    lines, cur = [], ""
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    for w_ in words:
        t = (cur + " " + w_).strip()
        if probe.textlength(t, font=F(56)) > max_w and cur:
            lines.append(cur); cur = w_
        else:
            cur = t
    if cur: lines.append(cur)
    im = Image.new("RGBA", (W, 190), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    y = 8
    for ln in lines[:2]:
        x = (W - probe.textlength(ln, font=F(56))) / 2
        for w_ in ln.split():
            col = ACCENT if (len(w_) > 2 and w_.strip(".,!?").isupper()) else WHITE
            d.text((x, y), w_, font=F(56), fill=col + (255,),
                   stroke_width=3, stroke_fill=(0, 0, 0, 255))
            x += probe.textlength(w_ + " ", font=F(56))
        y += 76
    return im

def base_png(script, scene, tmp, idx):
    p = os.path.join(tmp, f"base{idx}.png")
    if scene["type"] == "card":
        card_image(script, scene).save(p)
    else:
        img = Image.open(os.path.join(ROOT, "assets", scene["asset"])).convert("RGB")
        fit_cover(img, W, H).save(p)
    return p

def narrated_segment(script, scene, tmp, idx):
    base = base_png(script, scene, tmp, idx)
    hud_p = os.path.join(tmp, f"hud{idx}.png")
    hud(script, scene, scene.get("check", 0)).save(hud_p)
    subs = []
    for j, ph in enumerate(phrases(scene["narration"])):
        wav = tts(ph, os.path.join(tmp, f"p{idx}_{j}"))
        d = dur(wav) + 0.12
        pp = os.path.join(tmp, f"ph{idx}_{j}.png"); phrase_png(ph).save(pp)
        seg = os.path.join(tmp, f"seg{idx}_{j}.mp4")
        run(["ffmpeg", "-y", "-loop", "1", "-i", base, "-i", hud_p, "-i", pp, "-i", wav,
             "-filter_complex", "[0:v][1:v]overlay=0:0[a];[a][2:v]overlay=0:830[b];"
             "[3:a]apad=pad_dur=0.12[aud]",
             "-map", "[b]", "-map", "[aud]", "-t", f"{d:.2f}", "-r", "30",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", seg])
        subs.append(seg)
    print(f"scene {idx} ({scene['type']}) {len(subs)} phrases")
    return subs

def anim_segment(script, scene, tmp, idx):
    poses = [fit_cover(Image.open(os.path.join(ROOT, "assets", a)).convert("RGB"), W, H)
             for a in scene["poses"]]
    seq = scene.get("seq", list(range(len(poses))) + list(range(len(poses) - 2, 0, -1)))
    cycle = scene.get("cycle", 2.4)
    phs = phrases(scene["narration"])
    wavs = [tts(ph, os.path.join(tmp, f"pa{idx}_{j}")) for j, ph in enumerate(phs)]
    durs = [dur(w) + 0.12 for w in wavs]
    total = sum(durs)
    bounds = np.cumsum([0] + durs)
    sr = 44100
    track = np.zeros(int(total * sr), dtype=np.float32)
    for j, w in enumerate(wavs):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", w, "-f", "f32le", "-ac", "1",
                              "-ar", str(sr), "-"], capture_output=True).stdout
        v = np.frombuffer(raw, dtype=np.float32)
        s0 = int(bounds[j] * sr); track[s0:s0 + len(v)] += v[:max(0, len(track) - s0)]
    aud = os.path.join(tmp, f"aa{idx}.wav")
    p = subprocess.run(["ffmpeg", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "-",
                        "-c:a", "pcm_s16le", aud], input=track.tobytes(), capture_output=True)
    if p.returncode != 0: raise RuntimeError("anim audio failed")
    fps_a = 8
    fdir = os.path.join(tmp, f"af{idx}"); os.makedirs(fdir, exist_ok=True)
    hud_im = hud(script, scene, scene.get("check", 0))
    for fi in range(int(total * fps_a)):
        tt = fi / fps_a
        pose_i = seq[int(tt / (cycle / len(seq))) % len(seq)]
        fr = poses[pose_i].copy()
        j = int(np.searchsorted(bounds, tt, side="right") - 1)
        fr.paste(phrase_png(phs[j]), (0, 830), phrase_png(phs[j]))
        fr.paste(hud_im, (0, 0), hud_im)
        fr.save(os.path.join(fdir, f"f{fi:04d}.png"))
    seg = os.path.join(tmp, f"seg{idx}.mp4")
    run(["ffmpeg", "-y", "-framerate", str(fps_a), "-i", os.path.join(fdir, "f%04d.png"),
         "-i", aud, "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-c:a", "aac",
         "-shortest", seg])
    print(f"scene {idx} (anim) {total:.1f}s")
    return [seg]

def render3(script_path, out_path):
    script = json.load(open(script_path))
    sid = script.get("id", "x")
    tmp = os.path.join(ROOT, "out", f"tmp3_{sid}"); os.makedirs(tmp, exist_ok=True)
    segs = []
    for i, sc in enumerate(script["scenes"]):
        first = os.path.join(tmp, f"seg{i}.mp4") if sc["type"] in ("timer", "anim") else os.path.join(tmp, f"seg{i}_0.mp4")
        if os.path.exists(first) and os.path.getsize(first) > 10000:
            got = sorted(f for f in os.listdir(tmp) if f.startswith(f"seg{i}") and f.endswith(".mp4"))
            segs += [os.path.join(tmp, f) for f in got]; print(f"scene {i} cached"); continue
        if sc["type"] == "timer":
            segs.append(timer_segment(script, sc, tmp, i))
        elif sc["type"] == "anim":
            segs += anim_segment(script, sc, tmp, i)
        else:
            segs += narrated_segment(script, sc, tmp, i)
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
    bed = os.path.join(tmp, "bed.m4a"); music_bed(total, bed)
    run(["ffmpeg", "-y", "-i", body, "-i", bed,
         "-filter_complex",
         "[0:a]highpass=f=70,equalizer=f=3000:t=q:w=1:g=3,acompressor=threshold=0.5:ratio=3:attack=5:release=120[vox];"
         "[1:a]volume=0.5[bg];[vox][bg]amix=inputs=2:duration=first,loudnorm=I=-14:TP=-1.5:LRA=11[a]",
         "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", out_path])
    print("rendered v3:", out_path, f"{total:.0f}s")
    return total

if __name__ == "__main__":
    render3(sys.argv[1], sys.argv[2])
