#!/usr/bin/env python3
"""EFFECT 2 TEST 2 — MOSH GRAPH tracker (local WSL).

Second graph layer (director's note): a graph that tracks the
ACTUAL MOSHING — the motion of the finished, moshed picture
itself: smear fronts and carried content. Method: a fixed grid
of probe points over the finished base (preview_graph_base.mp4,
the same moshed leg the film is built on); per frame, each
probe's 21x21 patch is NCC-matched in the next frame (+-13 px).
Probes whose match is confident AND whose flow is significant
become nodes; ids propagate by predicted position, so a node
RIDES the melt. Edges are built at composite time between
grid-neighbors whose flow directions agree (coherent fronts).

Inside moshed segments the carried content sweeps coherently —
the graph should light up there; in clean segments it reports
only the picture's real motion. Stats prove the split.
"""
import os
RIG_ROOT = os.environ.get("RIG_ROOT", os.path.join(os.getcwd(), "rig-data"))
import json, subprocess
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

G2 = RIG_ROOT + '/rig2/graph2prev'
BASE = RIG_ROOT + '/rig2/graphprev/preview_graph_base.mp4'
W, H = 848, 464
FSZ = W * H * 3
N = int(os.environ.get("GRAPH_FRAMES", "480"))
# --- COST DRIVERS (desktop preset as shipped; see README.md) ---
RES_SCALE = 1.0        # probes run on the native 848x464 base
STEP = 44              # probe grid spacing, px (density)
PATCH = 21
SEARCH = 13
NCC_THR = 0.55
DIFF_GATE = 2.0        # mean |diff| of static patch -> flow 0
TEX_STD_MIN = 3.0      # flat-patch gate (gray-level std)
RESID_MIN = 1.2        # residual-flow node threshold, px/frame
FRONT_MIN_SP = 6.0     # front rule: raw speed floor, px/frame
FRONT_COS = 0.82       # front rule: >= ~35 deg off median dir
MOSH_CAP = 64          # max nodes drawn per frame
CLAIM_R = 34.0         # id-propagation claim radius, px
MOSH_SEGS = {1, 9, 15}  # moshed 1s segments of the window (test 1)

GX = list(range(22, W - 21, STEP))
GY = list(range(22, H - 21, STEP))
print('grid %d x %d = %d probes' % (len(GX), len(GY),
                                   len(GX) * len(GY)), flush=True)


def gray_of(buf):
    a = np.frombuffer(buf, dtype=np.uint8).reshape(H, W, 3)
    return (0.299 * a[:, :, 0] + 0.587 * a[:, :, 1]
            + 0.114 * a[:, :, 2]).astype(np.float32)


def match(gray, tmpl, cx, cy):
    hp = PATCH // 2
    x0, x1 = cx - hp - SEARCH, cx + hp + SEARCH + 1
    y0, y1 = cy - hp - SEARCH, cy + hp + SEARCH + 1
    if x0 < 0 or y0 < 0 or x1 > W or y1 > H:
        return None
    region = gray[y0:y1, x0:x1]
    win = sliding_window_view(region, (PATCH, PATCH))
    t = tmpl - tmpl.mean()
    tn = float(np.sqrt((t * t).sum()))
    if tn < 1e-6:
        return None
    wm = win - win.mean(axis=(2, 3), keepdims=True)
    wn = np.sqrt((wm * wm).sum(axis=(2, 3)))
    ncc = (wm * t).sum(axis=(2, 3)) / np.maximum(wn * tn, 1e-9)
    iy, ix = np.unravel_index(int(np.argmax(ncc)), ncc.shape)
    return float(ncc[iy, ix]), int(x0 + ix + hp - cx), \
        int(y0 + iy + hp - cy)


def main():
    bp = subprocess.Popen(
        ['ffmpeg', '-v', 'error', '-i', BASE, '-an',
         '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
        stdout=subprocess.PIPE)
    prev = None
    prev_nodes = []        # dicts with id, gx, gy, x, y, dx, dy
    next_id = 1
    frames_out = []
    born = {}
    spans = []
    seg_nodes = {'mosh': [], 'clean': []}
    hp = PATCH // 2
    for wf in range(N):
        buf = bp.stdout.read(FSZ)
        assert len(buf) == FSZ, 'base short at %d' % wf
        gray = gray_of(buf)
        kept = []
        if prev is not None:
            # pass 1: every confident probe match (the raw field)
            allm = []
            for gy in GY:
                for gx in GX:
                    tmpl = prev[gy - hp:gy + hp + 1,
                                gx - hp:gx + hp + 1]
                    if float(tmpl.std()) < TEX_STD_MIN:
                        continue    # flat patch: nothing to track
                    if float(np.abs(gray[gy - hp:gy + hp + 1,
                                         gx - hp:gx + hp + 1]
                                    - tmpl).mean()) < DIFF_GATE:
                        continue
                    m = match(gray, tmpl, gx, gy)
                    if m is None:
                        continue
                    ncc, dx, dy = m
                    if ncc >= NCC_THR:
                        allm.append({'gx': gx, 'gy': gy, 'x': gx,
                                     'y': gy, 'dx': dx, 'dy': dy,
                                     'ncc': ncc})
            # ego-motion: the frame's median flow is the camera;
            # the graph tracks what deviates from it (fronts)
            cands = []
            if allm:
                mv = np.median([[m['dx'], m['dy']] for m in allm],
                               axis=0)
                msp = float((mv[0] ** 2 + mv[1] ** 2) ** 0.5)
                for m in allm:
                    rdx, rdy = m['dx'] - mv[0], m['dy'] - mv[1]
                    rsp = (rdx * rdx + rdy * rdy) ** 0.5
                    sp = (m['dx'] ** 2 + m['dy'] ** 2) ** 0.5
                    front = False
                    if sp >= FRONT_MIN_SP and msp > 1e-6:
                        cos = (m['dx'] * mv[0] + m['dy'] * mv[1]) \
                            / (sp * msp)
                        front = cos < FRONT_COS
                    if rsp >= RESID_MIN or front:
                        m['rdx'], m['rdy'] = float(rdx), float(rdy)
                        m['sp'] = rsp * 30.0
                        cands.append(m)
                cands.sort(key=lambda c: -c['sp'])
                cands = cands[:MOSH_CAP]
            # propagate ids: strongest matches claim first
            cands.sort(key=lambda c: -c['ncc'])
            used = set()
            for c in cands:
                best, bd = None, CLAIM_R
                for pn in prev_nodes:
                    if pn['id'] in used:
                        continue
                    px, py = pn['x'] + pn['dx'], pn['y'] + pn['dy']
                    d = ((px - c['x']) ** 2 + (py - c['y']) ** 2) ** 0.5
                    if d < bd:
                        best, bd = pn, d
                if best is not None:
                    c['id'] = best['id']
                    used.add(best['id'])
                else:
                    c['id'] = next_id
                    born[next_id] = wf
                    next_id += 1
                kept.append(c)
            alive_ids = {c['id'] for c in kept}
            for pn in prev_nodes:
                if pn['id'] not in alive_ids and pn['id'] in born:
                    spans.append(wf - 1 - born.pop(pn['id']))
        frames_out.append({'wf': wf, 'nodes': [
            {'id': c['id'], 'gx': c['gx'], 'gy': c['gy'],
             'x': c['x'], 'y': c['y'], 'dx': c['dx'], 'dy': c['dy'],
             'rdx': round(c['rdx'], 2), 'rdy': round(c['rdy'], 2),
             'ncc': round(c['ncc'], 3),
             'sp': round(c['sp'], 1)} for c in kept]})
        seg_nodes['mosh' if (wf // 30) in MOSH_SEGS
                  else 'clean'].append(len(kept))
        prev_nodes = [{'id': c['id'], 'x': c['x'], 'y': c['y'],
                       'dx': c['dx'], 'dy': c['dy']} for c in kept]
        prev = gray
        if (wf + 1) % 120 == 0:
            print('  mosh track %d/480 (kept %d)' % (wf + 1, len(kept)),
                  flush=True)
    bp.stdout.close(); bp.wait()
    for pn in prev_nodes:
        if pn['id'] in born:
            spans.append(N - 1 - born[pn['id']])
    stats = {'nodes_mean_mosh_segments':
             float(np.mean(seg_nodes['mosh'])),
             'nodes_mean_clean_segments':
             float(np.mean(seg_nodes['clean'])),
             'total_tracks': next_id - 1,
             'lifespan_median_frames':
             float(np.median(spans)) if spans else 0}
    json.dump({'frames': frames_out, 'stats': stats},
              open(G2 + '/mosh_graph.json', 'w'))
    print(json.dumps(stats, indent=1))
    print('MOSH TRACK DONE -> %s/mosh_graph.json' % G2)


if __name__ == '__main__':
    main()
