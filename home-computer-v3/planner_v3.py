#!/usr/bin/env python3
"""Global EDL planner for Home Computer supercut v3.

High-frequency blend ("crazy style" density pass, the director's steer): within
each section (except exempt 0-30 and S6's kept spans), interleave all six
sources in SHORT windows -- home 2-4s, guests 2-3s -- home-weighted (share
0.50-0.70), boundaries snapped to measured flux accents. No section reads
single-source for more than ~4s. Guest windows are allocated CENTRALLY
from verified pools -- no source window is used twice anywhere in the
film. GitS is physically scarce (~11s never used): pre-packed as one 3s
window for S6 + one reserved 2s window in each of S2/S3/S5/S7 (S8 has
none and S9's 11s fits only 3 sources -- the cap is documented). S6
(221-258) is frame-precise and built separately; this planner emits its
pieces too.

Outputs plan_v3.json: rows for cut_sections-style cutting + s6 frame map +
allocation ledger.
"""
import json
import os

import numpy as np

W3 = os.path.dirname(os.path.abspath(__file__))
FEAT = json.load(open(os.environ.get(
    "MUSIC_VIDEO_FEATURES",
    os.path.join(W3, "home-computer_features.json"))))
FLUX = {s["t"]: s["flux"] for s in FEAT["seconds"]}

SRC = {  # logical name -> (diffs file, duration)
    "anime":   ("diffs_anime.npy",   231.18),
    "hands":   ("diffs_hands.npy",    61.10),
    "store":   ("diffs_store.npy",   251.13),
    "gits":    ("diffs_gits.npy",     40.51),
    "nature":  ("diffs_nature.npy",  207.02),
    "october": ("diffs_october.npy", 117.45),
}
LOGICAL = {
    "anime":   "sources/anime.mp4",
    "hands":   "sources/bw-hands-dm.mp4",
    "store":   "sources/conveniencestore-dm.mp4",
    "gits":    "sources/gits-dm.mp4",
    "nature":  "sources/gits-nature-dm.mp4",
    "october": "sources/october-dream.mp4",
}
PRE = {"hands": "transpose=1"}

# per-second motion (mean frame diff within each source second)
MOTION = {}
for name, (fn, dur) in SRC.items():
    d = np.load(f"{W3}/{fn}")
    fps = len(d) / dur
    n = int(dur)
    MOTION[name] = np.array([
        d[int(i * fps):int((i + 1) * fps)].mean() if int((i + 1) * fps) <= len(d)
        else d[int(i * fps):].mean() for i in range(n)])

def motion_ok(name, a, b):
    """No dead seconds. Anime is limited-animation (flat color = small
    diffs): it passes on mean >= 1.5 with no literally-frozen second;
    other sources need every second >= 1.2."""
    seg = MOTION[name][a:b]
    if len(seg) != b - a:
        return False
    if name == "anime":
        return float(seg.min()) >= 0.1 and float(seg.mean()) >= 1.5
    return float(seg.min()) >= 1.2

def motion_score(name, a, b):
    seg = MOTION[name][a:b]
    return float(seg.min()) + 0.25 * float(seg.mean())

# ---- global used-window ledger (source -> list of [a,b)) -------------------
USED = {k: [] for k in SRC}
def claim(name, a, b, why):
    for (x, y) in USED[name]:
        assert not (a < y and x < b), f"OVERLAP {name} [{a},{b}) vs [{x},{y}) ({why})"
    USED[name].append((a, b))

# surviving v2 content (definitional)
claim("october", 13, 19, "S0 exempt home clock")
claim("nature", 24, 48, "S1 exempt home clock")
claim("anime", 165, 173, "S6 kept spans (source clock, approx)")
claim("nature", 93, 97, "S6 kept char3 replacement (frames 2790-2909)")
claim("gits", 2, 5, "S6 zoneA guest1 (fixed 3s window)")
# GitS guest reservations: the 11 free seconds pack EXACTLY as one 3s
# window (S6, above) + four 2s windows, one per priority section.
RESERVED_GITS = {2: (34, 36), 3: (36, 38), 5: (38, 40), 7: (0, 2)}
for _i, (_a, _b) in RESERVED_GITS.items():
    claim("gits", _a, _b, f"S{_i} reserved gits guest")

# home clocks of blended sections are reserved as home spans
HOME_SPANS = {  # section idx -> (source, clock a, clock b)
    2: ("store", 120, 184), 3: ("hands", 8, 27), 4: ("gits", 5, 34),
    5: ("nature", 100, 179), 7: ("october", 45, 110),
    8: ("store", 190, 237), 9: ("nature", 190, 201),
}
for idx, (nm, a, b) in HOME_SPANS.items():
    claim(nm, a, b, f"S{idx} home clock")

# guest pools (free ranges minus reservations)
POOLS = {
    "nature":  [(0, 24), (48, 92), (180, 190), (201, 206)],
    "october": [(0, 13), (19, 45), (110, 117)],
    "store":   [(0, 120), (184, 190), (237, 251)],
    "hands":   [(0, 8), (27, 61)],
    "gits":    [(0, 5), (34, 40)],   # all never-used GitS: ~11s, budget-run
    "anime":   [(2, 4), (14, 17), (27, 29), (51, 53), (54, 58), (196, 199),
                (200, 204), (208, 212), (224, 227)],  # sheet+motion verified
}
def alloc_guest(name, length, why):
    """Best-motion window of `length` inside name's pool, unclaimed."""
    cands = []
    spans = []
    for (pa, pb) in POOLS[name]:
        for a in range(pa, pb - length + 1):
            spans.append((a, a + length))
    for (a, b) in spans:
        if any(a < y and x < b for (x, y) in USED[name]):
            continue
        if motion_ok(name, a, b):
            cands.append((motion_score(name, a, b), a, b))
    assert cands, f"no guest window for {name} len={length} ({why})"
    cands.sort(reverse=True)
    # spread: among near-best, prefer farthest from existing claims
    best = cands[0][0]
    near = [c for c in cands if c[0] >= best - 1.0]
    def spread(c):
        if not USED[name]:
            return 0
        return min(abs(c[1] - y) + abs(c[2] - x) for (x, y) in USED[name])
    near.sort(key=spread, reverse=True)
    _, a, b = near[0]
    claim(name, a, b, why)
    return a

# ---- per-section window layout via DP --------------------------------------
SECTIONS = {  # idx -> (start, end, home source, home offset)
    2: (30, 94, "store", 120), 3: (94, 113, "hands", 8),
    4: (113, 142, "gits", 5), 5: (142, 221, "nature", 100),
    7: (258, 323, "october", 45), 8: (323, 370, "store", 190),
    9: (370, 381, "nature", 190),
}
GUESTS = ["nature", "october", "store", "anime", "hands", "gits"]

def plan_section(idx, allow_gits=False):
    start, end, home, hoff = SECTIONS[idx]
    total = end - start
    others = [g for g in GUESTS if g != home]
    order = others[idx % 5:] + others[:idx % 5]  # rotated guest order
    # DP over (pos, last_is_home, guest_i, home_secs) -> (flux_sum, layout)
    from functools import lru_cache
    import sys
    sys.setrecursionlimit(10000)

    @lru_cache(maxsize=None)
    def go(pos, last_home, gi, home_secs, gits_used):
        if pos == total:
            share = home_secs / total
            return (0.0, []) if 0.50 <= share <= 0.70 else None
        rem = total - pos
        best = None
        # next window type: alternate strictly, home first
        is_home = not last_home
        if is_home:
            lengths = range(2, 5)
            nxt_gits = gits_used
        else:
            g_des = order[gi % len(order)]
            if g_des == "gits" and allow_gits and not gits_used:
                lengths = [2]  # one 2s GitS window per priority section
                nxt_gits = True
            else:
                lengths = range(2, 4)
                nxt_gits = gits_used
        for L in lengths:
            if L > rem:
                continue
            if rem - L == 1:   # never strand 1s
                continue
            if rem - L == 0 and not is_home:
                continue        # end on home
            nxt = go(pos + L, is_home, gi + (0 if is_home else 1),
                     home_secs + (L if is_home else 0), nxt_gits)
            if nxt is None:
                continue
            score = FLUX.get(start + pos + L, 0.0) + nxt[0]
            if best is None or score > best[0]:
                best = (score, [(pos, L, is_home, gi)] + nxt[1])
        return best

    res = go(0, False, 0, 0, False)
    assert res, f"section {idx}: no layout"
    rows = []
    used = set()          # guests already placed in this section
    gits_used_sec = False
    for (pos, L, is_home, gi) in res[1]:
        t0, t1 = start + pos, start + pos + L
        if is_home:
            rows.append({"clip": LOGICAL[home], "src": home,
                         "offset": hoff + pos, "start": t0, "end": t1,
                         "pre": PRE.get(home), "kind": "home"})
        else:
            # designated guest; GitS only once per priority section and
            # only while the budget lasts; duplicates collapse onto an
            # unused guest (keeps short sections maximally diverse)
            g_des = order[gi % len(order)]
            rot = [order[(gi + k) % len(order)] for k in range(len(order))]
            gits_ok = allow_gits and not gits_used_sec and L == 2
            if g_des == "gits" and not gits_ok:
                cands = [c for c in rot[1:] if c != "gits"]
                g = next((c for c in cands if c not in used), cands[0])
            else:
                g = g_des
            if g in used:
                unused = [c for c in rot if c != "gits" and c not in used]
                if unused:
                    g = unused[0]
            off = None
            for c in [g] + [c for c in rot if c != g]:
                if c == "gits":
                    if gits_ok:
                        off = RESERVED_GITS[idx][0]
                        g = c
                        break
                    continue
                try:
                    off = alloc_guest(c, L, f"S{idx} guest @{t0}")
                except AssertionError:
                    continue
                g = c
                break
            assert off is not None, f"S{idx} @{t0}: all guests exhausted"
            if g == "gits":
                gits_used_sec = True
            used.add(g)
            rows.append({"clip": LOGICAL[g], "src": g, "offset": off,
                         "start": t0, "end": t1, "pre": PRE.get(g),
                         "kind": "guest"})
    return rows

# (GitS scarcity is handled by RESERVED_GITS above -- no budget counter.)

plan = {"rows": [], "sections": {}}
# rows 0-1: reused v2 sec files (exempt)
plan["rows"].append({"clip": LOGICAL["october"], "src": "october", "offset": 13,
                     "start": 0, "end": 6, "pre": None, "kind": "reuse_v2_sec"})
plan["rows"].append({"clip": LOGICAL["nature"], "src": "nature", "offset": 24,
                     "start": 6, "end": 30, "pre": None, "kind": "reuse_v2_sec"})
for idx in (2, 3, 4, 5):
    plan["rows"].extend(plan_section(idx, allow_gits=idx in RESERVED_GITS))

# ---- S6 frame-precise map (film frames; row = one sec file 221-258) --------
# zone A blend pieces (film seconds), zone B kept, Jin replacement, zone C
s6 = {"row_span": [221, 258], "pieces": []}
def s6_piece(f0, f1, src, s0, note, pre=None):
    s6["pieces"].append({"film": [f0, f1], "src": src, "src_frame": s0,
                         "note": note, "pre": pre})
# zone A: [221,224)H anime clock, [224,227)G gits, [227,230)H, [230,233)G
# hands, [233,236.07)H -- with the nature/store/october replacements below,
# S6 carries all six sources.
g_a2 = alloc_guest("hands", 3, "S6 zoneA guest2")
s6_piece(6630, 6720, "anime", 4500, "zoneA home anime clock 150-153")
s6_piece(6720, 6810, "gits", 2 * 30, "zoneA guest gits @2")
s6_piece(6810, 6900, "anime", 4680, "zoneA home anime clock 156-159")
s6_piece(6900, 6990, "hands", g_a2 * 30, "zoneA guest hands",
         pre="transpose=1")
s6_piece(6990, 7082, "anime", 4860, "zoneA home anime clock 162-165.07")
s6_piece(7082, 7311, "anime", 4952, "KEPT praised spans (char1+Mugen)")
s6_piece(7311, 7431, "nature", 2790, "KEPT v2 char3 replacement (nature @93)")
jin_win = alloc_guest("nature", 4, "S6 Jin replacement")
s6_piece(7431, 7533, "nature", jin_win * 30,
         f"NEW Jin close-up replacement (nature @{jin_win}, first 102 frames)")
g_c1 = alloc_guest("store", 3, "S6 zoneC guest1")
g_c2 = alloc_guest("october", 3, "S6 zoneC guest2")
s6_piece(7533, 7635, "store", g_c1 * 30, "zoneC trio replacement part1 (store)")
s6_piece(7635, 7740, "october", g_c2 * 30, "zoneC trio replacement part2 (cat)")
assert sum(p["film"][1] - p["film"][0] for p in s6["pieces"]) == 1110
plan["s6"] = s6
plan["rows"].append({"clip": LOGICAL["anime"], "src": "anime", "offset": 150,
                     "start": 221, "end": 258, "pre": None,
                     "kind": "s6_frame_precise"})

for idx in (7, 8, 9):
    plan["rows"].extend(plan_section(idx, allow_gits=idx in RESERVED_GITS))

plan["used"] = {k: sorted([list(x) for x in v]) for k, v in USED.items()}
plan["sections"] = {str(k): {"span": [v[0], v[1]], "home": v[2],
                             "home_offset": v[3]} for k, v in SECTIONS.items()}

with open(f"{W3}/plan_v3.json", "w") as fh:
    json.dump(plan, fh, indent=1)

# human-readable map
for i, r in enumerate(plan["rows"]):
    print(f"row{i:02d} [{r['start']:>3}-{r['end']:>3}) {r['kind']:<16} "
          f"{r['src']:<8} @{r['offset']}")
print("\nS6 pieces:")
for p in s6["pieces"]:
    print(f"  film {p['film'][0]}-{p['film'][1]} {p['src']} frame {p['src_frame']}  {p['note']}")
print("\nUSED ledger:")
for k, v in plan["used"].items():
    print(f"  {k}: {v}")
