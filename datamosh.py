#!/usr/bin/env python3
"""Waveform-conducted datamosh of audio-reactive displacement.

Pipeline:
  1. Render displacement frames (glitch palette + beat-keyed RGB split),
     pipe into libx264 with long GOP, no scenecut, no B-frames -> base.h264
  2. Per-0.5s spectral drive from the audio (flatness + log RMS + centroid)
  3. Annex-B NAL parse; per IDR-headed segment, in high-drive windows the
     IDR is transplanted with the most recently kept anchor's IDR (valid
     stream, stale reference -> P-slices smear predictively against it);
     low-drive windows keep their own anchors, with a minimum anchor
     frequency so the image periodically resets
  4. Decode corrupted stream, re-encode CRF 18, mux original audio.

Usage:
  python3 datamosh.py --audio <mp3/wav> --out <mp4> [--workdir DIR]
                      [--width 1280 --height 720 --fps 30]
                      [--drop-thresh 0.55 --max-gap 60]
"""
import argparse
import math
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render import decode_audio, analyze, Renderer, FFMPEG, FFPROBE

SR = 44100
WIN_SEC = 0.5
KEYINT = 600


# ---------------------------------------------------------------- drive

def spectral_drive(samples, sr=SR, win_sec=WIN_SEC):
    wlen = int(sr * win_sec)
    nw = int(math.ceil(len(samples) / wlen))
    feats = np.zeros((nw, 3), dtype=np.float64)
    for w in range(nw):
        seg = samples[w * wlen:(w + 1) * wlen]
        if len(seg) < wlen:
            seg = np.pad(seg, (0, wlen - len(seg)))
        rms = float(np.sqrt(np.mean(seg ** 2)))
        seg = seg * np.hanning(wlen)
        mag = np.abs(np.fft.rfft(seg)) + 1e-12
        flat = float(np.exp(np.mean(np.log(mag))) / np.mean(mag))
        freqs = np.fft.rfftfreq(wlen, 1.0 / sr)
        cent = float(np.sum(freqs * mag) / np.sum(mag))
        feats[w] = (flat, math.log1p(rms * 10.0), cent)
    norm = np.zeros_like(feats)
    for j in range(3):
        lo, hi = np.percentile(feats[:, j], [5, 95])
        norm[:, j] = np.clip((feats[:, j] - lo) / (hi - lo + 1e-12), 0, 1)
    return np.mean(norm, axis=1)


# ------------------------------------------------- stage 1: long-GOP render

def render_long_gop(audio_path, h264_path, width, height, fps):
    samples = decode_audio(audio_path)
    bands, energy, flash, dur = analyze(samples, fps)
    n_frames = len(bands)
    cmd = [FFMPEG, "-v", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
           "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-preset", "medium", "-crf", "16",
           "-g", str(KEYINT),
           "-x264-params",
           f"keyint={KEYINT}:min-keyint={KEYINT}:scenecut=0:"
           "bframes=0:weightp=0",
           h264_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    rnd = Renderer(width, height, fps, palette_name="glitch", rgb_split=True)
    import time
    t0 = time.time()
    for f in range(n_frames):
        proc.stdin.write(
            rnd.frame(bands[f], energy[f], flash[f], f / fps).tobytes())
        if (f + 1) % 300 == 0:
            el = time.time() - t0
            print(f"  frame {f + 1}/{n_frames} ({(f + 1) / el:.1f} fps)",
                  flush=True)
    proc.stdin.close()
    proc.wait()
    print(f"  base encode done: {n_frames} frames", flush=True)
    return dur, n_frames


# ------------------------------------------------- stage 2: NAL surgery

def split_nals(data):
    """Split Annex-B stream into (nal_type, payload) with emulation-
    prevention-aware start-code scanning."""
    n = len(data)
    starts = []
    i = 0
    while i < n - 2:
        if data[i] == 0 and data[i + 1] == 0:
            if data[i + 2] == 1:
                starts.append((i, 3))
                i += 3
                continue
            if data[i + 2] == 0 and i + 3 < n and data[i + 3] == 1:
                starts.append((i, 4))
                i += 4
                continue
            if data[i + 2] == 3:
                i += 3  # emulation prevention, not a start code
                continue
        i += 1
    nals = []
    for k, (pos, sc) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else n
        payload = data[pos + sc:end]
        if payload:
            nals.append((payload[0] & 0x1F, bytes(payload)))
    return nals


def corrupt_stream(h264_path, out_path, drive, fps, n_frames,
                   drop_thresh, max_gap_s, thresh_win=None,
                   reset_times=None):
    """NAL-level datamosh by IDR transplant.

    In high-drive windows the segment's IDR NALs are replaced with a
    byte-identical copy of the most recently KEPT segment's IDR. The
    decoder sees a perfectly valid stream (IDR flushes the DPB, frame_num
    continuity holds), but every following P-slice motion-compensates
    against a stale reference image -> genuine predictive-frame smearing
    that melts from the old anchor into the current motion. No error
    concealment, no dropped frames, fully deterministic.
    """
    with open(h264_path, "rb") as fh:
        data = fh.read()
    nals = split_nals(data)
    print(f"  parsed {len(nals)} NAL units", flush=True)

    # group into preamble + IDR-headed segments; count VCL frames
    preamble, segments = [], []
    cur = None
    vcl_total = 0
    for typ, payload in nals:
        if typ == 5:  # IDR slice -> new segment
            cur = {"nals": [], "vcl_start": vcl_total}
            segments.append(cur)
        if cur is None:
            preamble.append((typ, payload))
        else:
            cur["nals"].append((typ, payload))
        if typ in (1, 5):
            vcl_total += 1
    print(f"  VCL frames: {vcl_total} (expected ~{n_frames}), "
          f"segments: {len(segments)}", flush=True)

    # frame index per segment
    for s_i, seg in enumerate(segments):
        vcl = sum(1 for t, _ in seg["nals"] if t in (1, 5))
        seg["f0"] = segments[s_i - 1]["f1"] if s_i else 0
        seg["f1"] = seg["f0"] + vcl
        seg["idr"] = [p for t, p in seg["nals"] if t == 5]

    def seg_drive(seg):
        w0 = int((seg["f0"] / fps) / WIN_SEC)
        w1 = max(w0 + 1, int(math.ceil((seg["f1"] / fps) / WIN_SEC)))
        return float(np.mean(drive[w0:w1]))

    out = bytearray()
    for typ, payload in preamble:
        out += b"\x00\x00\x00\x01" + payload
    kept, moshed = 0, []
    last_kept_t = -1e9
    anchor_idr = None  # IDR NALs of most recently kept segment
    for s_i, seg in enumerate(segments):
        t0 = seg["f0"] / fps
        d = seg_drive(seg)
        w0 = int((seg["f0"] / fps) / WIN_SEC)
        th = (float(thresh_win[min(w0, len(thresh_win) - 1)])
              if thresh_win is not None else drop_thresh)
        mosh = False
        if s_i > 0 and anchor_idr is not None:
            hard_cut = (reset_times is not None and any(
                abs(t0 - rt) < 0.51 for rt in reset_times))
            if not hard_cut and d >= th \
                    and (t0 - last_kept_t) <= max_gap_s:
                mosh = True
            if hard_cut:
                print(f"  seg {s_i}: t={t0:6.1f}s HARD CUT (fresh anchor)",
                      flush=True)
        if mosh:
            # swap this IDR for the last kept anchor's IDR, keep P-slices
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
            moshed.append(s_i)
            print(f"  seg {s_i}: t={t0:6.1f}s drive={d:.2f} MOSH "
                  f"(IDR<-seg anchor, P-slices kept)", flush=True)
        else:
            for typ, payload in seg["nals"]:
                out += b"\x00\x00\x00\x01" + payload
            kept += 1
            last_kept_t = t0
            anchor_idr = seg["idr"]
            print(f"  seg {s_i}: t={t0:6.1f}s drive={d:.2f} KEEP", flush=True)
    with open(out_path, "wb") as fh:
        fh.write(out)
    print(f"  anchors kept: {kept}, segments moshed: {len(moshed)}",
          flush=True)
    return kept, moshed


# ------------------------------------------------- stage 3: decode + mux

def finish(corrupt_path, audio_path, out_path):
    fixed = out_path + ".fixed.mp4"
    subprocess.run(
        [FFMPEG, "-v", "error", "-y",
         "-err_detect", "ignore_err", "-fflags", "+genpts",
         "-i", corrupt_path,
         "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", "-r", "30", fixed],
        check=True)
    subprocess.run(
        [FFMPEG, "-v", "error", "-y", "-i", fixed, "-i", audio_path,
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-map", "0:v:0", "-map", "1:a:0", "-shortest", out_path],
        check=True)
    os.unlink(fixed)
    print(f"  final: {out_path}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workdir", default="/tmp/datamosh")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--drop-thresh", type=float, default=0.55)
    ap.add_argument("--max-gap", type=float, default=60.0)
    ap.add_argument("--skip-render", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.workdir, exist_ok=True)
    base = os.path.join(a.workdir, "base.h264")
    corrupt = os.path.join(a.workdir, "corrupt.h264")

    print("stage 0: spectral drive", flush=True)
    samples = decode_audio(a.audio)
    drive = spectral_drive(samples)
    print(f"  drive: min={drive.min():.3f} max={drive.max():.3f} "
          f"mean={drive.mean():.3f} (n={len(drive)} windows)", flush=True)

    if not a.skip_render:
        print("stage 1: displacement render -> long-GOP h264", flush=True)
        dur, n_frames = render_long_gop(a.audio, base, a.width, a.height,
                                        a.fps)
    else:
        n_frames = int(math.ceil(len(samples) / (SR / a.fps)))
        print(f"  skip-render: reusing {base}", flush=True)

    print("stage 2: NAL surgery (IDR transplant datamosh)", flush=True)
    kept, moshed = corrupt_stream(base, corrupt, drive, a.fps, n_frames,
                                  a.drop_thresh, a.max_gap)

    print("stage 3: decode + re-encode + mux", flush=True)
    finish(corrupt, a.audio, a.out)
    print(f"done: kept={kept} moshed={moshed}", flush=True)


if __name__ == "__main__":
    main()
