# Music video engine

Audio-driven generative music-video pipeline. Every visual decision is driven
frame-by-frame by the actual audio track's feature stream — never a procedural
stand-in.

## End-to-end: vocals + backtrack → mastered mix → visuals

The full pipeline this repo supports, from raw stems to finished video:

**1. Mashup (vocal over beat)**
- Estimate both tempos (local beat tracking); time-stretch the vocal to the
  beat's BPM (rubberband, transients preserved). Trim leading silence.
- Build the beat's downbeat grid from first onset; drop the vocal after a
  short intro, on a downbeat.
- Fine-align with spectral-flux cross-correlation over ±1 beat, then
  tiebreak candidate nudges by *pulse clarity* — autocorrelation energy at
  the beat lag on a 60s test mix. Clarity beats raw correlation: the pocket
  that reinforces the groove wins.
- Vocal chain: high-pass → compression → light tonal EQ. Keep it clean
  unless FX are explicitly requested.
- Check for mid-track pauses; if a vocal re-entry lands off-grid, split in
  the silence and shift the tail so it hits the beat.
- Sidechain-duck the beat under vocals; balance levels; master with peak
  verified ≤ −1.0 dBFS. Version every render (`*_vN`); never overwrite.

**2. Visuals (this repo's core)**
- Slice the mastered mix into thematic sections (intro / verses / outro).
- Per section: pick footage matching the section's energy, write an EDL
  (`chaos_scale` per second — calm passages breathe, peaks mosh hard).
- `mosh_footage.py` cuts the section, builds mosaic bridges at hard cuts,
  encodes long-GOP, then performs audio-driven IDR-transplant datamosh:
  high spectral-drive windows smear predictively, low windows keep anchors.
- Concat the sections; the mix is already muxed per section.

**Design principle:** narrative → abstraction. Recognizable footage in quiet
passages; let the datamosh take over on peaks. The audio's dynamics envelope
conducts the whole edit.

## How it works

1. **Extract features** — `extract_features.py` analyzes the audio (beats,
   energy, spectral content) into a feature JSON.
2. **Conduct the edit** — `conductor.py` turns the feature stream into an
   edit decision list (EDL): where cuts land, how intense each section is.
3. **Render visuals** — pick a renderer:
   - `mosaic.py` — mosaic of library clips re-cut to the audio's rhythm
   - `datamosh.py` — datamoshed footage, glitch intensity driven by audio energy
   - `mosh_footage.py`, `mosh_super.py` — mosh variants and supercut assembly
   - `render.py` — main render pipeline
4. **Finish** — `finish_v2.py` does the final compositing pass and muxes the
   audio track back in.

## Quick-start

```bash
pip install numpy                    # Python 3.10+, plus ffmpeg on PATH

python3 make_test_audio.py           # synthesize a test signal (no audio needed)
python3 extract_features.py --audio test_signal.wav --out features.json
python3 datamosh.py --audio test_signal.wav --out demo.mp4
```

With your own audio:

```bash
python3 extract_features.py --audio your_track.mp3 --out features.json
python3 conductor.py --features features.json --out edl.json
python3 mosaic.py --audio your_track.mp3 --target base_footage.mp4 \
    --libs clip_a.mp4 clip_b.mp4 --out out.mp4
python3 finish_v2.py --in out.mp4 --audio your_track.mp3 --out final.mp4
```

Run any script with `--help` for its full options.

## Example output

`demo.mp4` is a finished render from this pipeline (the input footage and
audio it was built from are not included).

More output on YouTube: [pipeline render — watch here](https://youtu.be/XUoYSK5PrsI)

## TouchDesigner bridge

`palimpsest/td/` holds a TouchDesigner companion: probe scripts that map
TD's Python API (`td_ref.md` documents the verified operator/member set) and
a Linux numpy renderer (`palimpsest_render_linux.py`) implementing identical
shader logic for headless batch rendering.

## What's not here

No source footage or audio — only the code and one finished render.

## DJ workflow: multi-section music videos

For a full-length track, split it into thematic sections and run
`mosh_footage.py` per section with its own footage, audio slice, and EDL:

```bash
# slice the track
ffmpeg -i track.wav -ss 0 -t 42 -c copy sec1.wav
ffmpeg -i track.wav -ss 42 -t 168 -c copy sec2.wav
# ...
# per-section EDL (chaos_scale per second; see conductor.py schema)
python3 mosh_footage.py --footage clouds.mp4 --audio sec1.wav \
    --edl edl1.json --out sec1_out.mp4 --dur 42 --workdir w1
# concat
printf "file 'sec1_out.mp4'\nfile 'sec2_out.mp4'\n" > concat.txt
ffmpeg -f concat -safe 0 -i concat.txt -c copy final.mp4
```

See `SOURCING_PROTOCOL.md` for the clip-sourcing workflow.
