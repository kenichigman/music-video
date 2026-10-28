#!/usr/bin/env python3
"""Phase gate for home-computer_supercut_v3 (adapted from qa_v2.py).

Checks (sequential decode throughout):
 A. Every section boundary has a video accent within +/-0.25s. (GATE)
 B. Major in-section audio onsets (flux >= p90, >=2s apart, not near a
    boundary) have a video accent within +/-0.25s. (informational, as in
    v1/v2: sustained-melt stretches are the grammar working as designed)
 C. Video-diff spike clusters explained by declared cuts (v3 declares
    every plan-row boundary + S6 piece boundaries), timeline shifts, or
    section boundaries. (informational in a blend film: cuts land every
    ~2s by design)
 D. No dead stretch: in sections with chaos >= 0.85, no run of >=3
    consecutive seconds whose per-second peak diff stays below 2x the
    film median (the v1 frozen-window failure mode). (GATE)
"""
import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from render import decode_audio, FFMPEG  # noqa: E402

BASE = os.environ.get("MUSIC_VIDEO_WORK_ROOT", ".")
FILM = BASE + "/work_v3/home-computer_supercut_v3.mp4"
TIMELINE = BASE + "/work_super_v3/timeline.mp4"
AUDIO = BASE + "/audio/home-computer_CLEAN.mp3"
PLAN = BASE + "/plan_v3.json"
FPS = 30
CUTS = [6, 30, 94, 113, 142, 221, 258, 323, 370]
SECTIONS = [(0, 6, 0.35), (6, 30, 0.70), (30, 94, 0.95), (94, 113, 0.45),
            (113, 142, 0.85), (142, 221, 1.30), (221, 258, 1.20),
            (258, 323, 0.55), (323, 370, 0.90), (370, 381, 0.35)]
W2, H2 = 424, 232


def decode_gray(path, w, h):
    cmd = [FFMPEG, "-v", "error", "-i", path, "-vf",
           f"fps={FPS},scale={w}:{h},format=gray",
           "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    data = subprocess.run(cmd, capture_output=True).stdout
    n = len(data) // (w * h)
    return np.frombuffer(data[:n * w * h], dtype=np.uint8) \
        .reshape(n, h, w).astype(np.float32)


def frame_diffs(frames):
    return np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))


def timeline_shifts():
    frames = decode_gray(TIMELINE, 212, 116)
    d = frame_diffs(frames)
    thr = float(np.percentile(d, 98))
    cuts, i = [], 1
    while i < len(d) - 1:
        if d[i] > thr and d[i] >= d[i - 1] and d[i] >= d[i + 1]:
            t = (i + 1) / FPS
            if 1.0 < t < len(d) / FPS - 1.0 and \
                    (not cuts or t - cuts[-1] >= 2.0):
                cuts.append(t)
            i += 2 * FPS
        else:
            i += 1
    return cuts


def declared_cuts():
    plan = json.load(open(PLAN))
    cuts = set()
    for r in plan["rows"]:
        cuts.add(float(r["start"]))
        cuts.add(float(r["end"]))
    for p in plan["s6"]["pieces"]:
        cuts.add(p["film"][0] / FPS)
        cuts.add(p["film"][1] / FPS)
    return sorted(cuts)


def main():
    print("== decode film (sequential) ==", flush=True)
    frames = decode_gray(FILM, W2, H2)
    n = len(frames)
    print(f"  frames: {n} ({n / FPS:.2f}s)")
    D = frame_diffs(frames)
    med = float(np.median(D))

    print("== audio onset envelope at 30fps ==", flush=True)
    x = decode_audio(AUDIO).astype(np.float64)
    hop = 44100 // FPS
    win = 2048
    mags = []
    for start in range(0, len(x) - win, hop):
        seg = x[start:start + win] * np.hanning(win)
        mags.append(np.abs(np.fft.rfft(seg)))
    mags = np.array(mags)
    flux = np.maximum(0, np.diff(mags, axis=0)).sum(axis=1)
    flux = flux / (flux.max() or 1.0)
    nf = min(len(D), len(flux))
    D, flux = D[:nf], flux[:nf]
    print(f"  aligned frames: {nf}")

    def accent_near(t, halfwin=0.25):
        c = int(round(t * FPS))
        lo = max(0, c - int(halfwin * FPS))
        hi = min(len(D), c + int(halfwin * FPS) + 1)
        if hi <= lo:
            return 0.0, None
        j = lo + int(np.argmax(D[lo:hi]))
        return float(D[j]), (j - c) / FPS

    print("== A. boundary accents (+/-0.25s) ==")
    a_fail = []
    a_offsets = {}
    for c in CUTS:
        peak, off = accent_near(c)
        ok = peak >= 4 * med and off is not None and abs(off) <= 0.25
        a_offsets[c] = off
        print(f"  cut {c:>3}s: peak diff {peak:6.2f} (median {med:.2f}) "
              f"offset {off:+.2f}s -> {'OK' if ok else 'FAIL'}")
        if not ok:
            a_fail.append(c)

    print("== B. major in-section onsets ==")
    p90 = float(np.percentile(flux, 90))
    onsets, last = [], -10
    for f in range(1, len(flux) - 1):
        t = f / FPS
        if flux[f] >= p90 and flux[f] >= flux[f - 1] and \
                flux[f] >= flux[f + 1] and t - last >= 2.0 and \
                all(abs(t - c) > 1.0 for c in CUTS):
            onsets.append((t, float(flux[f])))
            last = t
    b_miss = []
    for t, fv in onsets:
        peak, off = accent_near(t)
        ok = peak >= 3 * med
        if not ok:
            b_miss.append(t)
    print(f"  onsets checked: {len(onsets)}, misses: {len(b_miss)} "
          f"{[round(t, 1) for t in b_miss]}")

    print("== C. unexplained spikes ==")
    shifts = timeline_shifts()
    declared = declared_cuts()
    print(f"  timeline shifts: {len(shifts)}, declared cuts: {len(declared)}")
    p = float(np.percentile(D, 98.5))
    idx = np.where(D >= p)[0]
    clusters = []
    for f in idx:
        t = f / FPS
        if not clusters or t - clusters[-1][-1] > 0.5:
            clusters.append([t])
        else:
            clusters[-1].append(t)

    def explained(t):
        return any(abs(t - c) <= 0.35 for c in CUTS) or \
            any(abs(t - c) <= 0.35 for c in declared) or \
            any(abs(t - s) <= 0.35 for s in shifts)

    c_bad = [cl[0] for cl in clusters if not explained(cl[0])]
    for t0 in c_bad:
        print(f"  UNEXPLAINED spike cluster at {t0:.1f}s "
              f"(peak {float(D[int(t0 * FPS)]):.1f})")
    print(f"  spike clusters: {len(clusters)}, unexplained: {len(c_bad)}")

    print("== D. dead-stretch scan (chaos >= 0.85 sections) ==")
    sec_peak = {}
    for f in range(len(D)):
        s = f // FPS
        sec_peak[s] = max(sec_peak.get(s, 0.0), float(D[f]))
    d_bad = []
    for (a, b, chaos) in SECTIONS:
        if chaos < 0.85:
            continue
        run = 0
        for s in range(a, min(b, 381)):
            if sec_peak.get(s, 0.0) < 2 * med:
                run += 1
                if run >= 3:
                    d_bad.append((a, s - 2, s))
                    run = 0
            else:
                run = 0
    for (sec, s0, s1) in d_bad:
        print(f"  DEAD stretch in section @{sec}s: seconds {s0}-{s1}")
    print(f"  dead stretches: {len(d_bad)}")

    print("== SUMMARY ==")
    print(json.dumps({
        "frames": int(n), "duration_s": round(n / FPS, 2),
        "boundary_fail": a_fail, "boundary_offsets": a_offsets,
        "onsets_checked": len(onsets), "onset_miss_count": len(b_miss),
        "spike_clusters": len(clusters), "unexplained_spikes": c_bad,
        "dead_stretches": d_bad,
    }, indent=1))


if __name__ == "__main__":
    main()
