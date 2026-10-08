#!/usr/bin/env python3
# PALIMPSEST — Linux numpy renderer
# Thesis: "Destruction as devotion."
# Fragment reconstitution driven by the real score (uReveal, uTear per frame).
import numpy as np
import os
import subprocess
import sys

W, H = 690, 480
FPS = 30
DURATION = 240  # seconds
NFRAMES = FPS * DURATION  # 7200

FOOTAGE = os.environ.get("PALIMPSEST_FOOTAGE", "sources/palimpsest/footage.mp4")
AUDIO_NPY = '/tmp/audio_analysis.npy'
OUT_MP4 = os.environ.get("PALIMPSEST_OUT", "palimpsest/palimpsest_test_real.mp4")

# Load audio analysis
audio = np.load(AUDIO_NPY)  # (7200, 2): uReveal, uTear
print(f"Audio: {audio.shape}, uReveal [{audio[:,0].min():.3f}, {audio[:,0].max():.3f}]", flush=True)

# Pre-compute static block data
# UV grid
ys, xs = np.mgrid[0:H, 0:W]
uv_x = (xs + 0.5) / W
uv_y = (ys + 0.5) / H

# Block grid 40x22.5
grid_x, grid_y = 40.0, 27.8
block_id_x = np.floor(uv_x * grid_x).astype(np.int32)
block_id_y = np.floor(uv_y * grid_y).astype(np.int32)

# Hash function (GLSL: fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123))
def hash2(px, py):
    d = px * 127.1 + py * 311.7
    s = np.sin(d) * 43758.5453123
    return s - np.floor(s)

h1 = hash2(block_id_x.astype(np.float64), block_id_y.astype(np.float64))
h2 = hash2(block_id_x.astype(np.float64) + 19.7, block_id_y.astype(np.float64) + 19.7)
h3 = hash2(block_id_x.astype(np.float64) + 47.3, block_id_y.astype(np.float64) + 47.3)
band = np.floor(block_id_y.astype(np.float64) / 2.0)

print("Static maps computed", flush=True)

# FFmpeg: extract footage frames as raw RGB
extract_cmd = [
    'ffmpeg', '-v', 'error',
    '-ss', '20', '-i', FOOTAGE,
    '-t', str(DURATION),
    '-r', str(FPS),
    '-f', 'rawvideo', '-pix_fmt', 'rgb24',
    '-'
]
# FFmpeg: encode output
encode_cmd = [
    'ffmpeg', '-y', '-v', 'error',
    '-f', 'rawvideo', '-pix_fmt', 'rgb24',
    '-s', f'{W}x{H}', '-r', str(FPS),
    '-i', '-',
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
    '-crf', '18', '-preset', 'medium',
    OUT_MP4
]

extract = subprocess.Popen(extract_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
encode = subprocess.Popen(encode_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

frame_size = W * H * 3

def sample_bilinear(img, map_x, map_y):
    """img: (H, W, 3) float32 0..1. map_x, map_y: (H, W) in pixel coords. Returns (H, W, 3)."""
    # Clip to bounds
    map_x = np.clip(map_x, 0, W - 1.001)
    map_y = np.clip(map_y, 0, H - 1.001)
    x0 = np.floor(map_x).astype(np.int32)
    y0 = np.floor(map_y).astype(np.int32)
    x1 = x0 + 1
    y1 = y0 + 1
    fx = map_x - x0
    fy = map_y - y0
    # Gather
    # img[y, x] -> use advanced indexing
    Ia = img[y0, x0]  # (H, W, 3)
    Ib = img[y0, x1]
    Ic = img[y1, x0]
    Id = img[y1, x1]
    fx = fx[..., None]
    fy = fy[..., None]
    return Ia * (1 - fx) * (1 - fy) + Ib * fx * (1 - fy) + Ic * (1 - fx) * fy + Id * fx * fy

for i in range(NFRAMES):
    # Read source frame
    raw = extract.stdout.read(frame_size)
    if len(raw) < frame_size:
        print(f"Frame {i}: short read ({len(raw)}), stopping", flush=True)
        break
    src = np.frombuffer(raw, dtype=np.uint8).reshape(H, W, 3).astype(np.float32) / 255.0
    
    uR = float(audio[i, 0])
    uT = float(audio[i, 1])
    uTime = float(i) / FPS
    
    # Displacement
    dispAmt = (1.0 - uR) * 0.45
    disp_x = (h1 - 0.5) * 2.0 * dispAmt
    disp_y = (h2 - 0.5) * 2.0 * dispAmt
    
    # Tear selection (depends on time)
    tear_hash = hash2(band, np.full_like(band, np.floor(uTime * 8.0)))
    tearSel = (tear_hash >= 0.72).astype(np.float64)
    disp_x += tearSel * uT * (h3 - 0.5) * 0.9
    
    # Sample UV (fract = wrap)
    sample_u = (uv_x + disp_x) % 1.0
    sample_v = (uv_y + disp_y) % 1.0
    map_x = sample_u * (W - 1)
    map_y = sample_v * (H - 1)
    
    col = sample_bilinear(src, map_x, map_y)
    
    # Chromatic aberration
    ab = uT * 0.012 + (1.0 - uR) * 0.004
    ab_px = ab * W
    col_r = sample_bilinear(src[..., 0:1], map_x + ab_px, map_y)[..., 0]
    col_b = sample_bilinear(src[..., 2:3], map_x - ab_px, map_y)[..., 0]
    col = np.stack([col_r, col[..., 1], col_b], axis=-1)
    
    # Brightness
    brightness = 0.12 + (1.0 - 0.12) * uR  # mix(0.12, 1.0, uReveal)
    edge = (np.clip(uR / 0.15, 0, 1) * 0.1)  # smoothstep approx
    # Actually smoothstep(0, 0.15, uR): 0 if uR<0, 1 if uR>0.15, smooth in between
    t = np.clip(uR / 0.15, 0, 1)
    edge = (t * t * (3 - 2 * t)) * 0.1
    col *= (brightness + edge)
    
    # Grain
    grain_h = hash2(uv_x * 913.7 + uTime, uv_y * 913.7 + uTime)
    grain = (grain_h - 0.5) * 0.06
    col += grain[..., None] * (0.3 + 0.7 * uR)
    
    # Clip and convert
    col = np.clip(col, 0, 1)
    out_frame = (col * 255).astype(np.uint8)
    encode.stdin.write(out_frame.tobytes())
    
    if (i + 1) % 100 == 0:
        print(f"Frame {i+1}/{NFRAMES} done", flush=True)

extract.stdout.close()
extract.wait()
encode.stdin.close()
encode.wait()
print(f"Done: {OUT_MP4}", flush=True)
