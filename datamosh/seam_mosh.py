#!/usr/bin/env python3
"""seam_mosh.py — datamosh placed at the seams between worlds.

Interior segments use the standard spectral-drive rule (see the
repository's datamosh.py). At chosen boundary times — the cuts
where one visual world gives way to another — the anchor reset
is removed and the one-second segments straddling the boundary
are force-corrupted, so the codec carries the outgoing picture
into the incoming one: a datamosh transition instead of a clean
cut. Boundaries listed as resets keep a fresh anchor and land
as hard cuts (use them for section downbeats that must hit).

The corruptor is the repository's datamosh.corrupt_stream; the
per-window threshold override is the mechanism: forced segments
get threshold -1.0 (corrupt regardless of drive), every other
half-second window keeps the interior threshold.

Example (the reference window: six world-swap seams, one
protected downbeat):
  python3 seam_mosh.py --input base_1s_idr.h264 \
      --output base_seam_moshed.h264 --drive drive.npy \
      --drive-offset 66 \
      --seams 35.0,36.5,41.3333,43.0667,45.0,46.0 \
      --resets 40.0 --fps 30 --frames 480 \
      --record mosh_record.json

Inputs the caller supplies:
  --input   H.264 stream encoded with one IDR per second
            (keyint == fps, no B-frames, no scenecut).
  --drive   .npy array of per-half-second spectral-drive values
            covering the window (see datamosh.spectral_drive);
            --drive-offset selects the window's first entry.
"""
import argparse, json, os, sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".."))
import datamosh  # noqa: E402  (repository root)


def parse_times(text):
    if not text:
        return []
    return [float(x) for x in text.split(",") if x.strip()]


def straddle_segments(seam_rel, fps):
    """1s segments (window-relative) a boundary straddles: a
    boundary on a segment edge forces both neighbours; one
    inside a segment forces that segment."""
    seg = int(seam_rel // 1.0)
    frac = seam_rel - seg
    if abs(frac) < 1e-6:
        return {seg - 1, seg} - {-1}
    return {seg}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--drive", required=True)
    ap.add_argument("--drive-offset", type=int, default=0,
                    help="first half-second drive index of the window")
    ap.add_argument("--seams", default="",
                    help="comma-separated boundary times, seconds, "
                         "in the same timebase as --window-start")
    ap.add_argument("--resets", default="",
                    help="comma-separated protected reset times")
    ap.add_argument("--window-start", type=float, default=0.0,
                    help="time (s) where the window starts in the "
                         "same timebase as --seams/--resets")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--frames", type=int, required=True)
    ap.add_argument("--drop-thresh", type=float, default=0.58)
    ap.add_argument("--max-gap", type=float, default=8.0)
    ap.add_argument("--record", default="")
    a = ap.parse_args()

    drive_full = np.load(a.drive)
    n_win = int(np.ceil(a.frames / a.fps * 2))
    drive = drive_full[a.drive_offset:a.drive_offset + n_win]
    if len(drive) < n_win:
        raise SystemExit("drive array too short for the window")

    seams_rel = [t - a.window_start for t in parse_times(a.seams)]
    resets_rel = [t - a.window_start for t in parse_times(a.resets)]
    forced = sorted(set().union(
        *[straddle_segments(t, a.fps) for t in seams_rel]) if seams_rel
        else set())

    thresh_win = np.full(len(drive), a.drop_thresh)
    for s in forced:
        thresh_win[2 * s] = -1.0
        thresh_win[2 * s + 1] = -1.0

    kept, moshed = datamosh.corrupt_stream(
        a.input, a.output, drive, a.fps, a.frames,
        drop_thresh=a.drop_thresh, max_gap_s=a.max_gap,
        thresh_win=thresh_win, reset_times=resets_rel)
    print("mosh done: kept", kept, "moshed", moshed, flush=True)
    if a.record:
        json.dump({"seam_times": parse_times(a.seams),
                   "reset_times": parse_times(a.resets),
                   "forced_segments": forced,
                   "drop_thresh_interior": a.drop_thresh,
                   "thresh_win_forced": -1.0,
                   "max_gap_s": a.max_gap,
                   "kept": kept, "moshed": moshed},
                  open(a.record, "w"), indent=1)
    print("ALL DONE")


if __name__ == "__main__":
    main()
