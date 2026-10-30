# VALIDATION — Blob Track TOP derivation vs the stage-1 oracle

Date: the initial build. Protocol: spec.md §6, registered before the
build; the bars did not move. Calibration subset (registered):
CP rows 12, 48 · TR rows 6, 24 · SR rows 2, 7 · VT rows 0, 13,
52 — 9 rows, 940 source frames, per-index comparison (cook f vs
derived frame f). Numbers: the validator recomputes every figure; reproduce with `python3 validate.py` against your own oracle captures (see README).

## Verdict table (pooled over the 9 rows)

| bar (registered) | primary (SPEC v1) | final (derived model) | bg_ema |
|---|---|---|---|
| 1. count ratio median in [0.75, 1.25] | **PASS** 0.762 | **PASS** 0.783 | FAIL 1.643 |
| 2. centroid median ≤ 0.01 | **PASS** 0.00843 | **PASS** 0.00743 | PASS 0.00634 |
| 3. size rank Spearman ≥ 0.8 | **FAIL** 0.065 | **FAIL** 0.038 | FAIL 0.050 |
| 4. lifecycle totals within 10× | **FAIL** (revivals 31×) | **FAIL** (revivals 43×) | FAIL (revivals 89×) |

maxdim and bbox_center variants are within noise of primary on
every statistic (pooled counts 0.788 / 0.762, centroids 0.00833 /
0.00844, Spearman 0.064 / 0.064, revivals 32× / 31×) — the two
SPEC §4 ambiguities they probed do not matter; the failures are
elsewhere. Bar-by-bar diagnosis below. Two of the four bars
pass pooled for the shipped derivation; two fail, both with
identified mechanisms. Per-row detail matters and is reported:
the pooled bar-1 pass is a median across rows that individually
sit on both sides of the band.

## Per-row numbers — final derived model (gauss bg, square size)

| row | world | count ratio | centroid med | Spearman | match rate |
|---|---|---|---|---|---|
| 00 | VT | 0.756 | 0.00793 | 0.037 | 0.316 |
| 13 | VT | 1.241 | 0.00767 | 0.025 | 0.374 |
| 52 | VT | 0.724 | 0.00694 | −0.023 | 0.422 |
| 02 | SR | 0.553 | 0.02221 | −0.016 | 0.126 |
| 07 | SR | 2.323 | 0.00730 | 0.036 | 0.325 |
| 06 | TR | 0.260 | 0.03034 | −0.004 | 0.047 |
| 24 | TR | 0.239 | 0.02073 | −0.017 | 0.067 |
| 12 | CP | 1.711 | 0.01564 | 0.044 | 0.300 |
| 48 | CP | 1.310 | 0.01539 | −0.100 | 0.156 |

Primary (SPEC v1) per-row counts: VT 0.706 / 0.310 / 0.779 ·
SR 0.274 / 1.820 · TR 1.520 / 0.565 · CP 0.210 / 1.335;
centroids 0.0077–0.0257; Spearman −0.086…0.074. Full grid in
`validation_numbers.json`.

## Effect equivalence (SPEC §6: graph test-1 node selection —
## blobs with age ≥ 0.5 s ranked by bbox-area × age, top 24/frame)

| row | config | nodes/frame oracle → derived | centroid dispersion oracle → derived |
|---|---|---|---|
| 02 | primary | 16.28 → 9.93 (−39%) | 0.238 → 0.283 (+19%) |
| 02 | final | 16.28 → 13.10 (−20%) | 0.238 → 0.220 (−7%) |
| 13 | primary | 19.85 → 17.08 (−14%) | 0.316 → 0.301 (−5%) |
| 13 | final | 19.85 → 16.80 (−15%) | 0.316 → 0.368 (+16%) |

Read: a downstream graph consumer fed the derived tables sees
node counts within ~15–20% (final config) and comparable
spatial dispersion — the *effect-level* behavior is much closer
than blob-level identity. The pseudo-graph layer would render
a similar graph; it would not be the same graph.

## Bar 1 — counts: PASS pooled, mixed per row (diagnosis)

VT (the clean oracle — see harness defect): final model lands
0.72–1.24× on all three rows; the background model is what
makes this possible (no-bg primary: 0.31–0.78×; binary EMA
overshoots 1.57–1.87×; the Gaussian-over-soft-matte model sits
between, as a real background subtractor should). E2 rows
scatter on both sides (0.24–2.32×) — expected under the
frame-delivery defect: when the oracle analyzed different
content than the exported index claims, per-index count
agreement is bounded by the content mismatch, not by the
derivation. Rows 06/24 (rain/trailer) undershoot at ~0.25× in
BOTH the final model and (row 24) every variant — thin streak
content the oracle's tracker resolves into far more blobs than
any matte-CC foreground produces; consistent with the TOP
splitting/merging by its own contour logic rather than by
8-connected regions.

## Bar 2 — centroids: PASS pooled, with a methodology warning

The pass is real but weak evidence. At VT densities
(1,000–2,500 blobs/frame), the registered greedy matcher
(radius 0.05) gives a median distance of **0.0100 for uniform
random points** at oracle density (measured on row 13) — the
bar sits at the chance level of its own measurement procedure.
The final model's 0.00767 on row 13 (at 1.24× oracle density;
density-adjusted chance ≈ 0.0090) is genuinely but modestly
below chance. On E2 rows the centroid medians (0.015–0.030)
fail the bar outright — again bounded by the harness defect:
the oracle positions describe content that is not at the
exported index. Treat bar 2 as: VT — weak pass; E2 —
unmeasurable against this oracle.

## Bar 3 — size rank: FAIL, mechanism identified, semantics
## corrected mid-validation

Every size statistic tried (bbox w, bbox h, bbox area,
sqrt-area, soft-area, equivalent diameter, bbox max) against
every foreground tried (raw matte, EMA bg, Gaussian bg,
inverted matte) yields pooled Spearman 0.01–0.07 — positional
partners' sizes are simply unrelated under bbox semantics.
The oracle evidence then forced a correction (SPEC addendum
A1): **the oracle's height is not measured — h = w × 848/464
exactly**, at every quantile, in every row. One-input Blob
Track reports SQUARE blobs generated from a single scalar
size; the public forum record confirms the behavior. The
shipped derivation therefore emits square sizes
(√area family). Rank correlation nevertheless stays ≈ 0.04:
even with the right *form*, the scalar the TOP reports is not
a monotone function of the current region's area/extent in any
foreground we can construct — it behaves like a property of
the TOP's internal OpenCV tracking state (per-blob size
fluctuates over a life with median CV 0.78). Honest verdict:
the size *law* is derived (square, gate on height fraction);
the size *values* are not reproduced, and bar 3 fails as
registered. Downstream impact is bounded: consumers that rank
by area × age (the graph selection) inherit size noise, yet
the effect-equivalence deltas above stay moderate because the
selection is dominated by position and age structure.

## Bar 4 — lifecycle: FAIL on revivals only (diagnosis)

Births, losses and expiries are within range for every variant
(final: 0.83× / 4.63× / 0.83×). Revivals fail everywhere
(31–89×). Presence-gap forensics (row 13): the oracle's tracks
rarely gap at all (258 gaps over 2,787 tracks; row 02's gaps
are 5–25 frames — real occlusions), while the derived tables
gap constantly (10,630 gaps over 2,793 tracks, final model),
with gap lengths clustered at 1–4 frames and an even-length
bias — detection flicker: regions alternate merged/split
across frames and the greedy associator drops and revives the
track each time. The oracle's tracker is temporally stable in
a way plain per-frame CC + NN association is not (smoother
detection and/or continuity-favoring association inside the
TOP). Identified fix direction — temporal hysteresis/coasting
in detection or association — is documented here but was NOT
adopted into the registered runs; the verdict stands as
measured. Note the counting identity (losses ≡ births +
revivals, expiries ≡ births) holds on both sides, so the
revival excess is the whole story of this bar.

## Oracle defects found (not the derivation's — flagged for
## the rig; see SPEC addendum A3/A4)

1. **E2 frame-delivery defect.** 60–78% of consecutive E2
   oracle tables are bit-identical while their source mattes
   never are; saved layer PNGs show analyzed content that is
   not the file frame at the exported index; the
   analyzed-content mapping wanders (union-matching and
   per-cook saturation tests) and cannot be recovered as a
   constant lag/rate. VT tables: 0% identical pairs, no
   symptoms. This plausibly also touched the stage-1 fields
   and layers baked into the shipped V3/V4 films.
2. **Row 53's table is degenerate** (whole-table dumps of 87
   rows under frames 1–3, 68 lines with a mangled frame field,
   DONE.txt mean 3.9/frame vs ~70/frame in the file). It was
   never in the subset; recorded so nobody calibrates on it.
3. Minor: exported tables carry
...[truncated 1872 chars]