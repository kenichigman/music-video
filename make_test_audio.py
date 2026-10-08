#!/usr/bin/env python3
"""20s synthetic test signal: sweep + kicks + hats + quiet section + noise sweep."""
import numpy as np
import wave

SR = 44100
DUR = 20.0
n = int(SR * DUR)
t = np.arange(n) / SR
sig = np.zeros(n, dtype=np.float64)
rng = np.random.default_rng(7)


def add(a, b, s, e):
    sig[s:e] += a


# 0-4s: sine sweep 60 -> 400 Hz
s, e = 0, int(4 * SR)
phase = 2 * np.pi * np.cumsum(60 + (400 - 60) * np.linspace(0, 1, e - s)) / SR
add(0.5 * np.sin(phase), None, s, e)

# 4-12s: kick hits every 0.5s + hats every 0.25s (offset)
for k in range(16):
    st = int((4 + k * 0.5) * SR)
    L = int(0.30 * SR)
    env = np.exp(-np.arange(L) / (SR * 0.07))
    f = 55 - 25 * np.arange(L) / L  # pitch drop
    ph = 2 * np.pi * np.cumsum(f) / SR
    add(0.9 * env * np.sin(ph), None, st, st + L)
for h in range(32):
    st = int((4.125 + h * 0.25) * SR)
    L = int(0.06 * SR)
    nz = rng.standard_normal(L)
    nz = np.diff(nz, prepend=0)  # crude highpass
    env = np.exp(-np.arange(L) / (SR * 0.012))
    add(0.28 * env * nz / (np.abs(nz).max() + 1e-9), None, st, st + L)

# 12-16s: quiet section (tests normalization)
s, e = int(12 * SR), int(16 * SR)
add(0.045 * np.sin(2 * np.pi * 220 * t[s:e]), None, s, e)
add(0.012 * rng.standard_normal(e - s), None, s, e)

# 16-20s: noise sweep with LFO amplitude + final big hit at 19s
s, e = int(16 * SR), int(20 * SR)
nz = rng.standard_normal(e - s)
lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 2.0 * t[s:e])
add(0.35 * lfo * nz / (np.abs(nz).max() + 1e-9) * 3.0, None, s, e)
st = int(19 * SR)
L = int(0.5 * SR)
env = np.exp(-np.arange(L) / (SR * 0.12))
add(0.95 * env * np.sin(2 * np.pi * 48 * np.arange(L) / SR), None, st, st + L)

sig = np.clip(sig, -1, 1)
pcm = (sig * 32767).astype(np.int16)
with wave.open("test_signal.wav", "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())
print("wrote test_signal.wav", DUR, "s")
