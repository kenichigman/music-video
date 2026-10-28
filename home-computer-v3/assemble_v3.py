#!/usr/bin/env python3
"""Assemble home-computer_supercut_v3 on the execution host.

- merges the 4 harvest frags (segs 0-379) + seg 380 (24f special pass)
- substitutes v2's delivered segments 236-243 verbatim (praised spans)
- measures per-second moshed flags: decoded base.h264 vs moshed.h264
  (KEEP seconds are bit-identical -> zero diff; MOSH seconds differ)
- writes manifest entries in the v2 schema
- concat -c copy -> film video; mux v2 master audio (stream copy)
Usage: python3 assemble_v3.py  (run from the stage root)
"""
import hashlib
import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from render import FFMPEG  # noqa: E402

ROOT = os.environ.get("MUSIC_VIDEO_WORK_ROOT", ".")
SEGDIR = ROOT + "/work_v3/segs_v3"
SUBDIR = ROOT + "/work_v3/segs_v2sub"
PLAN = json.load(open(ROOT + "/plan_v3.json"))
V2META = {e["index"]: e for e in
          json.load(open(ROOT + "/work_v2/manifest_v2.json"))["segments"]}
FPS = 30


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def seg_frames(p):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-show_entries",
         "stream=nb_read_frames", "-of", "csv=p=0", p],
        capture_output=True, text=True).stdout.strip()
    return int(out)


def decode_gray(path, w=424, h=232):
    cmd = [FFMPEG, "-v", "error", "-i", path, "-vf",
           f"scale={w}:{h},format=gray", "-f", "rawvideo",
           "-pix_fmt", "gray", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    prev = None
    sec_max = {}
    n = 0
    while True:
        raw = proc.stdout.read(w * h)
        if len(raw) < w * h:
            break
        fr = np.frombuffer(raw, dtype=np.uint8).astype(np.int16)
        if prev is not None:
            d = float(np.abs(fr - prev).mean())
            s = n // FPS
            sec_max[s] = max(sec_max.get(s, 0.0), d)
        prev = fr
        n += 1
    proc.wait()
    return n, sec_max


print("== measuring moshed seconds (base vs moshed, lockstep) ==",
      flush=True)
proc_a = subprocess.Popen(
    [FFMPEG, "-v", "error", "-i", ROOT + "/work_super_v3/base.h264",
     "-vf", "scale=424:232,format=gray", "-f", "rawvideo",
     "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE)
proc_b = subprocess.Popen(
    [FFMPEG, "-v", "error", "-i", ROOT + "/work_super_v3/moshed.h264",
     "-vf", "scale=424:232,format=gray", "-f", "rawvideo",
     "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE)
W2, H2 = 424, 232
pair_max = {}
n = 0
while True:
    ra = proc_a.stdout.read(W2 * H2)
    rb = proc_b.stdout.read(W2 * H2)
    if len(ra) < W2 * H2 or len(rb) < W2 * H2:
        break
    d = float(np.abs(np.frombuffer(ra, np.uint8).astype(np.int16)
                     - np.frombuffer(rb, np.uint8).astype(np.int16)
                     ).mean())
    s = n // FPS
    pair_max[s] = max(pair_max.get(s, 0.0), d)
    n += 1
proc_a.wait(); proc_b.wait()
print(f"  lockstep frames compared: {n}")
moshed_sec = {s: (pair_max.get(s, 0.0) > 0.01) for s in range(381)}
print(f"  moshed seconds: {sum(moshed_sec.values())}/381")

print("== merging frags + substitution ==", flush=True)
frags = {}
for f in ["hfrag_0_96.json", "hfrag_96_192.json", "hfrag_192_288.json",
          "hfrag_288_380.json"]:
    frags.update(json.load(open(ROOT + "/work_v3/" + f)))
assert len(frags) == 380, len(frags)
for i in range(236, 244):
    src = os.path.join(SUBDIR, f"seg_{i:04d}.mp4")
    dst = os.path.join(SEGDIR, f"seg_{i:04d}.mp4")
    assert sha(src) == V2META[i]["sha256"], f"sub sha mismatch seg {i}"
    assert seg_frames(src) == V2META[i]["frames"] == 30
    with open(src, "rb") as f_in, open(dst, "wb") as f_out:
        f_out.write(f_in.read())
    print(f"  substituted seg {i} from v2 (sha verified)")
p380 = os.path.join(SEGDIR, "seg_0380.mp4")
frags["380"] = {"file": "seg_0380.mp4", "frames": seg_frames(p380),
                "sha256": sha(p380)}
assert frags["380"]["frames"] == 24

rows = PLAN["rows"]
pieces = PLAN["s6"]["pieces"]


def seg_source(i):
    f0 = i * FPS
    for r in rows:
        if r["start"] * FPS <= f0 < r["end"] * FPS:
            if r["kind"] == "s6_frame_precise":
                for p in pieces:
                    if p["film"][0] <= f0 < p["film"][1]:
                        return p["src"], p["note"], \
                            p["src_frame"] / FPS + (f0 - p["film"][0]) / FPS
                raise AssertionError(("s6 piece", i))
            label = {"home": " (home)", "guest": " (guest)",
                     "reuse_v2_sec": " (v2 reuse)"}[r["kind"]]
            return r["src"], r["src"] + label, \
                r["offset"] + (f0 - r["start"] * FPS) / FPS
    raise AssertionError(("row", i))


entries = []
for i in range(381):
    if 236 <= i <= 243:
        fr = {"file": f"seg_{i:04d}.mp4",
              "frames": V2META[i]["frames"],
              "sha256": V2META[i]["sha256"]}
    else:
        fr = frags[str(i)]
    p = os.path.join(SEGDIR, fr["file"])
    assert sha(p) == fr["sha256"], f"harvest sha drift seg {i}"
    if 236 <= i <= 243:
        src, label = "v2-segment", \
            "v2 segment (substituted verbatim, praised span)"
        inpt = V2META[i]["source_in_point_s"]
        mosh = V2META[i]["moshed"]
    else:
        src, label, inpt = seg_source(i)
        mosh = moshed_sec[i]
    entries.append({"index": i, "file": fr["file"], "source": label,
                    "in_point_s": round(float(inpt), 3),
                    "frames": fr["frames"], "moshed": bool(mosh),
                    "sha256": fr["sha256"]})
tot = sum(e["frames"] for e in entries)
print(f"  total frames: {tot}")
assert tot == 11424, tot
json.dump(entries, open(ROOT + "/work_v3/segments_meta_v3.json", "w"),
          indent=1)

print("== concat + mux ==", flush=True)
lst = ROOT + "/work_v3/concat_v3.txt"
with open(lst, "w") as f:
    for i in range(381):
        f.write(f"file 'segs_v3/seg_{i:04d}.mp4'\n")
subprocess.run([FFMPEG, "-nostdin", "-v", "error", "-y",
                "-f", "concat", "-safe", "0", "-i", lst,
                "-c", "copy", ROOT + "/work_v3/film_video_v3.mp4"],
               check=True)
subprocess.run([FFMPEG, "-nostdin", "-v", "error", "-y",
                "-i", ROOT + "/work_v3/film_video_v3.mp4",
                "-i", ROOT + "/work_v2/home-computer_supercut_v2.mp4",
                "-map", "0:v", "-map", "1:a", "-c", "copy",
                ROOT + "/work_v3/home-computer_supercut_v3.mp4"],
               check=True)
print("ASSEMBLE_OK")
