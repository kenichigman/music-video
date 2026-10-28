#!/usr/bin/env python3
"""Verify v4 vs v3: frame count, decoded-frame MD5 identity outside
the patch span [3570, 4875), audio identity, -xerror decode pass, and
probe-frame extraction (sequential decode) at the re-phased onsets."""
import os
import subprocess
import sys

import numpy as np

ROOT = os.environ.get("MUSIC_VIDEO_WORK_ROOT", ".")
W4 = ROOT + "/work_v4"
V3 = ROOT + "/work_v3/song-six_supercut_v3.mp4"
V4 = W4 + "/song-six_supercut_v4.mp4"
FF = "ffmpeg"
W, H = 848, 464
P0, P1 = 3570, 4875


def framemd5(path):
    cmd = [FF, "-v", "error", "-i", path, "-map", "0:v:0",
           "-f", "framemd5", "-"]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    hashes = []
    for line in out.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = [p.strip() for p in line.split(",")]
        hashes.append(parts[-1])
    return hashes


def audiomd5(path):
    cmd = [FF, "-v", "error", "-i", path, "-map", "0:a:0",
           "-f", "md5", "-"]
    return subprocess.run(cmd, capture_output=True,
                          text=True).stdout.strip()


h3 = [l.strip() for l in open(W4 + "/v3_framemd5.txt") if l.strip()]
h4 = framemd5(V4)
print(f"frames: v3={len(h3)} v4={len(h4)}", flush=True)
assert len(h4) == 6840, "v4 frame count wrong"
diff_out = [i for i in range(6840)
            if not (P0 <= i < P1) and h4[i] != h3[i]]
diff_in = sum(1 for i in range(P0, P1) if h4[i] != h3[i])
print(f"identity outside [{P0},{P1}): "
      f"{'OK — 0 diffs' if not diff_out else 'FAIL ' + str(diff_out[:10])}")
print(f"frames changed inside patch: {diff_in}/{P1 - P0}")
print(f"head spot [0,3570) identical: "
      f"{all(h4[i] == h3[i] for i in range(0, 3570))}")
print(f"tail spot [4890,6840) identical: "
      f"{all(h4[i] == h3[i] for i in range(4890, 6840))}")
a3, a4 = audiomd5(V3), audiomd5(V4)
print(f"audio md5 equal: {a3 == a4} ({a4})")

r = subprocess.run([FF, "-v", "error", "-xerror", "-i", V4,
                    "-f", "null", "-"], capture_output=True, text=True)
print(f"decode -xerror: rc={r.returncode} stderr_len={len(r.stderr)}")

# probe frames at the onsets (sequential decode, no seeking)
want = {3582: "f119.4", 3600: "f120.0", 3900: "f130.0",
        4176: "f139.2", 4542: "f151.4", 4821: "f160.7"}
cmd = [FF, "-v", "error", "-i", V4, "-f", "rawvideo",
       "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-"]
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
fb = W * H * 3
n = 0
from PIL import Image
while True:
    raw = proc.stdout.read(fb)
    if len(raw) < fb:
        break
    if n in want:
        fr = np.frombuffer(raw, dtype=np.uint8).reshape(H, W, 3)
        Image.fromarray(fr).save(f"{W4}/probes_{want[n]}.png")
        print(f"  probe saved: {want[n]} (frame {n})", flush=True)
    n += 1
proc.wait()
print(f"probe decode frames: {n}")
print("VERIFY_DONE")
