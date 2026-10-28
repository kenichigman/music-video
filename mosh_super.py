#!/usr/bin/env python3
"""Super-collection datamosh cut: multiple source clips, hard cuts at every
conductor-section boundary, mosaic bridges on big in-section shifts,
audio-driven IDR-transplant mosh that melts each section from its own
opening frame (anchor resets at hard cuts, never smears across them).

Usage: python3 mosh_super.py --audio track.mp3 --edl edl.json
           --out out.mp4 [--workdir DIR] [--drop-thresh 0.55] [--max-gap 8]
"""
import argparse
import json
import math
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mosaic as M  # noqa: E402
from render import decode_audio, FFMPEG, FFPROBE  # noqa: E402
from datamosh import (spectral_drive, corrupt_stream,  # noqa: E402
                      finish, SR, WIN_SEC)

FPS = 30
W, H = 848, 464
KEYINT = 30            # 1s segments: EDL bounds (integer seconds) align
BRIDGE_HALF = 0.4
CUT_GUARD = 0.9       # no mosaic bridges this close to a hard cut

# (clip, offset_s, transpose) per EDL section [start, end)
PLAN = [
    # 0-9 intro, quiet: GitS nature, calm and legible
    ("sources/gits-nature-dm.mp4", 20, 0, 9, None),
    # 9-23 build: October dream cat
    ("sources/october-dream.mp4", 10, 9, 23, None),
    # 23-33 verse: convenience store
    ("sources/conveniencestore-dm.mp4", 30, 23, 33, None),
    # 33-49 lift, peak chaos: anime, fresh offset
    ("sources/anime.mp4", 120, 33, 49, None),
    # 49-63 drop: GitS
    ("sources/gits-dm.mp4", 5, 49, 63, None),
    # 63-78 breakdown, dense vox: B&W hands, rotated to landscape
    #   (rotate hand footage to match the other clips)
    ("sources/bw-hands-dm.mp4", 8, 63, 78, "transpose=1"),
    # 78-90 lift: GitS nature, new offset
    ("sources/gits-nature-dm.mp4", 100, 78, 90, None),
    # 90-100 hot outro: convenience store, new offset
    ("sources/conveniencestore-dm.mp4", 120, 90, 100, None),
    # 100-102 collapse tail: GitS, snap clear
    ("sources/gits-dm.mp4", 30, 100, 102, None),
]

# resolved at runtime against --srcmap (logical name -> real file)
SRCMAP = {
    "sources/anime.mp4": "sources/anime-2026-09-29.mp4",
    "sources/gits-nature-dm.mp4": "sources/gits-nature-datamosh-01.mp4",
    "sources/october-dream.mp4": "sources/october-dream-01.mp4",
    "sources/conveniencestore-dm.mp4":
        "sources/conveniencestore-datamosh-01.mp4",
    "sources/gits-dm.mp4": "sources/gits-datamosh-01.mp4",
    "sources/bw-hands-dm.mp4": "sources/bw-hands-datamosh-01.mp4",
}


def cut_sections(workdir):
    """Cut+conform each planned section. Returns (paths, bounds)."""
    os.makedirs(workdir, exist_ok=True)
    paths, bounds = [], []
    for i, (clip, ss, start, end, pre) in enumerate(PLAN):
        src = SRCMAP[clip]
        dur = end - start
        out = os.path.join(workdir, f"sec{i:02d}.mp4")
        if not os.path.exists(out):
            vf = []
            if pre:
                vf.append(pre)
            vf += [f"fps={FPS}", f"scale={W}:{H}:force_original_aspect_ratio=increase",
                   f"crop={W}:{H}"]
            subprocess.run(
                [FFMPEG, "-v", "error", "-y", "-ss", str(ss), "-i", src,
                 "-t", str(dur), "-vf", ",".join(vf),
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
                 "-pix_fmt", "yuv420p", "-an", out], check=True)
        paths.append(out)
        bounds.append((start, end))
        print(f"  sec{i}: {os.path.basename(src)} [{ss}s+{dur}s] -> {start}-{end}s",
              flush=True)
    return paths, bounds


def concat_timeline(paths, workdir):
    out = os.path.join(workdir, "timeline.mp4")
    if os.path.exists(out):
        return out
    lst = os.path.join(workdir, "concat.txt")
    with open(lst, "w") as fh:
        for p in paths:
            fh.write(f"file '{os.path.abspath(p)}'\n")
    subprocess.run(
        [FFMPEG, "-v", "error", "-y", "-f", "concat", "-safe", "0",
         "-i", lst, "-c", "copy", out], check=True)
    return out


def find_shifts(timeline, bounds):
    """Big shifts, excluding guard zones around hard cuts."""
    cuts_at = {b[0] for b in bounds} | {b[1] for b in bounds}
    prev, diffs = None, []
    for frame in M.decode_rawvideo(timeline, W, H):
        small = frame[::4, ::4].astype(np.float32)
        if prev is not None:
            diffs.append(float(np.abs(small - prev).mean()))
        prev = small
    diffs = np.array(diffs)
    total = len(diffs) / FPS
    thresh = float(np.percentile(diffs, 98))
    cuts, i = [], 1
    while i < len(diffs) - 1:
        if (diffs[i] > thresh and diffs[i] >= diffs[i - 1]
                and diffs[i] >= diffs[i + 1]):
            t = i / FPS
            near_hard = any(abs(t - c) < CUT_GUARD for c in cuts_at)
            if (1.0 < t < total - 1.0 and not near_hard
                    and (not cuts or t - cuts[-1] >= 2.0)):
                cuts.append(t)
            i += int(2.0 * FPS)
        else:
            i += 1
    print(f"  shifts: {len(cuts)} at " +
          ", ".join(f"{c:.1f}s" for c in cuts[:16]), flush=True)
    return cuts


def bridge_wet(t, cuts):
    if not cuts:
        return 0.0
    d = min(abs(t - c) for c in cuts)
    return max(0.0, 1.0 - d / BRIDGE_HALF)


def mosaic_frame(frame, tiles_f, lib_means):
    small = frame.reshape(M.ROWS, M.TILE, M.COLS, M.TILE, 3).mean(axis=(1, 3))
    idx = M.nearest_tiles(small.reshape(-1, 3), lib_means)
    canvas = tiles_f[idx].reshape(M.ROWS, M.COLS, M.TILE, M.TILE, 3)
    return canvas.transpose(0, 2, 1, 3, 4).reshape(M.H, M.W, 3)


def encode_bridged(timeline, cuts, tiles_f, lib_means, workdir):
    base = os.path.join(workdir, "base.h264")
    cmd = [FFMPEG, "-v", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-preset", "medium", "-crf", "16",
           "-g", str(KEYINT),
           "-x264-params",
           f"keyint={KEYINT}:min-keyint={KEYINT}:scenecut=0:"
           "bframes=0:weightp=0",
           base]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = 0
    try:
        for frame in M.decode_rawvideo(timeline, W, H):
            t = n / FPS
            wet = bridge_wet(t, cuts)
            if wet > 0:
                mos = mosaic_frame(frame, tiles_f, lib_means)
                out = mos * wet + frame.astype(np.float32) * (1.0 - wet)
                out = np.clip(out, 0, 255).astype(np.uint8)
            else:
                out = frame
            proc.stdin.write(out.tobytes())
            n += 1
            if n % 600 == 0:
                print(f"  bridged frame {n} ({t:.1f}s)", flush=True)
    finally:
        try:
            proc.stdin.close()
        except BrokenPipeError:
            pass
        proc.wait()
    print(f"  base encode done: {n} frames -> {base}", flush=True)
    return base, n


def edl_thresholds(edl_path, drive, drop_thresh):
    edl = json.load(open(edl_path))
    n_sec = int(math.ceil(len(drive) * WIN_SEC))
    chaos = np.ones(n_sec)
    for s in edl["sections"]:
        chaos[s["start_s"]:s["end_s"]] = s["chaos_scale"]
    thresh = np.empty(len(drive))
    for w in range(len(drive)):
        sec = min(int(w * WIN_SEC), n_sec - 1)
        thresh[w] = float(np.clip(drop_thresh / chaos[sec], 0.15, 0.95))
    print(f"  EDL thresholds: {thresh.min():.2f}..{thresh.max():.2f}",
          flush=True)
    return thresh


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--edl", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workdir", default="work_super")
    ap.add_argument("--drop-thresh", type=float, default=0.55)
    ap.add_argument("--max-gap", type=float, default=8.0)
    args = ap.parse_args()
    os.makedirs(args.workdir, exist_ok=True)

    print("== sections ==", flush=True)
    paths, bounds = cut_sections(args.workdir)
    hard_cuts = sorted({b[0] for b in bounds})
    print(f"  hard cuts at: {hard_cuts}", flush=True)

    print("== timeline ==", flush=True)
    timeline = concat_timeline(paths, args.workdir)

    print("== shifts ==", flush=True)
    cuts = find_shifts(timeline, bounds)

    print("== tile library (whole collection) ==", flush=True)
    M.COLS, M.ROWS, M.TILE = 53, 29, 16
    M.W, M.H = W, H
    rng = np.random.default_rng(8000)
    tiles, lib_means = M.build_library([timeline], rng)
    tiles_f = tiles.astype(np.float32)

    print("== bridge composite + long-GOP encode ==", flush=True)
    base, n_frames = encode_bridged(timeline, cuts, tiles_f, lib_means,
                                    args.workdir)

    print("== audio drive ==", flush=True)
    samples = decode_audio(args.audio)
    drive = spectral_drive(samples)
    print(f"  drive: {len(drive)} windows, "
          f"{drive.min():.3f}..{drive.max():.3f}", flush=True)
    thresh_win = edl_thresholds(args.edl, drive, args.drop_thresh)

    print("== NAL surgery (anchors reset at hard cuts) ==", flush=True)
    moshed = os.path.join(args.workdir, "moshed.h264")
    corrupt_stream(base, moshed, drive, FPS, n_frames,
                   args.drop_thresh, args.max_gap,
                   thresh_win=thresh_win, reset_times=hard_cuts)

    print("== finish ==", flush=True)
    finish(moshed, args.audio, args.out)


if __name__ == "__main__":
    main()
