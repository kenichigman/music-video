#!/usr/bin/env python3
"""Worker row-cutter for Home Computer v3 (coordinator plan: plan_v3.json).

Cuts the given global row indices into work_super_v3/secNN.mp4 using the
EXACT recipe of mosh_hc_v2.cut_sections (ss/t + optional pre-filter +
fps/scale/crop conform, libx264 veryfast crf16). Asserts frame counts
(dur*30 per row) and emits a JSON fragment {row: {file, frames, sha256}}.

Usage: python3 cut_rows.py plan_v3.json OUTDIR frag.json IDX [IDX ...]
Run with CWD = the stage root (sources/ lives there).
"""
import hashlib
import json
import os
import subprocess
import sys

BASE = os.environ.get("MUSIC_VIDEO_WORK_ROOT", ".") + "/"
SRCMAP = {
    "sources/anime.mp4": "sources/anime-2026-09-29.mp4",
    "sources/gits-nature-dm.mp4": "sources/gits-nature-datamosh-01.mp4",
    "sources/october-dream.mp4": "sources/october-dream-01.mp4",
    "sources/conveniencestore-dm.mp4":
        "sources/conveniencestore-datamosh-01.mp4",
    "sources/gits-dm.mp4": "sources/gits-datamosh-01.mp4",
    "sources/bw-hands-dm.mp4": "sources/bw-hands-datamosh-01.mp4",
}
FPS, W, H = 30, 848, 464


def seg_count(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-show_entries",
         "stream=nb_read_frames", "-of", "csv=p=0", path],
        capture_output=True, text=True).stdout.strip()
    return int(out)


def main():
    plan = json.load(open(sys.argv[1]))
    outdir, frag_path = sys.argv[2], sys.argv[3]
    idxs = [int(x) for x in sys.argv[4:]]
    os.makedirs(outdir, exist_ok=True)
    frag = {}
    for i in idxs:
        r = plan["rows"][i]
        assert r["kind"] not in ("reuse_v2_sec", "s6_frame_precise"), \
            f"row {i} is not a plain cut row ({r['kind']})"
        src = SRCMAP[r["clip"]]
        dur = r["end"] - r["start"]
        out = os.path.join(outdir, f"sec{i:02d}.mp4")
        vf = []
        if r["pre"]:
            vf.append(r["pre"])
        vf += [f"fps={FPS}",
               f"scale={W}:{H}:force_original_aspect_ratio=increase",
               f"crop={W}:{H}"]
        subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-y",
             "-ss", str(r["offset"]), "-i", src, "-t", str(dur),
             "-vf", ",".join(vf), "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "16", "-pix_fmt", "yuv420p", "-an", out], check=True)
        n = seg_count(out)
        assert n == dur * FPS, f"row {i}: {n} frames != {dur * FPS}"
        h = hashlib.sha256(open(out, "rb").read()).hexdigest()
        frag[str(i)] = {"file": f"sec{i:02d}.mp4", "frames": n, "sha256": h,
                        "span": [r["start"], r["end"]], "src": r["src"],
                        "offset": r["offset"], "kind": r["kind"]}
        print(f"row {i}: {r['src']} @{r['offset']} [{r['start']}-{r['end']}) "
              f"{n} frames ok", flush=True)
    json.dump(frag, open(frag_path, "w"), indent=1)
    print("FRAG_OK", frag_path)


if __name__ == "__main__":
    main()
