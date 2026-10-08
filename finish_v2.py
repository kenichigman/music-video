#!/usr/bin/env python3
"""Supercut v2 finishing pass: smoothness + color cohesion.

Input: the approved v1 cut (hard cuts, EDL timing, mosh — untouched).
Does NOT re-run the mosh. Post-process only:

1. Per-section color normalization (gentle, dynamics-preserving):
   - gray-world white balance at 50% strength (pulls casts together,
     keeps each section's character)
   - luma mean/std pulled 50% toward the global median (compresses the
     daylight-vs-near-black jumps, keeps the arc's ordering)
2. Smoothness: 0.5s smoothstep dissolves centered on the 8 hard cuts.
   Duration-preserving (the blend re-renders the overlap region in place;
   total frames unchanged, EDL/audio alignment intact).
3. Global motif grade (subtle, applied to everything): gentle S-curve,
   teal shadows / warm highlights split-tone, slight saturation lift.

Usage: python3 finish_v2.py --in supercut_v1.mp4 \
           --audio track.mp3 \
           --out supercut_v2.mp4
"""
import argparse
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mosaic as M  # noqa: E402
from render import FFMPEG  # noqa: E402

FPS = 30
W, H = 848, 464
BOUNDS = [(0, 9), (9, 23), (23, 33), (33, 49), (49, 63),
          (63, 78), (78, 90), (90, 100), (100, 102)]
CUTS = [9, 23, 33, 49, 63, 78, 90, 100]
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


def build_grade(secs):
    """Per-section WB gains + luma remap params, all at 50% strength."""
    lms = np.array([s['lm'] for s in secs])
    lvs = np.array([s['lv'] for s in secs])
    g_lm, g_ls = float(np.median(lms)), float(np.sqrt(np.median(lvs)))
    print(f"  global luma target: {g_lm:.1f} +/- {g_ls:.1f}", flush=True)
    per = []
    for i, s in enumerate(secs):
        mean = s['mean']
        lum = float(mean.mean())
        gains = np.array([lum / max(mean[c], 1.0) for c in range(3)])
        gains = np.clip(1.0 + 0.5 * (gains - 1.0), 0.7, 1.4)
        # luma: pure gain only (b=0), clamped. An additive lift would
        # multiply near-black chroma by 10x+ and explode into blocks.
        # Blacks stay black; only contrast breathes, mildly.
        s_ls = np.sqrt(max(s['lv'], 1.0))
        a = np.clip(0.5 + 0.5 * (g_ls / max(s_ls, 1e-6)), 0.8, 1.25)
        b = 0.0
        per.append({'gains': gains, 'a': a, 'b': b})
        print(f"  sec{i}: wb=({gains[0]:.3f},{gains[1]:.3f},{gains[2]:.3f}) "
              f"luma_gain a={a:.3f}", flush=True)
    return per


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
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    print("== section stats ==", flush=True)
    secs, n_frames = compute_stats(args.inp)
    print(f"  {n_frames} frames", flush=True)

    print("== per-section grade ==", flush=True)
    per = build_grade(secs)

    K = DISSOLVE
    blend = {}  # out_pos -> (a_idx, b_idx, alpha)
    for c in CUTS:
        m = int(c * FPS)
        for j in range(K):
            pos = m - K // 2 + j
            blend[pos] = (m - K + j, m + j, smoothstep(j / (K - 1)))
    # A-inputs overlap already-emitted passthrough frames: pin them.
    # (b_idx >= m > a_idx always, so only a_idx can collide.)
    keep_a = {a for (a, _b, _al) in blend.values()}

    def need_upto(pos):
        # highest input frame index required to emit out_pos
        if pos in blend:
            return blend[pos][1]
        return pos

    print("== process + encode ==", flush=True)
    tmp = args.out + ".graded.mp4"
    cmd = [FFMPEG, "-v", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-preset", "medium", "-crf", "17", tmp]
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
                        # b is itself a future blend output; blend outputs
                        # never read graded[pos], so free it now
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
        # drain (no more zones pending past the last cut +K)
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
    print(f"  wrote {out_n}/{n_frames} frames -> {tmp}", flush=True)
    assert out_n == n_frames, f"frame count mismatch {out_n} != {n_frames}"

    print("== mux audio ==", flush=True)
    subprocess.run(
        [FFMPEG, "-v", "error", "-y", "-i", tmp, "-i", args.audio,
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-map", "0:v:0", "-map", "1:a:0", "-shortest", args.out],
        check=True)
    os.unlink(tmp)
    print(f"  final: {args.out}", flush=True)


if __name__ == "__main__":
    main()
