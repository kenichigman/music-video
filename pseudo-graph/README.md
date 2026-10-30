# Pseudo-graph displacement

Tracked features become a sparse data-graph drawn over the
picture — small node markers with numeric labels, thin lines
between neighbours — and the picture is displaced *along the
graph's edges*, with RGB fringing on the displaced parts.
Displacement strength follows the audio. The graph layer sits
**above** the datamosh: drawn last, crisp, never smeared by
the codec.

Prior art: this effect is an independent implementation of
the grammar in PPPANIK's TouchDesigner tutorial
"Audioreactive Pseudo-Data-Graph" (Pseudo-Graph
Displacement) — https://youtu.be/gWusA464neI — rebuilt here
in numpy from the published videos.

## The two graphs

- **Object graph** (`object_graph.py`) — computed from the
  *unedited* footage only. Nodes are Shi–Tomasi corners
  (structure-tensor local maxima: line junctions, contour
  corners), propagated by dual-template normalized
  cross-correlation — each node carries its spawn patch and
  its previous-frame patch, re-anchors to the spawn patch so
  drift cannot accumulate, and snaps to the strongest nearby
  corner. The result locks onto object structure and rides
  it: a face in frame is graphed as a face. Detection
  language on top: confidence labels (the anchor match,
  decaying honestly) and corner-tick cluster brackets.
  Two disciplines share the machinery: *lock* (stable
  footage: strict thresholds, miss tolerance) and *haywire*
  (abstract geometry: hygiene removed — first-miss death,
  flux-driven jitter — so the graph visibly loses its grip
  on material that has no objects; the churn is genuine).
- **Mosh graph** (`mosh_graph.py`, `seam_mosh_graph.py`) —
  computed from the *finished moshed* picture. A grid of
  probes is patch-matched frame to frame; the frame's median
  flow (camera motion) is subtracted, and nodes are probes
  whose residual flow is significant, plus "front" probes
  moving fast against the median direction. It graphs the
  melt itself: smear fronts and carried content.
  `seam_mosh_graph.py` additionally buckets its statistics
  by segment class (seam / interior / clean) when fed the
  seam-mosh record, which is how the seam placement's pickup
  was measured (seam segments drew ~1.5× the node density of
  clean segments in the reference window).

The compositor (`composite.py`) displaces the moshed base
along the object graph's edges (multi-tap sampling along the
flow, per-channel scale for fringing, gain driven by the
bass envelope), then draws the mosh graph, then the object
graph, on top.

## Quickstart

Requirements: Python 3, numpy, Pillow, ffmpeg/ffprobe, a
DejaVu Sans Mono font (the compositor's default path is the
usual Linux location; edit `FONT` if yours differs).

The scripts read their inputs from a data root:

```bash
export RIG_ROOT=$PWD/example-data
# expected under $RIG_ROOT (see "Data layout" below)
python3 extract_window_base.py   # clean window -> 1s-IDR stream
python3 object_graph.py          # clean footage -> obj_graph.json
python3 seam_mosh_graph.py       # moshed base -> mosh_graph.json
python3 composite.py --gain 3.0 --out graph_only.mp4
```

Window bounds are named constants at the top of each script
(`GRAPH_F_START` / `GRAPH_FRAMES` / `GRAPH_F_END` environment
variables override them). Every cost driver — node caps,
probe spacing, template/search sizes, displacement taps and
gain, label density — is a named constant in the source; the
production values are the desktop preset.

## Data layout (under $RIG_ROOT)

```
assembly/assembly.mp4     clean edited footage (object-graph source)
rig2/edl.json             edit rows: world tag + frame counts
rig2/bass_env.json        {"fps": 30, "bass": [...]} film-aligned envelope
rig2/boxprev/track_win.wav
                          window audio (flux for haywire jitter)
rig2/graph2prev/          object-graph work dir (obj_graph.json out;
                          the plain mosh graph writes here too)
rig2/graph3prev/          seam work dir: comp_win_graph.h264 in,
                          preview_graph3_base.mp4 (finished moshed
                          base), mosh_graph3_record.json, and
                          mosh_graph.json out
rig2/graphprev/           finished base for the plain (non-seam)
                          mosh graph: preview_graph_base.mp4
```

The directory names are historical; only the relative layout
matters, and every path is built from `$RIG_ROOT`. The
compositor reads the object graph from `graph2prev/` and the
seam mosh graph and base from `graph3prev/`.

## Measured behaviour (reference window, 480 frames)

Object graph: ~20 nodes/frame on structured footage, ~30
(cap-saturated) on abstract geometry. Displacement reaches
~40 px at bass peaks and touches only pixels within ~7 px of
an edge — most of every frame is untouched, so the picture
stays legible. One honest caveat: track *lifespan* statistics
do not separate the lock and haywire modes (abstract shards
re-match permissively and fake persistence); judge the modes
by node *placement*, which is structural in both.

## What is and is not in this shelf

Included: both trackers, the seam-aware mosh-graph variant,
the window extractor, and the compositor — the complete
graph pipeline as run in production. Not included: the
datamoshed base itself (bring a finished base from the
datamosh shelf / root pipeline), the production footage and
edit data, and any rendered output. A mobile parameter
preset was recorded during development (half working
resolution, roughly half the nodes/probes, two displacement
taps, node labels off) but is not shipped as code — the
named constants are the dial; set them and the same grammar
runs lighter.
