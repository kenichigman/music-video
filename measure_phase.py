#!/usr/bin/env python3
"""Phase measurement: per-frame video diff energy (SEQUENTIAL decode) vs
audio onsets, for a film window. Usage:
  measure_phase.py <video.mp4> <wav> <out.npz> [f0 f1]
Saves diff energy per frame for frames [f0,f1) and prints, for each
spec onset, the nearest strong diff-accent peak and its offset.
"""
import subprocess
import sys

import numpy as np

FF = "ffmpeg"
W, H, FPS = 848, 464, 30
ONSETS = [119.4, 130.0, 139.2, 151.4, 153.2, 160.7]


def diff_profile(path, f0, f1):
    cmd = [FF, "-v", "error", "-i", path, "-f", "rawvideo",
           "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    fb = W * H * 3
    diffs = []
    prev = None
    n = 0
    while True:
        raw = proc.stdout.read(fb)
        if len(raw) < fb:
            break
        fr = np.frombuffer(raw, dtype=np.uint8).reshape(H, W, 3)
        if f0 <= n < f1:
            if prev is not None:
                diffs.append(float(np.abs(
                    fr[::2, ::2].astype(np.int16)
                    - prev[::2, ::2].astype(np.int16)).mean()))
            else:
                diffs.append(0.0)
        prev = fr
        n += 1
    proc.wait()
    return np.array(diffs), n


def main():
    video, wav, out = sys.argv[1], sys.argv[2], sys.argv[3]
    f0 = int(sys.argv[4]) if len(sys.argv) > 4 else 3450
    f1 = int(sys.argv[5]) if len(sys.argv) > 5 else 5010
    d, n = diff_profile(video, f0, f1)
    print(f"decoded {n} frames; profile frames {f0}..{f0 + len(d) - 1}",
          flush=True)
    np.savez(out, diffs=d, f0=f0)
    # accent = local peak of diff energy (frame i > neighbours in +-3)
    for o in ONSETS:
        c = int(round(o * FPS))
        lo, hi = c - FPS, c + FPS
        seg = d[lo - f0:hi - f0]
        tseg = np.arange(lo, hi) / FPS
        peaks = []
        for i in range(2, len(seg) - 2):
            if (seg[i] == seg[i - 2:i + 3].max()
                    and seg[i] > 0.6 * seg.max()):
                peaks.append((tseg[i], seg[i]))
        if peaks:
            best = min(peaks, key=lambda p: abs(p[0] - o))
            print(f"onset {o:6.1f}s: nearest accent {best[0]:7.3f}s "
                  f"(offset {best[0] - o:+.3f}s, energy {best[1]:.2f})")
        else:
            j = int(np.argmax(seg))
            print(f"onset {o:6.1f}s: no local peak; max at "
                  f"{tseg[j]:.3f}s (offset {tseg[j] - o:+.3f}s)")


if __name__ == "__main__":
    main()
