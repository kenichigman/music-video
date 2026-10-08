# TouchDesigner Scripted-Network Reference (PALIMPSEST)

**Source standard:** `docs.derivative.ca` operator pages + Python class pages, researched 2026-09-29. Third-party sources noted where used. Anything not directly verified on an official page is marked **uncertain**.

## The create() rule — verified official

`docs.derivative.ca/COMP_Class`, `create(opType, name, initialize=True)`:

> "opType can be a specific type object, example `waveCHOP`, or it can be a string `'waveCHOP'`. If given an actual instance of a node `n`, these can be accessed via `type(n)` and `n.OPType` respectively."

So the string form is the class name minus `_Class` (the `opType` string). The table below uses that exact form. Class names were confirmed on the docs pages themselves; entries where the class name was **not** directly seen are marked **uncertain**.

| Operator | `parent.create()` string | Basis |
|---|---|---|
| Movie File In TOP | `'moviefileinTOP'` | class `moviefileinTOP_Class` seen |
| Audio File In CHOP | `'audiofileinCHOP'` | class `audiofileinCHOP_Class` seen |
| Envelope CHOP | `'envelopeCHOP'` | class `envelopeCHOP_Class` seen |
| Trigger CHOP | `'triggerCHOP'` | cargo opType `trigger`; class not directly seen — **uncertain** |
| Lag CHOP | `'lagCHOP'` | cargo opType `lag`; class not directly seen — **uncertain** |
| Limit CHOP | `'limitCHOP'` | cargo opType `limit`; class not directly seen — **uncertain** (note: the *new* Limit TOP is `limitTOP`, different op) |
| Filter CHOP | `'filterCHOP'` | class `filterCHOP_Class` seen |
| Audio Filter CHOP | `'audiofilterCHOP'` | class `audiofilterCHOP_Class` seen |
| Math CHOP | `'mathCHOP'` | class `mathCHOP_Class` seen |
| Noise TOP | `'noiseTOP'` | **uncertain** — class not directly seen |
| Resolution TOP | `'resolutionTOP'` | class `resolutionTOP_Class` seen |
| Displace TOP | `'displaceTOP'` | class `displaceTOP_Class` seen |
| Threshold TOP | `'thresholdTOP'` | class `thresholdTOP_Class` seen |
| Blur TOP | `'blurTOP'` | **uncertain** — class not directly seen |
| Composite TOP | `'compositeTOP'` | class `compositeTOP_Class` seen |
| Blob Track TOP | `'blobtrackTOP'` | cargo opType `blobtrack`; class not directly seen — **uncertain** |
| Feedback TOP | `'feedbackTOP'` | **uncertain** — class not directly seen |
| Level TOP | `'levelTOP'` | class `levelTOP_Class` seen |
| Movie File Out TOP | `'moviefileoutTOP'` | class `moviefileoutTOP_Class` seen |
| Info CHOP | `'infoCHOP'` | **uncertain** — class not directly seen |
| Rename CHOP | `'renameCHOP'` | **uncertain** — class not directly seen |
| Time COMP | `'timeCOMP'` | class `timeCOMP_Class` seen (`docs.derivative.ca/Time_COMP`) |

Practical note (field-verified, third-party): in a DAT scope, `from td import *` injects type objects so `parent.create(moviefileinTOP, 'name')` also works; **not into imported `.py` modules** — those must `import td` and use `td.moviefileinTOP`.

## Media and audio — parameters

**Movie File In TOP** (`docs.derivative.ca/Movie_File_In_TOP`)
- `par.file` — path to video
- `par.play` — 0/1
- `par.playmode = 'locked'` — Locked to Timeline. Other values: `'specify'`, `'sequential'`, `'timecodeop'`

**Audio File In CHOP** (`derivative.ca/solr/audio-file-chop` — wiki search page, not a full docs page)
- `par.file`, `par.play`, `par.playmode = 'locked'` — other values: `'specify'`, `'sequential'`. In locked mode Play/Reset/Speed/Index are disabled (playback follows timeline).

**Time COMP** (`docs.derivative.ca/Time_COMP`, class `timeCOMP_Class`) — the timeline driver
- `par.play` (0 = stop, 1 = play)
- `par.rate` — fps
- `par.start`, `par.end` — overall frame range
- `par.rangelimit`: `'loop'` or `'hold'` — use `'hold'` so the 4-minute render stops dead at the end
- `par.rangestart`, `par.rangeend` — working range
- `par.tempo`, `par.signature1`, `par.signature2`
- `par.independent` — run independently of parent timelines
- Python members: `frame`, `fraction`, `seconds`, `rate`, `play`, `timecode`, `start`, `end`, `rangeStart`, `rangeEnd`, `loop`, `independent`, `tempo`
- Note: a Time COMP is a cloned network; "The Time Component's network can be modified if the path in the Clone parameter is removed."

**Envelope CHOP** (`docs.derivative.ca/Envelope_CHOP`) — envelope *analysis* of audio, not an ADSR. No attack/release.
- `par.method`: `'exp'` or `'window'`
- `par.bounds`: `'mag'`, `'power'`, `'min'`, `'max'`
- `par.width`, `par.widthunit`
- `par.interp`: `'none'`, `'linear'`, `'cubic'`
- `par.norm`, `par.resample`, `par.samplerate`

**Trigger CHOP** (`docs.derivative.ca/Trigger_CHOP`) — the ADSR, driven by a trigger channel
- `par.threshup` — trigger threshold; `par.threshdown` — release threshold
- `par.threshold` — only the "Release = Trigger Threshold" toggle (not the threshold itself)
- `par.attack`, `par.release`, `par.attackunit`, `par.releaseunit`

**Lag CHOP** (`docs.derivative.ca/Lag_CHOP`)
- `par.lag1` (lag up), `par.lag2` (lag down), `par.lagunit`

**Limit CHOP** (`docs.derivative.ca/Limit_CHOP`) — clamp to [0,1]:
- `par.type = 'clamp'`, `par.min = 0`, `par.max = 1`

**Audio Filter CHOP** (`docs.derivative.ca/Audio_Filter_CHOP`) — the frequency-domain filter
- `par.filter`: `'lowpass'`, `'highpass'`, `'bandpass'`, `'bandreject'`
- `par.units`: `'logarithmic'` or `'frequency'`
- `par.cutofflog`, `par.cutofffrequency`, `par.resonance`, `par.rolloff`, `par.drywet`
- Regular Filter CHOP (neighbor-sample smoothing, distinct op): class `filterCHOP_Class` seen; its exact menus remain **uncertain**

**Math CHOP** (`derivative.ca/UserGuide/Math_CHOP`)
- Combine channels within each input: `par.chanop = 'add'|'sub'|'mul'|'div'|'avg'|'min'|'max'|'len'|'off'`
- Combine input CHOPs: `par.chopop = 'add'|'sub'|'mul'|'div'|'avg'|'min'|'max'|'off'`
- Constant multiplication via `par.gain` — **uncertain**, not verified on the official page

**Rename CHOP** — **not doc-verified**. Dedicated Rename CHOP par names likely `renamefrom`/`renameto`, but the only official text found was the Expression CHOP common page (`commonrenamefrom`/`commonrenameto`). Mark **uncertain**; verify at runtime or sidestep by renaming channels in the Select CHOP that feeds them.

**Info CHOP** — target par not doc-verified (expected `op` = path to operator — **uncertain**). Movie File Out status channels not doc-verified. Common CHOP info channels seen in the Expression CHOP docs: `start`, `length`, `sample_rate`, `num_channels`, `time_slice`, `export_sernum`.

## Image processing — parameters

**Noise TOP** (`docs.derivative.ca/Noise_TOP`)
- `par.seed`, `par.period`, `par.harmon`, `par.spread`, `par.gain`, `par.rough`
- Type menu includes `'random'`, `'alligator'`; exact type-parameter name and full menu **uncertain**

**Resolution TOP** (`docs.derivative.ca/Resolution_TOP`)
- `par.outputresolution = 'custom'`, `par.resolutionw`, `par.resolutionh`, `par.highqualresize`
- Other modes: `'useinput'`, `'eighth'`, `'quarter'`, `'half'`, `'2x'`, `'4x'`, `'8x'`, `'fit'`, `'limit'`
- `par.inputfiltertype` = actual resampling; `par.filtertype` = viewer only

**Displace TOP** (`docs.derivative.ca/Displace_TOP`)
- Input 0 = source image, input 1 = displacement map
- `par.resolutionsource`: `'source'` or `'displace'`
- `par.horzsource`, `par.vertsource`, `par.zsource`: `'red'|'green'|'blue'|'alpha'|'none'`
- `par.midpointx`, `par.midpointy`, `par.midpointz`
- `par.displaceweightx`, `par.displaceweighty` (Z weight **uncertain**); `par.aspectcorrect`, `par.uvweight`
- Offset controls exist; exact tuple component names **uncertain**

**Threshold TOP** (`docs.derivative.ca/Threshold_TOP`) — makes a matte, not a preserved-color cutout
- `par.comparator`: `'less'`, `'greater'`, `'lessorequal'`, `'greaterorequal'`, `'equal'`, `'notequal'`
- `par.rgb`: `'luminance'`, `'red'`, `'green'`, `'blue'`, `'alpha'`, `'rgbaverage'`, `'average'`, `'rgbmax'`, `'max'`
- `par.threshold`, `par.alpha`: `'same'` or `'one'`, `par.soften`

**Blur TOP** — `par.size` strongly indicated; direct official page did not surface. Create string + remaining pars **uncertain**

**Composite TOP** (`docs.derivative.ca/Composite_TOP`)
- `par.operand` — verified values: `'add'`, `'average'`, `'difference'`, `'divide'`, `'inside'`, `'maximum'`, `'minimum'`, `'multiply'`, `'outside'`, plus more blend modes
- `par.top`, `par.selectinput`, `par.inputindex`
- No operator-level opacity — use a Level TOP on an input for opacity

**Blob Track TOP** (`docs.derivative.ca/Blob_Track_TOP`) — **architectural correction vs. earlier assumption**
- Type opType `blobtrack`; reports blob metadata via attached Info DAT/Info CHOP
- Does **not** output a selectable blob mask. `par.drawblobs` draws rectangles into the image — not a mask output. `par.threshold` is only for two-input background subtraction (input 0 = current image, input 1 = known background)
- Other pars: `monosource`, `drawblobs`, `minblobsize`, `maxblobsize`
- PALIMPSEST must build the survival mask from a separate Threshold/Blur/edge/GLSL branch

**Feedback TOP** (class + official page not directly verified; semantics verified via noisefactorllc TD-PLATFORM-NOTES.md and the Hermes TD skill)
- Outputs its **Target TOP's previous-frame result** (one-frame delay). Wiring: use the **`top`/`target` parameter reference**, not a direct input wire (a physical wire back = cook-dependency-loop error). "Not enough sources" resolves after first cook; a cook-dependency-loop *warning* is expected
- Pars: target-path (`target`/`top` — exact name **uncertain**), `reset` / `resetpulse.pulse()` for reset (exact names **uncertain**)

**Level TOP** (`docs.derivative.ca/Level_TOP`)
- Range page (verified): `par.inlow`, `par.inhigh`, `par.outlow` (**black level**), `par.outhigh`
- Per-channel: `par.lowr/highr`, `lowg/highg`, `lowb/highb`, `lowa/higha`
- `par.stepping`, `par.stepsize`, `par.threshold`, `par.clamplow`, `par.clamphigh`, `par.soften`
- Post page: `par.opacity` (verified via Level TOP usage example and Luma Level TOP), `par.gamma` (Gamma on Post page per release notes — strongly indicated but **uncertain** exact name; Luma Level has `gamma2`), `par.brightness2`
- Primary brightness name (e.g. `brightness1`) **uncertain**

## Output — Movie File Out TOP (`docs.derivative.ca/Movie_File_Out_TOP`)

- `par.type`: `'movie'`, `'image'`, `'imagesequence'`, `'stopframemovie'`
- `par.videocodec`: menu includes `'h264nvgpu'` and others — **uncertain** which are present on the 1070 build; the page snippet confirms codec menu exists, not the full list
- Image sequences support `.tiff`, `.jpeg`, `.bmp`, `.exr`, `.png`
- Class members: `writeCount`, `curSeqIndex`, `fileSuffix`
- Sequence naming: `me.fileSuffix` pattern (`N.ext` or `N.i.ext`); expression example `'name_{0}.{1}'.format(me.curSeqIndex, me.par.imagefiletype)` — so an `imagefiletype` par exists (exact value for PNG **uncertain**)
- **Unresolved:** output-path par name, record toggle vs. pulse name, N-frames limit par, whether `$F` works in the file path. Mark all **uncertain** — verify in-app on gdesk before the real render.

## Quit API — corrected

`project.quit(force=True)` — verified in practice by noisefactorllc's scripted-TD pipeline (builds the network from Python at startup, renders, auto-quits; `flush save() before quitting`). Also: Execute DATs have an `onExit()` callback. Official Derivative docs page for `project.quit` not directly hit — mark as **field-verified, not docs-verified**.

## Recommended record-completion detection (no doc'd status channel found)

The docs don't give Movie File Out status channels I can cite. Robust approach: drive the render from a Time COMP with `par.rangelimit = 'hold'` and 240s × fps as the frame range, and quit from a CHOP Execute / DAT script when `absTime.frame >= end` (members `frame`/`seconds` verified on `timeCOMP_Class`). Fallback: monitor `op('movieout').writeCount` / `curSeqIndex` members, which are doc-verified.

## Field notes (verified live on a Windows TouchDesigner install)

- TD's Movie File In video decoder is broken on this install: MP4 (H.264) and AVI (MJPEG) both show SMPTE color bars; single PNGs load fine. Workaround used for PALIMPSEST v1: Linux numpy renderer with identical shader logic (`td/palimpsest_render_linux.py`).
- Root has no `play`/`length` pars — timeline control needs a Time COMP (`timeCOMP`, `par.play`, `par.rangelimit='hold'`).
- GLSL TOP vectors: `par.vec0name` / `par.vec0valuex|y|z|w` (NOT `vec0value0`). Field-verified via probe.
- `TOP.save(path)` and `TOP.numpyArray()` both work — deterministic frame-by-frame capture path.
- `moviefileinTOP.par.cuepoint` + `par.cuepulse.pulse()` works for manual frame stepping.
- Forward slashes in Python file paths; backslash-escaped `\r` in `'\render.py'` is a real bug — use `/render.py`.
- Direct `Start-Process` over SSH launches TD in session 0 (broken); use ScheduledTasks with `-LogonType Interactive`.

## Full uncertain list (verify on gdesk at build time)

1. Create strings: `noiseTOP`, `blurTOP`, `feedbackTOP`, `infoCHOP`, `renameCHOP`, `triggerCHOP`, `limitCHOP`, `lagCHOP`, `blobtrackTOP` — class names not directly seen; rule-derived only.
2. Blur TOP pars beyond `size`.
3. Regular Filter CHOP exact menus.
4. Math CHOP constant multiplier (`gain` unconfirmed).
5. Noise TOP type-parameter name + full type menu.
6. Feedback TOP target/reset par names.
7. Level TOP `gamma`/`brightness1` exact names (use `outlow` for black level — verified).
8. Movie File Out: output-path par, record toggle/pulse name, N-frames limit par, PNG `imagefiletype` value, `$F` behavior.
9. Info CHOP `op` par; Movie File Out info channels.
10. Rename CHOP `renamefrom`/`renameto`.
11. `project.quit` — field-verified, not docs-verified.
12. CHOP expression syntax for audio-driven pars — not researched in this pass.

## Sources

- Official: `docs.derivative.ca/COMP_Class`, `/Time_COMP`, `/TimeCOMP_Class`, `/Movie_File_In_TOP`, `/Envelope_CHOP`, `/Trigger_CHOP`, `/Lag_CHOP`, `/Limit_CHOP`, `/Audio_Filter_CHOP`, `/Noise_TOP`, `/Resolution_TOP`, `/Displace_TOP`, `/Threshold_TOP`, `/Composite_TOP`, `/Blob_Track_TOP`, `/Level_TOP`, `/Movie_File_Out_TOP`; `derivative.ca/solr/audio-file-chop`, `/solr/expression-chop`; `derivative.ca/UserGuide/Math_CHOP`.
- Field-verified third-party: `github.com/noisefactorllc/noisemaker-for-touchdesigner` (TD-PLATFORM-NOTES.md, ARCHITECTURE.md), `github.com/nousresearch/hermes-plugin-touchdesigner` (skills/touchdesigner-mcp/SKILL.md).
