#!/usr/bin/env python3
"""Frame-precise S6 base for v2: identical to v1's sec06 except film frames
7311-7430 (the brown-haired character, source anime 5181-5300) replaced by
GitS nature source frames 2790-2909 (@93s+4s, non-vocal cutaway).
Local frame k (0..1109) <-> film 6630+k <-> anime source 4500+k.
Char1 NOT shifted (measurement: no clean offset). Char2 untouched.
"""
import os
import subprocess

import numpy as np

W, H, FPS = 848, 464, 30
FSZ = W * H * 3
BASE = os.environ.get("MUSIC_VIDEO_WORK_ROOT", ".") + "/"
ANIME = BASE + "sources/anime-2026-09-29.mp4"
NATURE = BASE + "sources/gits-nature-datamosh-01.mp4"
OUT = BASE + "work_super_v2/sec14.mp4"
VF = f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"

def stream(path):
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-vf", VF,
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE)

def read_frame(proc):
    buf = proc.stdout.read(FSZ)
    return buf if len(buf) == FSZ else None

enc = subprocess.Popen(
    ["ffmpeg", "-nostdin", "-v", "error", "-y",
     "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
     "-r", str(FPS), "-i", "-",
     "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
     "-pix_fmt", "yuv420p", "-an", OUT],
    stdin=subprocess.PIPE)

pa = stream(ANIME)
pn = stream(NATURE)
nat_idx = -1
n_written = 0
for k in range(1110):
    src_frame_no = 4500 + k
    # advance anime stream to src_frame_no
    while True:
        buf = read_frame(pa)
        assert buf is not None, f"anime EOF at {src_frame_no}"
        # count: we read sequentially; track via closure variable
        cur = read_frame.counter = getattr(read_frame, "counter", -1) + 1
        if cur == src_frame_no:
            anime_buf = buf
            break
    if 681 <= k <= 800:
        target = 2790 + (k - 681)
        while nat_idx < target:
            nbuf = read_frame(pn)
            assert nbuf is not None, "nature EOF"
            nat_idx += 1
        enc.stdin.write(nbuf)
    else:
        enc.stdin.write(anime_buf)
    n_written += 1
enc.stdin.close()
enc.wait()
pa.kill(); pn.kill()
print("wrote", n_written, "frames ->", OUT)
