#!/usr/bin/env python3
"""Datamosh-led music video: source footage, mosaic bridges on big shifts.

Pipeline (datamoshing leads, mosaic on big
frame shifts, datamoshing smooths it out):
  1. Cut a 102s section from the source footage; conform to 30fps and the
     848x464 tile grid.
  2. Detect big frame shifts (ffprobe scene detection).
  3. Composite mosaic bridges (~0.8s triangular wet) at each shift, tiles
     sampled from the footage itself (self-devouring, per motif). Pipe
     rawvideo straight into a long-GOP x264 encode (keyint 600, no
     scenecut, no B-frames).
  4. Audio-driven IDR-transplant datamosh (datamosh.py machinery). Drive
     from the track's spectral features; per-0.5s mosh threshold modulated
     by the conductor EDL's chaos_scale (the EDL is the dynamics envelope,
     the waveform drives the frames).
  5. Decode, re-encode CRF 18, mux the track.

Usage: python3 mosh_footage.py --footage clip.mp4 --audio track.mp3
           --edl edl.json --out out.mp4 [--ss SEC] [--workdir DIR]
           [--drop-thresh 0.55] [--max-gap 60]
"""
import argparse
import json
import math
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mosaic as M  # noqa: E402  (tile machinery + FFMPEG/FFPROBE)
from render import decode_audio, FFMPEG, FFPROBE  # noqa: E402
from datamosh import (spectral_drive, split_nals, corrupt_stream,  # noqa: E402
                      finish, SR, WIN_SEC)

FPS = 30
W, H = 848, 464          # 53x29 tiles of 16px
SEC_LEN = 102  # default; override with --dur
BRIDGE_HALF = 0.4        # seconds each side of a cut


def cut_section(footage, ss, workdir, dur):
    out = os.path.join(workdir, "section.mp4")
    if os.path.exists(out):
        return out
    subprocess.run(
        [FFMPEG, "-v", "error", "-y", "-ss", str(ss), "-i", footage,
         "-t", str(dur), "-vf", f"fps={FPS},crop={W}:{H}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
         "-pix_fmt", "yuv420p", "-an", out], check=True)
    return out


def find_shifts(section):
    """Big frame shifts via mean-absolute frame difference at 30fps.

    Deterministic, no lavfi quoting games: decode small, diff consecutive
    frames, take local maxima above the 98th percentile with >=2s
    separation. Only the big shifts get mosaic bridges.
    """
    sw, sh = 212, 116
    prev = None
    diffs = []
    for frame in M.decode_rawvideo(section, W, H):
        small = frame[::4, ::4].astype(np.float32)
        if prev is not None:
            diffs.append(float(np.abs(small - prev).mean()))
        prev = small
    diffs = np.array(diffs)
    thresh = float(np.percentile(diffs, 98))
    cuts = []
    i = 1
    while i < len(diffs) - 1:
        if (diffs[i] > thresh and diffs[i] >= diffs[i - 1]
                and diffs[i] >= diffs[i + 1]):
            t = i / FPS
            if 1.0 < t < SEC_LEN - 1.0 and (
                    not cuts or t - cuts[-1] >= 2.0):
                cuts.append(t)
            i += int(2.0 * FPS)  # min separation
        else:
            i += 1
    print(f"  shifts: {len(cuts)} at " +
          ", ".join(f"{c:.1f}s" for c in cuts[:12]), flush=True)
    return cuts


def build_bridge(section, workdir):
    """Tile library from the section's own frames (self-devouring)."""
    M.COLS, M.ROWS, M.TILE = 53, 29, 16
    M.W, M.H = W, H
    rng = np.random.default_rng(8000)
    tiles, lib_means = M.build_library([section], rng)
    return tiles.astype(np.float32), lib_means, rng


def bridge_wet(t, cuts):
    if not cuts:
        return 0.0
    d = min(abs(t - c) for c in cuts)
    return max(0.0, 1.0 - d / BRIDGE_HALF)


def mosaic_frame(frame, tiles_f, lib_means, rng):
    small = frame.reshape(M.ROWS, M.TILE, M.COLS, M.TILE, 3).mean(axis=(1, 3))
    idx = M.nearest_tiles(small.reshape(-1, 3), lib_means)
    canvas = tiles_f[idx].reshape(M.ROWS, M.COLS, M.TILE, M.TILE, 3)
    return canvas.transpose(0, 2, 1, 3, 4).reshape(M.H, M.W, 3)


def encode_bridged(section, cuts, tiles_f, lib_means, rng, workdir, keyint):
    """Composite mosaic bridges, pipe into long-GOP x264."""
    base = os.path.join(workdir, "base.h264")
    cmd = [FFMPEG, "-v", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-preset", "medium", "-crf", "16",
           "-g", str(keyint),
           "-x264-params",
           f"keyint={keyint}:min-keyint={keyint}:scenecut=0:"
           "bframes=0:weightp=0",
           base]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = 0
    try:
        for frame in M.decode_rawvideo(section, W, H):
            t = n / FPS
            wet = bridge_wet(t, cuts)
            if wet > 0:
                mos = mosaic_frame(frame, tiles_f, lib_means, rng)
                out = (mos * wet + frame.astype(np.float32)
                       * (1.0 - wet))
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
    """Per-0.5s mosh threshold from the conductor EDL's chaos_scale."""
    edl = json.load(open(edl_path))
    n_sec = int(math.ceil(len(drive) * WIN_SEC))
    chaos = np.ones(n_sec)
    for s in edl["sections"]:
        chaos[s["start_s"]:s["end_s"]] = s["chaos_scale"]
    n_win = len(drive)
    thresh = np.empty(n_win)
    for w in range(n_win):
        sec = min(int(w * WIN_SEC), n_sec - 1)
        thresh[w] = float(np.clip(drop_thresh / chaos[sec], 0.15, 0.95))
    print(f"  EDL thresholds: {thresh.min():.2f}..{thresh.max():.2f} "
          f"(base {drop_thresh})", flush=True)
    return thresh


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--footage", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--edl", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ss", type=float, default=0.0,
                    help="footage offset seconds for the section")
    ap.add_argument("--dur", type=float, default=102.0,
                    help="section length in seconds")
    ap.add_argument("--workdir", default="work_mosh")
    ap.add_argument("--drop-thresh", type=float, default=0.55)
    ap.add_argument("--max-gap", type=float, default=60.0)
    ap.add_argument("--keyint", type=int, default=150,
                    help="GOP length in frames; shorter = finer mosh granularity")
    args = ap.parse_args()
    global SEC_LEN
    SEC_LEN = args.dur
    os.makedirs(args.workdir, exist_ok=True)

    print("== section ==", flush=True)
    section = cut_section(args.footage, args.ss, args.workdir, args.dur)

    print("== shifts ==", flush=True)
    cuts = find_shifts(section)

    print("== tile library (self) ==", flush=True)
    tiles_f, lib_means, rng = build_bridge(section, args.workdir)

    print("== bridge composite + long-GOP encode ==", flush=True)
    base, n_frames = encode_bridged(section, cuts, tiles_f, lib_means,
                                    rng, args.workdir, args.keyint)

    print("== audio drive ==", flush=True)
    samples = decode_audio(args.audio)
    drive = spectral_drive(samples)
    print(f"  drive: {len(drive)} windows, "
          f"{drive.min():.3f}..{drive.max():.3f}", flush=True)
    thresh_win = edl_thresholds(args.edl, drive, args.drop_thresh)

    print("== NAL surgery ==", flush=True)
    moshed = os.path.join(args.workdir, "moshed.h264")
    corrupt_stream(base, moshed, drive, FPS, n_frames,
                   args.drop_thresh, args.max_gap, thresh_win=thresh_win)

    print("== finish ==", flush=True)
    finish(moshed, args.audio, args.out)


if __name__ == "__main__":
    main()
