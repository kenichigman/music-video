#!/usr/bin/env python3
"""Song Six supercut v4 — Drop II RE-PHASING patch on v3 (frames
3570..tail_start). The director's note on v3: "Audio seems late 1:58/59 to
2:30 ish but really like section after." Measured (sequential decode):
editorial phase, not a mux defect — v3's Drop II burst RAMPS for ~1.5s
after the 119.4s transient and in-section accents trail the audio
onsets (130.0/139.2/151.4/153.2/160.7) by ~0.7-2s.

FIX (Drop II section only; v1/v2/v3 character otherwise preserved):
- Base GOP grid gets FORCED keyframes at the onset frames, so anchor
  refreshes land exactly ON the hits (+-1 frame), not on the old
  max_gap clock: 3582 (119.4), 3900 (130.0), 4176 (139.2),
  4542 (151.4), 4596 (153.2), 4821 (160.7). Those segments are KEEP.
- Mosaic burst INVERTED: wet now PEAKS (0.85) at the 119.4 transient
  (rise 117.6->119.4, decay to 0 by 120.4) instead of ramping in.
- Chaos envelope breathes off the onsets: 1.90 at each hit, exp decay
  (tau 2.2s) toward a 1.32 floor between hits (v1 section chaos was
  1.45 flat; v2 patch peaked 1.9 then eased to 1.45 by ~135s).
- Non-anchor segments MOSH iff their spectral drive clears
  clip(0.55/chaos) — same drive/threshold math as patch_v2.
- Finish: v1 PER params verbatim; BOTH dissolves in range (119s and
  162s) computed with finish_songsix's exact blend formula.

Window: base/corrupt over global frames [3540, 4890) (seg 118 tail =
119-dissolve partners; sec-4 head = 162-dissolve partners). Patch
output = [3570, TAIL_START) where TAIL_START is the proven mkvmerge
split boundary in v3 (passed as argv[1]); frames outside the patch
are stream-copied from v3 bit-exact at assembly time.
"""
import math
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mosaic as M  # noqa: E402
import patch_v2 as P  # noqa: E402  (machinery + PER)
import finish_songsix as FS  # noqa: E402
import mosh_songsix as MS  # noqa: E402
from render import decode_audio, FFMPEG  # noqa: E402
from datamosh import spectral_drive, WIN_SEC  # noqa: E402

FPS, W, H = 30, 848, 464
ROOT = P.ROOT
V4WORK = os.path.join(ROOT, "work_v4")
os.makedirs(V4WORK, exist_ok=True)
TIMELINE = P.TIMELINE
AUDIO = P.AUDIO

WIN = (3540, 4890)                    # base/corrupt window (global)
PATCH0 = 3570                         # first patch output frame
ONSETS = [119.4, 130.0, 139.2, 151.4, 153.2, 160.7]
ONSET_FRAMES = [int(round(o * FPS)) for o in ONSETS]   # 3582, 3900, ...
KEEP_STARTS = {3570, 4860} | set(ONSET_FRAMES)         # + hard cuts
TAIL_START = int(sys.argv[1]) if len(sys.argv) > 1 else 4876


def burst4(t):
    """Mosaic burst as a plateau/crash: heavy mosaic (0.80->0.92)
    through the boundary approach, then a CRASH to 0.10 exactly at
    the 119.4 transient frame — the mosaic->near-clean step IS the
    detonation accent (measured: smooth mosaic ramps produce almost
    no frame-diff energy on this low-motion footage; a wet step of
    ~0.8 at the hit frame is the top accent in the window). Decays
    to 0 by 120.4 under the new anchor."""
    if 117.6 <= t < 119.4:
        return 0.80 + 0.12 * (t - 117.6) / 1.8
    if 119.4 <= t <= 120.4:
        return 0.10 * (1.0 - (t - 119.4) / 1.0)
    return 0.0


def chaos_at(t):
    c = 1.32
    for h in ONSETS:
        if t >= h - 1e-9:
            c += 0.58 * math.exp(-(t - h) / 2.2)
    return min(1.90, c)


def encode_base_forced(frames, out_path, forced_local):
    expr = "+".join(f"eq(n,{n})" for n in forced_local)
    cmd = [FFMPEG, "-v", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-force_key_frames", f"expr:{expr}",
           "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-preset", "medium", "-crf", "16",
           "-x264-params",
           "keyint=30:min-keyint=1:scenecut=0:bframes=0:weightp=0",
           out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = 0
    try:
        for fr in frames:
            proc.stdin.write(np.ascontiguousarray(fr, dtype=np.uint8)
                             .tobytes())
            n += 1
    finally:
        try:
            proc.stdin.close()
        except BrokenPipeError:
            pass
        proc.wait()
    print(f"  base encode (forced KF): {n} frames -> {out_path}",
          flush=True)
    return n


def grade_window(frames_by_idx):
    """finish_songsix math verbatim (PER + both in-range dissolves)."""
    graded = {i: FS.apply_section_grade(f.astype(np.float64),
                                        P.PER[FS.section_of(i / FPS)])
              for i, f in frames_by_idx.items()}
    blend = {}
    for c in FS.CUTS:
        m = int(c * FPS)
        for j in range(FS.DISSOLVE):
            pos = m - FS.DISSOLVE // 2 + j
            blend[pos] = (m - FS.DISSOLVE + j, m + j,
                          FS.smoothstep(j / (FS.DISSOLVE - 1)))
    out = {}
    for i in sorted(graded):
        if i in blend:
            a, b, al = blend[i]
            O = (1 - al) * graded[a] + al * graded[b]
        else:
            O = graded[i]
        out[i] = FS.apply_global_grade(O)
    return out


def main():
    print(f"== v4 Drop II re-phase; patch out [{PATCH0}, {TAIL_START}) ==",
          flush=True)
    print("== determinism checks ==", flush=True)
    M.COLS, M.ROWS, M.TILE = 53, 29, 16
    M.W, M.H = W, H
    bounds = [(s, e) for (_c, _o, s, e, _p) in MS.PLAN]
    cuts = MS.find_shifts(TIMELINE, bounds)
    assert len(cuts) == 48, f"shifts {len(cuts)} != 48"
    rng = np.random.default_rng(8000)
    tiles, lib_means = M.build_library([TIMELINE], rng)
    tiles_f = tiles.astype(np.float32)
    assert len(tiles) == 4000
    print("  shifts + library match v1 (48 / 4000)", flush=True)

    samples = decode_audio(AUDIO)
    drive = spectral_drive(samples)

    def seg_drive(f0, f1):
        w0 = int((f0 / FPS) / WIN_SEC)
        w1 = max(w0 + 1, int(math.ceil((f1 / FPS) / WIN_SEC)))
        return float(np.mean(drive[w0:w1]))

    # ------------------------------------------------------------ base
    print("== base window 3540-4890 (bridges + inverted burst) ==",
          flush=True)
    tl = P.read_frames(TIMELINE, WIN[0], WIN[1] - WIN[0])

    def frames_win():
        for k, fr in enumerate(tl):
            t = (WIN[0] + k) / FPS
            wet = max(MS.bridge_wet(t, cuts), burst4(t))
            if wet > 0:
                mos = MS.mosaic_frame(fr, tiles_f, lib_means)
                fr = np.clip(mos * wet + fr.astype(np.float32)
                             * (1 - wet), 0, 255).astype(np.uint8)
            yield fr

    base = os.path.join(V4WORK, "base_d2.h264")
    # + frame 3590: a second grid point 8 frames after the 119.4
    # anchor so the mosh transplant shock lands at 119.9s, sustaining
    # the detonation instead of waiting for the 3612 grid point.
    forced_local = [f - WIN[0] for f in ONSET_FRAMES] + [3590 - WIN[0]]
    encode_base_forced(frames_win(), base, forced_local)
    _pre, segs = P.parse_segments(base)
    starts, acc = [], WIN[0]
    for s in segs:
        starts.append(acc)
        acc += s["vcl"]
    assert acc == WIN[1], f"segments cover {acc} != {WIN[1]}"
    missing = [f for f in ONSET_FRAMES if f not in starts]
    assert not missing, f"onset frames not segment starts: {missing}"
    print(f"  segments: {len(segs)}; onset starts OK: {ONSET_FRAMES}",
          flush=True)

    # ---------------------------------------------------------- corrupt
    def decide(i, seg):
        s = starts[i]
        if s < PATCH0 or s >= 4860 or s in KEEP_STARTS:
            return False
        # a segment ending exactly ON an onset anchor always smears
        # into it — a clean segment there would eat the snap (the
        # [4536,4542) drive coin-flip did exactly that in build 1)
        if s + seg["vcl"] in ONSET_FRAMES:
            print(f"    seg @{s}: pre-onset -> MOSH (forced)",
                  flush=True)
            return True
        t0 = s / FPS
        ch = chaos_at(t0)
        th = float(np.clip(0.55 / ch, 0.15, 0.95))
        d = seg_drive(s, s + seg["vcl"])
        mosh = d >= th
        print(f"    seg @{s} ({t0:.2f}s): chaos={ch:.2f} th={th:.3f} "
              f"drive={d:.2f} -> {'MOSH' if mosh else 'KEEP'}",
              flush=True)
        return mosh

    moshed = P.corrupt_window(segs, decide,
                              os.path.join(V4WORK, "moshed_d2.h264"))
    print(f"  moshed segment starts: {[starts[i] for i in moshed]}",
          flush=True)
    frames = P.decode_corrupt(os.path.join(V4WORK, "moshed_d2.h264"),
                              WIN[1] - WIN[0])
    by_idx = {WIN[0] + k: frames[k] for k in range(len(frames))}

    # ------------------------------------------------------------ grade
    graded = grade_window(by_idx)
    patch = [graded[i] for i in range(PATCH0, TAIL_START)]
    out = os.path.join(V4WORK, "patch_d2.mp4")
    P.encode_patch(patch, out)
    print(f"  patch done: {out} frames [{PATCH0}, {TAIL_START})",
          flush=True)


if __name__ == "__main__":
    main()
