# The supercut dataset: one pool, three films

The strongest test of a generative editor is a fixed dataset. The
supercut line of this pipeline was developed against exactly one:
a **single six-clip pool** — nature footage, a dreamlike cat clip, a
convenience-store clip, an anime clip, a second science-fiction clip,
and a black-and-white hands clip — cut into **three complete films**.
Same footage every time. Only the track, the edit, and the iteration
history differ.

| Film | Track | Status |
|------|-------|--------|
| Reference cut | — | the human-made benchmark the pipeline's grammar was reverse-engineered from |
| Song Six supercut | DEATHPACT — "Song Six" | **v5, final** — [watch on YouTube](https://youtu.be/OjZCkGFgWKY) |
| Home Computer supercut | Kraftwerk — "Home Computer" (2009 remaster) | **v3** — [watch on YouTube](https://youtu.be/Zy179vQTPJ4); v2 (in-section source rotation) superseded |

## Method

One paragraph: the track is measured first — `extract_features.py`
produces per-second energy, brightness, and spectral-flux rows for the
full duration. A conductor draft edit decision list (EDL) is then
**verified against those measured features** before anything renders;
in this dataset's productions the draft misread the tracks' arcs more
than once and was corrected or discarded in favour of the measurement
every time. `mosh_super.py` assembles the film from the verified EDL:
hard cuts at section boundaries, per-section datamosh intensity,
mosaic bridges at joins, anchor frames force-reset at cuts.
`finish_v2.py` applies the finishing pass — short smoothstep dissolves,
per-section white-balance and gain-only luma correction, and a shared
global grade so six unrelated clips read as one film.

The Home Computer v3 cut (380.80s) replaced the one-source-per-section
assembly with a **global blend plan** (`home-computer-v3/planner_v3.py`):
short 2–4s windows interleaving all six sources inside every blended
section, home-source weighted 0.50–0.70, window boundaries snapped to
measured flux accents, and guest windows allocated from a central
ledger that asserts no source window is used twice anywhere in the
film. Assembly ran on retained one-second segment masters (381
segments plus a manifest, `assemble_v3.py` / `build_manifest.py`), so
v2's praised spans could be substituted into v3 verbatim — bit-
identical by construction. A QA catch during planning (guest windows
reintroducing a character the director had cut) was fixed in the plan
itself before rendering (`patch_plan.py`); the v3 phase gate
(`qa_v3.py`) adds a dead-stretch check on top of the standing gate.

## The QA gate

No render ships on vibes. `supercut_qa.py` is a standing pre-delivery
gate built from defects that review caught by eye and ear first, each
converted into a mechanical check: a full error-free decode, a
flash/insert test inside manifest-declared clean windows, a
drop-boundary detonation test (the cut must arrive with the
transient, not ramp up after it), and a head contact sheet for visual
review. Its calibration standard is strict: it fails early versions
of these films for exactly the defects human review flagged, and it
passes the versions review approved. Frame evidence inside the gate is
sequential-decode only — seeked frame grabs on this file family land
a full GOP early and once produced a completely wrong diagnosis.

## Iteration discipline

Revisions are surgical, never re-renders — see `PATCHING.md` for the
full workflow. The essentials: the review note is the spec; diagnose
by measurement before cutting; rebuild the smallest frame range that
covers the defect; prove everything outside the patch is identical
(decoded-frame hashes, audio stream untouched); retain **segment
masters** — the finished one-second segments plus a manifest — so a
later patch is a segment swap and a stream-copy concat, with identity
of untouched regions true by construction. Taste changes ship first
as short window previews for approval; measured defect fixes do not
wait for one. Every version is kept, and every patch logs its
wall-clock time: on pre-segment-master films the Song Six revisions
measured ~13–25 minutes each, against a 5–10 minute design target
that stays labelled unproven until a patch on retained masters
measures it.

The pipeline was built and iterated by a cloud agent head under
human direction, with human review as the final gate on every version
that shipped.
