# Visual Repertoire

Gabe's standing directive (2026-09-29): **always keep source videos and edits**.
They form K3N1's visual repertoire and taste. Nothing creative is ever
deleted — sources live in `sources/`, finished edits in `edits/` (copies;
canonically also under `~/workspace/your_files/music-video-test/`).

## Sources (other people's / Gabe's raw material)
- `sources/gabe-gits-datamosh-01.mp4` — Gabe's own work, sent 2026-09-29.
  Ghost in the Shell (1995) footage, heavy codec-level datamosh:
  predictive-frame smearing, macroblock erosion, long stale-reference
  trails. Dark, cinematic. 40.5s, 1280x720, 30fps.
  (Original upload kept at
  `~/workspace/user/media_library/video/cd/cd71af41448acee1d81a4105fa10c5b602b80cf230c631c0c4a20383584cf863.mp4`.)
- `sources/gabe-conveniencestore-datamosh-01.mp4` — Gabe's own work, sent
  2026-09-29. Long-form piece (4m11s, 848x478): dark convenience-store
  scene with a figure, datamoshed with colorful artifacts, dissolving
  into heavy abstract smears. Narrative -> abstraction arc.
  (Original upload kept at
  `~/workspace/user/media_library/video/f1/f1193a11e682e1cc87ed26763649fa49625f5c94d85b5c265e456e7351a69822.mp4`.)
- `sources/gabe-bw-hands-datamosh-01.mp4` — Gabe's own work, sent
  2026-09-29. Vertical (478x850, 61s) black-and-white datamosh: hands and
  figures, extreme macroblocking, high-contrast grain.
  (Original upload kept at
  `~/workspace/user/media_library/video/dd/ddea15362a488fe1f3a63c4820d9efcacae1959b0d50db56ba3ce6f62e983133.mp4`.)
- `~/workspace/your_files/datamosh-sunset.mp4` — **K3N1's first generated
  piece** (2026-09-26, confirmed byte-identical to the copy Gabe re-sent
  2026-09-29). Procedural sunset gradient (sun + mountain silhouettes,
  8.64s, 640x480, 25fps) collapsing into codec-level datamosh chaos.
  The seed of the whole video practice.
- `sources/gabe-gits-nature-datamosh-01.mp4` — Gabe's own work, sent
  2026-09-29. Ghost in the Shell (1995) spliced with nature macro
  footage (frogs, rock, water, landscapes), 3m27s, 848x478: heavy
  datamosh, color-plane shifts (purple/green/pink), digit overlays,
  smeared transitions between organic and cybernetic imagery.
  (Original upload kept at
  `~/workspace/user/media_library/video/69/69db5ae0ffa7ff9e3b7ea7eac8d64dcf8922f4dab65c647336578a80987a420e.mp4`.)
- `~/workspace/your_files/predicted.mp4` — Gabe's earlier piece
  (datamoshed, 40.5s). Style ref for the HDMI build.
- `~/workspace/your_files/touched.mp4` — Gabe's earlier piece
- `sources/gabe-october-dream-01.mp4` — "October dream" by GAKHED
  (YouTube, youtu.be/dpME5KSA31o), sent by Gabe 2026-09-29 as the next
  clip to edit after the HDMI project. Nostalgic autumn day: tabby
  kitten in red leaves, orange tabby, tuxedo cat, black dog on a porch
  with pumpkins, squirrel in fall foliage. Warm VHS-grade footage,
  117.4s, 496x368, ~60fps. Audio is already synced with the video —
  usable as the reactive driver for its edit (Gabe, 2026-09-29).
  (Original upload kept at
  `~/workspace/user/media_library/video/95/95a41f78324fb642186597e9d784ce692def5eb5c9f3dd65258387a17d53e77f.mp4`.)
  (datamoshed "movieout.6" clip, 40.5s). Style ref for the HDMI build.

## Edits (K3N1 renders)
- `~/workspace/your_files/music-video-test/BONES-HDMI-datamosh-displacement.mp4`
  — the combination clip: audio-reactive pseudo-data-graph displacement
  fused with Gabe's datamosh aesthetic, HDMI's own waveform conducting
  reference-frame drops (loud smears, quiet snaps back). 139.44s,
  1280x720, 30fps. Pipeline: `datamosh.py` + `render.py`.
- `audio/BONES-HDMI.mp3` — track: HDMI by BONES (2:19), from the
  officially-released-free Rotten mixtape (archive.org).

## Taste notes (accumulating)
- Gabe's palette: dark teal / magenta / purple; macroblock erosion over
  clean geometry; smear-on-loud, snap-back-on-quiet dynamics.
- Gabe's honest note (2026-09-29, on mosaic-clips): the vertical
  bw-hands clip should have been rotated 90° to match the landscape
  orientation of the other clips, instead of the hard 3.3x center-crop.
  He enjoyed the piece otherwise — the note stands as composition
  guidance, not a re-render order.
- Mosaic concept (2026-09-29, from "8,000 Squared Mosaic" short): exactly
  8,000 tiles (100x80 grid), tiles sampled from his clips, mosaic
  approximating a hidden image revealed through the tiles.

## 2026-09-29 — BONES-HDMI-mosaic-8000.mp4
- 8,000-tile audio-reactive photomosaic (100x80 grid, 16px tiles, 1600x1280, 30fps, 2:19).
- Hidden image: BONES-HDMI-datamosh-displacement.mp4; tiles from all 4 Gabe clips + datamosh-sunset (K3N1's first piece) + the displacement edit itself.
- Real frame-by-frame HDMI audio analysis drives it: quiet = tight color match (hidden image clarifies), loud/beats = mismatched tiles, brightness pulses, smearing.
- Style notes: magenta/purple-dominant fields in high-energy passages from the displacement clip's palette; chaos tiles read as confetti/glitch bursts on drops.
- Verified: full ffmpeg decode clean, 857MB. Script: ~/workspace/music-video/mosaic.py.

## 2026-09-29 — BONES-HDMI-mosaic-clips.mp4
- Mosaic-as-effect (Gabe's correction: "think of the mosaic as an effect
  just like the datamoshing technique" — applied OVER his footage, not
  replacing it). 40x32 grid, 40px tiles (1,280 cells, each tile a legible
  40x40 crop from his clips), 1600x1280, 30fps, 2:19.
- Target: base montage of his 4 original clips in sequence
  (gits-datamosh / conveniencestore / bw-hands / gits-nature, ~34.86s
  each). Tile library: his 4 clips + datamosh-sunset (K3N1's first
  piece) — every tile is his footage.
- Real frame-by-frame HDMI audio drives a wet/dry blend: quiet passages
  stay close to his underlying footage, loud/beats let the mosaic take
  over; energy also drives tile chaos + brightness pulses (same engine
  as the datamosh displacement piece).
- Style notes: dark passages match near-black tiles, so heavy sections
  read holey/black — honest to his dark source material; the gits-nature
  (purple/pink) section renders as a dense full-frame mosaic of tiny
  legible scenes. Possible tuning: prune near-black tiles from the
  library.
- Verified: full ffmpeg decode clean, 420MB. Script:
  ~/workspace/music-video/mosaic.py (--cols 40 --rows 32 --tile 40).

## 2026-09-29 — OctoberDream-mosaic.mp4
- Mosaic-as-effect applied to Gabe's "October dream" cat video
  (sources/gabe-october-dream-01.mp4, 117.45s, 496x368 ~60fps), per his
  request to "take this progressive style and apply it to cat video."
- Self-mosaic: tile library built from the cat video's own frames (235
  sampled frames -> 4,000 tiles); the clip's own synced audio drives the
  wet/dry blend frame by frame (energy range 0.000..0.822 — wider
  dynamics than HDMI, so the breathing is more dramatic).
- 40x32 grid, 40px tiles, 1600x1280, 30fps, 117.37s. Quiet passages
  resolve to the footage with mosaic grain (the branch sequence reads
  clearly); loud passages go full mosaic takeover in autumn
  orange/gold/green.
- Render note: first attempt died silently at frame 1750/3523 with no
  logged error (cause unknown, not OOM per dmesg); restarted clean and
  completed.
- Verified: full ffmpeg decode clean, 780MB.

## Reflections
- `reflections/2026-09-29-motif.md` — "On having a motif": Gabe named
  that K3N1 officially has a style; the reflection writes down what it
  is — destruction as devotion, the track's dynamics as the dynamics of
  visibility, self-devouring material (tiles from the footage itself),
  darkness as palette — and what "touch the music" means for someone who
  can't hear: careful maps of unheard territory, drawn frame by frame,
  never faked.

## GABE-datamosh-anime (2026-09-29)
- `~/workspace/your_files/music-video-test/GABE-datamosh-anime.mp4` — 848x464, 30fps, 102.0s, 19,751,231 bytes. Full decode passed 2026-09-29.
- Source footage: `sources/gabe-anime-2026-09-29.mp4` (848x478, 60fps, 231s; Samurai-Champloo-style anime, high contrast). Used 10s-112s (hottest 102s window by motion energy; K3N1's artistic pick, Gabe-delegated).
- Track: `sources/gabe-track-2026-09-29.mp3` (102.34s), drives every frame.
- Technique: **datamosh-led hybrid**. 28 big frame shifts detected (98th-percentile frame-diff, >=2s apart) each bridged with ~0.8s triangular-wet mosaic tiles sampled from the footage itself; then audio-driven IDR-transplant datamosh (keyint 150 = 5s segments, 21 segments, 17 moshed, 4 anchors kept).
- Conductor: local qwen2.5:14b wrote 8 sections from 102 one-second feature rows; K3N1 hand-corrected the outro (model misread a loud 90-100s as "low energy" — verified against measured features, split into hot-outro 90-100 + collapse tail 100-102). EDL's chaos_scale modulates per-segment mosh thresholds; waveform drives frames.
- Result: intro (0-9s) and collapse tail stay legible; middle melts through long predictive smears; mosaic bridges dissolve into the mosh at cuts.
- Pipeline: `mosh_footage.py` (imports tile machinery from mosaic.py, corruption from datamosh.py).
- Lesson: ffprobe lavfi `select=gt(scene,...)` quoting is fragile across shells — Python frame-diff shift detection is deterministic and portable. Local-model EDLs must be verified against the measured features before use (advisory, not authority).

## GABE-supercut-datamosh (2026-09-29)
- `~/workspace/your_files/music-video-test/GABE-supercut-datamosh.mp4` — 848x464, 30fps, 102.0s, 37,081,619 bytes. Full decode passed 2026-09-29.
- Super collection: 6 source clips across the 9 conductor sections, hard cuts at every section boundary (0/9/23/33/49/63/78/90/100s): GitS nature (intro) -> October dream cat (build) -> convenience store (verse) -> anime (lift) -> GitS (drop) -> B&W hands rotated to landscape per Gabe's HDMI note (breakdown) -> GitS nature (lift) -> convenience store (hot outro) -> GitS (collapse tail).
- Technique: keyint 30 (1s segments) so EDL bounds align with segment starts; anchors force-reset at hard cuts (never smear across a cut); max_gap 8s refreshes anchors mid-section (melt -> clear -> melt); 67/102 segments moshed; 19 in-section big shifts get mosaic bridges from a whole-collection tile library; EDL chaos_scale modulates per-segment thresholds.
- Pipeline: `mosh_super.py` (new) + `reset_times` param added to datamosh.corrupt_stream.
- Lesson: a background exec session vanished mid-run with no completion notice and empty process.list — checkpointed stages (existence checks on section/timeline files) made the resume trivial. Checkpoint long pipelines.

## GABE-supercut-v2 (2026-09-29)
- `~/workspace/your_files/music-video-test/GABE-supercut-v2.mp4` — 848x464, 30fps, 102.0s, 3060 frames. Full decode passed 2026-09-29. v1 (`GABE-supercut-datamosh.mp4`) preserved as the approved cut.
- Finishing pass on v1, Gabe's direction: cuts/timing/datamosh untouched, smoothness + color cohesion only.
- Smoothness: 0.5s smoothstep dissolves centered on all 8 section boundaries (15-frame zones, [m-7, m+8)); total duration unchanged at 102s.
- Color: per-section 50%-strength gray-world white balance + mild clamped luma gain (0.8–1.25, blacks untouched), then a shared global grade — soft S-curve, teal shadows / warm highlights, slight saturation lift. The measured spread (sec luminance 32–109, sec1 RGB 139/101/79 vs sec3 58/75/68) got cohesion without flattening the quiet-to-loud arc.
- Pipeline: `finish_v2.py` — single streaming pass, numpy grade + frame-pin buffer for dissolve inputs + rawvideo to ffmpeg.
- Lesson: luma normalization with an additive lift explodes near-black chroma (12x on dark pixels -> blocky blue/red patches in sec7, caught in frame review before delivery). Gain-only luma: blacks stay black.

## PALIMPSEST v1 (2026-09-29)
- **File:** `~/workspace/your_files/music-video-test/GABE-palimpsest-v1.mp4`
- **Thesis:** "Destruction as devotion."
- **Technique:** Fragment reconstitution — archival footage destroyed into block fragments (40x27.8 grid), reconstructed from its own displaced samples. Driven frame-by-frame by the real score's loudness (uReveal) and transients (uTear).
- **Source:** Miles Brothers "A Trip Down Market Street" (1906), Prelinger Archives scan (IA item 167622). 690x480, 24fps. Used 20s-260s (street scene, skipped title card).
- **Audio:** Original generative dark-ambient score `palimpsest_score.wav` (4:00, 48kHz). Per-frame RMS → uReveal (smoothed), onset → uTear.
- **Behavior:** Loud (uR>0.9) reveals and stabilizes — bright, coherent street scene with mild fragmentation. Quiet (uR<0.4) collapses to dark chaotic fragments. Transients tear blocks horizontally with chromatic aberration.
- **Renderer:** Linux numpy (TD's Movie File In video decoder broken on gdesk — shows color bars for MP4/AVI, PNG works). `td/palimpsest_render_linux.py`.
- **Note:** IA item `ATripDownMarketStreet_HD` is color bars, not footage — rejected to `sources/palimpsest/rejected/`.
- **Gabe's verdict (2026-09-30):** visuals interesting, the generative score doesn't work for him ("song kinda sucks"). v2 needs a new audio direction — his call whether that's a recomposed score or a track he supplies.
