# Writing an EDL by hand

The edit decision list (EDL) is the slow dynamics envelope over the
fast frame-by-frame audio signal. In the full setup a local LLM writes
it (`conductor.py`, from the per-second features produced by
`extract_features.py`); this edition does not include that model
helper, so the EDL is written by hand. `mosaic.py --edl <file>` and
`mosh_footage.py --edl <file>` both read this format.

## Schema

Top level: an object with one key, `sections`, holding an array of
section objects:

| field | type | range | meaning |
|---|---|---|---|
| `start_s` | integer | seconds | section start; the first section starts at 0 |
| `end_s` | integer | seconds | section end; the last section ends at the track duration |
| `chaos_scale` | number | 0.3 – 1.5 | tile-mismatch intensity multiplier (mosaic) / mosh-threshold shaping (mosh_footage) |
| `wet_scale` | number | 0.3 – 1.3 | mosaic blend-strength multiplier |
| `note` | string | — | one line naming what the section sounds like; documentation only |

Rules:

- 6 to 12 sections.
- Sections tile the track contiguously: each `start_s` equals the
  previous section's `end_s`; no gaps, no overlaps.
- House rule: quiet, sparse sections get low scales so the footage
  stays readable; loud, dense sections get high scales so the mosaic
  takes over. A vocal moment at moderate energy stays readable
  (scales ≤ 1.0).

## Usage

`sample_edl.json` in this directory is a complete example for a
60-second track. Copy it, retime the sections to your track's
structure (the `features.json` table from `extract_features.py` shows
where the energy actually is), and pass it to the render:

```bash
python3 mosaic.py --audio your_track.mp3 --target base_footage.mp4 \
    --libs clip_a.mp4 clip_b.mp4 --edl edl.json --out out.mp4
```
