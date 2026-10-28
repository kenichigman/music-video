#!/usr/bin/env python3
"""Prove the exact frame spans of mkvmerge split parts vs v3 (framemd5)."""
import os
import subprocess
import sys

FF = "ffmpeg"
ROOT = os.environ.get("MUSIC_VIDEO_WORK_ROOT", ".")
W4 = ROOT + "/work_v4"
V3 = ROOT + "/work_v3/song-six_supercut_v3.mp4"


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


def main():
    h3 = framemd5(V3)
    print(f"v3 frames: {len(h3)}", flush=True)
    with open(W4 + "/v3_framemd5.txt", "w") as fh:
        fh.write("\n".join(h3))
    pos = {}
    for i, h in enumerate(h3):
        pos.setdefault(h, []).append(i)
    for part in sys.argv[1:]:
        hp = framemd5(part)
        # locate hp[0] in v3
        starts = pos.get(hp[0], [])
        span = None
        for s in starts:
            if h3[s:s + len(hp)] == hp:
                span = (s, s + len(hp) - 1)
                break
        print(f"{part}: {len(hp)} frames, span in v3 = {span}",
              flush=True)


if __name__ == "__main__":
    main()
