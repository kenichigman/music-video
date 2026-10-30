# Abstract × structured fusion

Two visual worlds interpenetrating in time with the music:
each frame cross-blends toward the other world's picture with
a strength driven by the measured bass oscillation — at
troughs the frame settles back to nearly its own world; at
peaks the worlds genuinely fuse; at the strongest accents
the blend ceiling rises so the fusion goes furthest exactly
where the music hits hardest. Foreign object layers can ride
the same pulse on top.

**Status: parked.** The grammar works and was validated on
window-length previews, but it has not been tuned to the
standard of the datamosh and pseudo-graph shelves, and a
full-length render has not been attempted. It is published
as a working starting point, honestly labelled — not as a
finished effect.

## How it works

`composite_fusion.py` renders each needed shot's warped
frames (a flux-gated velocity-field warp; per-source gains
halved from the full-strength preset, displacement clamped)
into a cache, then blends frame-by-frame toward the
temporally nearest opposite-world shot's warped frames:

```
alpha(t) = 0.55 * I(t)                          I(t) < 0.9
         = 0.495 + (I(t) - 0.9) / 0.1 * 0.205   I(t) >= 0.9
```

with `I(t)` the window-normalized bass intensity. Donor
shots are chosen by edit-row centre distance; donor frames
loop over the receiving row's local index. The blend happens
before the datamosh stage; `clean_cut_mosh.py` is the
companion moshing step used in the reference previews
(every edit boundary reset — clean cuts, smear only inside
shots). It reads `comp_win_fuse3.h264` from `$FUSION_WORK_DIR`
(default `$RIG_ROOT/fusion-work`) and a half-second drive
array from `$FUSION_DRIVE` (default `$RIG_ROOT/drive.npy`),
and writes the moshed stream and a JSON record back to the
work directory.

## Quickstart

Requirements: Python 3, numpy, ffmpeg/ffprobe.

The compositor reads its edit data from its own directory
and its footage/fields from `$RIG_ROOT`:

```bash
export RIG_ROOT=$PWD/example-data
# place in this directory: edl.json, rows_manifest.json,
# manifest_stage1.json, signals.npz, bass_env.json, and
# fields/rowNN/fields.npy per edit row (velocity fields)
python3 composite_fusion.py --help   # window + output options
```

## What is and is not in this shelf

Included: the oscillation-blend compositor and its companion
mosh step, with production parameters. Not included: the
velocity-field generation stage (fields are an input here),
the footage, and any full-length validation — the boundary
of this shelf is exactly the boundary of what was proven:
window-scale previews. Treat the code as a running start for
an idea with potential, and expect to tune it.
