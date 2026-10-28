#!/usr/bin/env python3
"""Frame-precise S6 row for Home Computer v3 (mirrors build_sec06.py).

Assembles the 221-258 section row (1110 frames) piece by piece from
plan_v3.json's s6.pieces: zone-A blend windows (anime clock + allocated
guests), the KEPT praised spans (anime frames 4952-5180), the KEPT v2
char-3 replacement (nature 2790-2909), the NEW Jin close-up replacement,
and the zone-C trio replacement. Every source is conformed with the same
VF chain as the row cuts; one encode (veryfast crf16) -> sec76.mp4.

Usage: python3 build_sec06_v3.py plan_v3.json OUTDIR/sec76.mp4
Run with CWD = the stage root.
"""
import json
import subprocess
import sys

import numpy as np

W, H, FPS = 848, 464, 30
FSZ = W * H * 3
SRCMAP = {
    "anime": "sources/anime-2026-09-29.mp4",
    "nature": "sources/gits-nature-datamosh-01.mp4",
    "october": "sources/october-dream-01.mp4",
    "store": "sources/conveniencestore-datamosh-01.mp4",
    "gits": "sources/gits-datamosh-01.mp4",
    "hands": "sources/bw-hands-datamosh-01.mp4",
}
VF = f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"


def stream_frames(path, first, last, pre=None):
    """Yield conformed rgb24 frames [first, last) of a source."""
    vf = (pre + ",") if pre else ""
    proc = subprocess.Popen(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-vf", vf + VF,
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE)
    idx = -1
    try:
        while idx < last - 1:
            buf = proc.stdout.read(FSZ)
            assert len(buf) == FSZ, f"{path}: EOF before frame {last}"
            idx += 1
            if idx >= first:
                yield buf
    finally:
        proc.kill()


def main():
    plan = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    pieces = plan["s6"]["pieces"]
    enc = subprocess.Popen(
        ["ffmpeg", "-nostdin", "-v", "error", "-y",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
         "-pix_fmt", "yuv420p", "-an", out],
        stdin=subprocess.PIPE)
    n = 0
    expect_film = 6630
    for p in pieces:
        f0, f1 = p["film"]
        assert f0 == expect_film, f"piece gap at {f0} != {expect_film}"
        expect_film = f1
        cnt = f1 - f0
        got = 0
        for buf in stream_frames(SRCMAP[p["src"]], p["src_frame"],
                                 p["src_frame"] + cnt, p.get("pre")):
            enc.stdin.write(buf)
            got += 1
        assert got == cnt, f"piece {p['note']}: {got} != {cnt}"
        n += cnt
        print(f"piece film {f0}-{f1} {p['src']}@{p['src_frame']} "
              f"({cnt} f) {p['note']}", flush=True)
    enc.stdin.close()
    enc.wait()
    assert n == 1110, f"wrote {n} != 1110"
    cnt = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-show_entries",
         "stream=nb_read_frames", "-of", "csv=p=0", out],
        capture_output=True, text=True).stdout.strip()
    assert int(cnt) == 1110, f"sec file has {cnt} frames"
    print(f"S6_OK wrote {n} frames -> {out}")


if __name__ == "__main__":
    main()
