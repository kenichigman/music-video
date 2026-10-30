# BLOB TRACK TOP — DERIVATION SPEC
Clean-room behavioral derivation of Derivative's Blob Track TOP,
as used by the the reference production rig (blobnet / TDeffectPool). Written
BEFORE the implementation, from observed I/O only: the upstream
build script (`agentic-touchdesigner-harness/build_blob_network.py`), the stage-1 oracle tables
(the stage-1 oracle tables (59 shot rows)), the capture
harness (the per-row capture commands), and the public
parameter documentation summarized in a public research summary.
No Derivative binary was inspected or decompiled. The derivation
exists so the browser port owns its tracking front-end: this spec
+ the numpy reference implementation (`blobtrack.py`, this directory) are what the JS port follows. TouchDesigner
stays as oracle and fallback until the bars below pass.

## 1. The oracle contract (observed)

Upstream chain (per the harness build script, verified live at capture):
  movie -> Level TOP (contrast 1.35) -> Threshold TOP
  (threshold T, smooth 0.10) -> Blob Track TOP (minblobsize,
  maxblobsize 0.9, maxmovedistance 0.25) -> Info DAT.
Capture state per world: E2 (CP/TR/SR) T=0.22, min 0.0015;
VT T=0.35, min 0.004. The tracker is reset (resetpulse) per row.
Processing geometry is the source movie's: 848x464 for every rig
row (sizes in the oracle tables quantize to 1/848 and 1/464).

Output — the exported table (tracks.csv), one line per blob the
tracker reports on that source frame, NO header:
  frame,id,u,v,width,height,age
- frame: 0-based source-frame index (row-local).
- id: tracker-issued integer identity, stable across the row.
- u,v: blob position, normalized frame coordinates.
- width,height: blob bounding-box extents as frame fractions
  (w = px/848, h = px/464 at rig geometry).
- age: seconds (semantics in §2).
The full Info DAT also carries active/revived/lost/expired/
lost_time/expired_time columns; the stage-1 export wrote only the
7 columns above, so tracks.csv is the contract the derivation
must reproduce byte-compatibly in schema and units. (The derived
module additionally exposes its internal lifecycle so a full
12-column table CAN be emitted; that is an extension, not the
contract.)

Measured oracle semantics (evidence gathered the initial build from the
59 oracle tables; this is the behavior to reproduce):
- AGE: a newborn's first reported age is 0.0; age increases by
  exactly 1/60 per frame thereafter — the TD timeline rate,
  independent of source fps (24 fps E2 and 60 fps VT rows both
  step 0.016667). Age NEVER decreases, and it keeps counting
  while a blob is lost: on revival after a gap of g absent
  frames, age has advanced by exactly (g+1)/60 (verified on all
  12 revivals in row02). I.e. age(f) = (f - birth_frame)/60.
- LIFECYCLE / EXPORT: the export lists only blobs the tracker
  reports that frame. Ids disappear for gaps of 1..25+ frames
  and return with the SAME id and continuous age (revivals are
  real; the tracker retains lost identities internally for at
  least ~0.45 s of cooks). Ids are issued roughly monotonically;
  a few ids are skipped (issued to blobs never exported) and
  ids are never reused within a row.
- SIZE GATE: across 789k VT oracle blobs (min 0.004), ZERO have
  height < minblobsize while ~60% have width < minblobsize;
  across E2 rows (min 0.0015) neither dimension ever violates
  the min. The gate therefore binds on the blob's HEIGHT (in
  v-fraction), equivalently on max(w,h) for every observed blob
  (no observed blob separates the two rules; §4 pre-declares
  both candidate semantics). Maximum extents observed: w 0.73,
  h 0.61 on E2 rows.
- NO OPERATIVE BACKGROUND ABSORPTION at row scale: although the
  TOP documents a "learned background" (the reset par clears
  it), perfectly static matte features persist as blobs for
  entire rows (row02: ids with max displacement 0.0 over 61 of
  72 frames; row06/07/24 show the same pattern). Whatever the
  background register does, it does not remove static bright
  regions within a row's timespan. The derivation therefore
  models detection as matte-driven (§3), with background modes
  carried as declared variants (§4), defaulting OFF.
- KNOWN ORACLE ARTIFACTS (accepted divergences, not targets):
  (a) frame 0 of each row is a capture-harness warmup frame —
  counts are unrepresentative (row02: 14 vs ~159 steady) and
  ages arrive pre-warmed up to 0.2 s from setup cooks;
  (b) 12 of 343k rows in row00 report h = w x aspect (1.8276)
  instead of a v-fraction — a rare internal quirk;
  (c) positions/extents carry sub-pixel values not on the
  pixel grid (the TOP's internal analysis is not a naive
  pixel-grid labeling).

## 2. Derived subset (what we implement — and what we don't)

IN: luminance matte with contrast -> soft threshold ->
binarize -> connected components -> size gate -> per-frame
association (max move distance) with lifecycle bookkeeping
(active / lost / revived / expired) -> age per §1.
OUT: tracks.csv (7 columns, oracle schema/units) per input
sequence; optional full-lifecycle table as an extension.
NOT derived: the TOP's render output (ID-map image), Draw Blob
Bounds, and any parameter the rig never used. The instancing /
layer machinery downstream of the table is ours already and is
not part of this derivation.

## 3. Derived algorithm (pipeline, in order)

1. DECODE the input video at native resolution; optionally
   downscale by RES_SCALE (browser cost dial; rig work at 1.0).
2. LUMINANCE Y = 0.299R + 0.587G + 0.114B (Rec.601). The
   oracle's Level contrast is affine per channel and luminance
   is linear, so applying contrast to Y is identical to the
   oracle's per-channel order: Y' = clamp((Y-0.5)*CONTRAST+0.5).
3. MATTE: soft threshold with smoothstep over
   [T - SMOOTH/2, T + SMOOTH/2]; binary mask M = (soft >= 0.5),
   which is exactly Y' >= T. (The soft matte's fractional band
   is retained only if a future consumer needs it.)
4. BACKGROUND: default OFF (per §1 evidence). Variants in §4.
5. COMPONENTS: connected components of M (CC_CONNECTIVITY=8).
   Per component: pixel count, bbox (w,h as frame fractions),
   centroid (mean pixel position, in (u,v)), bbox center.
6. SIZE GATE: keep components whose SIZE_MEASURE (see §4;
   primary: max(w,h)) is >= MIN_BLOB_SIZE and <= MAX_BLOB_SIZE.
   NOTE from the oracle evidence: whatever the measure, in
   practice the gate's teeth are the height test.
7. ASSOCIATION: between the previous frame's known tracks
   (active, plus lost tracks still inside their expiry window)
   and this frame's gated components: greedy nearest-neighbor
   on (u,v) Euclidean distance, ascending, one-to-one, matches
   only within MAX_MOVE_DISTANCE. A component matching a LOST
   track is a REVIVAL (same id). Unmatched components are
   BIRTHS (new monotone ids). Unmatched active tracks become
   LOST (not exported while lost). A lost track unrevived for
   EXPIRED_TIME_S of timeline time becomes EXPIRED and is
   forgotten. Known tracks' reported positions are THIS frame's
   component measurements (no smoothing — the oracle's
   positions are per-frame measurements).
8. AGE: age(f) = (f - birth_frame) / TIMELINE_FPS with
   TIMELINE_FPS = 60 (the oracle's timeline rate), counting
   lost frames, never decreasing. Newborns report 0.0.
9. EMIT per frame, for each ACTIVE track, the 7-column row in
   oracle format; lifecycle events are counted for the sidecar.

## 4. Pre-declared candidate semantics (resolved by validation)

The oracle's internals leave three choices underdetermined by
passive observation. All three are declared HERE, before the
build; validation reports EVERY variant's numbers, ships the
best-fitting, and the choice is documented in VALIDATION.md.
This is implementation tuning against fixed bars (§5), not bar
movement.
- CENTER_MODE in {centroid, bbox_center}: what (u,v) reports.
  Primary hypothesis: centroid (oracle positions are sub-pixel
  in both axes, including for 2-px blobs whose bbox center
  would sit on the half-pixel grid).
- SIZE_MEASURE in {height, max_dim}: the size gate's measure.
  Primary: height (the only dimension never violated).
- BG_MODE in {off, ema}: background register. Primary: off
  (§1 static-persistence evidence). EMA variant: per-pixel
  exponential average of M at BG_LEARN_RATE, foreground =
  M AND (bg < 0.5).

## 5. Parameters (named cost drivers — standing browser rule)

All cost drivers are named parameters of the module; nothing
desktop-tuned is hard-coded. Desktop values are the rig's
calibrated ones; the mobile preset is RECORDED here (not
rendered) for the browser port.

  parameter          desktop        mobile (recorded)   notes
  RES_SCALE          1.0            0.5                 working-res dial
  MATTE_THRESHOLD    0.22 E2/0.35 VT  same              content calibration, not a tier dial
  CONTRAST           1.35           1.35
  THRESHOLD_SMOOTH   0.10           0.10
  MIN_BLOB_SIZE      0.0015 E2 /    0.003 / 0.008       coarser grid -> larger floor
                     0.004 VT
  MAX_BLOB_SIZE      0.9            0.9
  MAX_MOVE_DISTANCE  0.25           0.25                (u,v) units
  EXPIRED_TIME_S     0.5            0.5                 at TIMELINE_FPS
  TIMELINE_FPS       60             60                  age rate (oracle semantic)
  CC_CONNECTIVITY    8              8
  MAX_BLOBS_PER_FRAME none          800                 cost guard; largest kept
  BG_MODE            off            off                 §4 variant
  BG_LEARN_RATE      0.02           0.02                only if BG_MODE=ema

## 6. Validation protocol + PRE-REGISTERED BARS

Calibration subset (spans all four worlds; stage-1 oracle
inputs src.mp4 + oracle tracks.csv):
  CP rows 12, 48 | TR rows 6, 24 | SR rows 2, 7 |
  VT rows 0, 13, 52   (9 rows, 940 source frames)
Derived tables are produced per row with that world's desktop
settings (E2: T=0.22/min 0.0015; VT: T=0.35/min 0.004).

Matching (for the centroid and size bars): per frame, greedy
nearest-neighbor between oracle and derived (u,v) sets, radius
0.05, one-to-one. Match rate is reported as context, not a bar.

Lifecycle events (counted IDENTICALLY on both tables from
presence sequences alone): birth = an id's first appearance;
loss = present at f, absent at f+1; revival = appearance after
>=1 absent frame; expiry = a loss never followed by a revival
in the table (every loss is either revived or expired).

THE BARS (registered verbatim from the derivation brief —
they do not move after results are seen):
  1. Median per-frame blob-count agreement within +/-25%
     (per-frame ratio derived/oracle, median over all frames
     of the subset; per-row medians reported for diagnosis).
  2. Matched-blob centroid median distance <= 0.01 in (u,v).
  3. Blob-size rank correlation >= 0.8 (Spearman, over matched
     pairs; size = bbox area w*h, computed identically on both
     tables).
  4. Lifecycle event totals within one order of magnitude
     (pooled totals per event type; ratio within [0.1, 10]).

Effect-equivalence check (reported delta, no bar): the graph
test-1 style node selection — per frame, blobs with age >=
0.5 s ranked by bbox-area x age, top 24 — computed on rows 02
and 13 from oracle vs derived tables. Statistics: mean
selected nodes/frame and mean centroid dispersion of the
selected set (mean distance to the set centroid). Both deltas
reported.

If a bar fails, VALIDATION.md says so and diagnoses; the
implementation may be tuned and re-run, the bars may not.

---

## ADDENDUM (post-validation, the initial build — discoveries, NOT
## amendments: the registered text above stands as written,
## including the bars; this section records what the oracle
## turned out to actually do, per VALIDATION.md)

A1. SQUARE-SIZE LAW. The oracle's (width, height) are not two
measurements: h == w x (848/464) holds exactly across the
tables (median ratio 1.8276 = frame aspect at every quantile).
One-input mode reports SQUARE blobs generated from a single
scalar size s (pixels): width = s/848, height = s/464. The
public forum record concurs ("with just 1 input the blobs are
always square"; a second 'background image' input yields true
rectangles). Section 1's "12 aspect-quirk rows" were this law,
not a quirk. The SPEC v1 independent-bbox size semantics is
therefore falsified as oracle semantics; blobtrack.py carries
it as `size_source='bbox'` for the record and the square
family (`square_sqrt_area` etc.) as the derived semantics.
Size-gate evidence under the law: min gate binds on s/464
(the height fraction), max gate on s/848.

A2. BACKGROUND MODEL. The TOP's detection is OpenCV-based
(Derivative staff, forum record). A per-pixel running
Gaussian background over the SOFT matte (the Threshold TOP's
output the TOP actually receives) fits the VT tables
materially better than no background model and better than
the binary EMA candidate: VT per-frame counts and
nearest-neighbor centroid distances enter the registered
bars' range on the healthy VT rows; the binary-EMA variant
overshoots counts ~1.8x. Registered as BG candidate 'gauss'
in the module (history/sigma parameters exposed).

A3. ORACLE HARNESS DEFECT (E2 rows). The E2 captures are not
a clean per-file-frame record: 60-78% of consecutive exported
table pairs are bit-identical while the source mattes never
are; layer PNGs show analyzed content that is not the file
frame at the exported index; the analyzed-content mapping
wanders and is not recoverable as a constant lag/rate from
the saved artifacts. VT tables show none of these symptoms
(0% identical pairs). Verdicts in VALIDATION.md are therefore
reported per world, with VT as the clean judge of the
derivation and E2 read as oracle-limited. The same defect
plausibly touched the stage-1 fields/layers baked into the
shipped V3/V4 films — flagged upstream; not this task's fix.

A4. ROW 53's oracle table is degenerate (349 lines for 72
frames; whole-table dumps of 87 rows under frames 1-3, a
mangled frame field on 68 lines; DONE.txt mean 3.9/frame
against ~70/frame in the file's head frames) and is excluded
from calibration; it was never in the registered subset.

A5. SHIPPED DEFAULTS. blobtrack.py's defaults embody the
derived model (bg_mode='gauss', bg_history=200,
size_source='square_sqrt_area'); the SPEC v1 semantics remain
selectable (bg_mode='off', size_source='bbox'). The registered
validation (VALIDATION.md) reports both, explicitly.
