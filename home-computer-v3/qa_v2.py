#!/usr/bin/env python3
"""Phase check for home-computer_supercut_v1 (own implementation of the
delivery gate): per-frame video diff energy vs audio onset envelope,
sequential decode.

Checks:
 A. Every section boundary has a video accent within +/-0.25s.
 B. Major in-section audio onsets (flux >= p90, >=2s apart, not near a
    boundary) have a video accent within +/-0.25s.
 C. No unexplained video-diff spikes (clusters >= p98.5 not within
    +/-0.35s of a boundary, a bridged timeline shift, or a moshed
    segment start).
"""
import json
import os
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from render import decode_audio, FFMPEG  # noqa: E402

WORK_ROOT = os.environ.get("MUSIC_VIDEO_WORK_ROOT", ".")
FILM = os.path.join(WORK_ROOT, "work_v2/home-computer_supercut_v2.mp4")
TIMELINE = os.path.join(WORK_ROOT, "work_super_v2/timeline.mp4")
AUDIO = os.path.join(WORK_ROOT, "audio/home-computer_CLEAN.mp3")
MOSHLOG = os.path.join(WORK_ROOT, "work_v2/mosh_v2.log")
FPS = 30
CUTS = [6, 30, 94, 113, 142, 221, 258, 323, 370]
ROTCUTS = [50, 66, 78, 91, 160, 176, 192, 204, 243.7, 247.7, 276, 293, 310, 322]  # declared v2 rotation/replacement cuts (manifest)
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
    # find_shifts works at 30fps on quarter-res; here frames are 30fps
    # already at small size: same 98th-percentile peak method.
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


def moshed_starts():
    starts = []
    pat = re.compile(r"seg\s+(\d+):\s+t=\s*([\d.]+)s\s+drive=[\d.]+\s+MOSH")
    for line in open(MOSHLOG):
        m = pat.search(line)
        if m:
            starts.append(float(m.group(2)))
    return starts


def main():
    print("== decode film (sequential) ==", flush=True)
    frames = decode_gray(FILM, W2, H2)
    n = len(frames)
    print(f"  frames: {n} ({n / FPS:.2f}s)")
    D = frame_diffs(frames)  # D[f] = diff between frame f and f+1
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
        """Peak diff within +/-halfwin s of t; returns (peak, offset)."""
        c = int(round(t * FPS))
        lo = max(0, c - int(halfwin * FPS))
        hi = min(len(D), c + int(halfwin * FPS) + 1)
        if hi <= lo:
            return 0.0, None
        j = lo + int(np.argmax(D[lo:hi]))
        return float(D[j]), (j - c) / FPS

    print("== A. boundary accents (+/-0.25s) ==")
    a_fail = []
    for c in CUTS:
        peak, off = accent_near(c)
        ok = peak >= 4 * med and off is not None and abs(off) <= 0.25
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
        print(f"  onset {t:6.1f}s flux {fv:.2f}: video peak {peak:6.2f} "
              f"offset {off if off is None else round(off, 2)} "
              f"-> {'OK' if ok else 'MISS'}")
        if not ok:
            b_miss.append(t)

    print("== C. unexplained spikes ==")
    shifts = timeline_shifts()
    mstarts = moshed_starts()
    print(f"  timeline shifts: {len(shifts)}, moshed segments: {len(mstarts)}")
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
            any(abs(t - c) <= 0.35 for c in ROTCUTS) or \
            any(abs(t - s) <= 0.35 for s in shifts) or \
            any(abs(t - s) <= 0.35 for s in mstarts)

    c_bad = []
    for cl in clusters:
        t0 = cl[0]
        if not explained(t0):
            c_bad.append(t0)
            print(f"  UNEXPLAINED spike cluster at {t0:.1f}s "
                  f"(peak {float(D[int(t0 * FPS)]):.1f})")
    print(f"  spike clusters: {len(clusters)}, unexplained: {len(c_bad)}")

    print("== SUMMARY ==")
    print(json.dumps({
        "frames": int(n), "duration_s": round(n / FPS, 2),
        "boundary_fail": a_fail,
        "onsets_checked": len(onsets), "onset_miss": b_miss,
        "spike_clusters": len(clusters), "unexplained_spikes": c_bad,
    }, indent=1))


if __name__ == "__main__":
    main()
