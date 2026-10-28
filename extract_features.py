#!/usr/bin/env python3
"""Per-second audio descriptors for the Conductor (local LLM edit decisions).

Reads a track, decodes to mono 44.1k via render.decode_audio, and emits a
compact JSON table, one row per second:
  t        - second index
  energy   - RMS energy, 0..1 normalized to track peak
  bright   - spectral centroid, 0..1 normalized
  flux     - onset density proxy (spectral flux), 0..1 normalized
  vox      - vocal-band (300..3400 Hz) energy share, 0..1

Usage: python3 extract_features.py --audio track.mp3 --out features.json
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render import decode_audio  # noqa: E402

SR = 44100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    x = decode_audio(args.audio).astype(np.float64)
    dur = len(x) / SR
    n_sec = int(dur)
    win = SR  # 1-second windows
    hop = SR // 2  # 0.5s hop for flux, then aggregate per second

    rows = []
    prev_mag = None
    fluxes = []
    # spectral flux at 0.5s hop
    for start in range(0, len(x) - win, hop):
        seg = x[start:start + win] * np.hanning(win)
        mag = np.abs(np.fft.rfft(seg))
        if prev_mag is not None:
            fluxes.append(float(np.maximum(0, mag - prev_mag).sum()))
        prev_mag = mag
    fluxes = np.array(fluxes) if fluxes else np.zeros(1)

    freqs = np.fft.rfftfreq(win, 1.0 / SR)
    vox_mask = (freqs >= 300) & (freqs <= 3400)

    for s in range(n_sec):
        seg = x[s * SR:(s + 1) * SR]
        if len(seg) == 0:
            continue
        rms = float(np.sqrt(np.mean(seg ** 2)))
        w = seg * np.hanning(len(seg))
        mag = np.abs(np.fft.rfft(w, n=win))
        tot = mag.sum() + 1e-9
        centroid = float((freqs * mag).sum() / tot)
        vox = float(mag[vox_mask].sum() / tot)
        # flux: average the two 0.5s hops inside this second
        fi = fluxes[max(0, 2 * s - 1):2 * s + 1]
        flux = float(fi.mean()) if len(fi) else 0.0
        rows.append({"t": s, "rms": rms, "centroid_hz": centroid,
                     "flux": flux, "vox": vox})

    # normalize 0..1 against track peaks
    for key, out in (("rms", "energy"), ("centroid_hz", "bright"),
                     ("flux", "flux"), ("vox", "vox")):
        peak = max(r[key] for r in rows) or 1e-9
        for r in rows:
            r[out] = round(r[key] / peak, 3)
        if out != key:
            for r in rows:
                del r[key]
    # keep vox under its own name already; rows now have t, energy, bright, flux, vox

    with open(args.out, "w") as f:
        json.dump({"duration_s": round(dur, 2), "seconds": rows}, f)
    print(f"wrote {args.out}: {len(rows)} seconds, track {dur:.1f}s")


if __name__ == "__main__":
    main()
