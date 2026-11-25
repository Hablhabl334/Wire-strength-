# Wire Strength — the Part 2 channel machine

A GitHub-only, YouTube-credentials-only automated channel in The Rep Theory's
formula, with our own identity (Ren: black hair, teal shorts, cyan glow) and our
own scripts. **There is no AI/LLM call anywhere in the daily loop.** All AI work
happened once, at build time, and its output is banked in this repo.

## The core idea: the BANK
AI tokens are only ever spent once — when scripts and artwork are created and
committed to `bank/` and `assets/`. After that the machine is pure plumbing:

| Piece | Where the intelligence lives | Runtime cost |
|---|---|---|
| Scripts | `bank/NNN_*.json` — full narration written at build time | $0 |
| Artwork | `assets/*.webp` — character/scene library made at build time | $0 |
| Voice | Edge TTS (free, no key) with offline Piper model as fallback | $0 |
| Video | ffmpeg zoom/pan over stills + burned captions + synth music bed | $0 |
| Upload | YouTube Data API, OAuth refresh token, 1,600 quota units/video | $0 |
| Learning | `src/learn.py` — deterministic scoring, re-orders `bank/topics.json` | $0 |

When the bank runs low, the machine prints `BANK EMPTY` and stops cleanly.
Refilling the bank is a build-time job (a human + AI session), never a runtime
dependency. Bank depth at launch decides how long it runs untouched. Current bank: 5 full v2 scripts (001-005) + 11 Ren images + 11-topic queue.

## Renderer v4 (current standard)
BEATS (added 2026-11-24, Habl's last 5%): every scene can declare "beats" -
content elements that appear every 5-10s so the picture is never just static:
chip (label), stat (big number), bars (comparison), pip (inset picture),
mark (check/cross). Only the 2 most recent beats stay on screen. Scripts
should place a beat roughly every 3-5 phrases in every narrated scene.

Scripts with `"v4": true` use `src/render4.py`. Built from Habl's 80% review:
- VOICE: Kokoro-82M (open weights, fully offline, downloaded by the workflow
  like the Piper model) is the primary narrator - near-human, $0 forever.
  Fallback chain: Edge -> Piper. Mastering: hard voice compression + limiter,
  measured -14.9 LUFS (reference channel: -14.1..-14.5).
- MUSIC: three real Creative Commons tracks banked in assets/music/
  (Kevin MacLeod, CC BY 4.0): bed_dark (hooks/science), bed_calm (education),
  bed_drive (circuits). Scenes choose; beds crossfade; attribution is added
  to every description automatically by the uploader.
- CADENCE: phrases <=5 words, card lines reveal as spoken, glow pulse +
  micro-sway + section progress bar - something new roughly every 1-2s,
  matching the measured winners (a visual change every 0.4-0.9s).
- PAUSES: gaps between phrases, longer after sentences, lead_pause at
  section changes (music-only breathing room).
- ANGLES: anim scenes switch camera angle between pose sets
  (side / front / back / 45 deg) every few phrases.
Verified 2026-11-24: #009 re-rendered in v4 by this code alone - 6:08,
1920x1080, A/V in sync, angle switching + card reveals confirmed on frames.

## Renderer v5 (current standard, from Habl's 95% review of sample #010)
Scripts with `"v5": true` use `src/render5.py`. v5 = v4 + two new beat
kinds so the TALKING scenes get a new piece of content every 5-10s:
- `swap`: the main picture itself changes mid-scene (e.g. grip close-up
  -> finger hang -> active hang), so no scene is one static picture.
- `fact`: a large gold-outlined content card (headline + 2 lines) - a new
  fact/diagram block, not a label chip.
Also fixed in the #010 v5 script: a bars beat at phrase 20 that could
never appear (scene has 23 phrases, beat now at 14). Verified
2026-11-24: #010 re-rendered in v5 by this code alone - same locked
Kokoro voice/music, one side per workout, new content every 5-10s.

## Renderer v3 (current standard, from the top-8 analysis)
Scripts with `"v3": true` use `src/render3.py`. Measured from The Rep Theory's
8 most-viewed videos (TOP8_ANALYSIS.md): no zoom/pan anywhere; ANIM scenes cycle
exercise poses (top/mid/bottom) so the character actually moves; emphasis text
is voiced phrase-by-phrase and appears exactly while spoken (ALL-CAPS words in
the script render in the accent colour); narration bus gets EQ + compression
and the master sits at -14 LUFS, matching all 8 reference videos (-14.1..-14.5).
Verified 2026-11-24: bank #009 rendered by this code alone - 1920x1080, A/V in
sync, push-up pose cycle + synced emphasis text + study card confirmed on frames.

## Renderer v2 (matches the reference channel's system)
Scripts with `"v2": true` use `src/render2.py`, which adds, in pure code:
- a persistent HUD: section title (top-left), episode badge (top-right), and a
  bottom checklist bar that ticks off as the video progresses;
- PIL infographic cards: big-number, study-citation, and layered-diagram scenes;
- follow-along TIMER scenes: animated countdown ring, WORK/REST phases, round
  counter, pose sway, and phase beeps - viewers train with the video;
- script architecture: interactive hook test, science cards, circuit block,
  honest-timeline card, and a callback ending that re-tests the opening number.
Verified 2026-11-24: bank #002 rendered by this code alone - 1920x1080, 8:18,
video/audio in sync. (Two bugs were found and fixed during verification:
timer audio container, and audio-gap insertion in concatenation - the
renderer now assembles with a concat filter with per-stream timestamp resets.)

## Run it
- GitHub Actions: `.github/workflows/daily.yml`, daily 13:00 UTC.
  Renders the next banked script; uploads only if the secrets exist,
  otherwise renders as a dry run. Commits `state.json` back.
- Local dry run: `python main.py` (needs ffmpeg, `pip install -r requirements.txt`,
  and the Piper voice model in `assets/voices/` — the workflow downloads it
  automatically; it is git-ignored because it exceeds GitHub's file-size limit).

## Secrets (owner sets these in GitHub Secrets — never in code, never in chat)
- `YT_CLIENT_ID`
- `YT_CLIENT_SECRET`
- `YT_REFRESH_TOKEN`  (OAuth consent must include youtube.upload;
  add yt-analytics.readonly if you want the learner fed automatically)

## Notes from the verified first render (2026-11-24)
- Sample: `bank/001` rendered locally end-to-end with the offline Piper voice —
  1920x1080, h264/aac, captions burned, thumbnail generated. Zero AI calls.
- Piper speaks fast (~200 wpm): scripts are banked at ~1,100 words and the
  renderer slows the voice (WS_LENGTH_SCALE=1.15). For a true ~8:00 runtime,
  bank scripts at ~1,350-1,450 words.
- Edge TTS is the primary voice on GitHub's network; Piper is the fallback
  that makes the machine independent of any external service.
