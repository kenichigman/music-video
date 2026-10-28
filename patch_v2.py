#!/usr/bin/env python3
"""Song Six supercut v2 — surgical patches on v1 (the director's two review notes).

FIX A (0-6s): v1 opened mid-melt (segs 1-5 moshed off seg0) AND carried a
mosaic bridge at 2.3s. Rebuild: base frames 0-179 from timeline with the
2.3s bridge SUPPRESSED; mosh decisions: seg0 KEEP, seg1 KEEP (clean legible
open), segs 2-5 MOSH off seg1's anchor (staleness 1s->4s = melt ramp,
full chaos by ~4-5s). Finish with v1 sec0 params verbatim.

FIX B (112-135s, Drop II boundary at 119s): mosaic-bridge BURST into the
cut (wet ramps 0->0.85 over 117.6-119.0s, decays 119.0-119.5s) on top of
v1's bridge field; chaos 1.9 + max_gap 3 for segs 120-126, easing to
chaos 1.45 / gap 8 across 127-134; segs 112-118 KEEP (v1-identical),
119 hard-cut KEEP. Finish with v1 sec2/sec3 params + the 119 dissolve
replicated exactly as finish_songsix.py computes it.

Assembly: patches are frame ranges [0,219) and [3352,4063) of the final
film (bounds chosen at v1 keyframes 7.300s / 111.733s / 135.433s so the
untouched spans can be stream-copied bit-exact). Margin frames inside the
patches (180-218, 3352-3359, 4050-4062) are taken from decoded v1 so
their content is v1's own; everything outside the patches is -c copy.
Audio is copied untouched from v1.
"""
import json
import math
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mosaic as M  # noqa: E402
from render import decode_audio, FFMPEG  # noqa: E402
from datamosh import spectral_drive, split_nals, WIN_SEC  # noqa: E402
import mosh_songsix as MS  # noqa: E402  (PLAN/find_shifts/mosaic_frame)
import finish_songsix as FS  # noqa: E402  (grade math, verbatim)

FPS, W, H = 30, 848, 464
ROOT = os.path.dirname(HERE)
WORK = os.path.join(ROOT, "work")
WS = os.path.join(ROOT, "work_super_six")
V2WORK = os.path.join(ROOT, "work_v2")
os.makedirs(V2WORK, exist_ok=True)

TIMELINE = os.path.join(WS, "timeline.mp4")
AUDIO = os.path.join(ROOT, "audio", "song-six_from-62s.wav")
V1 = os.path.join(WORK, "song-six_supercut_v1.mp4")
EDL = os.path.join(WORK, "edl_songsix.json")

# v1 finish params, verbatim from work/finish_songsix.log (log precision)
PER = [
    {"gains": np.array([0.934, 1.033, 1.049]), "a": 0.956, "b": 0.0},
    {"gains": np.array([0.991, 1.007, 1.003]), "a": 0.993, "b": 0.0},
    {"gains": np.array([0.930, 1.014, 1.079]), "a": 1.150, "b": 0.0},
    {"gains": np.array([0.993, 1.074, 0.948]), "a": 1.007, "b": 0.0},
    {"gains": np.array([1.010, 1.032, 0.963]), "a": 0.955, "b": 0.0},
    {"gains": np.array([0.999, 1.006, 0.995]), "a": 1.115, "b": 0.0},
]

PATCH_A = (0, 220)        # frames [0,220)   (split-002 starts at 220)
PATCH_B = (3352, 4064)    # frames [3352,4064) (split-004 starts at 4064)
NEW_A = (0, 180)          # rebuilt content inside patch A
NEW_B = (3360, 4050)      # rebuilt content inside patch B (segs 112-134)


def run(cmd, **kw):
    subprocess.run(cmd, check=True, **kw)


# ---------------------------------------------------------------- base enc
def encode_base(frames, out_path):
    """frames: iterable of uint8 (H,W,3). Same settings as mosh_songsix."""
    cmd = [FFMPEG, "-v", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-preset", "medium", "-crf", "16",
           "-g", "30",
           "-x264-params",
           "keyint=30:min-keyint=30:scenecut=0:bframes=0:weightp=0",
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
    print(f"  base encode: {n} frames -> {out_path}", flush=True)
    return n


def read_frames(path, start, count):
    """Decode frames [start, start+count) of a video as rgb24 arrays."""
    out = []
    gen = M.decode_rawvideo(path, W, H)
    for i, fr in enumerate(gen):
        if i < start:
            continue
        if i >= start + count:
            break
        out.append(fr)
    assert len(out) == count, f"{path}: wanted {count} from {start}, " \
                              f"got {len(out)}"
    return out


# ------------------------------------------------------------- NAL surgery
def parse_segments(h264_path):
    data = open(h264_path, "rb").read()
    nals = split_nals(data)
    preamble, segments, cur = [], [], None
    for typ, payload in nals:
        if typ == 5:
            cur = {"nals": []}
            segments.append(cur)
        if cur is None:
            preamble.append((typ, payload))
        else:
            cur["nals"].append((typ, payload))
        if typ in (1, 5):
            cur.setdefault("vcl", 0)
            cur["vcl"] += 1
    for i, s in enumerate(segments):
        s["idr"] = [p for t, p in s["nals"] if t == 5]
    return preamble, segments


def corrupt_window(segments, decide, out_path):
    """decide(local_i, seg) -> True to mosh (IDR transplant from last kept
    anchor in THIS window). Mirrors datamosh.corrupt_stream exactly."""
    out = bytearray()
    anchor_idr, kept, moshed = None, 0, []
    for i, seg in enumerate(segments):
        mosh = bool(decide(i, seg)) and i > 0 and anchor_idr is not None
        if mosh:
            swapped = False
            for typ, payload in seg["nals"]:
                if typ == 5 and not swapped:
                    for ap in anchor_idr:
                        out += b"\x00\x00\x00\x01" + ap
                    swapped = True
                elif typ == 5:
                    continue
                else:
                    out += b"\x00\x00\x00\x01" + payload
            moshed.append(i)
        else:
            for typ, payload in seg["nals"]:
                out += b"\x00\x00\x00\x01" + payload
            kept += 1
            anchor_idr = seg["idr"]
    with open(out_path, "wb") as fh:
        fh.write(out)
    print(f"  corrupt: kept={kept} moshed={moshed}", flush=True)
    return moshed


def decode_corrupt(h264_path, n_expect):
    cmd = [FFMPEG, "-v", "error", "-y",
           "-err_detect", "ignore_err", "-fflags", "+genpts",
           "-i", h264_path, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)
    fb = W * H * 3
    frames = []
    while True:
        raw = proc.stdout.read(fb)
        if len(raw) < fb:
            break
        frames.append(np.frombuffer(raw, dtype=np.uint8)
                      .reshape(H, W, 3).copy())
    proc.wait()
    assert len(frames) == n_expect, \
        f"corrupt decode: {len(frames)} != {n_expect}"
    return frames


# ------------------------------------------------------------------ finish
def grade_frames(frames_by_idx):
    """Apply v1 finish math. frames_by_idx: {global_idx: uint8 frame}.
    Handles the 119s dissolve exactly like finish_songsix (blend of
    section-graded frames, then global grade). Returns {idx: uint8}."""
    graded = {i: FS.apply_section_grade(f.astype(np.float64),
                                        PER[FS.section_of(i / FPS)])
              for i, f in frames_by_idx.items()}
    m = 119 * FPS
    K = FS.DISSOLVE
    blend = {}
    for j in range(K):
        pos = m - K // 2 + j
        blend[pos] = (m - K + j, m + j, FS.smoothstep(j / (K - 1)))
    out = {}
    for i in sorted(graded):
        if i in blend:
            a, b, al = blend[i]
            O = (1 - al) * graded[a] + al * graded[b]
        else:
            O = graded[i]
        out[i] = FS.apply_global_grade(O)
    return out


def encode_patch(frames, out_path):
    """libx264 medium crf17 — the finish_songsix encode settings."""
    cmd = [FFMPEG, "-v", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-preset", "medium", "-crf", "17", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for fr in frames:
            proc.stdin.write(np.ascontiguousarray(fr, dtype=np.uint8)
                             .tobytes())
    finally:
        try:
            proc.stdin.close()
        except BrokenPipeError:
            pass
        proc.wait()
    print(f"  patch encode: {len(frames)} frames -> {out_path}", flush=True)


# --------------------------------------------------------------------- main
def main():
    print("== determinism checks (tile library + shifts) ==", flush=True)
    M.COLS, M.ROWS, M.TILE = 53, 29, 16
    M.W, M.H = W, H
    bounds = [(s, e) for (_c, _o, s, e, _p) in MS.PLAN]
    cuts = MS.find_shifts(TIMELINE, bounds)
    assert len(cuts) == 48, f"shifts {len(cuts)} != 48"
    rng = np.random.default_rng(8000)
    tiles, lib_means = M.build_library([TIMELINE], rng)
    tiles_f = tiles.astype(np.float32)
    assert len(tiles) == 4000, f"tiles {len(tiles)} != 4000"
    print("  shifts + library match v1 log (48 shifts, 4000 tiles)",
          flush=True)

    samples = decode_audio(AUDIO)
    drive = spectral_drive(samples)

    def seg_drive(f0):
        w0 = int((f0 / FPS) / WIN_SEC)
        w1 = max(w0 + 1, int(math.ceil(((f0 + 30) / FPS) / WIN_SEC)))
        return float(np.mean(drive[w0:w1]))

    # ------------------------------------------------------------ FIX A
    print("== FIX A: base 0-6s, 2.3s bridge suppressed ==", flush=True)

    def frames_a():
        for i, fr in enumerate(M.decode_rawvideo(TIMELINE, W, H)):
            if i >= NEW_A[1]:
                break
            t = i / FPS
            wet = MS.bridge_wet(t, cuts)
            # suppress any bridge whose wet reaches into the clean open
            if t < 6.5:
                wet = 0.0
            if wet > 0:
                mos = MS.mosaic_frame(fr, tiles_f, lib_means)
                fr = np.clip(mos * wet + fr.astype(np.float32) * (1 - wet),
                             0, 255).astype(np.uint8)
            yield fr

    base_a = os.path.join(V2WORK, "base_a.h264")
    encode_base(frames_a(), base_a)
    _pre, segs_a = parse_segments(base_a)
    assert len(segs_a) == 6, f"A segments {len(segs_a)}"
    # seg0 KEEP, seg1 KEEP, segs 2-5 MOSH (anchor = seg1, staleness ramp)
    moshed_a = corrupt_window(segs_a, lambda i, s: i >= 2,
                              os.path.join(V2WORK, "moshed_a.h264"))
    frames_a_new = decode_corrupt(os.path.join(V2WORK, "moshed_a.h264"),
                                  180)
    graded_a = grade_frames({i: frames_a_new[i] for i in range(180)})
    v1_margins_a = read_frames(V1, 180, PATCH_A[1] - 180)
    assert len(v1_margins_a) == 40
    patch_a_frames = [graded_a[i] for i in range(180)] + v1_margins_a
    patch_a = os.path.join(V2WORK, "patch_a.mp4")
    encode_patch(patch_a_frames, patch_a)

    # ------------------------------------------------------------ FIX B
    print("== FIX B: base 112-135s + burst into the 119 cut ==", flush=True)

    def burst_wet(t):
        if 117.6 <= t < 119.0:
            return 0.85 * (t - 117.6) / 1.4
        if 119.0 <= t <= 119.5:
            return 0.85 * (1.0 - (t - 119.0) / 0.5)
        return 0.0

    tl_b = read_frames(TIMELINE, NEW_B[0], NEW_B[1] - NEW_B[0])

    def frames_b():
        for k, fr in enumerate(tl_b):
            t = (NEW_B[0] + k) / FPS
            wet = max(MS.bridge_wet(t, cuts), burst_wet(t))
            if wet > 0:
                mos = MS.mosaic_frame(fr, tiles_f, lib_means)
                fr = np.clip(mos * wet + fr.astype(np.float32) * (1 - wet),
                             0, 255).astype(np.uint8)
            yield fr

    base_b = os.path.join(V2WORK, "base_b.h264")
    encode_base(frames_b(), base_b)
    _pre, segs_b = parse_segments(base_b)
    assert len(segs_b) == 23, f"B segments {len(segs_b)}"

    # decisions: local seg i <-> global t0 = 112 + i
    state = {"last_kept": 111.0}  # shadow of corrupt_window's keep chain;
    # EVERY keep (incl. 112-118 and the 119 hard cut) must be recorded or
    # the gap math wrongly blocks seg 120.

    def decide_b(i, seg):
        t0 = 112.0 + i
        if t0 < 120:
            state["last_kept"] = t0
            return False             # 112-118 KEEP (v1); 119 hard-cut KEEP
        if t0 <= 126:
            chaos, gap = 1.9, 3.0
        else:
            k = t0 - 126             # 1..8 across 127..134
            chaos = 1.9 - k * (0.45 / 8.0)
            gap = 3.0 + k * (5.0 / 8.0)
        th = float(np.clip(0.55 / chaos, 0.15, 0.95))
        d = seg_drive(int(t0 * FPS))
        mosh = d >= th and (t0 - state["last_kept"]) <= gap
        print(f"    B seg {int(t0)}: drive={d:.2f} th={th:.3f} "
              f"gap={gap:.1f} -> {'MOSH' if mosh else 'KEEP'}", flush=True)
        if not mosh:
            state["last_kept"] = t0
        return mosh

    moshed_b = corrupt_window(segs_b, decide_b,
                              os.path.join(V2WORK, "moshed_b.h264"))
    frames_b_new = decode_corrupt(os.path.join(V2WORK, "moshed_b.h264"),
                                  690)
    graded_b = grade_frames({NEW_B[0] + k: frames_b_new[k]
                             for k in range(690)})
    patch_b_frames = (read_frames(V1, PATCH_B[0], NEW_B[0] - PATCH_B[0])
                      + [graded_b[NEW_B[0] + k] for k in range(690)]
                      + read_frames(V1, NEW_B[1], PATCH_B[1] - NEW_B[1]))
    assert len(patch_b_frames) == PATCH_B[1] - PATCH_B[0]
    patch_b = os.path.join(V2WORK, "patch_b.mp4")
    encode_patch(patch_b_frames, patch_b)

    # Assembly is a separate step (mkvmerge append of patch_a +
    # split-002-trimmed + patch_b + split-004, then remux with v1 audio).
    print(f"  patches done: A={PATCH_A} B={PATCH_B}", flush=True)
    print(f"  moshed A (local): {moshed_a}  B (local): {moshed_b}",
          flush=True)


if __name__ == "__main__":
    main()
