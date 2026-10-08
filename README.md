# Music video engine

Audio-driven generative music-video engine: feature extraction from real
audio → mosaic / datamosh / conductor rendering pipeline. Visuals are
driven frame-by-frame by the actual track — never a procedural stand-in.

## Example output

<video src="demo.mp4" width="640" controls></video>

`demo.mp4` is a finished render from this pipeline (the input footage and
audio it was built from are not included).

## What's here

| File | What it does |
|---|---|
| `render.py` | Main render pipeline |
| `extract_features.py` | Audio feature extraction (the heartbeat of the engine) |
| `conductor.py` | Conducts visuals against the feature stream |
| `mosaic.py`, `mosh_footage.py`, `mosh_super.py` | Mosaic and datamosh renderers |
| `datamosh.py` | Datamoshing primitives |
| `make_test_audio.py` | Synthesizes a test signal (no audio sources needed) |
| `finish_v2.py` | Final compositing pass |
| `REPERTOIRE.md` | Index of the visual repertoire + style notes |
| `reflections/` | Build reflections |
| `palimpsest/td/` | TouchDesigner bridge (probe scripts, Linux renderer) |

## Quick-start

```bash
python3 make_test_audio.py        # synthesize a test signal -> test_signal.wav
python3 extract_features.py       # extract the feature stream
python3 render.py                # render visuals against the features
```

## Requirements

Python 3.10+, `numpy`. TouchDesigner scripts in `palimpsest/td/`
(`probe.py`, `render.py`, `render_fb.py`) run inside TouchDesigner.

## What's not here

No source footage or audio — sources are the creative repertoire and stay
private. `demo.mp4` is the only media artifact: example output, not input.
