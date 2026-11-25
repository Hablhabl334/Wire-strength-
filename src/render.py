"""Wire Strength renderer. NO AI/LLM calls anywhere in this file.
Input : a banked script JSON (written once, at build time) + banked image assets.
Voice : Microsoft Edge TTS (free, no API key) via edge-tts.
Video : ffmpeg zoom/pan over stills + burned captions + generated music bed.
"""
import asyncio, json, math, os, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOICE = os.environ.get("WS_VOICE", "en-US-ChristopherNeural")
RATE = os.environ.get("WS_RATE", "-4%")
W, H, FPS = 1920, 1080, 30

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"cmd failed: {' '.join(cmd[:4])}... {r.stderr[-400:]}")
    return r

def dur(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path])
    return float(r.stdout.strip())

PIPER_MODEL = os.path.join(ROOT, "assets", "voices", "en_US-ryan-high.onnx")

def piper_tts(text, out_wav):
    r = subprocess.run([sys.executable, "-m", "piper", "--model", PIPER_MODEL,
                        "--output_file", out_wav,
                        "--length-scale", os.environ.get("WS_LENGTH_SCALE", "1.15")], input=text.encode(),
                       capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("piper failed: " + r.stderr.decode()[-300:])

async def _edge(text, out):
    import edge_tts
    await edge_tts.Communicate(text, VOICE, rate=RATE).save(out)

_KOKORO = None
def kokoro_tts(text, out_wav):
    """Kokoro-82M offline TTS (open weights). Near-human voice, $0, no network.
    Model files live in assets/voices/ (downloaded by the workflow; git-ignored
    for size). Voice/speed via WS_KOKORO_VOICE / WS_KOKORO_SPEED."""
    global _KOKORO
    import soundfile as sf
    if _KOKORO is None:
        from kokoro_onnx import Kokoro
        _KOKORO = Kokoro(os.path.join(ROOT, "assets", "voices", "kokoro-v1.0.onnx"),
                         os.path.join(ROOT, "assets", "voices", "voices-v1.0.bin"))
    samples, sr = _KOKORO.create(text, voice=os.environ.get("WS_KOKORO_VOICE", "am_michael"),
                                 speed=float(os.environ.get("WS_KOKORO_SPEED", "1.05")), lang="en-us")
    sf.write(out_wav, samples, sr)

def tts(text, out_base):
    """Returns path of the narration audio. Edge TTS first (free, no key);
    Piper offline model as automatic fallback. WS_TTS=piper forces offline."""
    engine = os.environ.get("WS_TTS", "kokoro")
    if engine == "kokoro":
        wav = out_base + ".wav"
        try:
            kokoro_tts(text, wav)
            if os.path.getsize(wav) > 1000:
                return wav
        except Exception as e:
            print("kokoro unavailable, falling back:", str(e)[:120])
    if engine != "piper":
        mp3 = out_base + ".mp3"
        try:
            asyncio.run(_edge(text, mp3))
            if os.path.getsize(mp3) > 1000:
                return mp3
        except Exception as e:
            print("edge-tts unavailable, falling back to piper:", str(e)[:120])
    wav = out_base + ".wav"
    piper_tts(text, wav)
    return wav

def music_bed(seconds, out, seed=7):
    sr = 44100; t = np.arange(int(seconds * sr)) / sr
    rng = np.random.default_rng(seed)
    freqs = [110.0, 164.81, 220.0]  # A2 E3 A3 low pulse
    y = np.zeros_like(t)
    for i, f in enumerate(freqs):
        env = (0.5 + 0.5 * np.sin(2 * math.pi * 0.11 * t + i)) ** 2
        y += 0.10 * env * np.sin(2 * math.pi * f * t)
    beat = ((t % 0.857) < 0.06).astype(float) * 0.05 * np.sin(2 * math.pi * 65 * t)
    y = (y + beat).astype(np.float32)
    fade = int(sr * 2); y[:fade] *= np.linspace(0, 1, fade); y[-fade:] *= np.linspace(1, 0, fade)
    p = subprocess.run(["ffmpeg", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "1",
                        "-i", "-", "-c:a", "aac", out], input=y.tobytes(), capture_output=True)
    if p.returncode != 0: raise RuntimeError("music bed failed")

def make_thumbnail(script, out):
    bg = Image.open(os.path.join(ROOT, "assets", "big_vs_lean_jump.webp")).convert("RGB")
    bg = bg.resize((1280, 720))
    d = ImageDraw.Draw(bg)
    try:
        f1 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 150)
    except Exception:
        f1 = ImageFont.load_default()
    d.rectangle([0, 470, 1280, 720], fill=(0, 0, 0))
    d.text((40, 495), "IT'S TENDONS", font=f1, fill=(0, 229, 255))
    bg.save(out, quality=90)

def render(script_path, out_path):
    script = json.load(open(script_path))
    tmp = os.path.join(ROOT, "out", "tmp"); os.makedirs(tmp, exist_ok=True)
    segs = []
    for i, sc in enumerate(script["scenes"]):
        mp3 = tts(sc["narration"], os.path.join(tmp, f"s{i}"))
        d = dur(mp3) + 0.35
        img = os.path.join(ROOT, "assets", sc["asset"])
        seg = os.path.join(tmp, f"seg{i}.mp4")
        frames = int(d * FPS)
        z = "min(zoom+0.0012,1.25)" if sc.get("move") == "in" else "if(eq(on,1),1.25,max(zoom-0.0012,1.0))"
        cap = sc.get("caption", "").replace("'", "").replace(":", "")
        vf = (f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
              f"zoompan=z='{z}':d={frames}:s={W}x{H}:fps={FPS},"
              f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
              f"text='{cap}':fontsize=64:fontcolor=white:borderw=3:bordercolor=black:"
              f"x=(w-text_w)/2:y=h-140")
        run(["ffmpeg", "-y", "-loop", "1", "-i", img, "-i", mp3,
             "-filter_complex", f"[0:v]{vf}[v];[1:a]apad=pad_dur=0.35[a]",
             "-map", "[v]", "-map", "[a]", "-t", f"{d:.2f}",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", seg])
        segs.append(seg)
        print(f"scene {i+1}/{len(script['scenes'])} {d:.1f}s")
    lst = os.path.join(tmp, "list.txt")
    open(lst, "w").write("\n".join(f"file '{s}'" for s in segs))
    body = os.path.join(tmp, "body.mp4")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", body])
    total = dur(body)
    bed = os.path.join(tmp, "bed.m4a"); music_bed(total, bed)
    run(["ffmpeg", "-y", "-i", body, "-i", bed,
         "-filter_complex", "[1:a]volume=0.5[bg];[0:a][bg]amix=inputs=2:duration=first,"
         "loudnorm=I=-14:TP=-1.5:LRA=11[a]",
         "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", out_path])
    make_thumbnail(script, os.path.join(ROOT, "out", "thumbnail.jpg"))
    print("rendered:", out_path, f"{total:.0f}s")
    return total

if __name__ == "__main__":
    render(sys.argv[1], sys.argv[2])
