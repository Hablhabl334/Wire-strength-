"""Daily entry point. Renders the next banked script; uploads only if the three
YouTube secrets exist. Without secrets it renders and exits cleanly (dry run)."""
import glob, json, os, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))
from render import render
from render2 import render2
from render3 import render3
from render4 import render4
from render5 import render5
from learn import score_queue

state_p = os.path.join(ROOT, "state.json")
state = json.load(open(state_p)) if os.path.exists(state_p) else {"published": [], "done_scripts": []}
scripts = sorted(glob.glob(os.path.join(ROOT, "bank", "[0-9]*.json")))
todo = [s for s in scripts if os.path.basename(s) not in state["done_scripts"]]
if not todo:
    print("BANK EMPTY: no unrendered scripts left. Refill bank/ at build time.")
    sys.exit(0)
script_path = todo[0]
raw_meta = json.load(open(script_path))

# Channel identity lives in channel.json only. Scripts carry the token
# {channel}; it is resolved here, at publish time, so one edit in
# channel.json renames the entire bank (all 780 episodes).
_cfg_path = os.path.join(ROOT, "channel.json")
_cfg = json.load(open(_cfg_path)) if os.path.exists(_cfg_path) else {}
_channel_name = _cfg.get("name", "")

def _subst(o):
    if isinstance(o, str):
        return o.replace("{channel}", _channel_name)
    if isinstance(o, list):
        return [_subst(x) for x in o]
    if isinstance(o, dict):
        return {k: _subst(v) for k, v in o.items()}
    return o

meta = _subst(raw_meta)
resolved_path = os.path.join(ROOT, "out", "_resolved.json")
os.makedirs(os.path.dirname(resolved_path), exist_ok=True)
json.dump(meta, open(resolved_path, "w"), indent=2)
out = os.path.join(ROOT, "out", "video.mp4")
# Pre-flight: if secrets exist, prove the YouTube token exchange works BEFORE
# spending ~40 minutes rendering (fail in seconds, with Google's error printed).
if all(os.environ.get(k) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")):
    from upload import access_token
    access_token()
    print("pre-flight: YouTube token exchange OK")
render5(resolved_path, out) if meta.get("v5") else (render4(resolved_path, out) if meta.get("v4") else (render3(resolved_path, out) if meta.get("v3") else (render2(resolved_path, out) if meta.get("v2") else render(resolved_path, out))))
try:
    # Music rotation: the renderer's resolved track titles ride the meta
    # dict to upload.py, which credits exactly the tracks this episode
    # used (CC BY 4.0). Empty for non-v5 renderers -> static fallback.
    import render5 as _r5mus
    if getattr(_r5mus, "LAST_MUSIC", None):
        meta["_music"] = list(_r5mus.LAST_MUSIC)
        print("music credit:", meta["_music"])
except Exception as e:
    print("music credit skipped:", e)
try:
    from thumbs import make_thumbnail
    make_thumbnail(meta, os.path.join(ROOT, "out", "thumbnail.jpg"))
    print("thumbnail composed")
except Exception as e:
    print("thumbnail skipped (upload proceeds without it):", e)
try:
    from render import dur
    _chapters, _t = [], 0.0
    # v6.2: prefer the renderer's own assembled timeline (it counts the
    # title card, roadmaps, tease and route segments the scene-only
    # walk below cannot see, so its boundaries are the true ones).
    if meta.get("v5"):
        import render5 as _r5ch
        _lc = getattr(_r5ch, "LAST_CHAPTERS", None) or []
        if len(_lc) >= 3:
            _chapters = [(float(_s), str(_l).title()) for _s, _l in _lc]
            print(f"chapters: {len(_chapters)} from renderer timeline")
    if not _chapters:
        _tmp = os.path.join(ROOT, "out", f"tmp5_{meta['id']}")
        for _i, _sc in enumerate(meta["scenes"]):
            _seg = os.path.join(_tmp, f"seg{_i}.mp4")
            if not os.path.exists(_seg):
                _chapters = []
                break
            _label = (_sc.get("section") or _sc.get("type", "")).title()
            if _label and (not _chapters or _chapters[-1][1] != _label):
                _chapters.append((_t, _label))
            _t += dur(_seg)
    if len(_chapters) >= 3:
        meta["_chapters"] = _chapters
        print(f"chapters ready: {len(_chapters)}")
except Exception as e:
    print("chapters skipped:", e)
entry = {"script": os.path.basename(script_path), "title": meta["title"],
         "category": meta.get("category", ""), "video_id": None, "views": None, "days_live": 0}
try:
    import render5 as _r5mod
    entry["art"] = list(_r5mod.LAST_USED)
except Exception:
    entry["art"] = []
try:
    import thumbs as _thmod
    entry["thumb"] = _thmod.LAST_THUMB
except Exception:
    entry["thumb"] = None
if all(os.environ.get(k) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")):
    from upload import upload
    entry["video_id"] = upload(out, meta, os.path.join(ROOT, "out", "thumbnail.jpg"))
    print("uploaded:", entry["video_id"])
else:
    print("DRY RUN: no YouTube secrets present, video rendered only.")
state["published"].append(entry)
state["done_scripts"].append(os.path.basename(script_path))
json.dump(state, open(state_p, "w"), indent=2)
score_queue(state)
