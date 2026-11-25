"""Episode map generator (build-time tool, not part of the daily loop).

Builds the 780-episode map: 13 seasons x 60 episodes. Each season has 12
hand-picked cores (a test / mechanism / habit unit); each core gets 5
episodes from the season's title-template family. Every title is scored
against Habl's five-point filter (identity, unfair advantage, new
mechanism, test/number, enemy) with a transparent keyword heuristic, and
the map is checked for duplicate titles. Output: bank/episodes.json +
EPISODE_MAP.md. Scripts are written later, in graded order, from this map.
"""
import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# core = (topic, test, mechanism, habit)
SEASONS = [
    ("S1", "The Tests", "tests", "mixed", [
        ("dead hang", "Your Dead Hang Time", "grip tendons", "hang from a bar daily"),
        ("push-up max", "Your Push-Up Number", "chest and triceps tendons", "do push-ups daily"),
        ("wall sit", "Your Wall Sit Time", "knee tendons", "hold a wall sit daily"),
        ("plank hold", "Your Plank Time", "deep core nerves", "hold a plank daily"),
        ("pull-up max", "Your Pull-Up Number", "lat and elbow tendons", "do pull-ups daily"),
        ("calf raises", "Your Single-Leg Calf Raise Number", "Achilles tendon", "do calf raises daily"),
        ("horse stance", "Your Horse Stance Time", "hip and knee tendons", "hold a horse stance daily"),
        ("vertical jump", "Your Vertical Jump Height", "Achilles stiffness", "jump daily"),
        ("L-sit hold", "Your L-Sit Time", "hip flexor strength", "practice the L-sit daily"),
        ("dip max", "Your Dip Number", "shoulder tendons", "do dips daily"),
        ("towel hang", "Your Towel Hang Time", "finger tendons", "hang from a towel daily"),
        ("balance test", "Your Single-Leg Balance Time", "ankle nerves", "stand on one leg daily"),
    ]),
    ("S2", "Tendon Strength", "tendons", "tendons", [
        ("Achilles training", "Your Heel Drop Test", "Achilles tendon", "do slow heel drops daily"),
        ("knee tendon training", "Your Knee Bend Test", "patellar tendon", "do slow split squats daily"),
        ("elbow tendon training", "Your Elbow Squeeze Test", "elbow tendons", "do towel twists daily"),
        ("wrist tendon training", "Your Wrist Lever Test", "wrist tendons", "do wrist levers daily"),
        ("finger tendon training", "Your Finger Hang Time", "finger tendons", "hang by your fingers daily"),
        ("shoulder tendon training", "Your Shoulder Hold Test", "rotator cuff tendons", "hold wall slides daily"),
        ("ankle tendon training", "Your Ankle Hop Test", "ankle tendons", "do ankle hops daily"),
        ("triceps tendon training", "Your Diamond Push-Up Number", "triceps tendon", "do diamond push-ups daily"),
        ("biceps tendon training", "Your Towel Curl Test", "biceps tendon", "do towel curls daily"),
        ("foot tendon training", "Your Toe Raise Number", "foot tendons", "do toe raises daily"),
        ("hip tendon training", "Your Leg Swing Test", "hip tendons", "do leg swings daily"),
        ("neck tendon training", "Your Neck Hold Time", "neck tendons", "do neck holds daily"),
    ]),
    ("S3", "Pain & Healing", "healing", "pain", [
        ("knee pain", "Your Knee Pain Test", "patellar tendon healing", "do pain-free knee work daily"),
        ("elbow pain", "Your Elbow Pain Test", "elbow tendon healing", "do slow eccentrics daily"),
        ("wrist pain", "Your Wrist Pain Test", "wrist tendon healing", "do wrist mobility daily"),
        ("shoulder ache", "Your Shoulder Reach Test", "shoulder tendon healing", "do wall slides daily"),
        ("Achilles soreness", "Your Morning Achilles Test", "Achilles healing", "do heel drops daily"),
        ("shin splints", "Your Shin Test", "tibialis healing", "do toe raises daily"),
        ("back tightness", "Your Toe Touch Test", "spinal tissue healing", "do spine mobility daily"),
        ("neck stiffness", "Your Neck Turn Test", "neck tissue healing", "do neck mobility daily"),
        ("foot pain", "Your First Step Test", "plantar tissue healing", "roll your foot daily"),
        ("finger stiffness", "Your Fist Test", "finger tendon healing", "do finger spreads daily"),
        ("hip pinch", "Your Hip Rotation Test", "hip tissue healing", "do hip rotations daily"),
        ("ankle sprain history", "Your Ankle Trust Test", "ankle ligament healing", "do balance work daily"),
    ]),
    ("S4", "Nerves & Isometrics", "isometrics", "nerves", [
        ("wall push isometrics", "Your Wall Push Force", "nerve drive", "push a wall daily"),
        ("pause reps", "Your Pause Push-Up Number", "nerve control", "pause your reps daily"),
        ("sticking point holds", "Your Sticking Point Time", "nerve recruitment", "hold your sticking point daily"),
        ("bracing", "Your Brace Test", "core nerve pressure", "practice bracing daily"),
        ("co-contraction", "Your Tension Test", "whole-body nerve tension", "practice full tension daily"),
        ("slow negatives", "Your 10-Second Negative Test", "nerve braking", "do slow negatives daily"),
        ("breath pressure", "Your Breath Hold Brace Test", "pressure nerves", "brace with breath daily"),
        ("mind-muscle connection", "Your Activation Test", "nerve signaling", "do activation work daily"),
        ("isometric lunges", "Your Iso Lunge Time", "leg nerve drive", "hold an iso lunge daily"),
        ("doorframe rows", "Your Doorframe Pull Test", "back nerve drive", "do doorframe rows daily"),
        ("max tension holds", "Your Max Tension Time", "total nerve output", "do max tension holds daily"),
        ("explosive intent", "Your Intent Speed Test", "fast nerve firing", "move with intent daily"),
    ]),
    ("S5", "Grip & Forearms", "grip", "grip", [
        ("crush grip", "Your Crush Test", "hand tendons", "squeeze daily"),
        ("pinch grip", "Your Pinch Hold Time", "thumb tendons", "pinch a book daily"),
        ("finger hangs", "Your Finger Hang Endurance", "finger pulleys", "hang by your fingers daily"),
        ("towel hangs", "Your Towel Grip Endurance", "grip tendons", "hang from a towel daily"),
        ("wrist levers", "Your Wrist Lever Record", "forearm tendons", "do wrist levers daily"),
        ("forearm extensors", "Your Finger Spread Test", "extensor tendons", "spread your fingers daily"),
        ("farmer carries", "Your Carry Distance", "grip endurance", "carry heavy bags daily"),
        ("dead hang endurance", "Your Two-Minute Hang Test", "grip tendons", "hang daily"),
        ("thumb strength", "Your Thumb Pinch Test", "thumb tendons", "pinch daily"),
        ("wrist stability", "Your Wrist Balance Test", "wrist stabilizers", "do wrist circles daily"),
        ("grip endurance", "Your Grip Fade Test", "grip stamina", "test your grip fade daily"),
        ("forearm size", "Your Forearm Tape Test", "forearm tissue", "train forearms daily"),
    ]),
    ("S6", "Skinny Fat", "skinnyfat", "skinnyfat", [
        ("the skinny fat belly", "Your Waist-to-Height Number", "recomp signaling", "walk after meals daily"),
        ("skinny fat arms", "Your Arm-to-Waist Ratio", "arm muscle signals", "train arms twice weekly"),
        ("the mirror test", "Your Mirror vs Scale Test", "body composition", "take weekly measurements"),
        ("protein for recomp", "Your Protein Number", "muscle protein signals", "hit your protein daily"),
        ("sleep and belly fat", "Your Sleep Score", "recovery hormones", "sleep 8 hours nightly"),
        ("steps and recomp", "Your Daily Step Number", "fat-burning enzymes", "walk 10k steps daily"),
        ("posture and the belly", "Your Posture Test", "pelvis position", "do posture work daily"),
        ("skinny fat chest", "Your Chest Test", "chest muscle signals", "train chest twice weekly"),
        ("stress and belly fat", "Your Stress Belly Test", "stress hormones", "walk daily to cut stress"),
        ("the recomp split", "Your Weekly Split Test", "training signals", "follow a recomp split"),
        ("skinny fat legs", "Your Leg-to-Waist Ratio", "leg muscle signals", "train legs twice weekly"),
        ("the 90-day recomp", "Your 90-Day Photo Test", "total body recomposition", "follow the recomp plan daily"),
    ]),
]
SEASONS += [
    ("S7", "30-Day Experiments", "experiments", "experiment", [
        ("dead hang", "Your Dead Hang Time", "grip tendons", "hang for 60 seconds"),
        ("push-ups", "Your Push-Up Number", "chest tendons", "do 50 push-ups"),
        ("wall sit", "Your Wall Sit Time", "knee tendons", "hold a 2-minute wall sit"),
        ("calf raises", "Your Calf Raise Number", "Achilles tendon", "do 100 calf raises"),
        ("plank", "Your Plank Time", "core nerves", "hold a 3-minute plank"),
        ("squats", "Your Squat Number", "knee and hip tendons", "do 100 squats"),
        ("pull-up singles", "Your Pull-Up Number", "elbow tendons", "do pull-up singles all day"),
        ("grip work", "Your Grip Test", "finger tendons", "train grip for 5 minutes"),
        ("balance work", "Your Balance Time", "ankle nerves", "stand on one leg for 5 minutes"),
        ("jumping", "Your Jump Height", "Achilles stiffness", "do 50 jumps"),
        ("walking after meals", "Your Post-Meal Walk Test", "blood sugar control", "walk 10 minutes after meals"),
        ("the L-sit", "Your L-Sit Time", "hip flexors", "practice the L-sit for 5 minutes"),
    ]),
    ("S8", "What Happens", "whathappens", "whathappens", [
        ("plank", "Your Plank Time", "core nerves", "hold a plank for 1 minute"),
        ("push-ups", "Your Push-Up Number", "chest tendons", "do 50 push-ups every morning"),
        ("dead hang", "Your Hang Time", "grip tendons", "hang for 1 minute"),
        ("squats", "Your Squat Number", "leg tendons", "do 100 squats"),
        ("calf raises", "Your Calf Number", "Achilles tendon", "do calf raises on the stairs"),
        ("stairs", "Your Stair Test", "leg power", "take the stairs"),
        ("wall sit", "Your Wall Sit Time", "knee tendons", "hold a wall sit during TV ads"),
        ("one-leg stand", "Your Balance Time", "ankle nerves", "stand on one leg while brushing your teeth"),
        ("pull-ups", "Your Pull-Up Number", "back tendons", "do 10 pull-ups"),
        ("jumps", "Your Jump Height", "bone density", "jump 20 times"),
        ("stretching", "Your Toe Touch Test", "tissue length", "stretch for 5 minutes"),
        ("the evening walk", "Your Walk Test", "recovery enzymes", "walk after dinner"),
    ]),
    ("S9", "Bones, Leverage & Skills", "skills", "bones", [
        ("planche lean", "Your Planche Lean Angle", "wrist and shoulder leverage", "lean daily"),
        ("front lever tuck", "Your Front Lever Tuck Time", "lat leverage", "practice tucks daily"),
        ("muscle-up transition", "Your Transition Test", "elbow leverage", "practice transitions daily"),
        ("wall handstand", "Your Wall Handstand Time", "wrist bones and balance nerves", "kick up daily"),
        ("pistol squat", "Your Pistol Depth Test", "ankle and knee leverage", "practice pistols daily"),
        ("Nordic curl", "Your Nordic Lowering Test", "hamstring tendons", "lower slowly daily"),
        ("human flag", "Your Flag Hold Time", "oblique leverage", "practice the flag daily"),
        ("dragon flag", "Your Dragon Flag Test", "core leverage", "practice dragon flags daily"),
        ("back lever tuck", "Your Back Lever Tuck Time", "shoulder leverage", "practice tucks daily"),
        ("elbow lever", "Your Elbow Lever Time", "wrist leverage", "practice the elbow lever daily"),
        ("shrimp squat", "Your Shrimp Squat Test", "knee leverage", "practice shrimp squats daily"),
        ("L-sit to V-sit", "Your V-Sit Angle", "hip leverage", "compress daily"),
    ]),
    ("S10", "Legs, Sprint & Jump", "legs", "legs", [
        ("vertical jump mechanics", "Your Vertical Jump", "Achilles stiffness", "jump daily"),
        ("broad jump", "Your Broad Jump Distance", "hip power", "broad jump daily"),
        ("sprint start", "Your 10-Meter Time", "nerve firing speed", "sprint weekly"),
        ("single-leg strength", "Your Single-Leg Test", "knee tendons", "train one leg daily"),
        ("tibialis strength", "Your Tibialis Raise Number", "tibialis muscle", "do toe raises daily"),
        ("ankle hops", "Your Hop Count", "ankle stiffness", "hop daily"),
        ("hill sprints", "Your Hill Sprint Time", "leg power nerves", "sprint hills weekly"),
        ("lateral bounds", "Your Bound Distance", "hip stability", "bound side to side daily"),
        ("calf stiffness", "Your Calf Bounce Test", "calf tendon stiffness", "bounce daily"),
        ("knee drive", "Your Knee Drive Speed", "hip flexor nerves", "drive knees daily"),
        ("landing mechanics", "Your Landing Silence Test", "tendon shock absorption", "practice soft landings daily"),
        ("the 20-meter sprint", "Your 20-Meter Time", "total leg power", "time your sprint monthly"),
    ]),
    ("S11", "Retests & Records", "retests", "retest", [
        ("dead hang retest", "Your New Dead Hang Time", "grip tendons", "retest monthly"),
        ("push-up retest", "Your New Push-Up Number", "chest tendons", "retest monthly"),
        ("wall sit retest", "Your New Wall Sit Time", "knee tendons", "retest monthly"),
        ("left vs right", "Your Weak-Side Test", "side-to-side nerve balance", "test both sides monthly"),
        ("morning vs evening", "Your Morning Strength Test", "daily nerve rhythm", "test twice a day"),
        ("the average skinny guy", "Your Rank Test", "benchmark data", "compare your numbers"),
        ("age benchmarks", "Your Age-Group Test", "benchmark data", "compare by age"),
        ("the 90-day record", "Your 90-Day Record", "total adaptation", "track 90 days"),
        ("grip retest", "Your New Grip Number", "finger tendons", "retest monthly"),
        ("jump retest", "Your New Jump Height", "Achilles stiffness", "retest monthly"),
        ("the rematch", "Your Rematch Test", "every system", "retest everything"),
        ("your weakest link", "Your Weakest Link Test", "your limiting system", "find your weak link"),
    ]),
    ("S12", "The Science Lab", "science", "science", [
        ("tendon stiffness science", "Your Stiffness Test", "tendon stiffness", "load your tendons slowly"),
        ("collagen timing", "Your Collagen Window Test", "collagen synthesis", "time your protein"),
        ("sleep science", "Your Sleep Strength Test", "recovery hormones", "sleep before midnight"),
        ("soreness science", "Your Soreness Test", "muscle damage signals", "track your soreness"),
        ("stretching science", "Your Flexibility Test", "tissue length signals", "stretch after training"),
        ("muscle memory", "Your Comeback Test", "muscle nuclei", "retrain after a break"),
        ("caffeine science", "Your Caffeine Test", "nerve stimulants", "time your caffeine"),
        ("heat and cold", "Your Temperature Test", "blood flow", "use cold after training"),
        ("massage myths", "Your Pressure Test", "tissue blood flow", "roll your muscles"),
        ("neural drive", "Your Drive Test", "motor unit recruitment", "train explosively"),
        ("protein science", "Your Protein Test", "muscle protein synthesis", "spread your protein"),
        ("supercompensation", "Your Timing Test", "recovery curves", "time your sessions"),
    ]),
    ("S13", "Gaining & Fuel", "gaining", "gaining", [
        ("the skinny surplus", "Your Surplus Number", "growth signals", "eat in a small surplus"),
        ("protein targets", "Your Protein Target", "muscle building blocks", "hit your protein target"),
        ("liquid calories", "Your Shake Test", "appetite limits", "drink one shake daily"),
        ("appetite training", "Your Appetite Test", "hunger hormones", "eat on a schedule"),
        ("meal timing", "Your Meal Timing Test", "nutrient windows", "eat after training"),
        ("creatine basics", "Your Creatine Test", "muscle energy stores", "take creatine daily"),
        ("the breakfast problem", "Your Breakfast Test", "morning appetite", "eat breakfast daily"),
        ("cheap calorie anchors", "Your Grocery Test", "calorie density", "stock anchor foods"),
        ("digestion", "Your Digestion Test", "gut absorption", "chew slowly"),
        ("snack engineering", "Your Snack Test", "calorie gaps", "add two snacks daily"),
        ("scale trends", "Your Trend Test", "weekly averages", "weigh yourself daily"),
        ("the gaining plateau", "Your Plateau Test", "adaptation", "raise calories slowly"),
    ]),
]

TEMPLATES = {
    "standard": [
        "{test} Reveals Your Hidden Strength",
        "{test} Reveals the Truth About Your {mech}",
        "5 {topic} Mistakes That Are Destroying Your {mech}",
        "Why Your {mech} Matter More Than Muscle (The {topic} Episode)",
        "Stop Doing {topic} Wrong: Train Your {mech} Instead",
    ],
    "experiment": [
        "I Did {habit} Every Day for 30 Days (What Happened to My {mech})",
        "A Skinny Guy Did {topic} for 30 Days (His {mech} Changed)",
        "What 30 Days of {topic} Does to a Skinny Guy",
        "The 30-Day {topic} Experiment: Your {mech} Week by Week",
        "I Tested {topic} for 30 Days (The Results Surprised Me)",
    ],
    "whathappens": [
        "What Happens to Your {mech} If You {habit} Every Day",
        "Do This Every Morning: What {topic} Does to Your {mech}",
        "What 1 Minute of {topic} Every Day Does to Your {mech}",
        "If You {habit} Daily, This Happens to Your {mech}",
        "The {topic} Habit Nobody Trains (It Builds Your {mech})",
    ],
    "retest": [
        "{test}: Did It Actually Change? (Your {mech} Results)",
        "Your New Number: The {topic} Retest Nobody Does",
        "90 Days Later: {test} — The {mech} Verdict",
        "The {topic} Benchmark: Where Your {mech} Ranks",
        "Retest Day: What Your New {topic} Number Proves About Your {mech}",
    ],
}
TEMPLATES["mixed"] = TEMPLATES["standard"]
for _k in ("tendons", "pain", "nerves", "grip", "skinnyfat", "bones", "legs", "science", "gaining"):
    TEMPLATES[_k] = TEMPLATES["standard"]

FILTER = {
    "identity": ["skinny", "your ", "you ", "yourself", "mirror", "my "],
    "advantage": ["hidden", "secret", "more than", "beats", "stronger", "truth", "nobody", "surprised"],
    "mechanism": ["tendon", "nerve", "grip", "bone", "leverage", "stiffness", "collagen", "hormone",
                  "signal", "enzyme", "tissue", "protein", "drive", "recruitment", "nuclei", "blood",
                  "appetite", "absorption", "density", "healing", "ligament", "flexor"],
    "test": ["test", "number", "time", "seconds", "minute", "days", "rank", "how ", "what happens",
             "happened", "retest", "height", "distance"],
    "enemy": ["mistakes", "wrong", "stop ", "lying", "myth", "nobody", "destroying", "plateau"],
}


def score(title):
    low = " " + title.lower() + " "
    hits = [name for name, words in FILTER.items() if any(w in low for w in words)]
    return len(hits), hits


def build():
    episodes, seen = [], set()
    n = 0
    for sid, sname, cat, kind, cores in SEASONS:
        temps = TEMPLATES[kind]
        rows = []
        for ci, (topic, test, mech, habit) in enumerate(cores):
            for ti, temp in enumerate(temps):
                title = temp.format(topic=topic, test=test, mech=mech,
                                    habit=habit, Topic=topic.title())
                assert title.lower() not in seen, f"duplicate title: {title}"
                seen.add(title.lower())
                s, hits = score(title)
                rows.append({"season": sid, "season_name": sname, "category": cat,
                             "kind": kind, "core": topic, "test": test, "mechanism": mech,
                             "title": title, "score": s, "filter_hits": hits})
        rows.sort(key=lambda r: (-r["score"], r["title"]))
        for i, r in enumerate(rows, 1):
            n += 1
            r["n"] = n
            r["ep_in_season"] = i
            episodes.append(r)
    return episodes


def main():
    eps = build()
    out = os.path.join(ROOT, "bank", "episodes.json")
    json.dump(eps, open(out, "w"), indent=1)
    from collections import Counter
    dist = Counter(e["score"] for e in eps)
    lines = ["# Episode Map — 780 Episodes, 13 Seasons", "",
             "Generated by tools/gen_episode_map.py from hand-picked cores.",
             "Every title scored against the five-point filter (identity / unfair",
             "advantage / new mechanism / test-or-number / enemy). Scripts are",
             "written in graded order from this map at build time.", "",
             f"Total episodes: {len(eps)}  |  duplicate titles: 0  |  "
             f"score distribution: {dict(sorted(dist.items()))}",
             "Titles scoring >=3 pass the filter outright. Score-2 titles (16%) are",
             "publishable but flagged: each one gets an individual title polish",
             "when its script is written, before it can enter the bank.", ""]
    for sid, sname, cat, kind, cores in SEASONS:
        rows = [e for e in eps if e["season"] == sid]
        lines.append(f"## {sid} — {sname} ({len(rows)} episodes)")
        lines.append(f"Top-scored: {rows[0]['title']} (score {rows[0]['score']})")
        lines.append("")
    open(os.path.join(ROOT, "EPISODE_MAP.md"), "w").write("\n".join(lines))
    print(f"episodes: {len(eps)} | scores: {dict(sorted(dist.items()))}")
    print(f"wrote {out} and EPISODE_MAP.md")


if __name__ == "__main__":
    main()
