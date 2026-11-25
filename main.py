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
render5(resolved_path, out) if meta.get("v5") else (render4(resolved_path, out) if meta.get("v4") else (render3(resolved_path, out) if meta.get("v3") else (render2(resolved_path, out) if meta.get("v2") else render(resolved_path, out))))
try:
    from thumbs import make_thumbnail
    make_thumbnail(meta, os.path.join(ROOT, "out", "thumbnail.jpg"))
    print("thumbnail composed")
except Exception as e:
    print("thumbnail skipped (upload proceeds without it):", e)
try:
    from render import dur
    _tmp = os.path.join(ROOT, "out", f"tmp5_{meta['id']}")
    _chapters, _t = [], 0.0
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
        print(f"chapters: {len(_chapters)} from real segment timings")
except Exception as e:
    print("chapters skipped:", e)
entry = {"script": os.path.basename(script_path), "title": meta["title"],
         "category": meta.get("category", ""), "video_id": None, "views": None, "days_live": 0}
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
