#!/usr/bin/env python3
"""Authoritative bank validator — replicates render5's phrases5 exactly.
Usage: .venv/bin/python tools/validate_bank.py 201 300
Checks: title vs episodes.json, word targets by kind, checklist/tags/hashtags,
beats in range + not on timers, all referenced assets in manifest AND on disk,
{channel} token in outro, badge format, no '#' in description."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from render5 import phrases5

ROOT = os.path.join(os.path.dirname(__file__), "..")
eps = {e["n"]: e for e in json.load(open(f"{ROOT}/bank/episodes.json"))}
man = json.load(open(f"{ROOT}/assets/manifest.json"))
man_files = set()
def collect(o):
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(k, str) and k.endswith(".webp"): man_files.add(k)
            collect(v)
    elif isinstance(o, list):
        for v in o: collect(v)
    elif isinstance(o, str) and o.endswith(".webp"):
        man_files.add(o)
collect(man)

TARGETS = {"standard": (1100, 1500), "experiment": (950, 1450),
           "whathappens": (520, 850), "retest": (1100, 1500),
           "skinnyfat": (1100, 1500)}
BEAT_ASSET_KINDS = {"pip", "swap"}

def scene_assets(sc):
    out = []
    if sc.get("asset"): out.append(sc["asset"])
    for p in sc.get("poses") or []: out.append(p)
    for b in sc.get("beats") or []:
        if b.get("kind") in BEAT_ASSET_KINDS and b.get("asset"): out.append(b["asset"])
    return out

def validate(n):
    probs = []
    path = f"{ROOT}/bank/{n:03d}.json"
    if not os.path.exists(path): return ["MISSING FILE"], 0
    s = json.load(open(path))
    ep = eps[n]
    if s.get("title") != ep["title"]: probs.append(f"title mismatch: {s.get('title')!r}")
    kind = ep.get("kind", "standard")
    lo, hi = TARGETS.get(kind, (1100, 1500))
    words = 0
    for i, sc in enumerate(s["scenes"]):
        nar = sc.get("narration") or ""
        ph = phrases5(nar) if nar else []
        words += len(nar.split())
        if sc.get("type") == "timer":
            if sc.get("beats"): probs.append(f"scene {i}: beats on timer")
            continue
        if nar:
            for b in sc.get("beats") or []:
                if not (0 <= b.get("at", -1) < len(ph)):
                    probs.append(f"scene {i}: beat at={b.get('at')} out of range (phrases={len(ph)})")
            nb = len(sc.get("beats") or [])
            if nb and not (3 <= nb <= 7): probs.append(f"scene {i}: {nb} beats (want 3-7)")
        for a in scene_assets(sc):
            if a not in man_files: probs.append(f"scene {i}: asset {a} not in manifest")
            elif not os.path.exists(f"{ROOT}/assets/{a}"): probs.append(f"scene {i}: asset {a} missing on disk")
    if not (lo <= words <= hi): probs.append(f"words {words} outside {lo}-{hi} for kind={kind}")
    if len(s.get("checklist") or []) != 4: probs.append("checklist != 4")
    if not (6 <= len(s.get("tags") or []) <= 9): probs.append(f"tags {len(s.get('tags') or [])} not 6-9")
    if not (5 <= len(s.get("hashtags") or []) <= 8): probs.append(f"hashtags {len(s.get('hashtags') or [])} not 5-8")
    if "#" in (s.get("description") or ""): probs.append("'#' in description")
    if not (s.get("badge") or "").startswith(f"EP {n} -"): probs.append(f"badge format: {s.get('badge')!r}")
    if s.get("thumb", {}).get("asset"):
        a = s["thumb"]["asset"]
        if a not in man_files: probs.append(f"thumb asset {a} not in manifest")
    last = s["scenes"][-1].get("narration") or ""
    if "{channel}" not in last: probs.append("no {channel} token in outro")
    return probs, words

if __name__ == "__main__":
    a, b = int(sys.argv[1]), int(sys.argv[2])
    bad = 0; total_words = 0
    for n in range(a, b + 1):
        probs, w = validate(n)
        total_words += w
        if probs:
            bad += 1
            print(f"EP {n}: " + "; ".join(probs))
    print(f"checked {b-a+1} scripts, {bad} with problems, {total_words} words total")
