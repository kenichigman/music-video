#!/usr/bin/env python3
"""Validation of the Blob Track derivation against the stage-1 oracle
tables, per spec.md §6. Computes the four pre-registered bars +
effect-equivalence deltas, per row and pooled. Bars do not move;
implementation variants (SPEC §4) are all reported.

Usage: python3 validate.py [--rows 0,13,52] [--out-prefix derived_]
Derived tables are cached as derived_rowNN_<variant>.csv next to
this script; delete to force a rebuild.
"""
import csv, json, os, sys
from collections import defaultdict

import numpy as np
from scipy.spatial import cKDTree
from scipy.stats import spearmanr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blobtrack as bt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RIG = os.environ.get("BLOBTRACK_RIG_DIR", os.path.join(HERE, "rig", "rows"))
SRC = os.path.join(HERE, "src")
MANIFEST = os.environ.get("BLOBTRACK_MANIFEST", os.path.join(HERE, "rig", "manifest.json"))

SUBSET = {12: "CP", 48: "CP", 6: "TR", 24: "TR", 2: "SR", 7: "SR",
          0: "VT", 13: "VT", 52: "VT"}
VARIANTS = [  # SPEC §4 pre-declared candidate semantics
    # primary is spelled out in full so it stays reproducible even
    # if the module defaults move to the derived model.
    ("primary_height_centroid_off", dict(bg_mode="off",
                                         size_source="bbox",
                                         size_measure="height",
                                         center_mode="centroid")),
    ("maxdim", dict(size_measure="max_dim")),
    ("bbox_center", dict(center_mode="bbox_center")),
    ("bg_ema", dict(bg_mode="ema")),
    # round-2/3 derivation (added during validation forensics,
    # disclosed in VALIDATION.md): per-pixel Gaussian background
    # over the soft matte (the TOP is OpenCV-based per the public
    # record) + square-size emission (oracle h == w*aspect exactly).
    ("final_gauss_square", dict(bg_mode="gauss", bg_history=200.0,
                                size_source="square_sqrt_area")),
]


def load_table(path):
    frames = defaultdict(list)
    with open(path) as fh:
        for r in csv.reader(fh):
            if len(r) < 7:
                continue
            try:
                f, tid = int(r[0]), int(r[1])
                u, v, w, h, age = (float(x) for x in r[2:7])
            except ValueError:
                continue
            frames[f].append(dict(id=tid, u=u, v=v, w=w, h=h, age=age))
    return frames


def lifecycle_events(frames):
    """SPEC §6 operational definitions, from presence sequences alone."""
    pres = defaultdict(set)
    for f, blobs in frames.items():
        for b in blobs:
            pres[b["id"]].add(f)
    ev = dict(births=0, losses=0, revivals=0, expiries=0)
    for tid, fs in pres.items():
        fs = sorted(fs)
        ev["births"] += 1
        for a, b in zip(fs, fs[1:]):
            if b > a + 1:
                ev["losses"] += 1      # a disappearance...
                ev["revivals"] += 1    # ...followed by a return
        ev["losses"] += 1              # final disappearance
        ev["expiries"] += 1            # never revived -> expired
    return ev


def evaluate(oracle, derived):
    """The four bars' raw statistics for one row (or pooled frames)."""
    ratios, dists, osizes, dsizes = [], [], [], []
    allf = sorted(set(oracle) | set(derived))
    for f in allf:
        O = oracle.get(f, [])
        D = derived.get(f, [])
        if O:
            ratios.append(len(D) / len(O))
        if O and D:
            tree = cKDTree([(b["u"], b["v"]) for b in D])
            used = set()
            pairs = []
            for b in O:
                d, j = tree.query((b["u"], b["v"]))
                pairs.append((d, j, b))
            pairs.sort(key=lambda t: t[0])
            for d, j, b in pairs:
                if d <= 0.05 and j not in used:
                    used.add(j)
                    dists.append(d)
                    osizes.append(b["w"] * b["h"])
                    dsizes.append(D[j]["w"] * D[j]["h"])
    res = dict(
        count_ratio_median=float(np.median(ratios)) if ratios else None,
        n_frames=len(ratios),
        centroid_median=float(np.median(dists)) if dists else None,
        n_matched=len(dists),
        match_rate=(len(dists) / max(1, sum(len(oracle.get(f, []))
                                            for f in allf))),
    )
    if len(osizes) >= 3:
        res["size_spearman"] = float(spearmanr(osizes, dsizes).statistic)
    else:
        res["size_spearman"] = None
    return res


def node_selection_stats(frames):
    """Graph test-1 style selection: age>=0.5s, rank area*age, top 24.
    Returns mean selected/frame and mean centroid dispersion."""
    counts, disps = [], []
    for f in sorted(frames):
        elig = [b for b in frames[f] if b["age"] >= 0.5]
        elig.sort(key=lambda b: -(b["w"] * b["h"] * b["age"]))
        sel = elig[:24]
        counts.append(len(sel))
        if len(sel) >= 2:
            P = np.array([(b["u"], b["v"]) for b in sel])
            disps.append(float(np.mean(np.hypot(
                *(P - P.mean(axis=0)).T))))
    return (float(np.mean(counts)) if counts else 0.0,
            float(np.mean(disps)) if disps else 0.0)


def build_derived(rn, variant_kw, world):
    preset = "vt" if world == "VT" else "e2"
    kw = dict(bt.PRESETS[preset])
    kw.update(variant_kw)
    p = bt.Params(**kw)
    rows, _full, _ev, _nf = bt.track_video(
        os.path.join(SRC, f"row{rn:02d}.mp4"), p)
    frames = defaultdict(list)
    for f, tid, u, v, w, h, age in rows:
        frames[f].append(dict(id=tid, u=u, v=v, w=w, h=h, age=age))
    return frames


def main():
    only = None
    if "--rows" in sys.argv:
        only = {int(x) for x in
                sys.argv[sys.argv.index("--rows") + 1].split(",")}
    report = {}
    for vname, vkw in VARIANTS:
        pooled_o, pooled_d = defaultdict(list), defaultdict(list)
        per_row = {}
        ev_o = dict(births=0, losses=0, revivals=0, expiries=0)
        ev_d = dict(births=0, losses=0, revivals=0, expiries=0)
        for rn, world in sorted(SUBSET.items()):
            if only and rn not in only:
                continue
            oracle = load_table(os.path.join(RIG, f"row{rn:02d}",
                                             "tracks.csv"))
            cache = os.path.join(HERE, f"derived_row{rn:02d}_{vname}.csv")
            if os.path.exists(cache):
                derived = load_table(cache)
            else:
                derived = build_derived(rn, vkw, world)
                with open(cache, "w") as fh:
                    for f in sorted(derived):
                        for b in derived[f]:
                            fh.write("%d,%d,%s,%s,%s,%s,%s\n" % (
                                f, b["id"], bt.fmt(b["u"]), bt.fmt(b["v"]),
                                bt.fmt(b["w"]), bt.fmt(b["h"]),
                                bt.fmt(b["age"])))
            per_row[rn] = evaluate(oracle, derived)
            eo, ed = lifecycle_events(oracle), lifecycle_events(derived)
            for k in ev_o:
                ev_o[k] += eo[k]
                ev_d[k] += ed[k]
            for f, blobs in oracle.items():
                pooled_o[(rn, f)].extend(blobs)
            for f, blobs in derived.items():
                pooled_d[(rn, f)].extend(blobs)
        pooled = evaluate(pooled_o, pooled_d)
        report[vname] = dict(per_row=per_row, pooled=pooled,
                             events_oracle=ev_o, events_derived=ev_d)
        print(f"== {vname}")
        for rn, r in sorted(per_row.items()):
            print(f"  row{rn:02d} ({SUBSET[rn]}): count_med "
                  f"{r['count_ratio_median']} centroid_med "
                  f"{r['centroid_median']} spearman {r['size_spearman']} "
                  f"matched {r['n_matched']} match_rate "
                  f"{r['match_rate']:.3f}")
        print(f"  POOLED: {pooled}")
        print(f"  events oracle {ev_o} derived {ev_d}")
    # effect equivalence, rows 02 + 13: primary + final config
    eq = {}
    for vname in ("primary_height_centroid_off", "final_gauss_square"):
        eq[vname] = {}
        for rn in (2, 13):
            oracle = load_table(os.path.join(RIG, f"row{rn:02d}",
                                             "tracks.csv"))
            derived = load_table(os.path.join(
                HERE, f"derived_row{rn:02d}_{vname}.csv"))
            eq[vname][rn] = dict(
                oracle=node_selection_stats(oracle),
                derived=node_selection_stats(derived))
            print(f"effect-equiv [{vname}] row{rn:02d}: oracle "
                  f"{eq[vname][rn]['oracle']} derived "
                  f"{eq[vname][rn]['derived']}")
    with open(os.path.join(HERE, "validation_numbers.json"), "w") as fh:
        json.dump(dict(report=report, effect_equivalence=eq), fh, indent=1,
                  default=str)


if __name__ == "__main__":
    main()
