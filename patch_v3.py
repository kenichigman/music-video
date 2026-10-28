#!/usr/bin/env python3
"""Song Six supercut v3 — HEAD PATCH ONLY on top of v2.

The director's verdict on v2: the 1:58 Drop II patch is GOOD (carried over
untouched); the beginning is still "off". Sequential-decode diagnosis
(the parent's seek-based sheets were unreliable on this file family —
the mp4 demuxer seek lands a GOP early; sequential decode is truth):

- v1 and v2 both open on the right shot: the anime walk, character
  composed in-frame from t=0 (timeline frame 0 = source 100.0s, PLAN
  offset confirmed by frame match, NCC 0.975).
- The defect is in the SOURCE window itself: at timeline frame 71
  (output 2.37s, source 102.37s) the anime cuts to a static BRIDGE
  scene that runs 149 frames (timeline 71-219, source 102.37-107.3s).
- In v1, segs 1-5 moshed off seg0's anchor + a mosaic bridge over the
  cut masked it into a glitch flash (still "off" to the director).
- In v2, FIX A suppressed the mosaic and kept segs 0-1 clean; seg2's
  IDR transplant could not stop the bridge P-frame's giant residual
  (encoded against the walk frame) from REPAINTING a clean, legible
  bridge for frames 71-89, before seg3's transplanted walk IDR
  snapped back at frame 90. A clean 0.63s stray insert — worse.
- Shifting the window cannot help: the surrounding source is rapid
  montage (cuts at source 96.9 / 99.283 / 102.35 / 107.33 / 110.15);
  no cut-free 6s span exists in this shot, and timeline 220+ is
  foreign scenes. So the window stays at v1's exact in-point and the
  insert is neutralised in the BASE frames instead:

FIX (frames 0-179 rebuilt; 180-219 = v2 margin frames; 220+ stream-
copied from v2 bit-exact, including the approved 1:58 patch; audio
copied untouched from v2):
- Base frames 71-89 (the legible bridge span) are replaced by a HOLD
  of timeline frame 70 (last walk frame). Identical frames encode as
  ~zero-residual P-frames, so nothing can repaint the bridge.
- Base frames 90-179 stay the timeline's bridge statics — with seg
  IDR transplants they decode as the walk anchor's image (near-zero
  residuals), exactly the v1 behaviour the director never flagged at 3-6s.
- Mosaic bridges suppressed in the head (no flash).
- Mosh: seg0 KEEP (clean legible anchor, ~1s), segs 1-5 MOSH off
  seg0's anchor — melt depth ramps with anchor staleness 1s->5s,
  full Drop I chaos (1.30) character by ~3-4s.
- Finish: v1 sec0 params verbatim (patch_v2.grade_frames / PER).

Assembly (separate step): mkvmerge append of patch_head.mkv +
v2 tail split at the frame-220 keyframe, spans proven by frame MD5,
then remux with v2's audio stream copied untouched.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mosaic as M  # noqa: E402
import patch_v2 as P  # noqa: E402  (machinery + PER + grade_frames)

FPS, W, H = 30, 848, 464
ROOT = P.ROOT
V3WORK = os.path.join(ROOT, "work_v3")
os.makedirs(V3WORK, exist_ok=True)
TIMELINE = P.TIMELINE
V2 = os.path.join(ROOT, "work", "song-six_supercut_v2.mp4")

HOLD_SRC = 70            # last walk frame before the bridge cut
HOLD_SPAN = (71, 90)     # base frames replaced by the hold


def main():
    print("== v3 head: base frames from timeline, bridge held ==",
          flush=True)
    tl = []
    for i, fr in enumerate(M.decode_rawvideo(TIMELINE, W, H)):
        if i >= 180:
            break
        tl.append(fr)
    assert len(tl) == 180, f"timeline head frames: {len(tl)}"
    # sanity: the only big cut inside 0..180 must be at frame 71
    d = [float(np.abs(tl[i].astype(np.int16)
                      - tl[i - 1].astype(np.int16)).mean())
         for i in range(1, 180)]
    big = [i + 1 for i, x in enumerate(d) if x > 8]
    assert big == [71], f"unexpected cuts in head window: {big}"
    print("  scene check: single internal cut at frame 71 (bridge "
          "insert) — no other cut in 0..180", flush=True)

    base = list(tl)
    for i in range(HOLD_SPAN[0], HOLD_SPAN[1]):
        base[i] = tl[HOLD_SRC]
    base_h = os.path.join(V3WORK, "base_head.h264")
    P.encode_base(iter(base), base_h)
    _pre, segs = P.parse_segments(base_h)
    assert len(segs) == 6, f"head segments {len(segs)}"
    # seg0 KEEP (clean anchor); segs 1-5 MOSH off seg0 (staleness ramp)
    moshed = P.corrupt_window(segs, lambda i, s: i >= 1,
                              os.path.join(V3WORK, "moshed_head.h264"))
    frames = P.decode_corrupt(os.path.join(V3WORK, "moshed_head.h264"),
                              180)
    graded = P.grade_frames({i: frames[i] for i in range(180)})
    margins = P.read_frames(V2, 180, 40)
    assert len(margins) == 40
    patch = [graded[i] for i in range(180)] + margins
    out = os.path.join(V3WORK, "patch_head.mp4")
    P.encode_patch(patch, out)
    print(f"  patch done: {out} (moshed segs local: {moshed})",
          flush=True)


if __name__ == "__main__":
    main()
