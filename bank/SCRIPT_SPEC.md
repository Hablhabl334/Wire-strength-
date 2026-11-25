# v5 Script Spec — every bank script follows this exactly

Reference implementation: bank/legacy/010_dead_hang_v5.json (format proof).
Renderer: src/render5.py. NO AI at runtime — scripts are banked JSON.

## File
bank/NNN.json where NNN = zero-padded episode number from bank/episodes.json.
Top-level fields:
- "id": "NNN"
- "v5": true
- "title": exactly the title from episodes.json for this n
- "description": 2-4 sentences, the episode's promise + what the viewer
  learns. NO hashtags here (the metadata engine adds them). NO disclaimer
  (engine adds it).
- "tags": 6-9 lowercase tags specific to the episode
- "hashtags": 5-8 episode hashtags, plain words ("dead hang"), the first 3
  are the display hooks — put the most clickable first
- "category": from episodes.json
- "badge": "EP {n} - {SHORT ALL-CAPS EPISODE NAME}" (<= 30 chars after EP n -)
- "checklist": exactly 4 short ALL-CAPS section labels, in scene order
- "thumb": {"asset": hero file, "big": the test number ("60 SEC", "x2",
  "12 REPS"), "hook": 2-4 word hook ALL CAPS, "accent": one of
  cyan/gold/red/green/violet by category (grip cyan, tendons gold,
  pain red, healing green, nerves violet, isometrics violet, bones gold,
  others cyan)}
- "scenes": per structure below

## Narration rules (locked format)
- Phrases separated by " | " in anim scenes; <= 5 words per phrase.
  In art/card scenes, plain sentences are fine (renderer splits them).
- ALL-CAPS words render highlighted — use for the number/mechanism keywords.
- Total narration 1,150-1,450 words (standard episodes).
- Voice is Ren's channel voice: direct, warm, zero hype, speaks to ONE
  skinny guy. Science claims must be mainstream-safe (tendons adapt to
  load, isometrics build strength, etc.). Never promise medical outcomes;
  pain episodes say "see a professional if it persists" once.
- The channel name is the token {channel} — use it in the outro only:
  "This is {channel}. Train the cable." Never write a literal channel name.

## Scene structure (9-11 scenes, in this order)
1. anim — THE TEST: do-it-now test instructions, viewer gets their number,
   open loop ("keep your number, at the end I tell you what it means").
   Poses = the family's cycle set from assets/manifest.json (ONE side).
   music "dark". check 0.
2. card bignum — THE NUMBER: the benchmark line (big number + label + sub
   with the weak/elite bands). music "calm". check 1. lead_pause 1.2.
3. art — THE MECHANISM: the hidden system explained (asset = anatomy plate
   or close-up). beats: fact card with the key study-style stat. check 2.
4. art — THE SCIENCE / DEEPER: second mechanism angle, comparison bars
   beat (skinny vs big guy or before/after). check 2.
5. anim or art — THE ADVANTAGE: why skinny/light is an advantage here,
   the reframe. check 2 or 3.
6. timer — TRAIN WITH ME: follow-along block. Fields: exercise, work
   (sec), rest (sec), rounds, asset. Narration = one short intro line.
   music "drive". check 3.
7. art — THE PROTOCOL / MISTAKES: what to do this week, or the 3 mistakes.
   beats: mark beats (ok true/false). check 3.
8. card bignum or art — THE VERDICT: what the viewer's number means
   (bands: untrained / building / wired), retest in 30 days, comment your
   number CTA. check 3.
9. art — OUTRO (short, ~40 words): retest promise + subscribe line +
   "This is {channel}. Train the cable."
Optional extra art scene between 4 and 5 if word count is short.

## Beats rules (renderer v5)
- Every narrated scene carries 3-7 beats; a beat roughly every 3-5 phrases.
- "at" = phrase index (0-based) — must be < the scene's phrase count.
- kinds: chip {text, pos}, stat {text, label, pos}, bars {items:[[label,
  value],...], pos}, pip {asset, pos}, mark {text, ok, pos},
  fact {title, lines:[1-2 short lines], pos}, swap {asset} (art scenes:
  changes the main picture for the rest of the scene).
- pos: "tr" or "br". Alternate positions; never stack two beats on the
  same "at".
- In art scenes include at least one swap OR the scene asset must be
  episode-specific. Timer scenes: no beats.

## Assets
- ONLY files listed in assets/manifest.json (entries with "planned": true
  are allowed — the art is generated in the same wave).
- ONE cycle set per workout: never mix sides within an episode's anim
  scenes. If a family has no set, use its stills as art scenes and use the
  hang or pushup set for the test anim only if the movement matches;
  otherwise make scene 1 an art scene with the family still.
