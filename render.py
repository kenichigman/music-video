#!/usr/bin/env python3
"""Audio-reactive pseudo-data-graph displacement renderer.

Style target: dark glowing graph/grid mesh displaced in real time by audio
frequency-band energy (TouchDesigner "audioreactive pseudo-data-graph
displacement" genre). Renders a final MP4 with the original audio muxed in.

Usage:
    python3 render.py --audio <wav/mp3/...> --out <mp4>
                     [--width 1280 --height 720 --fps 30]
"""
import argparse
import math
import os
import subprocess
import sys
import tempfile
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FFMPEG = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "ffprobe")

# ---------------------------------------------------------------- analysis

SR = 44100
N_BANDS = 64
F_LO, F_HI = 30.0, 16000.0
FFT_N = 2048

# normalization / smoothing time constants (seconds)
NORM_RELEASE = 2.0     # rolling-max release: quiet sections still move
SMOOTH_RELEASE = 0.20  # per-band release (~200ms), attack is instant
ENERGY_TAU = 0.10
FLASH_DECAY = 0.15


def decode_audio(path):
    """ffmpeg -> mono 44.1kHz s16 wav in a temp file; return float32 samples."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    cmd = [FFMPEG, "-v", "error", "-y", "-i", path,
           "-ac", "1", "-ar", str(SR), "-sample_fmt", "s16", tmp.name]
    subprocess.run(cmd, check=True)
    with wave.open(tmp.name, "rb") as w:
        assert w.getsampwidth() == 2 and w.getnchannels() == 1
        raw = w.readframes(w.getnframes())
    os.unlink(tmp.name)
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def band_edges():
    return np.logspace(math.log10(F_LO), math.log10(F_HI), N_BANDS + 1)


def build_bin_map():
    """Map each rfft bin to a band index (-1 = out of range)."""
    freqs = np.fft.rfftfreq(FFT_N, 1.0 / SR)
    edges = band_edges()
    idx = np.digitize(freqs, edges) - 1
    idx[(freqs < F_LO) | (freqs >= F_HI)] = -1
    idx = np.clip(idx, -1, N_BANDS - 1)
    return idx


def analyze(samples, fps):
    """Return per-frame: bands (F x 64 smoothed/normalized), energy (F,),
    flash (F,)."""
    hop = SR / fps
    n_frames = int(math.ceil(len(samples) / hop))
    bin_map = build_bin_map()
    valid = bin_map >= 0
    # per-band mean magnitude via bincount
    counts = np.bincount(bin_map[valid], minlength=N_BANDS).astype(np.float32)
    counts[counts == 0] = 1.0

    window = np.hanning(FFT_N)
    bands = np.zeros((n_frames, N_BANDS), dtype=np.float32)
    for f in range(n_frames):
        center = int((f + 0.5) * hop)
        seg = np.zeros(FFT_N, dtype=np.float32)
        a = max(0, center - FFT_N // 2)
        b = min(len(samples), center + FFT_N // 2)
        seg[a - (center - FFT_N // 2): b - (center - FFT_N // 2)] = samples[a:b]
        mag = np.abs(np.fft.rfft(seg * window))
        sums = np.bincount(bin_map[valid], weights=mag[valid], minlength=N_BANDS)
        bands[f] = sums / counts

    hop_dur = hop / SR
    rel_norm = math.exp(-hop_dur / NORM_RELEASE)
    rel_sm = math.exp(-hop_dur / SMOOTH_RELEASE)

    roll_max = np.full(N_BANDS, 1e-6, dtype=np.float32)
    smooth = np.zeros(N_BANDS, dtype=np.float32)
    out = np.zeros_like(bands)
    energy = np.zeros(n_frames, dtype=np.float32)
    flash = np.zeros(n_frames, dtype=np.float32)

    prev_log = np.zeros(12, dtype=np.float32)
    roll_flux = 1e-6
    flash_env = 0.0
    raw_e = np.zeros(n_frames, dtype=np.float32)
    for f in range(n_frames):
        m = bands[f]
        raw_e[f] = float(m.mean())
        # rolling max: instant attack, slow release
        roll_max = np.maximum(m, roll_max * rel_norm)
        n = np.clip(m / (roll_max + 1e-9), 0.0, 1.0)
        # temporal smoothing: instant attack, ~200ms release
        smooth = np.where(n >= smooth, n, smooth * rel_sm + n * (1.0 - rel_sm))
        out[f] = smooth
        # beat/onset: spectral flux on low bands
        logm = np.log1p(m[:12] / (roll_max[:12] + 1e-9) * 4.0)
        flux = float(np.maximum(0.0, logm - prev_log).sum())
        prev_log = logm
        roll_flux = max(flux, roll_flux * math.exp(-hop_dur / 1.0))
        bn = min(1.5, flux / (roll_flux + 1e-9))
        flash_env = max(flash_env * math.exp(-hop_dur / FLASH_DECAY), bn)
        flash[f] = min(1.0, flash_env)

    # absolute energy (for palette): raw band-mean normalized by track peak,
    # lightly smoothed. Normalized bands drive displacement; absolute level
    # drives color so quiet sections stay cool.
    peak = max(float(raw_e.max()), 1e-9)
    ea = raw_e / peak
    ce = 1.0 - math.exp(-hop_dur / ENERGY_TAU)
    se = np.zeros_like(ea)
    acc = 0.0
    for f in range(n_frames):
        acc += (ea[f] - acc) * ce
        se[f] = acc
    energy = se

    return out, energy, flash, n_frames * hop / SR


# ---------------------------------------------------------------- visual

BG = (5, 6, 7)
N_LINES = 28
PTS = 150
TRAIL = 0.88  # frame feedback blend


def palette(energy, name="classic"):
    """Deep teal/cyan -> magenta -> amber as energy rises (classic);
    dark teal -> magenta -> purple (glitch, Gabe's palette)."""
    if name == "glitch":
        teal = np.array([25.0, 165.0, 160.0])
        mag = np.array([225.0, 45.0, 150.0])
        pur = np.array([135.0, 65.0, 220.0])
        t = min(1.0, energy * 1.5)
        if t < 0.5:
            c = teal * (1 - t * 2) + mag * (t * 2)
        else:
            c = mag * (1 - (t - 0.5) * 2) + pur * ((t - 0.5) * 2)
        return c
    teal = np.array([30.0, 230.0, 210.0])
    mag = np.array([255.0, 60.0, 180.0])
    amb = np.array([255.0, 160.0, 60.0])
    t = min(1.0, energy * 1.5)
    if t < 0.5:
        c = teal * (1 - t * 2) + mag * (t * 2)
    else:
        c = mag * (1 - (t - 0.5) * 2) + amb * ((t - 0.5) * 2)
    return c


class Renderer:
    def __init__(self, width, height, fps, palette_name="classic",
                 rgb_split=False):
        self.W, self.H, self.fps = width, height, fps
        self.palette_name = palette_name
        self.rgb_split = rgb_split
        self.margin = int(width * 0.06)
        self.xs = np.linspace(self.margin, width - self.margin, PTS)
        # x position -> band index (log across the band range)
        frac = (self.xs - self.margin) / (width - 2 * self.margin)
        self.band_for_x = np.clip(
            (frac * N_BANDS).astype(int), 0, N_BANDS - 1)
        top = int(height * 0.18)
        bot = int(height * 0.86)
        self.base_y = np.linspace(top, bot, N_LINES)
        self.depth = 0.30 + 0.70 * (np.arange(N_LINES) / (N_LINES - 1))
        self.amp = height * 0.20  # max displacement for front line
        self.prev = np.zeros((height, width, 3), dtype=np.float32)
        try:
            self.font = ImageFont.load_default(size=15)
        except TypeError:
            self.font = ImageFont.load_default()
        # faint grid furniture (precomputed RGB layer)
        grid = Image.new("RGB", (width, height), (0, 0, 0))
        g = ImageDraw.Draw(grid)
        for x in range(0, width, 128):
            g.line([(x, 0), (x, height)], fill=(14, 18, 20))
        for y in range(0, height, 90):
            g.line([(0, y), (width, y)], fill=(12, 15, 17))
        self.grid = np.asarray(grid).astype(np.float32)

    def frame(self, bands, energy, flash, t):
        W, H = self.W, self.H
        col = palette(energy, self.palette_name)
        lift = 1.0 + 0.55 * flash
        layer = Image.new("RGB", (W, H), (0, 0, 0))
        d = ImageDraw.Draw(layer)
        # traveling ripple so the field feels alive even on steady tones
        ripple = (6.0 * np.sin(t * 0.9 + np.arange(N_LINES) * 0.45)).astype(int)
        for i in range(N_LINES):
            idx = (self.band_for_x + ripple[i] + i * 2) % N_BANDS
            disp = bands[idx] * self.amp * self.depth[i]
            ys = self.base_y[i] - disp
            pts = list(zip(self.xs.tolist(), ys.tolist()))
            c = col * (0.35 + 0.65 * self.depth[i]) * lift
            c = tuple(int(min(255, v)) for v in c)
            d.line(pts, fill=tuple(v // 4 for v in c), width=7)   # halo
            d.line(pts, fill=tuple(v * 3 // 5 for v in c), width=3)
            d.line(pts, fill=c, width=1)                          # core
        arr = np.asarray(layer).astype(np.float32)
        # RGB channel separation keyed to beat onsets (glitch ghost traces)
        if self.rgb_split and flash > 0.6:
            sh = int(10 * flash)
            r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
            r = np.roll(r, sh, axis=1)
            b = np.roll(b, -(sh // 2), axis=1)
            arr = np.stack([r, g, b], axis=2)
        # motion trails via frame feedback
        self.prev = self.prev * TRAIL + arr * (1.0 - TRAIL) + self.grid * 0.5
        img = Image.fromarray(np.clip(self.prev, 0, 255).astype(np.uint8))
        d2 = ImageDraw.Draw(img)
        fg = (95, 105, 110)
        d2.text((14, H - 30),
                f"T+{t:06.2f}s   BANDS {N_BANDS}   ENG {energy:.2f}"
                + ("   BEAT" if flash > 0.55 else ""),
                font=self.font, fill=fg)
        # energy bar, bottom right
        bw = int(W * 0.16)
        bx, by = W - bw - 16, H - 26
        d2.rectangle([bx, by, bx + bw, by + 8], outline=(60, 70, 75))
        d2.rectangle([bx, by, bx + int(bw * min(1.0, energy * 1.6)), by + 8],
                     fill=(40, 200, 185))
        # subtle film grain
        g = np.random.default_rng().integers(0, 5, (H, W, 1)).astype(np.float32)
        out = np.clip(np.asarray(img).astype(np.float32) + g - 2.0, 0, 255)
        return out.astype(np.uint8)


# ---------------------------------------------------------------- encode

def render_video(audio_path, out_path, width, height, fps,
                 palette_name="classic", rgb_split=False):
    samples = decode_audio(audio_path)
    bands, energy, flash, dur = analyze(samples, fps)
    n_frames = len(bands)
    print(f"audio {dur:.2f}s -> {n_frames} frames @ {fps}fps",
          flush=True)

    tmp_vid = out_path + ".video_only.mp4"
    enc = [FFMPEG, "-v", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
           "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-crf", "18", "-preset", "medium", tmp_vid]
    proc = subprocess.Popen(enc, stdin=subprocess.PIPE)

    rnd = Renderer(width, height, fps, palette_name=palette_name,
                   rgb_split=rgb_split)
    import time
    t0 = time.time()
    for f in range(n_frames):
        t = f / fps
        frame = rnd.frame(bands[f], energy[f], flash[f], t)
        proc.stdin.write(frame.tobytes())
        if (f + 1) % 150 == 0:
            el = time.time() - t0
            print(f"  frame {f + 1}/{n_frames} "
                  f"({(f + 1) / el:.1f} fps render)", flush=True)
    proc.stdin.close()
    proc.wait()
    render_dt = time.time() - t0
    print(f"rendered {n_frames} frames in {render_dt:.1f}s "
          f"({n_frames / render_dt:.1f} fps)", flush=True)

    # mux original audio
    subprocess.run(
        [FFMPEG, "-v", "error", "-y", "-i", tmp_vid, "-i", audio_path,
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-map", "0:v:0", "-map", "1:a:0", "-shortest", out_path],
        check=True)
    os.unlink(tmp_vid)
    return dur, render_dt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--palette", default="classic",
                    choices=["classic", "glitch"])
    ap.add_argument("--rgb-split", action="store_true")
    a = ap.parse_args()
    dur, rdt = render_video(a.audio, a.out, a.width, a.height, a.fps,
                            palette_name=a.palette, rgb_split=a.rgb_split)
    print(f"done: {a.out}  ({dur:.2f}s audio, rendered in {rdt:.1f}s)")


if __name__ == "__main__":
    main()
