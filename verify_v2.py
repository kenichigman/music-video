#!/usr/bin/env python3
"""Verify song-six_supercut_v2.mp4 against v1:
- full decode of v2, error-counted (separate ffmpeg pass in launcher)
- per-frame MD5 compare: frames outside the patch ranges MUST be
  bit-identical to v1; margin frames inside patches (v1-sourced) get a
  PSNR report; rebuilt frames are expected to differ.
"""
import hashlib
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mosaic as M  # noqa: E402

W, H = 848, 464
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V1 = os.path.join(ROOT, "work", "song-six_supercut_v1.mp4")
V2 = os.path.join(ROOT, "work", "song-six_supercut_v2.mp4")
PATCHES = [(0, 220), (3352, 4064)]
MARGINS = [(180, 220), (3352, 3360), (4050, 4064)]


def in_ranges(i, ranges):
    return any(a <= i < b for a, b in ranges)


def psnr(a, b):
    d = a.astype(np.float64) - b.astype(np.float64)
    mse = float(np.mean(d * d))
    return 99.0 if mse == 0 else 10 * np.log10(255.0 ** 2 / mse)


g1 = M.decode_rawvideo(V1, W, H)
g2 = M.decode_rawvideo(V2, W, H)
n = 0
bad_outside, diff_new = [], []
margin_psnr = []
while True:
    try:
        f1 = next(g1)
    except StopIteration:
        f1 = None
    try:
        f2 = next(g2)
    except StopIteration:
        f2 = None
    if f1 is None or f2 is None:
        assert f1 is None and f2 is None, "frame count mismatch at end"
        break
    i = n
    n += 1
    same = hashlib.md5(f1.tobytes()).digest() == \
        hashlib.md5(f2.tobytes()).digest()
    if in_ranges(i, PATCHES):
        if in_ranges(i, MARGINS):
            margin_psnr.append((i, psnr(f1, f2)))
        elif not same:
            diff_new.append(i)
    elif not same:
        bad_outside.append(i)
print(f"frames compared: {n}")
print(f"OUTSIDE patches differing (must be 0): {len(bad_outside)} "
      f"{bad_outside[:10]}")
print(f"rebuilt frames differing from v1: {len(diff_new)} "
      f"(expect 180 + 690 = 870 minus any coincidences)")
if margin_psnr:
    vals = [p for _i, p in margin_psnr]
    print(f"margin frames: {len(vals)}, PSNR min={min(vals):.1f} "
          f"mean={sum(vals) / len(vals):.1f} dB")
