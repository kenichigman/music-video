#!/usr/bin/env python3
"""Home Computer v3 finishing pass (mirrors finish_hc_v2.py exactly).

Same grammar as v1/v2 finish: per-section gray-world WB (50%) + clamped
gain-only luma, params FORCED VERBATIM from the v2 manifest (identical to
v1's -- v2 carried them over), 0.5s smoothstep dissolves centered on the
9 section cuts, global motif grade (soft S-curve, teal shadows / warm
highlights, saturation x1.06).

Difference from finish_hc_v2.py: VIDEO ONLY out. The caller muxes the
audio by stream-copy from the v2 master, so the v3 audio stream is
bit-identical to v2's (the brief: audio untouched from v2).

Usage: python3 finish_hc_v3.py --in work_super_v3/moshed.h264 \
           --out work_v3/finished_v3.mp4
Run with the pipeline modules importable (the repo root, this
file's parent directory, is added to sys.path below).
"""
import argparse
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import mosaic as M  # noqa: E402
from render import FFMPEG  # noqa: E402

FPS = 30
W, H = 848, 464
BOUNDS = [(0, 6), (6, 30), (30, 94), (94, 113), (113, 142),
          (142, 221), (221, 258), (258, 323), (323, 370), (370, 381)]
CUTS = [6, 30, 94, 113, 142, 221, 258, 323, 370]
DISSOLVE = 15  # frames = 0.5s, centered on each cut


def section_of(t):
    for i, (a, b) in enumerate(BOUNDS):
        if a <= t < b or (i == len(BOUNDS) - 1 and t >= a):
            return i
    return len(BOUNDS) - 1


def compute_stats(path):
    stats = [{'n': 0, 'sum': np.zeros(3), 'lsum': 0.0, 'lsumsq': 0.0}
             for _ in BOUNDS]
    n = 0
    for frame in M.decode_rawvideo(path, W, H):
        si = section_of(n / FPS)
        f = frame.astype(np.float64).reshape(-1, 3)
        lum = 0.299 * f[:, 0] + 0.587 * f[:, 1] + 0.114 * f[:, 2]
        s = stats[si]
        s['n'] += 1
        s['sum'] += f.sum(0)
        s['lsum'] += lum.sum()
        s['lsumsq'] += (lum ** 2).sum()
        n += 1
    secs = []
    for s in stats:
        px = s['n'] * W * H
        lm = s['lsum'] / px
        secs.append({'mean': s['sum'] / px, 'lm': lm,
                     'lv': s['lsumsq'] / px - lm ** 2})
    return secs, n


def smoothstep(x):
    return x * x * (3 - 2 * x)


def apply_section_grade(frame_f, g):
    f = frame_f * g['gains'][None, None, :]
    lum = 0.299 * f[..., 0] + 0.587 * f[..., 1] + 0.114 * f[..., 2]
    lum_t = g['a'] * lum + g['b']
    scale = np.divide(lum_t, np.maximum(lum, 1e-3),
                      out=np.ones_like(lum_t), where=lum > 1e-3)
    return np.clip(f * scale[..., None], 0, 255)


def apply_global_grade(frame_f):
    x = frame_f / 255.0
    s = 0.10  # gentle S-curve
    x = x + s * (x - 0.5) * (1 - (2 * x - 1) ** 2)
    sh_w = (1 - x) ** 2   # shadow mask
    hi_w = x ** 2         # highlight mask
    x[..., 0] += 0.020 * hi_w[..., 0]   # warm highlights
    x[..., 1] += 0.022 * sh_w[..., 1]   # teal shadows
    x[..., 2] += 0.030 * sh_w[..., 2]
    x[..., 0] -= 0.012 * sh_w[..., 0]   # red out of shadows
    lum = (0.299 * x[..., 0] + 0.587 * x[..., 1] + 0.114 * x[..., 2])
    x = lum[..., None] + (x - lum[..., None]) * 1.06
    return np.clip(x * 255.0, 0, 255).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    print("== section stats (decode validation) ==", flush=True)
    secs, n_frames = compute_stats(args.inp)
    print(f"  {n_frames} frames", flush=True)
    for i, s in enumerate(secs):
        print(f"  sec{i}: luma mean {s['lm']:.1f}", flush=True)

    # v2 PATCH RULE carried forward: per-section finish params VERBATIM
    # from the v2 manifest (= v1's), so the v3 finish matches v1/v2's.
    V2 = [([0.901, 1.008, 1.15], 0.986), ([1.011, 1.035, 0.96], 1.053),
          ([0.974, 1.098, 0.951], 0.967), ([0.993, 1.004, 1.003], 0.938),
          ([1.013, 1.033, 0.96], 0.945), ([1.017, 0.998, 0.986], 1.05),
          ([0.947, 0.972, 1.108], 0.858), ([0.912, 1.013, 1.116], 1.079),
          ([0.953, 1.105, 0.967], 1.03), ([1.024, 1.013, 0.966], 1.015)]
    per = [{'gains': np.array(g), 'a': a, 'b': 0.0} for g, a in V2]
    print("  per-section grade = v2 manifest params (verbatim)", flush=True)

    K = DISSOLVE
    blend = {}  # out_pos -> (a_idx, b_idx, alpha)
    for c in CUTS:
        m = int(c * FPS)
        for j in range(K):
            pos = m - K // 2 + j
            blend[pos] = (m - K + j, m + j, smoothstep(j / (K - 1)))
    keep_a = {a for (a, _b, _al) in blend.values()}

    def need_upto(pos):
        if pos in blend:
            return blend[pos][1]
        return pos

    print("== process + encode (video only, crf17 medium) ==", flush=True)
    cmd = [FFMPEG, "-v", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-preset", "medium", "-crf", "17", args.out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    graded = {}
    decoded = 0
    out_n = 0
    try:
        for frame in M.decode_rawvideo(args.inp, W, H):
            n = decoded
            graded[n] = apply_section_grade(
                frame.astype(np.float64), per[section_of(n / FPS)])
            decoded += 1
            while out_n < decoded and need_upto(out_n) < decoded:
                if out_n in blend:
                    a, b, al = blend[out_n]
                    O = (1 - al) * graded[a] + al * graded[b]
                    del graded[a]
                    if b in blend:
                        del graded[b]
                else:
                    O = graded[out_n]
                    if out_n not in keep_a:
                        del graded[out_n]
                proc.stdin.write(apply_global_grade(O).tobytes())
                out_n += 1
            if decoded % 600 == 0:
                print(f"  frame {decoded}/{n_frames} "
                      f"(buf {len(graded)})", flush=True)
        while out_n < n_frames:
            assert need_upto(out_n) < decoded, f"stuck at {out_n}"
            if out_n in blend:
                a, b, al = blend[out_n]
                O = (1 - al) * graded[a] + al * graded[b]
                del graded[a]
                if b in blend:
                    del graded[b]
            else:
                O = graded[out_n]
                if out_n not in keep_a:
                    del graded[out_n]
            proc.stdin.write(apply_global_grade(O).tobytes())
            out_n += 1
    finally:
        try:
            proc.stdin.close()
        except BrokenPipeError:
            pass
        proc.wait()
    print(f"  wrote {out_n}/{n_frames} frames -> {args.out}", flush=True)
    assert out_n == n_frames, f"frame count mismatch {out_n} != {n_frames}"
    print("FINISH_OK", flush=True)


if __name__ == "__main__":
    main()
