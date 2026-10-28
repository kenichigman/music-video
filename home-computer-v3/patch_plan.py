#!/usr/bin/env python3
"""QA-catch patch to plan_v3.json (cloud agent head).

The first planner pass's anime guest pool was motion-verified but NOT
character-verified: four guest windows show the removed man (Jin --
long black ponytail, glasses, dark-blue crested kimono), which the
blend steer forbids ("blend windows must never reintroduce ... the
newly flagged man"):
  film 32-34  anime @14  (his back, action beat -- identifiable)
  film 52-54  anime @210 (PROMINENT: grinning mid-shot + a face
              close-up of another character, held 2s)
  film 96-98  anime @56  (wide cart two-shot, clearly identifiable)
  film 260-262 anime @54 (same cart scene)
Replacement windows were motion-scanned from diffs_anime.npy and
sheet-verified frame-by-frame by the cloud agent head (no Jin, no face
close-ups). Usage: patch_plan.py PLAN.json OFF14 OFF210 OFF56 OFF54
(windows are [off, off+2) for the rows at film 32-34, 52-54, 96-98,
260-262 respectively). Prints the row indices / sec file names whose
renders must be discarded before the mosh re-run.
"""
import json
import sys

path = sys.argv[1]
new_off = {(32, 34): int(sys.argv[2]), (52, 54): int(sys.argv[3]),
           (96, 98): int(sys.argv[4]), (260, 262): int(sys.argv[5])}
plan = json.load(open(path))
old = {}
for i, r in enumerate(plan["rows"]):
    key = (r["start"], r["end"])
    if key in new_off:
        assert r["src"] == "anime" and r["kind"] == "guest", (i, r)
        old[key] = r["offset"]
        r["offset"] = new_off[key]
        print(f"row {i} (sec{i:02d}.mp4): film {key[0]}-{key[1]} "
              f"anime @{old[key]} -> @{new_off[key]}")
assert len(old) == 4, old
used = plan["used"]["anime"]
for (a, b), off in zip(sorted(old), [old[k] for k in sorted(old)]):
    pass
for key, off in old.items():
    rng = [off, off + 2]
    if rng in used:
        used.remove(rng)
for key, off in new_off.items():
    rng = [off, off + 2]
    assert not any(rng[0] < y and x < rng[1] for x, y in used), rng
    used.append(rng)
plan["used"]["anime"] = sorted(used)
plan["v3_coordinator_patch"] = {
    "reason": "anime guest windows at film 32-34 (@14), 52-54 (@210), "
              "96-98 (@56), 260-262 (@54) showed the removed man (Jin); "
              "the blend steer forbids reintroducing him. Replaced with "
              "motion-scanned, sheet-verified Jin-free windows.",
    "replaced": {f"{a}-{b}": {"from_offset": old[(a, b)],
                              "to_offset": new_off[(a, b)]}
                 for (a, b) in sorted(old)},
    "verified": "contact sheets of every anime guest "
                "window + candidate windows (frames at both seconds "
                "of each replacement window)",
}
json.dump(plan, open(path, "w"), indent=1)
print("patched", path)
