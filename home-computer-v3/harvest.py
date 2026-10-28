#!/usr/bin/env python3
"""Harvest v2 segments from finished_v2.mp4 (frame-exact, one encoder per
segment), build hybrids for the S6 boundary segments, assemble the v2
segment set + master, verify."""
import os, subprocess, sys, json, hashlib, shutil
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import mosaic as M

W, H, FPS = 848, 464, 30
BASE = os.environ.get("MUSIC_VIDEO_WORK_ROOT", ".") + "/"
FIN = BASE + "work_v2/finished_v2.mp4"
V1SEGS = BASE + "work/segments_v1"
OUTSEGS = BASE + "work_v2/segments_v2"
TMP = BASE + "work_v2/harvest_tmp"
NEW = os.path.join(TMP, "new")
os.makedirs(OUTSEGS, exist_ok=True)
os.makedirs(NEW, exist_ok=True)

SEGSET = set()
for (a, b) in [(50, 66), (78, 91), (160, 176), (192, 204), (243, 248),
               (276, 293), (310, 322)]:
    SEGSET.update(range(a, b))
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "16",
       "-g", "30", "-keyint_min", "30", "-sc_threshold", "0",
       "-pix_fmt", "yuv420p", "-an"]

def start_encoder(path):
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-"] + ENC + [path]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)

def frames_of(path):
    return list(M.decode_rawvideo(path, W, H))

def seg_count(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames",
                          "-show_entries", "stream=nb_read_frames",
                          "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    return int(out)

# ---- 1. decode finished film once; encode each needed segment directly
print("== harvesting segments ==", flush=True)
new_segs = {}
enc = None
cur = None
n = 0
for frame in M.decode_rawvideo(FIN, W, H):
    s = n // FPS
    if s != cur:
        if enc is not None:
            enc.stdin.close(); enc.wait()
            enc = None
        cur = s
        if s in SEGSET:
            p = os.path.join(NEW, f"seg_{s:04d}.mp4")
            new_segs[s] = p
            enc = start_encoder(p)
    if enc is not None:
        enc.stdin.write(frame.tobytes())
    n += 1
if enc is not None:
    enc.stdin.close(); enc.wait()
print(f"  decoded {n} frames; new segments: {len(new_segs)}", flush=True)
for s, p in new_segs.items():
    assert seg_count(p) == 30, f"{p} frames != 30"

# ---- 2. hybrids: seg243 (v1 frames 0-20 + new 21-29),
#         seg247 (new frames 0-20 + v1 21-29) ----
def write_segment(frames, path):
    p = start_encoder(path)
    for fr in frames:
        p.stdin.write(fr.tobytes())
    p.stdin.close(); p.wait()
    assert seg_count(path) == 30

v1_243 = frames_of(os.path.join(V1SEGS, "seg_0243.mp4"))
new_243 = frames_of(new_segs[243])
hyb243 = os.path.join(NEW, "seg_0243_hyb.mp4")
write_segment(v1_243[:21] + new_243[21:], hyb243)
new_segs[243] = hyb243
v1_247 = frames_of(os.path.join(V1SEGS, "seg_0247.mp4"))
new_247 = frames_of(new_segs[247])
hyb247 = os.path.join(NEW, "seg_0247_hyb.mp4")
write_segment(new_247[:21] + v1_247[21:], hyb247)
new_segs[247] = hyb247
print("  hybrids built: seg243 (21 v1 + 9 new), seg247 (21 new + 9 v1)",
      flush=True)

# ---- 3. assemble v2 segment dir ----
for i in range(381):
    dst = os.path.join(OUTSEGS, f"seg_{i:04d}.mp4")
    if i in new_segs:
        shutil.copy(new_segs[i], dst)
    else:
        shutil.copy(os.path.join(V1SEGS, f"seg_{i:04d}.mp4"), dst)
meta = []
for i in range(381):
    p = os.path.join(OUTSEGS, f"seg_{i:04d}.mp4")
    h = hashlib.sha256(open(p, "rb").read()).hexdigest()
    meta.append({"index": i, "file": f"seg_{i:04d}.mp4",
                 "frames": seg_count(p), "sha256": h,
                 "new": i in new_segs})
json.dump(meta, open(BASE + "work_v2/segments_meta_v2.json", "w"), indent=1)
bad = [m["index"] for m in meta
       if m["frames"] != (24 if m["index"] == 380 else 30)]
print(f"  segment set assembled; bad frame counts: {bad}", flush=True)

# ---- 4. concat + mux v1 audio ----
lst = os.path.join(TMP, "concat_v2.txt")
with open(lst, "w") as fh:
    for i in range(381):
        fh.write(f"file '{os.path.join(OUTSEGS, f'seg_{i:04d}.mp4')}'\n")
vid = BASE + "work_v2/video_v2.mp4"
subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "concat",
                "-safe", "0", "-i", lst, "-c", "copy", vid], check=True)
master = BASE + "work_v2/home-computer_supercut_v2.mp4"
subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", vid,
                "-i", BASE + "work/home-computer_supercut_v1.mp4",
                "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", master],
               check=True)
nf = seg_count(master)
sha = hashlib.sha256(open(master, "rb").read()).hexdigest()
print(f"  MASTER: {master} frames={nf} sha256={sha}", flush=True)
print("HARVEST_OK", flush=True)
