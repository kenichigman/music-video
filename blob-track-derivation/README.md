# Blob-track derivation

A clean-room, behavioral reimplementation of the blob
tracking used by the rig's TouchDesigner front-end —
derived from the operator's *observed* input/output only
(public parameter documentation and recorded output tables;
no vendor binary was inspected) — so that ports of the rig
(for example to the browser) do not depend on a proprietary
operator.

## What is here

- `blobtrack.py` — the numpy reference implementation.
  Pipeline: luminance → contrast → soft-threshold matte →
  (optional Gaussian background model) → connected
  components → size gate → per-frame greedy association
  with a lifecycle (active / lost / revived / expired) →
  a tracks table in the oracle's schema:
  `frame,id,u,v,width,height,age` (positions and sizes are
  frame fractions; age is in seconds).
- `spec.md` — the derivation spec: the observed oracle
  contract and semantics, written *before* the
  implementation, including the acceptance bars registered
  in advance.
- `validation.md` — the validation report against recorded
  oracle output: which bars passed, which failed, and the
  mechanisms behind both.
- `validate.py` — the validator that produced the report.

## Quickstart

Requirements: Python 3, numpy, scipy, ffmpeg/ffprobe.

```bash
python3 blobtrack.py input.mp4 --preset e2 --out tracks.csv
python3 blobtrack.py input.mp4 --preset vt --out tracks.csv
```

Presets `e2` / `vt` are the two production calibrations
(matte threshold and minimum blob size for structured vs
abstract footage); every parameter can be overridden on the
command line or via the `Params` dataclass. Recorded mobile
presets (`e2-mobile`, `vt-mobile`: half working resolution,
larger minimum size, per-frame cap) are included as values
for porters.

Semantics that were derived exactly and are safe to build
on: age advances at 1/60 s per frame *including* frames
where the blob is lost; emitted blob sizes are square
(the oracle reports one scalar; height = width × aspect);
the revive window is 0.4167 s; positions are sub-pixel.

## Honest status

Two of the four pre-registered bars pass (blob counts,
centroid positions). Two fail, with identified mechanisms:
the oracle's size scalar behaves like internal tracker
state rather than a statistic of the current region (its
*law* is derived and shipped; its values are not
reproducible from the image), and the derivation's
detection flickers at short periods where the oracle's is
temporally stable, inflating revivals — the recorded fix
direction is temporal hysteresis / coasting, not yet
implemented. Downstream, the pseudo-graph's node selection
fed from derived tables reads similar to oracle-fed
(~15–20% fewer nodes). `validation.md` has the numbers;
nothing in this README rounds them up.

## What is and is not in this shelf

Included: the spec, the implementation, the validator, and
the full report. Not included: the oracle capture tables
themselves (recorded output of a commercial operator on
production footage) — `validate.py` expects you to point it
at your own captures (`BLOBTRACK_RIG_DIR`,
`BLOBTRACK_MANIFEST`) if you want to reproduce the
comparison; the implementation needs nothing but a video.
