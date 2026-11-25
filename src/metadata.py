"""Metadata engine. NO AI/LLM calls anywhere.

Turns an episode's banked fields into the final upload metadata:
- build_description: authored core + auto chapters (from the renderer's
  real segment timings) + disclaimer + the canonical hashtag block.
- build_tags: episode tags + channel base tags, deduped, inside
  YouTube's limits.
- Hashtags are owned HERE, never by the script text: episode hashtags
  first (the first 3 are the ones YouTube displays above the title),
  then the channel base set, deduped, capped at 12 (YouTube ignores
  ALL hashtags past 15 - we stay well under).
"""
import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_HASHTAGS = 12
MAX_TAG_CHARS = 480


def _cfg():
    try:
        return json.load(open(os.path.join(ROOT, "channel.json")))
    except Exception:
        return {}


def canon_hashtag(raw):
    words = re.sub(r"[^A-Za-z0-9 ]", "", str(raw).replace("#", "")).split()
    if not words:
        return None
    return "#" + "".join(w.capitalize() for w in words)


def build_hashtags(meta):
    seen, out = set(), []
    pool = list(meta.get("hashtags", [])) + list(_cfg().get("base_hashtags", []))
    for raw in pool:
        h = canon_hashtag(raw)
        if h and h.lower() not in seen:
            seen.add(h.lower())
            out.append(h)
    return out[:MAX_HASHTAGS]


def strip_hashtags(text):
    return re.sub(r"#\w+", "", text).rstrip()


def fmt_ts(sec):
    sec = int(sec)
    return f"{sec // 60:02d}:{sec % 60:02d}" if sec < 3600 else \
        f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def build_description(meta):
    cfg = _cfg()
    core = strip_hashtags(meta.get("description", "").strip())
    parts = []
    badge = (meta.get("badge") or "").strip()
    if badge:
        parts.append(badge.title())
    if core:
        parts.append(core)
    chapters = meta.get("_chapters") or []
    if len(chapters) >= 3:
        lines = ["⏱ Chapters:"]
        for start, label in chapters:
            lines.append(f"{fmt_ts(start)} {label}")
        parts.append("\n".join(lines))
    disclaimer = cfg.get("disclaimer", "")
    if disclaimer:
        parts.append(disclaimer)
    tags_line = " ".join(build_hashtags(meta))
    if tags_line:
        parts.append(tags_line)
    return "\n\n".join(parts)


def build_tags(meta):
    seen, out, total = set(), [], 0
    pool = list(meta.get("tags", [])) + list(_cfg().get("base_tags", []))
    for raw in pool:
        t = str(raw).strip()
        if not t or t.lower() in seen or len(t) > 100:
            continue
        if total + len(t) + 1 > MAX_TAG_CHARS:
            continue
        seen.add(t.lower())
        out.append(t)
        total += len(t) + 1
    return out


def title_problems(meta, other_titles=()):
    """Cheap guards run before any upload and in bank QA."""
    problems = []
    title = meta.get("title", "")
    if not title:
        problems.append("missing title")
    if len(title) > 100:
        problems.append(f"title over 100 chars ({len(title)})")
    low = title.strip().lower()
    if any(low == str(t).strip().lower() for t in other_titles):
        problems.append("duplicate title")
    return problems
