#!/usr/bin/env python3
"""Vocal-over-beat DJ mashup.

Chain: time-stretch vocal to beat BPM (rubberband) -> trim leading silence ->
vocal chain (HP/comp) -> drop on downbeat after intro -> fine-align via
xcorr + pulse-clarity tiebreak -> sidechain-style ducking -> master
(normalize, fades) -> WAV + MP3. Verifies alignment, no drift, peak headroom.

Usage:
  python3 mashup.py --vocal acapella.mp3 --beat instrumental.mp3 \\
      --vocal-bpm 97 --beat-bpm 103 --out mix.wav [--workdir work]
"""
import argparse
import os
import subprocess

import numpy as np
from scipy import signal
from scipy.io import wavfile

SR = 44100


def run(cmd):
    subprocess.run(cmd, check=True)


def decode(path):
    """Decode to stereo float32 @ SR."""
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-ar", str(SR),
           "-ac", "2", "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).copy()


def rms_envelope(mono, win_s=0.05):
    w = int(win_s * SR)
    ker = np.ones(w) / w
    return np.sqrt(np.convolve(mono ** 2, ker, mode="same") + 1e-12)


def peak_envelope(mono, attack_ms=5.0, release_ms=150.0):
    ca = np.exp(-1.0 / (attack_ms * SR / 1000.0))
    cr = np.exp(-1.0 / (release_ms * SR / 1000.0))
    ax = np.abs(mono)
    e_att = signal.lfilter([1 - ca], [1, -ca], ax)
    e_rel = signal.lfilter([1 - cr], [1, -cr], ax)
    return np.maximum(e_att, e_rel)


def biquad_shelf(f0, gain_db, kind="low"):
    A = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * f0 / SR
    alpha = np.sin(w0) / np.sqrt(2.0)
    cw = np.cos(w0)
    sA = 2 * np.sqrt(A) * alpha
    if kind == "high":
        b0 = A * ((A + 1) + (A - 1) * cw + sA)
        b1 = -2 * A * ((A - 1) + (A + 1) * cw)
        b2 = A * ((A + 1) + (A - 1) * cw - sA)
        a0 = (A + 1) - (A - 1) * cw + sA
        a1 = 2 * ((A - 1) - (A + 1) * cw)
        a2 = (A + 1) - (A - 1) * cw - sA
    else:
        b0 = A * ((A + 1) - (A - 1) * cw + sA)
        b1 = 2 * A * ((A - 1) - (A + 1) * cw)
        b2 = A * ((A + 1) - (A - 1) * cw - sA)
        a0 = (A + 1) + (A - 1) * cw + sA
        a1 = -2 * ((A - 1) + (A + 1) * cw)
        a2 = (A + 1) + (A - 1) * cw - sA
    return [b0 / a0, b1 / a0, b2 / a0], [1.0, a1 / a0, a2 / a0]


def flux22(y, asr=22050, hop=512):
    f, t, Z = signal.stft(y, fs=asr, nperseg=2048, noverlap=2048 - hop,
                          boundary=None, padded=False)
    mag = np.abs(Z)
    logmag = np.log1p(100.0 * mag / (mag.max() + 1e-9))
    fl = np.sum(np.maximum(0.0, np.diff(logmag, prepend=logmag[:, [0]], axis=1)), axis=0)
    k = np.hanning(5)
    k /= k.sum()
    return np.convolve(fl, k, mode="same")


def pulse_clarity(mix_mono, beat_period, fps):
    mix22 = signal.resample_poly(mix_mono, 1, 2)
    e = flux22(mix22)
    e = e / (e.max() + 1e-9)
    ac = np.correlate(e - e.mean(), e - e.mean(), mode="full")[len(e) - 1:]
    ac /= ac[0] + 1e-12
    lag = int(round(beat_period * fps))
    return float(ac[lag] + ac[2 * lag] - ac[lag // 2])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vocal", required=True)
    ap.add_argument("--beat", required=True)
    ap.add_argument("--vocal-bpm", type=float, required=True)
    ap.add_argument("--beat-bpm", type=float, required=True)
    ap.add_argument("--out", required=True, help="output WAV path (MP3 alongside)")
    ap.add_argument("--workdir", default="work_mashup")
    ap.add_argument("--intro-bars", type=int, default=4)
    ap.add_argument("--vocal-db", type=float, default=-2.0,
                    help="vocal level relative to beat, dB")
    args = ap.parse_args()

    os.makedirs(args.workdir, exist_ok=True)
    ratio = args.beat_bpm / args.vocal_bpm
    beat_period = 60.0 / args.beat_bpm
    bar = 4 * beat_period

    print(f"== 1. stretch vocal x{ratio:.4f} (rubberband)")
    run(["ffmpeg", "-v", "error", "-y", "-i", args.vocal,
         "-filter:a", f"rubberband=tempo={ratio:.6f}:transients=mixed",
         "-ar", str(SR), "-ac", "2",
         os.path.join(args.workdir, "vocals_stretched.wav")])
    run(["ffmpeg", "-v", "error", "-y", "-i", args.beat,
         "-ar", str(SR), "-ac", "2",
         os.path.join(args.workdir, "beat.wav")])

    print("== 2. load + trim leading silence; beat bass shaping")
    voc = decode(os.path.join(args.workdir, "vocals_stretched.wav"))
    beat = decode(os.path.join(args.workdir, "beat.wav"))
    b, a = biquad_shelf(80.0, 4.0, "low")
    beat = signal.lfilter(b, a, beat, axis=0)
    sos = signal.butter(4, 30.0, btype="highpass", fs=SR, output="sos")
    beat = signal.sosfiltfilt(sos, beat, axis=0)
    beat = beat * 10 ** (2.0 / 20)
    mono_v = voc.mean(axis=1)
    idx = np.argmax(np.abs(mono_v) > 0.02)
    trim = max(0, idx - int(0.15 * SR))
    voc = voc[trim:]
    print(f"   trimmed {trim / SR:.2f}s; vocal {len(voc) / SR:.1f}s")

    print("== 3. vocal chain: HP 80Hz + gentle 3:1 compression")
    sos = signal.butter(4, 80.0, btype="highpass", fs=SR, output="sos")
    voc = signal.sosfiltfilt(sos, voc, axis=0)
    voc *= 10 ** (-20.0 / 20) / (np.sqrt(np.mean(voc ** 2)) + 1e-12)
    mono = voc.mean(axis=1)
    env = peak_envelope(mono)
    over_db = np.maximum(0.0, 20 * np.log10(env + 1e-9) - (-18))
    gr = 10 ** (-(over_db * (1 - 1 / 3.0)) / 20.0)
    voc = voc * gr[:, None] * 10 ** (3.0 / 20)

    print("== 4. beat grid + drop after intro")
    t0 = 0.53  # first beat onset; adjust per track
    drop = t0
    while drop < args.intro_bars * bar:
        drop += bar
    print(f"   drop at {drop:.3f}s")

    print("== 5. fine alignment: xcorr + pulse-clarity tiebreak")
    fps2 = 22050 / 512
    bv_f = flux22(signal.resample_poly(beat.mean(axis=1), 1, 2))
    vv_f = flux22(signal.resample_poly(voc.mean(axis=1), 1, 2))
    n_vf = len(vv_f)
    curve = []
    for d_ms in range(-600, 605, 10):
        s = int(round((drop + d_ms / 1000.0) * fps2))
        seg = bv_f[s:s + n_vf]
        if len(seg) < n_vf:
            continue
        xc = float(np.sum(vv_f * seg) /
                   (np.linalg.norm(vv_f) * np.linalg.norm(seg) + 1e-12))
        curve.append((d_ms, xc))
    peaks = []
    for i in range(1, len(curve) - 1):
        if curve[i][1] >= curve[i - 1][1] and curve[i][1] >= curve[i + 1][1]:
            if not peaks or curve[i][0] - peaks[-1][0] >= 150:
                peaks.append(curve[i])
            elif curve[i][1] > peaks[-1][1]:
                peaks[-1] = curve[i]
    peaks.sort(key=lambda t: -t[1])
    rms_b = np.sqrt(np.mean(beat ** 2)) + 1e-12
    rms_v = np.sqrt(np.mean(voc ** 2)) + 1e-12
    vg = rms_b * 1.1 / rms_v
    best_d, best_c = 0.0, -1e18
    for d_ms, xc in peaks[:4]:
        d = d_ms / 1000.0
        s0t = int(round((drop + d) * SR))
        n = min(len(beat) - s0t, len(voc), int(60 * SR))
        test = beat[s0t:s0t + n] * 0.8 + voc[:n] * vg
        c = pulse_clarity(test.mean(axis=1), beat_period, fps2)
        print(f"   nudge {d_ms:+d}ms: xcorr {xc:.4f}, clarity {c:.4f}")
        if c > best_c:
            best_c, best_d = c, d
    drop += best_d
    print(f"   => drop {drop:.3f}s (clarity {best_c:.4f})")

    print("== 6. duck beat under vocals")
    venv = rms_envelope(mono)
    venv_db = 20 * np.log10(venv + 1e-9)
    duck_amt = np.clip((venv_db + 48) / 28.0, 0, 1) ** 1.5
    g = np.empty_like(duck_amt)
    e = 0.0
    aa, rr = np.exp(-1 / (0.015 * SR)), np.exp(-1 / (0.250 * SR))
    for i, x in enumerate(duck_amt):
        c = aa if x > e else rr
        e = c * e + (1 - c) * x
        g[i] = e
    duck = 1.0 - 0.32 * g

    print("== 7. assemble + master")
    nb, nv = len(beat), len(voc)
    s0 = int(round(drop * SR))
    mix_len = max(nb, s0 + nv)
    mix = np.zeros((mix_len, 2), dtype=np.float64)
    duck_full = np.ones(nb)
    duck_full[s0:s0 + nv] = duck[:max(0, min(nv, nb - s0))]
    b_ducked = beat * duck_full[:, None]
    mix[:nb] += b_ducked
    rms_b = np.sqrt(np.mean(b_ducked ** 2))
    rms_v = np.sqrt(np.mean(voc ** 2))
    v_gain = 10 ** ((20 * np.log10(rms_b) + args.vocal_db -
                     20 * np.log10(rms_v)) / 20.0)
    mix[s0:s0 + nv] += voc * v_gain
    peak = np.abs(mix).max()
    mix *= (10 ** (-1.0 / 20)) / peak
    fi, fo = int(1.5 * SR), int(8.0 * SR)
    mix[:fi] *= np.sin(0.5 * np.pi * np.linspace(0, 1, fi))[:, None] ** 2
    mix[-fo:] *= np.cos(0.5 * np.pi * np.linspace(0, 1, fo))[:, None] ** 2
    print(f"   {mix_len / SR:.1f}s, peak {20 * np.log10(np.abs(mix).max()):.1f} dBFS")

    print("== 8. write WAV + MP3")
    mix16 = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
    wavfile.write(args.out, SR, mix16)
    mp3 = os.path.splitext(args.out)[0] + ".mp3"
    run(["ffmpeg", "-v", "error", "-y", "-i", args.out,
         "-filter:a", "volume=-2dB",
         "-codec:a", "libmp3lame", "-b:a", "320k", mp3])
    print(f"done: {args.out}, {mp3}")


if __name__ == "__main__":
    main()
