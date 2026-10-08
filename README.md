# Music video engine

Audio-driven generative music-video engine: feature extraction from real
audio → mosaic / datamosh / conductor rendering pipeline. Visuals are
driven frame-by-frame by the actual track — never a procedural stand-in.

## Example output

<video src="demo.mp4" width="640" controls></video>

`demo.mp4` is a finished render from this pipeline (the input footage and
audio it was built from are not included).

## What's here

- `render.py` — main render pipeline
- `extract_features.py` — audio feature extraction (the engine's heartbeat)
- `conductor.py` — conducts visuals against the feature stream
- `mosaic.py`, `mosh_footage.py`, `mosh_super.py`, `datamosh.py` — renderers
- `make_test_audio.py` — synthesizes a test signal (no audio sources needed)
- `finish_v2.py` — final compositing pass
- `REPERTOIRE.md` — visual repertoire index + style notes
- `reflections/` — build reflections
- `palimpsest/td/` — TouchDesigner bridge (probe scripts, Linux renderer)

## Quick-start

```bash
python3 make_test_audio.py   # synthesize a test signal -> test_signal.wav
python3 extract_features.py  # extract the feature stream
python3 render.py            # render visuals against the features
```

Requirements: Python 3.10+, `numpy`. TouchDesigner scripts in
`palimpsest/td/` run inside TouchDesigner.

## What's not here

No source footage or audio — sources are the creative repertoire and
stay private. `demo.mp4` is the only media artifact: example output,
not input.
