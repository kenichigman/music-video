# PATCHING.md — supercut revision workflow

How a supercut gets revised after review. Written 2026-10-27 after the
Song Six v1→v2→v3 cycle, where every lesson below was paid for once.

## The loop

1. **The review note is the spec.** Timestamp-targeted notes ("first 3
   seconds seem off", "audio seems late 1:58–2:30") name the span.
   Never defend a render against the note; diagnose the named span.
2. **Diagnose by sequential decode only.** Extract frames by decoding
   from t=0 (or from a checkpoint) — NEVER `-ss` seeks or seek-based
   contact sheets: on this file family the mp4 demuxer seek lands a
   full GOP early, and a wrong diagnosis from seeked frames burned the
   entire v2→v3 cycle. Measure before cutting: diff profiles, onset
   tables (`supercut_qa.py`), frame grabs by decode.
3. **Rebuild the smallest frame range that covers the defect**, plus
   margins. Everything else is carried from the previous version.
4. **New versioned deliverable, always.** `<film>_vN.mp4`; the prior
   version is never overwritten or deleted (it is the fallback and the
   identity reference).
5. **Prove identity.** Decoded-frame MD5 compare across the whole film:
   0 differences outside the patch ranges; the audio stream MD5 must be
   identical (audio is copied untouched, never re-encoded).
6. **Run the QA gate** (`supercut_qa.py`) on the new version BEFORE
   it goes back to review.
7. **Version-log entry per version**: the driver notes, the diagnosis
   (with the measurements), the fix, the exact frame ranges rebuilt,
   identity/verification numbers, hashes, and the patch's wall-clock
   time.

## Assembly rules (learned the hard way, 2026-10-27)

- **mkvmerge split/append is frame-exact; ffmpeg splicing is not.**
  On this file family: ffmpeg `-ss` stream-copy landed a full GOP
  early (−4.93s), the concat demuxer produced non-monotonic DTS and
  +27 phantom frames, inpoint mode +177 frames, `-t` copy trims eat
  the boundary packet.
- mkvmerge split parts each END on the boundary keyframe (the next
  part starts one frame later). **Prove every part's true span by
  frame MD5 before assembling**, and let single boundary frames ride
  as patch margins instead of fighting single-packet extraction.
- **Margins**: patch ranges include a margin of the previous version's
  own decoded frames, re-encoded once (measured cost: PSNR min ~41.5 /
  mean ~44 dB vs the original — acceptable, and disclosed in the
  version-log entry). Stream-copied spans are bit-identical.
- **Finish params are reused verbatim** from the previous version's
  finish log (per-section WB gains + luma gain, global grade) — a patch
  must be invisible at its seams, including color.
- **Determinism check**: the patch script re-derives the prior
  version's timeline / tile library / feature drive and asserts they
  reproduce exactly (v2 patch: 48 shifts, 4000 tiles) before building
  anything on top of them.

## STANDARD 1 — Segment masters are the patching substrate

*Applies from the next production on. Adopted 2026-10-27 as a
refinement for post-render editing speed. The Kraftwerk "Home Computer"
supercut was produced under this standard.*

Every production retains its **finished 1-second segments as separate
files** alongside the spliced master. A patch then becomes: render
only the changed segments, swap the files, concat with `-c copy`.
No re-encode anywhere else — identity of untouched regions is true
**by construction**, not proven after the fact by MD5 archaeology,
and there are no re-encoded margin frames at all.

Layout, next to the master:

```
<film>_vN.mp4                     the spliced master (deliverable)
<film>_segments/
  seg_0000.mp4                    finished segment 0 (1.000s, keyint-aligned)
  seg_0001.mp4
  ...
  manifest.json
```

`manifest.json` contents (the single source of truth for the film):

```json
{
  "film": "song-six_supercut",
  "version": 1,
  "fps": 30, "width": 848, "height": 464,
  "track": {"file": "song-six_CLEAN.mp3", "span_s": [62.0, 292.52],
            "sha256": "..."},
  "sections": [{"start": 0, "end": 45, "source": "anime",
                "source_in": 100.0, "chaos": 1.30, "mosh": true}, ...],
  "bridges": [47.0, 49.4],
  "clean_windows": [[0, 6.63]],
  "finish": {"wb_strength": 0.5,
             "per_section": [{"wb": [0.934, 1.033, 1.049], "luma": 0.956}],
             "global_grade": "soft S-curve, teal shadows / warm highlights"},
  "segments": [{"file": "seg_0000.mp4", "sha256": "...", "frames": 30}],
  "audio": {"stream_md5": "...", "note": "copied untouched, never re-encoded"}
}
```

The manifest doubles as the QA gate's `--sections` input (sections,
bridges, clean windows all live there) — QA config is never re-typed
by hand for a revision.

Patch procedure under this standard:

1. Diagnose (sequential decode + QA report on the current master).
2. Re-render only the affected `seg_*.mp4` files (same EDL row, same
   finish params from the manifest; changed params are recorded as a
   manifest diff in the new version).
3. Concat segments with `-c copy`, remux the untouched audio stream.
4. Bump version, update manifest (new segment hashes, changed rows),
   QA gate, version-log entry.

**Retro-note**: Song Six v1–v4 were NOT retained this way — their
segments exist only baked into the masters, which is why v2/v3 patches
needed mkvmerge surgery, frame-MD5 span proofs, and margin frames
re-encoded once at ~44 dB PSNR. That cost is exactly what this
standard removes. Do not retrofit v1–v4; the standard binds the next
production onward.

## STANDARD 2 — Window previews for taste iterations

*Applies from the next production on. Adopted 2026-10-27 as a
refinement for post-render editing speed.*

A patch that changes **feel** — chaos level, ramp shape, phase,
detonation timing — ships FIRST as a **window preview** for review
approval:

- The preview is the patched window **plus ~2s handles on each side**
  (so the entry/exit seams are judgeable in context), cut from the
  segment masters with `-c copy` where possible.
- The reviewer approves or redirects on the preview — a couple of minutes per
  round-trip instead of a full patch cycle (render + splice + full
  verify + delivery).
- Only on approval does the full splice + identity proof + QA gate
  run, producing the new versioned master.

Defect fixes with a measured right answer (a flash insert in a clean
window, a decode error) don't need a preview — the measurement is the
spec. Taste is what previews are for: if the review note contains "seems",
"should feel", a vibe word, or a timestamped energy complaint (late /
early / too much / not enough), preview first.

## Worked example — Song Six v2→v3 (pre-standard, for the record)

- Driver: the beginning read as off (the earlier 1:58 patch was
  approved and carried over bit-exact).
- Diagnosis (sequential decode): the anime source window contains an
  internal cut at timeline frame 71 (2.37s) to a static bridge scene;
  v2's cleaned head let its P-frame repaint a legible bridge for
  frames 71–89. NOT a window shift (an earlier seek-based sheet had
  suggested one — wrong; see the evidence rule above).
- Fix: frames 0–179 rebuilt (frame-70 hold over the repaint span,
  mosaic suppressed in head, mosh ramp off seg0's clean anchor);
  180–219 = v2 margin frames; 220+ stream-copied from v2.
- Proof: frames 220–6839 MD5-identical to v2; audio MD5 identical;
  head diff profile max 3.9 in frames 1–199 (v1/v2: 59).
- QA gate on v3: decode clean, clean-window violations 0 — and the
  gate still FAILs v3 on Drop II detonation (ratio 0.41), which is
  the v4 job. A gate that passes everything proves nothing.
- Wall time: ~19 min.

## Worked example — Song Six v3→v4 (onset re-phase, pre-standard)

- Driver: the audio seemed late around 1:58–2:30, while the section
  after it was liked (Drop II, 119–162s). Editorial phase, not a mux
  defect — the audio stream is untouched in every version.
- Diagnosis (sequential decode + QA gate): the boundary cut sits at
  119s but the track's transient hits at 119.4s and the video's diff
  energy doesn't peak until ~120–121s (detonation ratio 0.41 vs the
  0.5 gate); in-section onsets trail their accents by up to +2.0s.
- Fix: frames 3570–4874 rebuilt. Detonation as plateau/crash — a
  mosaic ramp alone produces almost no frame-diff energy on this
  low-motion footage: wet 0.80→0.92 across 117.6–119.37s, crash to
  0.10 exactly at frame 3582 (the transient), transplant shock at
  3590. Onset-phased grid: forced keyframes on the six measured
  onsets (119.4 / 130.0 / 139.2 / 151.4 / 153.2 / 160.7); chaos peaks
  at 1.90 on each onset, exponential decay τ≈2.2s to a 1.32 floor;
  segments ending exactly on an onset force-moshed (build 1's
  coin-flip left a clean 6-frame segment before the 151.4 anchor and
  ate its snap — the onset table caught it, the rule fixed it).
- Proof: all 6 onsets within ±0.25s after the fix, 4 on the exact
  frame (119.4 / 151.4 / 160.7 went +0.600 / −0.400 / +0.300 →
  0.000s); diff at the hit frame 2.51 → 16.07; decoded-frame MD5
  0 diffs outside [3570, 4875); audio MD5 identical.
- QA gate on v4: PASS. Wall time: ~25 min.

## Worked example — Song Six v5 head (window preview, bookend + stretch)

- Drivers: a huge pulling sound in the first 2–3 seconds deserved
  motion — multiple-frame glitches, a felt sense of pulling and
  stretching — and the beginning should use the same clips as the
  ending, matched to it in style. A taste note, so STANDARD 2
  applies: window preview first, no full splice until approved.
- Build: 10s preview over v4's head. Bookend base: frames 0–119 are
  the film's OWN ending window (timeline frames 5490–5609, GitS
  nature @120.0s) in the ending's exact finish params, so head and
  tail rhyme. Stretch ratchet keyed to measured STFT accents (dark
  swell peaking ~0.88s; bright flux stabs at 1.30 / 1.85 / 2.35 /
  2.50 / 3.00s): frame-hold runs grow 2→3→a 6-frame freeze at 3.0s
  (max lag 0.46s at 3.17s), horizontal smear + anisotropic stretch
  scale on the same tension curve, RGB-tear bursts on each accent.
  Release from 3.45s — lag sheds at up to ~2× catch-up, terminal tear
  across frames 118–121, hard snap at frame 120 (4.0s) into v4's own
  Drop I frames, untouched to 10s.
- Verdict: preview approved on review. The full
  splice starts from the saved preview state (patch script + design
  params), never a re-derivation.
- QA gate on the preview: decode clean, PASS (flash/phase gates
  informational without a full-film manifest). Wall time: ~13 min.

## Measured patch times (honesty ledger)

Measured 2026-10-27 on pre-segment-master films: v3 head splice
~19 min wall, v4 section re-phase ~25 min, v5 taste preview ~13 min.
The 5–10 min patch figure is a design target for STANDARD 1,
UNPROVEN until a patch actually runs on retained segment masters —
do not quote it as achieved. Every new patch records its wall time
in its version-log entry (loop step 7) so the target can be checked
against evidence.
