#!/usr/bin/env python3
"""Segmented driver around render.py (the house renderer, unmodified).

render.py's analysis is stateful across the whole track (rolling-max band
normalization, track-peak energy), so segments rendered independently from
raw audio would not match. This driver runs analyze() ONCE on the full
track and shares the arrays; each segment then renders a frame range with
a preroll (frames rendered but discarded) so the trail-feedback state in
Renderer.prev settles before the segment's first kept frame — same seam
treatment as a continuous run, minus a few frames of trail history.

Usage:
  chunk_render.py analyze --audio track.wav --npz arrays.npz [--fps 30]
  chunk_render.py segment --npz arrays.npz --start 1153 --frames 1153 \
      --out seg1.mp4 [--preroll 60] [--width 1280] [--height 720] \
      [--fps 30] [--palette glitch]
"""
import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

import render as R


def do_analyze(audio, npz, fps):
    samples = R.decode_audio(audio)
    bands, energy, flash, dur = R.analyze(samples, fps)
    np.savez_compressed(npz, bands=bands, energy=energy, flash=flash)
    print(f"analyze: {dur:.2f}s -> {len(bands)} frames @ {fps}fps -> {npz}",
          flush=True)


def do_segment(npz, start, count, out, preroll, width, height, fps, palette):
    d = np.load(npz)
    bands, energy, flash = d["bands"], d["energy"], d["flash"]
    total = len(bands)
    end = min(total, start + count)
    pre = max(0, start - preroll)
    enc = [R.FFMPEG, "-v", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
           "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-crf", "18", "-preset", "medium", out]
    proc = subprocess.Popen(enc, stdin=subprocess.PIPE)
    rnd = R.Renderer(width, height, fps, palette_name=palette)
    t0 = time.time()
    kept = 0
    for f in range(pre, end):
        frame = rnd.frame(bands[f], float(energy[f]), float(flash[f]), f / fps)
        if f >= start:
            proc.stdin.write(frame.tobytes())
            kept += 1
    proc.stdin.close()
    proc.wait()
    dt = time.time() - t0
    print(f"segment start={start} kept={kept} frames in {dt:.1f}s "
          f"({kept / dt:.1f} fps kept-rate) -> {out}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pa = sub.add_parser("analyze")
    pa.add_argument("--audio", required=True)
    pa.add_argument("--npz", required=True)
    pa.add_argument("--fps", type=int, default=30)
    ps = sub.add_parser("segment")
    ps.add_argument("--npz", required=True)
    ps.add_argument("--start", type=int, required=True)
    ps.add_argument("--frames", type=int, required=True)
    ps.add_argument("--out", required=True)
    ps.add_argument("--preroll", type=int, default=60)
    ps.add_argument("--width", type=int, default=1280)
    ps.add_argument("--height", type=int, default=720)
    ps.add_argument("--fps", type=int, default=30)
    ps.add_argument("--palette", default="glitch")
    a = ap.parse_args()
    if a.cmd == "analyze":
        do_analyze(a.audio, a.npz, a.fps)
    else:
        do_segment(a.npz, a.start, a.frames, a.out, a.preroll,
                   a.width, a.height, a.fps, a.palette)


if __name__ == "__main__":
    main()
