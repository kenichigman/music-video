#!/usr/bin/env python3
"""HDMI 8,000-tile audio-reactive mosaic.

Concept (from the "8,000 squared mosaic" short): the frame is a photomosaic
of exactly 8,000 tiles (100 cols x 80 rows, 16x16 px tiles -> 1600x1280
canvas). Each tile is a tiny crop sampled from Gabe's two source clips
(predicted.mp4, touched.mp4) plus the combination clip
(BONES-HDMI-datamosh-displacement.mp4). The mosaic approximates the
combination clip itself frame-by-frame -- the hidden image IS the video,
revealed through the tiles.

Audio reactivity (reuses render.py's frame-by-frame analysis of the real
HDMI track):
  - loud passages -> tiles go chaotic (random mismatches, the mosaic
    "smears", mirroring the datamosh logic: loud smears, quiet snaps back)
  - quiet passages -> tiles snap to best color match (hidden image crisp)
  - per-cell brightness pulses with band energy; beats add flash

Usage:
  python3 mosaic.py --audio BONES-HDMI.mp3 --target <combination mp4>
      --lib-a predicted.mp4 --lib-b touched.mp4 --out out.mp4
"""
import argparse
import math
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render import decode_audio, analyze, FFMPEG, FFPROBE  # noqa: E402  (the audio-reactive complex)

SR = 44100
COLS, ROWS = 100, 80          # 8,000 tiles exactly
TILE = 16
W, H = COLS * TILE, ROWS * TILE   # 1600 x 1280
N_TILES = 4000                # tile library size
LIB_FPS = 2                   # sampling rate for library frames


def run(cmd, **kw):
    subprocess.run(cmd, check=True, **kw)


def decode_rawvideo(path, w, h, fps=None, ss=None, t=None):
    """Yield rgb24 frames (H, W, 3) uint8 from a video file."""
    cmd = [FFMPEG, "-v", "error"]
    if ss is not None:
        cmd += ["-ss", str(ss)]
    cmd += ["-i", path]
    if t is not None:
        cmd += ["-t", str(t)]
    vf = []
    if fps is not None:
        vf.append(f"fps={fps}")
    if vf:
        cmd += ["-vf", ",".join(vf)]
    cmd += ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)
    frame_bytes = w * h * 3
    n = 0
    while True:
        raw = proc.stdout.read(frame_bytes)
        if len(raw) < frame_bytes:
            break
        yield np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3)
        n += 1
    proc.wait()
    if proc.returncode != 0 and n == 0:
        raise RuntimeError(f"ffmpeg decode failed with zero frames: {path}")


def valid_video(path):
    """True if ffprobe can read a decodable video stream with frames."""
    try:
        out = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=nb_frames,avg_frame_rate",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, check=True)
        return bool(out.stdout.strip())
    except subprocess.CalledProcessError:
        return False


def prepare_target(src, workdir):
    """Normalize any source clip to fill WxH at 30fps (scale-to-cover,
    center-crop). Cache key includes the source name so different
    targets don't collide."""
    base = os.path.splitext(os.path.basename(src))[0]
    out = os.path.join(workdir, f"target_{W}x{H}_{base}.mp4")
    if os.path.exists(out) and not valid_video(out):
        print("cached target corrupt, regenerating", flush=True)
        os.remove(out)
    if not os.path.exists(out):
        run([FFMPEG, "-v", "error", "-y", "-i", src, "-vf",
             f"scale={W}:{H}:force_original_aspect_ratio=increase,"
             f"crop={W}:{H},fps=30",
             "-r", "30",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
             "-pix_fmt", "yuv420p", "-an", out])
    return out


def clip_size(path):
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True)
    w, h = out.stdout.strip().split(",")
    return int(w), int(h)


def build_library(clips, rng):
    """Sample N_TILES diverse 16x16 tiles from the source clips."""
    cands, means, stds = [], [], []
    for clip in clips:
        w, h = clip_size(clip)
        n = 0
        for frame in decode_rawvideo(clip, w, h, fps=LIB_FPS):
            for _ in range(10):
                y = rng.integers(0, h - TILE + 1)
                x = rng.integers(0, w - TILE + 1)
                tile = frame[y:y + TILE, x:x + TILE]
                cands.append(tile)
                means.append(tile.mean(axis=(0, 1)))
                stds.append(tile.std())
            n += 1
        print(f"  {os.path.basename(clip)}: {w}x{h}, {n} frames sampled",
              flush=True)
    cands = np.stack(cands)
    means = np.stack(means).astype(np.float32)
    stds = np.array(stds)
    # drop near-flat tiles (gray mush), keep the most colorful
    order = np.argsort(stds)[::-1]
    keep = order[: min(N_TILES * 2, len(order))]
    keep = keep[rng.choice(len(keep), size=min(N_TILES, len(keep)),
                           replace=False)]
    print(f"library: {len(cands)} candidates -> {len(keep)} tiles kept",
          flush=True)
    return cands[keep], means[keep]


def nearest_tiles(cell_means, lib_means, chunk=2000):
    """Argmin color distance per cell, chunked over cells. Returns (8000,) idx."""
    n = cell_means.shape[0]
    out = np.empty(n, dtype=np.int64)
    lib = lib_means.astype(np.float32)
    for s in range(0, n, chunk):
        c = cell_means[s:s + chunk].astype(np.float32)
        # (chunk, T) squared distances
        d = ((c[:, None, :] - lib[None, :, :]) ** 2).sum(-1)
        out[s:s + chunk] = d.argmin(axis=1)
    return out


def render(args):
    global COLS, ROWS, TILE, W, H
    COLS, ROWS, TILE = args.cols, args.rows, args.tile
    W, H = COLS * TILE, ROWS * TILE
    os.makedirs(args.workdir, exist_ok=True)
    rng = np.random.default_rng(8000)

    print("== audio analysis (render.py complex) ==", flush=True)
    samples = decode_audio(args.audio)
    fps = 30
    bands, energy, flash, _audio_dur = analyze(samples, fps)
    n_aframes = bands.shape[0]
    print(f"audio frames: {n_aframes}, energy range "
          f"{energy.min():.3f}..{energy.max():.3f}", flush=True)

    # conductor EDL: slow dynamics envelope over the fast audio signal
    n_sec = n_aframes // fps + 1
    chaos_env = np.ones(n_sec)
    wet_env = np.ones(n_sec)
    if args.edl:
        import json as _json
        edl = _json.load(open(args.edl))
        for s in edl["sections"]:
            chaos_env[s["start_s"]:s["end_s"]] = s["chaos_scale"]
            wet_env[s["start_s"]:s["end_s"]] = s["wet_scale"]
        print(f"EDL: {len(edl['sections'])} sections, "
              f"chaos {chaos_env.min():.2f}..{chaos_env.max():.2f}, "
              f"wet {wet_env.min():.2f}..{wet_env.max():.2f}", flush=True)

    print("== target prep ==", flush=True)
    target = prepare_target(args.target, args.workdir)

    print("== tile library ==", flush=True)
    tiles, lib_means = build_library(
        args.libs + [args.target], rng)
    tiles_f = tiles.astype(np.float32)
    n_lib = len(tiles)

    # count target frames
    n_frames = n_aframes
    print(f"== rendering {n_frames} mosaic frames "
          f"({COLS}x{ROWS}={COLS * ROWS} tiles) ==", flush=True)

    enc = [FFMPEG, "-v", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(fps), "-i", "-",
           "-i", args.audio,
           "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
           "-shortest", args.out]
    proc = subprocess.Popen(enc, stdin=subprocess.PIPE)

    previews = {500: None, 2000: None, 3500: None}
    n_t = COLS * ROWS
    try:
        for fi, frame in enumerate(decode_rawvideo(target, W, H)):
            if fi >= n_frames:
                break
            e = float(np.clip(energy[fi], 0, 1))
            fl = float(np.clip(flash[fi], 0, 1))

            # cell mean colors -> (8000, 3)
            small = frame.reshape(ROWS, TILE, COLS, TILE, 3).mean(axis=(1, 3))
            cell_means = small.reshape(n_t, 3)

            # best-match tiles
            idx = nearest_tiles(cell_means, lib_means)

            # chaos: loud passages smear the mosaic (random mismatches),
            # shaped by the conductor's per-second envelope
            si = min(fi // fps, n_sec - 1)
            chaos_p = min(0.75, e * 0.60 + fl * 0.25) * chaos_env[si]
            chaos_p = min(chaos_p, 0.9)
            chaos = rng.random(n_t) < chaos_p
            idx[chaos] = rng.integers(0, n_lib, size=int(chaos.sum()))

            # assemble (8000,16,16,3) -> (1280,1600,3), fully vectorized
            canvas = tiles_f[idx].reshape(ROWS, COLS, TILE, TILE, 3)
            canvas = canvas.transpose(0, 2, 1, 3, 4).reshape(H, W, 3)

            # per-cell brightness pulse from band energy + beat flash
            bass = float(bands[fi, :8].mean())
            mult = (0.72 + 0.85 * e + 0.9 * fl
                    + 0.25 * (bass - 0.5))
            mult = np.clip(mult, 0.35, 2.2)
            jitter = 1.0 + (rng.random(n_t).astype(np.float32) - 0.5) * 0.3 * e
            m = (mult * jitter).reshape(ROWS, COLS, 1, 1, 1)
            m = np.broadcast_to(m, (ROWS, COLS, TILE, TILE, 3))
            m = m.transpose(0, 2, 1, 3, 4).reshape(H, W, 3)
            out = np.clip(canvas * m, 0, 255).astype(np.uint8)

            # mosaic as an effect (wet/dry), like datamoshing: the
            # treatment's strength follows the audio energy — quiet
            # passages stay close to the source footage, loud passages
            # let the mosaic take over
            wet = float(np.clip((0.15 + 0.85 * e + 0.30 * fl)
                                * wet_env[si], 0.0, 1.0))
            final = (out.astype(np.float32) * wet
                     + frame.astype(np.float32) * (1.0 - wet))
            final = np.clip(final, 0, 255).astype(np.uint8)

            proc.stdin.write(final.tobytes())
            if fi in previews:
                previews[fi] = final
            if fi % 250 == 0:
                print(f"frame {fi}/{n_frames} (e={e:.2f} fl={fl:.2f} "
                      f"chaos={chaos_p:.2f})", flush=True)
    finally:
        try:
            proc.stdin.close()
        except BrokenPipeError:
            pass
        proc.wait()

    for fi, img in previews.items():
        if img is not None:
            from PIL import Image
            Image.fromarray(img).save(
                os.path.join(args.workdir, f"preview_{fi:05d}.png"))
    print("done ->", args.out, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--target", required=True,
                    help="combination clip (hidden image source)")
    ap.add_argument("--libs", nargs="+", required=True,
                    help="tile-source clips (Gabe's pieces)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workdir", default="work_mosaic")
    ap.add_argument("--cols", type=int, default=100)
    ap.add_argument("--rows", type=int, default=80)
    ap.add_argument("--tile", type=int, default=16,
                    help="tile size in px; larger tiles keep source-clip "
                         "footage recognizable")
    ap.add_argument("--edl", default=None,
                    help="conductor edit decision list (JSON): per-section "
                         "chaos_scale / wet_scale multipliers over the "
                         "frame-by-frame audio signal")
    args = ap.parse_args()
    render(args)


if __name__ == "__main__":
    main()
