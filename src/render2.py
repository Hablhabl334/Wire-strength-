"""Wire Strength renderer v2. NO AI/LLM calls anywhere.
Adds over v1: persistent HUD dashboard (section title, badge, checklist bar),
PIL infographic cards (bignum / study / layers), and follow-along TIMER scenes
(animated countdown ring, pose sway, phase beeps) - all deterministic code.
Voice: Edge TTS free / Piper offline fallback (see render.py tts)."""
import json, math, os, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render import tts, dur, run, music_bed, ROOT

W, H, FPS = 1920, 1080, 30
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_R = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
CYAN = (0, 229, 255); GOLD = (255, 193, 7); RED = (229, 57, 53)
WHITE = (245, 245, 245); GREY = (140, 140, 140); DARK = (12, 12, 12)

def F(size, bold=True):
    return ImageFont.truetype(FONT if bold else FONT_R, size)

def hud(script, scene, done_upto):
    """Transparent HUD layer: section title TL, badge TR, checklist bar bottom."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rectangle([36, 30, 46, 78], fill=RED + (255,))
    d.text((60, 34), scene.get("section", ""), font=F(34), fill=WHITE + (255,))
    badge = script.get("badge", "")
    tw = d.textlength(badge, font=F(26))
    d.rounded_rectangle([W - tw - 90, 28, W - 36, 80], 10, outline=CYAN + (255,), width=3)
    d.text((W - tw - 63, 40), badge, font=F(26), fill=CYAN + (255,))
    items = script.get("checklist", [])
    if items:
        d.rectangle([0, H - 64, W, H], fill=(0, 0, 0, 190))
        x = 40
        for i, it in enumerate(items):
            mark = "✓ " if i < done_upto else ("▸ " if i == done_upto else "• ")
            col = CYAN if i < done_upto else (WHITE if i == done_upto else GREY)
            t = mark + it
            d.text((x, H - 48), t, font=F(26), fill=col + (255,))
            x += d.textlength(t, font=F(26)) + 46
        t = "WIRE STRENGTH"
        d.text((W - d.textlength(t, font=F(26)) - 40, H - 48), t, font=F(26), fill=GOLD + (255,))
    return im

def fit_cover(img, w, h):
    s = max(w / img.width, h / img.height)
    img = img.resize((int(img.width * s) + 2, int(img.height * s) + 2))
    x = (img.width - w) // 2; y = (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))

def card_image(script, scene):
    im = Image.new("RGB", (W, H), DARK); d = ImageDraw.Draw(im)
    kind = scene["card"]
    if kind == "bignum":
        d.text((140, 300), scene["big"], font=F(230), fill=CYAN)
        d.text((146, 580), scene["label"], font=F(64), fill=WHITE)
        d.text((146, 680), scene.get("sub", ""), font=F(38, False), fill=GREY)
    elif kind == "study":
        d.rounded_rectangle([240, 200, W - 240, 820], 24, fill=(24, 24, 24), outline=GREY, width=2)
        d.rectangle([240, 200, W - 240, 290], fill=RED)
        d.text((290, 224), scene["head"], font=F(40), fill=WHITE)
        y = 350
        for ln in scene["lines"]:
            d.text((290, y), ln, font=F(44, False), fill=WHITE); y += 74
        d.text((290, 740), scene.get("foot", ""), font=F(32, False), fill=GOLD)
    elif kind == "layers":
        d.text((140, 130), scene["title"], font=F(64), fill=WHITE)
        y = 300
        for name, note, pct, colname in scene["layers"]:
            col = CYAN if colname == "cyan" else (WHITE if colname == "white" else GREY)
            bw = int(1300 * pct / 100)
            d.rounded_rectangle([140, y, 140 + bw, y + 110], 16, fill=(30, 30, 30), outline=col, width=4)
            d.text((170, y + 18), name, font=F(52), fill=col)
            d.text((170, y + 122), note, font=F(32, False), fill=GREY)
            y += 220
    return im

def beep_track(seconds, marks, sr=44100):
    """marks: list of (time, freq, len). Returns float32 array."""
    y = np.zeros(int(seconds * sr), dtype=np.float32)
    for t0, f, ln in marks:
        i = int(t0 * sr); n = int(ln * sr)
        seg = 0.25 * np.sin(2 * math.pi * f * np.arange(n) / sr) * np.linspace(1, 0.3, n)
        y[i:i + n] += seg[:max(0, len(y) - i)]
    return y

def mix_voice(track, wav_path, sr=44100):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", wav_path, "-f", "f32le",
                          "-ac", "1", "-ar", str(sr), "-"], capture_output=True).stdout
    v = np.frombuffer(raw, dtype=np.float32)
    n = min(len(v), len(track)); track[:n] += v[:n]
    return track

def timer_segment(script, scene, tmp, idx):
    work, rest, rounds = scene["work"], scene["rest"], scene.get("rounds", 1)
    total = (work + rest) * rounds
    base = Image.open(os.path.join(ROOT, "assets", scene["asset"])).convert("RGB")
    base = fit_cover(base, 1150, H)
    frames_dir = os.path.join(tmp, f"tf{idx}"); os.makedirs(frames_dir, exist_ok=True)
    fps_t = 4
    marks = []
    narr = tts(scene["narration"], os.path.join(tmp, f"t{idx}"))
    track = beep_track(total, marks)
    track = mix_voice(track, narr)
    phase_at = []
    t = 0
    for r in range(rounds):
        phase_at.append((t, "WORK", work, r + 1)); t += work
        phase_at.append((t, "REST", rest, r + 1)); t += rest
    for start, name, length, r in phase_at:
        if name == "WORK":
            marks += [(start, 880, 0.18)]
        else:
            marks += [(start + length - 3, 660, 0.12), (start + length - 2, 660, 0.12),
                      (start + length - 1, 660, 0.12), (start + length, 990, 0.3)]
    track = beep_track(total, marks); track = mix_voice(track, narr)
    n_frames = int(total * fps_t)
    for fi in range(n_frames):
        tt = fi / fps_t
        ph = phase_at[0]
        for p in phase_at:
            if tt >= p[0]: ph = p
        start, name, length, r = ph
        remain = math.ceil(start + length - tt)
        frac = 1 - (tt - start) / length
        fr = Image.new("RGB", (W, H), DARK)
        sway = 6 if int(tt * 2) % 2 == 0 else -6
        fr.paste(base, (770 + sway, 0))
        d = ImageDraw.Draw(fr)
        col = CYAN if name == "WORK" else GOLD
        d.text((90, 150), scene["exercise"], font=F(58), fill=WHITE)
        d.text((90, 240), f"ROUND {r} / {rounds}", font=F(34), fill=GREY)
        cx, cy, rad = 330, 620, 190
        d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=(50, 50, 50), width=26)
        d.arc([cx - rad, cy - rad, cx + rad, cy + rad], start=-90, end=-90 + 360 * frac, fill=col, width=26)
        num = str(remain)
        d.text((cx - d.textlength(num, font=F(150)) / 2, cy - 95), num, font=F(150), fill=col)
        d.text((cx - d.textlength(name, font=F(44)) / 2, cy + 70), name, font=F(44), fill=WHITE)
        fr.paste(hud(script, scene, scene.get("check", 0)), (0, 0), hud(script, scene, scene.get("check", 0)))
        fr.save(os.path.join(frames_dir, f"f{fi:04d}.png"))
    seg = os.path.join(tmp, f"seg{idx}.mp4")
    aud = os.path.join(tmp, f"ta{idx}.wav")
    p = subprocess.run(["ffmpeg", "-y", "-f", "f32le", "-ar", "44100", "-ac", "1", "-i", "-",
                        "-c:a", "pcm_s16le", aud], input=track.tobytes(), capture_output=True)
    if p.returncode != 0: raise RuntimeError("timer audio failed")
    run(["ffmpeg", "-y", "-framerate", str(fps_t), "-i", os.path.join(frames_dir, "f%04d.png"),
         "-i", aud, "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-c:a", "aac",
         "-shortest", seg])
    print(f"timer scene {idx} {total}s")
    return seg

def still_segment(script, scene, tmp, idx):
    narr = tts(scene["narration"], os.path.join(tmp, f"s{idx}"))
    d = dur(narr) + 0.35
    if scene["type"] == "card":
        img_p = os.path.join(tmp, f"card{idx}.png")
        card_image(script, scene).save(img_p)
    else:
        img_p = os.path.join(ROOT, "assets", scene["asset"])
    hud_p = os.path.join(tmp, f"hud{idx}.png")
    hud(script, scene, scene.get("check", 0)).save(hud_p)
    frames = int(d * FPS)
    z = "min(zoom+0.0012,1.22)" if scene.get("move") == "in" else "if(eq(on,1),1.22,max(zoom-0.0012,1.0))"
    cap = scene.get("caption", "").replace("'", "").replace(":", "")
    vf = (f"[0:v]scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
          f"zoompan=z='{z}':d={frames}:s={W}x{H}:fps={FPS}[bg];"
          f"[bg][1:v]overlay=0:0[v0];"
          f"[v0]drawtext=fontfile={FONT}:text='{cap}':fontsize=64:fontcolor=white:"
          f"borderw=3:bordercolor=black:x=(w-text_w)/2:y=h-190[v]")
    seg = os.path.join(tmp, f"seg{idx}.mp4")
    run(["ffmpeg", "-y", "-loop", "1", "-i", img_p, "-i", hud_p, "-i", narr,
         "-filter_complex", f"{vf};[2:a]apad=pad_dur=0.35[a]",
         "-map", "[v]", "-map", "[a]", "-t", f"{d:.2f}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", seg])
    print(f"scene {idx} ({scene['type']}) {d:.1f}s")
    return seg

def render2(script_path, out_path):
    script = json.load(open(script_path))
    tmp = os.path.join(ROOT, "out", "tmp2", script.get("id", "x")); os.makedirs(tmp, exist_ok=True)
    segs = []
    for i, sc in enumerate(script["scenes"]):
        cached = os.path.join(tmp, f"seg{i}.mp4")
        if os.path.exists(cached) and os.path.getsize(cached) > 10000:
            print(f"scene {i} cached, skipping"); segs.append(cached); continue
        segs.append(timer_segment(script, sc, tmp, i) if sc["type"] == "timer"
                    else still_segment(script, sc, tmp, i))
    body = os.path.join(tmp, "body.mp4")
    inputs = []
    for s in segs:
        inputs += ["-i", s]
    parts = "".join(f"[{i}:v]fps=30,format=yuv420p,setpts=PTS-STARTPTS[v{i}];"
                    f"[{i}:a]aresample=44100,asetpts=PTS-STARTPTS[a{i}];" for i in range(len(segs)))
    chain = "".join(f"[v{i}][a{i}]" for i in range(len(segs)))
    fc = parts + chain + f"concat=n={len(segs)}:v=1:a=1[v][a]"
    run(["ffmpeg", "-y"] + inputs + ["-filter_complex", fc, "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-c:a", "aac", body])
    total = dur(body)
    bed = os.path.join(tmp, "bed.m4a"); music_bed(total, bed)
    run(["ffmpeg", "-y", "-i", body, "-i", bed,
         "-filter_complex", "[1:a]volume=0.5[bg];[0:a][bg]amix=inputs=2:duration=first,"
         "loudnorm=I=-14:TP=-1.5:LRA=11[a]",
         "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", out_path])
    print("rendered v2:", out_path, f"{total:.0f}s")
    return total

if __name__ == "__main__":
    render2(sys.argv[1], sys.argv[2])
