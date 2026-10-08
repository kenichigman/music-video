# Music video engine

Audio-driven generative music-video pipeline. Every visual decision is driven
frame-by-frame by the actual audio track's feature stream — never a procedural
stand-in.

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
