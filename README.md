# Music video engine

Audio-driven generative music-video pipeline. Every visual decision is driven
frame-by-frame by the actual audio track's feature stream — never a procedural
stand-in.

## End-to-end: vocals + backtrack → mastered mix → visuals

The full pipeline this repo supports, from raw stems to finished video:

**1. Mashup (vocal over beat)**
- Estimate both tempos (by ear or beat-tracking tool); pass to `mashup.py`
  as `--vocal-bpm` / `--beat-bpm`. Time-stretch the vocal to the beat's BPM
  (rubberband, transients preserved). Trim leading silence.
- Build the beat's downbeat grid from first onset; drop the vocal after a
  short intro, on a downbeat.
- Fine-align with spectral-flux cross-correlation over ±1 beat, then
  tiebreak candidate nudges by *pulse clarity* — autocorrelation energy at
  the beat lag on a 60s test mix. Clarity beats raw correlation: the pocket
  that reinforces the groove wins.
- Vocal chain: high-pass → compression → light tonal EQ. Keep it clean
  unless FX are explicitly requested.
- Manual check: scan for mid-track pauses; if a vocal re-entry lands
  off-grid, split in the silence and shift the tail so it hits the beat.
- Sidechain-duck the beat under vocals; balance levels; master with peak
  verified ≤ −1.0 dBFS. Version every render (`*_vN`); never overwrite.
- Reference implementation: `mashup.py --vocal acapella.mp3 --beat beat.mp3
  --vocal-bpm 97 --beat-bpm 103 --out mix.wav`
- Guiding rule: the ear is the final arbiter. Metrics guide; listening
  decides. Never defend a render against "it sounds off" — diagnose the
  named timestamp.

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
5. **Gate** — `supercut_qa.py` is the standing pre-delivery QA gate: clean
   decode, flash/insert checks in declared clean windows, drop-boundary
   detonation timing, and a head contact sheet. No render ships until
   it passes.

## Quick-start

```bash
pip install numpy Pillow             # Python 3.10+, plus ffmpeg on PATH

python3 make_test_audio.py           # synthesize a test signal (no audio needed)
python3 extract_features.py --audio test_signal.wav --out features.json
python3 datamosh.py --audio test_signal.wav --out demo_out.mp4
```

Expect the render step to take a few minutes (about 3 minutes for the
test signal at the 720p default). The test signal ends with a loud,
dense section, so the stage-2 log shows at least one `MOSH` segment —
the IDR transplant firing. On quiet or single-segment material every
segment stays in the keep band and nothing is transplanted; that is
the design, not a failure.

### Additional tools for the full workflows

The quick-start needs only numpy, Pillow and ffmpeg. The wider
workflows documented in this repo use more:

- `mashup.py` (the DJ workflow below): `pip install scipy`, plus the
  `rubberband` command-line tool on PATH.
- The surgical patching workflow in PATCHING.md: `mkvmerge`
  (mkvtoolnix) for frame-exact splits and appends.

With your own audio:

```bash
python3 extract_features.py --audio your_track.mp3 --out features.json
# write an EDL by hand (see below), then:
python3 mosaic.py --audio your_track.mp3 --target base_footage.mp4 \
    --libs clip_a.mp4 clip_b.mp4 --edl edl.json --out out.mp4
python3 finish_v2.py --in out.mp4 --audio your_track.mp3 --out final.mp4
```

The EDL is the conductor's output: sections of the track, each with
`chaos_scale` / `wet_scale` multipliers that shape the mosaic's
intensity over time. In the full setup a local LLM writes it
(`conductor.py`, driven by the per-second features above), but that
step uses a local model helper (an `ollama_local` module, configured
via `MUSIC_VIDEO_LOCAL_BIN`) that is not included in this edition —
`conductor.py` exits with an explanation when it is not configured.
Here you write the EDL by hand instead: start from
`examples/sample_edl.json`; `examples/README.md` documents the schema.

Run any script with `--help` for its full options.

## Example output

`demo.mp4` is a finished render from this pipeline (the input footage and
audio it was built from are not included).

More output on YouTube: [pipeline render — watch here](https://youtu.be/XUoYSK5PrsI)

## The supercut dataset

The supercut line was developed against a fixed dataset — **one
six-clip pool cut into three films**: a human-made reference cut, a
DEATHPACT "Song Six" supercut (v5, final —
[watch](https://youtu.be/OjZCkGFgWKY)), and a Kraftwerk "Home
Computer" supercut (v3 —
[watch](https://youtu.be/Zy179vQTPJ4)), also embedded in the
portfolio site (kenichigman.pages.dev). Same footage, three
tracks, three edits. See [DATASET.md](DATASET.md) for the method, the
QA gate, and the surgical-patching discipline (`PATCHING.md`) that
the iteration ran on.

## Production drivers & the Home Computer v3 set

The root also carries the surgical-patch drivers the iteration ran
on: `patch_v2.py`–`patch_v4.py` (frame-range rebuilds of the Song Six
film), their verifiers (`verify_v2.py`, `verify_v4.py`,
`prove_parts_v4.py` — decoded-frame MD5 identity proofs outside the
patch spans), `chunk_render.py` (segmented driver around
`render.py`), `measure_phase.py` and `supercut_qa_hc.py` (phase
gates), and `run_conductor_hc.py` (the conductor run for the Home
Computer track). The patch drivers import the production variants
of the core modules they were run against.

`home-computer-v3/` holds the complete production set for the
current Home Computer cut: `planner_v3.py` (the global blend
planner), the mosh/finish chain (`mosh_hc_v2.py`, `mosh_hc_v3.py`,
`finish_hc_v2.py`, `finish_hc_v3.py`, `build_sec06.py`,
`build_sec06_v3.py`), the segment-master tooling (`cut_rows.py`,
`harvest.py`, `harvest_rows.py`, `assemble_v3.py`,
`build_manifest.py`, `patch_plan.py`), the phase gates (`qa_v2.py`,
`qa_v3.py`), and the executed plan and segment manifest
(`plan_v3.json`, `segments_meta_v3.json`, `frag_S*.json`). Machine-
specific locations are read from the environment
(`MUSIC_VIDEO_WORK_ROOT`, `MUSIC_VIDEO_FEATURES`,
`MUSIC_VIDEO_LOCAL_BIN`) — the scripts carry no fixed paths.

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
