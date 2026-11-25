"""Deterministic learner. NO AI. Reads state.json performance entries (filled by the
owner or by an Analytics pull when google libs are present) and re-orders the topic
queue: winning categories get their next topics pulled forward, losers sink.
Scoring: views/day since publish, simple and auditable."""
import json, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def score_queue(state):
    perf = state.get("published", [])
    by_cat = {}
    for p in perf:
        if p.get("views") is not None and p.get("days_live", 0) > 0:
            by_cat.setdefault(p["category"], []).append(p["views"] / p["days_live"])
    avg = {c: sum(v) / len(v) for c, v in by_cat.items()}
    q = json.load(open(os.path.join(ROOT, "bank", "topics.json")))
    q["queue"].sort(key=lambda t: -avg.get(t["category"], 0))
    json.dump(q, open(os.path.join(ROOT, "bank", "topics.json"), "w"), indent=2)
    return avg
