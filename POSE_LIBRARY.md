# Pose Library — the artwork system for 780 episodes

## The problem this solves
780 episodes cannot each get one-off AI artwork: ~3,000 images would bloat
the repo past GitHub's practical limits and make the build endless. Instead:
**one deep library + code variation.** Every episode still looks fresh,
because no two episodes combine the same cycle set, swap shots, fact cards,
HUD state and thumbnail — but the character art is banked once.

## Style lock (every generated image, no exceptions)
Ren: lean muscular young man, black messy hair, teal shorts, cyan glow
running through the working tendons/muscles, manga line art, dark
background, dramatic side light. No text inside images. Same character in
all 780 episodes — the audience must recognize him in one frame.

## The math
- 156 episode cores group into ~46 exercise families.
- Per family: ONE pose-cycle set (3–4 frames, ONE camera side — Habl's
  one-side-per-workout rule is enforced by choosing a single set per
  episode) + 1–2 detail/swap shots (close-ups, second pose).
- Plus ~24 shared anatomy plates (tendons, bones, nerves per body region).
- Target library: **~250 images ≈ 85 MB**. Whole repo stays under ~150 MB,
  so GitHub Actions checkouts stay fast for 5 years.

## Coverage today (28 images, see assets/manifest.json)
Complete cycle sets: push-up (side, front), hang (side).
Partial/stills: calf, wall sit, grip, jump, sprint, punch, balance,
Achilles anatomy. Everything else is generated during the script waves,
in wave order — wave 1 generates the families its 100 episodes need first.

## Freshness without new art (already in renderer v5)
- Pose cycles animate every exercise scene (never a frozen frame).
- `swap` beats change the main picture mid-scene (set → close-up → detail).
- `fact` cards, chips, stat pop-ins and bars add new content every few
  seconds on top of the art.
- Thumbnails recompose art + number + hook per episode (src/thumbs.py).

## Rules for script waves
1. A script may only reference files listed in assets/manifest.json.
2. One cycle set (one side) per workout block. No mid-workout side switches.
3. New art is generated only for families the wave's episodes need, added
   to the manifest the same day, in the style lock above.
4. QA (final phase) fails any script referencing a missing asset.
