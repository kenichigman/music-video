# Datamosh

Codec-level smear: the picture melts because the codec is told
to predict new frames from a stale reference. This is the
foundation effect of the repository — the core implementation
lives at the repository root (`datamosh.py`, `mosh_super.py`);
this shelf documents the grammar and adds the seam-placement
tool developed for the pseudo-graph work.

## How it works

1. Encode the footage with a one-second GOP (one IDR per
   second, no B-frames, no scene-cut keyframes).
2. Compute a per-half-second **spectral drive** from the audio
   (flatness + log RMS + centroid, normalized) — the music
   decides where smearing is allowed.
3. `corrupt_stream` walks the IDR-headed segments: in
   high-drive windows it transplants the most recently kept
   anchor's IDR over the segment's own, so the segment's
   P-slices smear predictively against the stale picture;
   low-drive windows keep their anchors, and a maximum-gap
   rule guarantees the image periodically resets.

Two placements of the same mechanism:

- **Interior placement** (the house style): resets at edit
  cuts, smear inside shots.
- **Seam placement** (`seam_mosh.py`, this shelf): at chosen
  world-swap boundaries the reset is removed and the
  straddling segments are force-corrupted, so one world is
  *carried* into the next — a datamosh transition. Protected
  resets keep section downbeats as hard cuts.

## Quickstart

Requirements: Python 3, numpy, ffmpeg/ffprobe on PATH.

```bash
# the repository's audio-conducted datamosh, end to end:
python3 ../datamosh.py --audio track.mp3 --out moshed.mp4

# seam placement on a prepared 1s-IDR stream:
python3 seam_mosh.py --input base_1s_idr.h264 \
    --output base_seam_moshed.h264 --drive drive.npy \
    --seams 35.0,36.5,41.3333 --resets 40.0 \
    --fps 30 --frames 480 --record mosh_record.json
```

`drive.npy` is an array of per-half-second drive values; see
`datamosh.spectral_drive` for how it is computed from audio.

## What is and is not in this shelf

Included: the seam-placement tool and the placement grammar,
with the parameters used in production (interior threshold
0.58 on the reference drive, max gap 8 s). Not included: the
core corruptor's source listing is not duplicated here — it
lives once, at the repository root — and no rendered media
ships in this repository. The seam tool expects you to bring
your own 1s-IDR stream and drive array; producing those is
the root pipeline's job (see the top-level README).
