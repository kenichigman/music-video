#!/usr/bin/env python3
"""Build the delivered v3 manifest.json (v2 wrapper schema) from the
the segments_meta_v3.json + plan_v3.json."""
import json
import sys

meta = json.load(open(sys.argv[1]))          # segments_meta_v3.json
plan = json.load(open(sys.argv[2]))          # plan_v3.json (patched)
film_sha = sys.argv[3]
film_bytes = int(sys.argv[4])

SRCFILE = {
    "nature": "sources/gits-nature-datamosh-01.mp4",
    "october": "sources/october-dream-01.mp4",
    "store": "sources/conveniencestore-datamosh-01.mp4",
    "anime": "sources/anime-2026-09-29.mp4",
    "gits": "sources/gits-datamosh-01.mp4",
    "hands": "sources/bw-hands-datamosh-01.mp4",
}
BOUNDS = [0, 6, 30, 94, 113, 142, 221, 258, 323, 370, 381]
rows = plan["rows"]
pieces = plan["s6"]["pieces"]
FPS = 30


def section_of(i):
    for s in range(10):
        if BOUNDS[s] <= i < BOUNDS[s + 1]:
            return s
    raise AssertionError(i)


def src_of(i):
    f0 = i * FPS
    for r in rows:
        if r["start"] * FPS <= f0 < r["end"] * FPS:
            if r["kind"] == "s6_frame_precise":
                for p in pieces:
                    if p["film"][0] <= f0 < p["film"][1]:
                        return p["src"]
                raise AssertionError(("piece", i))
            return r["src"]
    raise AssertionError(("row", i))


segs = []
for e in meta:
    i = e["index"]
    if 236 <= i <= 243:
        sf = "v2 segment (substituted verbatim)"
    else:
        sf = SRCFILE[src_of(i)]
    segs.append({
        "index": i, "file": e["file"], "frames": e["frames"],
        "sha256": e["sha256"], "section": section_of(i),
        "source_file": sf, "source_label": e["source"],
        "source_in_point_s": e["in_point_s"], "moshed": e["moshed"],
    })

out = {
    "film": "home-computer_supercut_v3.mp4",
    "film_sha256": film_sha,
    "film_bytes": film_bytes,
    "duration_s": 380.8,
    "width": 848, "height": 464, "fps": 30,
    "total_frames": sum(s["frames"] for s in segs),
    "segments_moshed": sum(1 for s in segs if s["moshed"]),
    "substrate_note": "Per-second moshed flags measured by the "
                      "coordinator: decoded base.h264 vs moshed.h264 "
                      "in lockstep; seconds differing beyond 0.01 mean "
                      "gray diff flagged moshed (53/381, matching "
                      "corrupt_stream's own count of 53). Segments "
                      "236-243 are v2's delivered segments substituted "
                      "verbatim (sha-verified against v2's manifest) "
                      "to protect the praised spans.",
    "segments": segs,
}
json.dump(out, open(sys.argv[5], "w"), indent=1)
print("manifest segments:", len(segs), "frames:", out["total_frames"],
      "moshed:", out["segments_moshed"])
