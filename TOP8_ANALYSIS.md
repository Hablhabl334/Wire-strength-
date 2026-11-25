# Top-8 analysis - The Rep Theory, measured 2026-11-24 from the actual video files
Top 8 = 11.1M of the channel's 12.1M views (92%).

| # | Video | Views | Length | Loudness | Motion (frame-diff) |
|---|---|---|---|---|---|
| 1 | How Training Tendons Makes You Stronger Than Big Guys | 5.6M | 8:03 | -14.4 LUFS | low cuts (6), constant internal motion |
| 2 | Quit the Gym, Do Calisthenics (skinny) | 1.8M | 8:02 | -14.4 | high |
| 3 | How Some Skinny Guys Are Stronger Than Big Guys | 1.1M | 4:44 | -14.1 | medium |
| 4 | How to Do Isometric Holds (Full Guide) | 769k | 14:15 | -14.3 | high |
| 5 | Boost Your Bone Density (3 Minute Habit) | 604k | 12:37 | -14.4 | highest |
| 6 | I'll Prove You Can Do a Planche | 491k | 13:06 | -14.4 | medium |
| 7 | Abs by CHRISTMAS | 470k | 8:06 | -14.4 | high |
| 8 | Training Tendons Makes You Insane at Pull Ups | 296k | 8:09 | -14.5 | high |

## Sound (Habl's note: get the sound near theirs)
- ALL 8 mastered at -14.1..-14.5 LUFS (YouTube standard; our loudnorm already targets -14).
- Narrator: male, median pitch ~130 Hz (measured), fast confident pace, short
  phrases, zero dead air. Sounds like a premium TTS voice, processed (EQ + compression).
- Music: low, constant, never competing. Our synth bed at same relative level is fine.

## Motion (Habl's note: the character MOVES)
- Almost no hard cuts (as few as 2-6 per video). Scenes are long held compositions.
- Inside a scene, three things animate: (1) the character cycles exercise poses
  (e.g. push-up: top -> mid -> bottom -> mid, ~3-4 frames, looping); (2) anatomical
  highlights PULSE (glow dots travel along the tendon); (3) text and labels BUILD
  in piece by piece. The art is often still; the elements around it are not.
- NO camera zoom/pan on the winners. Static framing. (v1/v2 zoompan = wrong.)

## Text (Habl's note: our caption was not synced)
- Their on-screen text is NOT subtitles. It is EMPHASIS text that appears phrase by
  phrase, timed to the exact words being spoken: "LONG TENDONS" -> "ALL THE WAY TO"
  -> "YOUR FINGERTIPS" (key word in orange). Plus leader-line labels on diagrams
  ("YOUR WHOLE BODY" pointing at the tendons) and study citations printed on the
  graphic itself ("Arampatzis et al. 2007 - J Exp Biol", "LIGHT vs HEAVY").
- Micro-CTA inside the video: a LIKED button animation mid-video framed as helping
  ("so the next guy stops wasting his time").
- Safety micro-print bottom-left on exercise scenes.

## Hook formula (identical skeleton in all 8, first 30 seconds)
1. Mirror or test: "Have you ever noticed some skinny guys are way stronger than
   their size?" / "Drop down and do as many push-ups as you can. Right now."
2. Mechanism reveal by ~0:15: "It's their tendons." / "It's not muscle. It's isometrics."
3. Study stat by ~0:30: "57% stiffer" / "1,000 men followed for 10 years" / "26 studies".
4. Open loop to the end: "Got your number? Keep it. At the end of this video I'll
   tell you what it says about you."
5. The reframe: skinny/light is an ADVANTAGE ("being light isn't a weakness",
   "the physics is on your side", "you're not behind, you're built for this").
6. First segment starts immediately: "Hold number one. The wall hold. You can do
   it right now."
Audience contract: they talk to skinny guys who want to be POWERFUL, not big.
Every winner promises hidden power > visible size.

## What v3 changes (implemented in src/render3.py)
- Zoom/pan REMOVED everywhere. Static framing only.
- New ANIM scenes: pose-cycle animation (ping-pong pose sequence at rep tempo).
- Emphasis text system: narration is split into phrases; each phrase is voiced
  separately and shown on screen exactly while it is spoken; ALL-CAPS words in
  the script render in cyan (our accent) - the sync bug is structural, now fixed.
- Glow-pulse overlays for anatomy scenes.
- Voice chain: high-pass + presence EQ + compression on the narration bus to sit
  closer to their produced sound; -14 LUFS master (unchanged, already matched).
