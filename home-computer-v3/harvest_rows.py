#!/usr/bin/env python3
"""Worker segment harvester for Home Computer v3 (mirrors harvest.py).

Decodes the finished film once, encodes the requested 1s segments with
the segment contract (libx264 medium crf16, -g 30, keyint_min 30,
sc_threshold 0, yuv420p) into OUTDIR, asserts frame counts (30 per
segment; the last segment takes the remainder), and writes a JSON
fragment {index: {file, frames, sha256}}.

Usage: python3 harvest_rows.py FINISHED.mp4 OUTDIR frag.json A B
       (segments A..B-1)
"""
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import mosaic as M  # noqa: E402

W, H, FPS = 848, 464, 30
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "16",
       "-g", "30", "-keyint_min", "30", "-sc_threshold", "0",
       "-pix_fmt", "yuv420p", "-an"]


def seg_count(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-show_entries",
         "stream=nb_read_frames", "-of", "csv=p=0", path],
        capture_output=True, text=True).stdout.strip()
    return int(out)


def main():
    fin, outdir, frag_path = sys.argv[1], sys.argv[2], sys.argv[3]
    a, b = int(sys.argv[4]), int(sys.argv[5])
    os.makedirs(outdir, exist_ok=True)
    want = set(range(a, b))
    frag = {}
    enc = None
    cur = None
    n = 0
    total = 0
    for frame in M.decode_rawvideo(fin, W, H):
        total += 1
        s = n // FPS
        if s != cur:
            if enc is not None:
                enc.stdin.close(); enc.wait()
                enc = None
            cur = s
            if s in want:
                p = os.path.join(outdir, f"seg_{s:04d}.mp4")
                enc = subprocess.Popen(
                    ["ffmpeg", "-nostdin", "-v", "error", "-y",
                     "-f", "rawvideo", "-pix_fmt", "rgb24",
                     "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"] + ENC + [p],
                    stdin=subprocess.PIPE)
        if enc is not None:
            enc.stdin.write(frame.tobytes())
        n += 1
        if cur is not None and cur >= b:
            break
    if enc is not None:
        enc.stdin.close(); enc.wait()
    print(f"decoded {total} frames (stopped at segment {cur})", flush=True)
    for s in sorted(want):
        if s * FPS >= total and s != 380:
            continue
        p = os.path.join(outdir, f"seg_{s:04d}.mp4")
        cnt = seg_count(p)
        frag[str(s)] = {"file": f"seg_{s:04d}.mp4", "frames": cnt,
                        "sha256": hashlib.sha256(
                            open(p, "rb").read()).hexdigest()}
        print(f"seg {s}: {cnt} frames", flush=True)
    json.dump(frag, open(frag_path, "w"), indent=1)
    print("FRAG_OK", frag_path)


if __name__ == "__main__":
    main()
