#!/usr/bin/env python3
"""Graph3 preview stage 1a: window base WITHOUT any processing.
Identical to test 1/2's extract_base_win.py — sequential decode
of the locked patch-#3 assembly, film frames 990..1469
(33.0-49.0s), passthrough into the same 1s-IDR encode every
taste leg used (keyint 30, bframes 0, crf 16). Only the output
path differs (graph3prev)."""
import os
RIG_ROOT = os.environ.get("RIG_ROOT", os.path.join(os.getcwd(), "rig-data"))
import subprocess
import numpy as np

W, H = 848, 464
FSZ = W * H * 3
BASE = RIG_ROOT + '/assembly/assembly.mp4'
OUT = RIG_ROOT + '/rig2/graph3prev/comp_win_graph.h264'
F_START = int(os.environ.get("GRAPH_F_START", "990"))
N = int(os.environ.get("GRAPH_FRAMES", "480"))

bp = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', BASE, '-an',
                       '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                      stdout=subprocess.PIPE)
for _ in range(F_START):
    buf = bp.stdout.read(FSZ)
    assert len(buf) == FSZ, 'base short during skip'
enc = subprocess.Popen(
    ['ffmpeg', '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
     '-s', '%dx%d' % (W, H), '-r', '30', '-i', '-', '-an',
     '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-preset', 'medium',
     '-crf', '16', '-g', '30', '-x264-params',
     'keyint=30:min-keyint=30:scenecut=0:bframes=0:weightp=0',
     '-f', 'h264', OUT], stdin=subprocess.PIPE)
for i in range(N):
    buf = bp.stdout.read(FSZ)
    assert len(buf) == FSZ, 'base short at %d' % i
    enc.stdin.write(buf)
bp.stdout.close(); bp.wait()
enc.stdin.close(); enc.wait()
print('base window encode done: %d frames -> %s' % (N, OUT))
