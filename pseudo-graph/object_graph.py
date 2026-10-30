#!/usr/bin/env python3
"""EFFECT 2 TEST 2 — OBJECT GRAPH tracker, v2 (local WSL).

Director's notes (EFFECTS.md, test-1 notes): the graph derives
from the UNEDITED layer (clean patch-#3 assembly window, film
990..1469) and must feel like a super-intelligent AI object
detector — nodes LOCK ONTO OBJECT STRUCTURE and ride it.

v1 of this tracker failed the lock (median anime lifespan 4
frames): single-template matching drifted off corners, the
frame-max spawn threshold starved low-contrast regions, and a
2-frame probation hid half the population. v2 mechanics:
  * nodes are Shi-Tomasi corners (structure-tensor min-eigen
    value local maxima — line junctions, contour corners);
  * DUAL-template propagation: every node carries its SPAWN
    (anchor) patch and its previous-frame patch; it re-anchors
    against the spawn patch whenever that matches, else follows
    the previous patch — drift cannot accumulate;
  * CORNER SNAP: the matched position snaps to the strongest
    corner response within +-4 px, gluing the node to structure;
  * spawn selection is grid-balanced (4x3, top-2 per cell) so
    the graph covers the subject (the face), not just the
    hottest cluster (the ceiling lines);
  * confidence label = anchor NCC: starts at 1.00 and honestly
    decays as the object's appearance evolves.
Anime rows run lock discipline (dual thr, 3-miss tolerance,
1-frame probation). VT17 rows run the SAME machinery with the
hygiene removed — 1-miss death, no probation, drawn positions
jittered by spectral flux: the geometry's corners genuinely are
short-lived shards, and the churn reads as the AI going
haywire. Tracking never crosses an EDL row cut.
"""
import os
RIG_ROOT = os.environ.get("RIG_ROOT", os.path.join(os.getcwd(), "rig-data"))
import json, subprocess, wave
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

G2 = RIG_ROOT + '/rig2/graph2prev'
W, H = 848, 464
FSZ = W * H * 3
F_START = int(os.environ.get("GRAPH_F_START", "990"))
N = int(os.environ.get("GRAPH_FRAMES", "480"))
# --- COST DRIVERS (desktop preset as shipped; see README.md
# for the full table + suggested mobile preset) ---
RES_SCALE = 1.0        # working res = 848x464 native x RES_SCALE
PATCH = 21             # tracker template size, px
SEARCH = 10            # propagation search radius, px
SNAP_RAD = 4           # corner-snap radius, px
SPAWN_MIN_DIST = 24    # min px between live nodes (density)
EDGE_MARGIN = 24
GRID_COLS, GRID_ROWS = 4, 3   # spawn-balance grid
GRID_PER_CELL = 4      # spawn candidates tried per cell

ANIME = {'CP', 'TR', 'SR'}
MODE = {
    'lock': dict(thr_prev=0.55, thr_anchor=0.45, die_below=0.50,
                 miss_tol=3, cap=22, prob=1, spawn_frac=0.04,
                 jitter=0.0),
    'haywire': dict(thr_prev=0.45, thr_anchor=0.35, die_below=0.40,
                    miss_tol=1, cap=30, prob=0, spawn_frac=0.03,
                    jitter=1.0),
}


def load_rows():
    edl = json.load(open(RIG_ROOT + '/rig2/edl.json'))
    rows, f0 = [], 0
    for r in edl['rows']:
        rows.append({'row': r['row'], 'world': r['world'],
                     'f0': f0, 'f1': f0 + r['frames']})
        f0 += r['frames']
    return rows


def row_at(rows, film_f):
    for r in rows:
        if r['f0'] <= film_f < r['f1']:
            return r
    raise AssertionError(film_f)


def spectral_flux():
    w = wave.open(RIG_ROOT + '/rig2/boxprev/track_win.wav')
    sr = w.getframerate()
    raw = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    raw = raw.astype(np.float64) / 32768.0
    if w.getnchannels() == 2:
        raw = raw.reshape(-1, 2).mean(axis=1)
    nfft, hop = 2048, 512
    win = np.hanning(nfft)
    nfr = 1 + max(0, (len(raw) - nfft) // hop)
    mags = []
    for i in range(nfr):
        seg = raw[i * hop:i * hop + nfft]
        if len(seg) < nfft:
            seg = np.pad(seg, (0, nfft - len(seg)))
        mags.append(np.abs(np.fft.rfft(seg * win)))
    mags = np.array(mags)
    flux = np.maximum(np.diff(mags, axis=0), 0).sum(axis=1)
    flux = np.concatenate([[flux[0]], flux])
    t_src = (np.arange(nfr) * hop + nfft / 2) / sr
    t_dst = (np.arange(N) + 0.5) / 30.0
    f = np.interp(t_dst, t_src, flux)
    return (f - f.min()) / max(1e-9, f.max() - f.min())


def gray_of(buf):
    a = np.frombuffer(buf, dtype=np.uint8).reshape(H, W, 3)
    return (0.299 * a[:, :, 0] + 0.587 * a[:, :, 1]
            + 0.114 * a[:, :, 2]).astype(np.float32)


def box_blur(a, r):
    p = np.pad(a, r, mode='edge')
    c = np.cumsum(np.cumsum(p, axis=0), axis=1)
    c = np.pad(c, ((1, 0), (1, 0)), mode='constant')
    k = 2 * r + 1
    out = (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k])
    return (out / (k * k)).astype(np.float32)


def corner_response(g):
    P = np.pad(g, 1, mode='edge')
    sy = (P[2:, 1:-1] + 2 * P[1:-1, 1:-1] + P[:-2, 1:-1]) / 4.0
    Q = np.pad(sy, ((0, 0), (1, 1)), mode='edge')
    Ix = (Q[:, 2:] - Q[:, :-2]) / 2.0
    sx = (P[1:-1, 2:] + 2 * P[1:-1, 1:-1] + P[1:-1, :-2]) / 4.0
    R = np.pad(sx, ((1, 1), (0, 0)), mode='edge')
    Iy = (R[2:, :] - R[:-2, :]) / 2.0
    Sxx = box_blur(Ix * Ix, 3)
    Syy = box_blur(Iy * Iy, 3)
    Sxy = box_blur(Ix * Iy, 3)
    tr = (Sxx + Syy) / 2.0
    di = np.sqrt(np.maximum(tr * tr - (Sxx * Syy - Sxy * Sxy), 0))
    return tr - di


def local_maxima(R, frac):
    thr = frac * float(R.max())
    mx = R.copy()
    for dy in (-2, -1, 0, 1, 2):
        for dx in (-2, -1, 0, 1, 2):
            if dx == 0 and dy == 0:
                continue
            mx = np.maximum(mx, np.roll(np.roll(R, dy, 0), dx, 1))
    ys, xs = np.nonzero((R >= mx) & (R > thr))
    keep = (xs >= EDGE_MARGIN) & (xs < W - EDGE_MARGIN) \
        & (ys >= EDGE_MARGIN) & (ys < H - EDGE_MARGIN)
    ys, xs = ys[keep], xs[keep]
    vals = R[ys, xs]
    order = np.argsort(-vals)
    return ys[order], xs[order], vals[order]


def ncc_match(gray, tmpl, cx, cy):
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
    return float(ncc[iy, ix]), x0 + ix + hp, y0 + iy + hp


def patch_at(gray, x, y):
    hp = PATCH // 2
    return gray[y - hp:y + hp + 1, x - hp:x + hp + 1].copy()


def snap(R, x, y, rad=SNAP_RAD):
    x0, x1 = max(0, x - rad), min(W, x + rad + 1)
    y0, y1 = max(0, y - rad), min(H, y + rad + 1)
    sub = R[y0:y1, x0:x1]
    iy, ix = np.unravel_index(int(np.argmax(sub)), sub.shape)
    return x0 + ix, y0 + iy


class Node:
    __slots__ = ('id', 'x', 'y', 'vx', 'vy', 'anchor', 'prev',
                 'conf', 'age', 'miss', 'born')

    def __init__(self, nid, x, y, tmpl, born):
        self.id, self.x, self.y = nid, float(x), float(y)
        self.vx = self.vy = 0.0
        self.anchor = tmpl
        self.prev = tmpl
        self.conf = 1.0
        self.age, self.miss, self.born = 0, 0, born


def main():
    rows = load_rows()
    flux = spectral_flux()
    rng = np.random.default_rng(20261028)
    bp = subprocess.Popen(
        ['ffmpeg', '-v', 'error', '-i',
         RIG_ROOT + '/assembly/'
         'assembly.mp4',
         '-an', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
        stdout=subprocess.PIPE)
    for _ in range(F_START):
        assert len(bp.stdout.read(FSZ)) == FSZ

    nodes = []
    next_id = 1
    cur_row = None
    cur_world = None
    frames_out = []
    lifespans = {}
    churn = {'lock': [0, 0], 'haywire': [0, 0]}

    for wf in range(N):
        buf = bp.stdout.read(FSZ)
        assert len(buf) == FSZ, 'clean short at %d' % wf
        gray = gray_of(buf)
        r = row_at(rows, F_START + wf)
        world = r['world']
        mode = 'lock' if world in ANIME else 'haywire'
        P = MODE[mode]
        if r['row'] != cur_row:
            for nd in nodes:
                lifespans[nd.id] = (cur_world, nd.born, wf - 1)
            nodes = []
            cur_row, cur_world = r['row'], world
        R = corner_response(gray)

        # --- propagate: anchor first (anti-drift), else previous
        alive = []
        for nd in nodes:
            px = int(round(nd.x + nd.vx))
            py = int(round(nd.y + nd.vy))
            ma = ncc_match(gray, nd.anchor, px, py)
            mp = ncc_match(gray, nd.prev, px, py)
            cand, cncc = None, -1.0
            if ma is not None and ma[0] >= P['thr_anchor']:
                cand, cncc = (ma[1], ma[2]), ma[0]
                nd.conf = ma[0]
            if mp is not None and mp[0] >= P['thr_prev'] \
                    and mp[0] > cncc:
                cand, cncc = (mp[1], mp[2]), mp[0]
                if ma is not None:
                    nd.conf = ma[0]
            if cand is not None and cncc >= P['die_below']:
                nx, ny = snap(R, cand[0], cand[1])
                nd.vx = 0.6 * nd.vx + 0.4 * (nx - nd.x)
                nd.vy = 0.6 * nd.vy + 0.4 * (ny - nd.y)
                nd.x, nd.y = float(nx), float(ny)
                nd.miss = 0
                nd.age += 1
                nd.prev = patch_at(gray, nx, ny)
                alive.append(nd)
            else:
                nd.miss += 1
                if nd.miss >= P['miss_tol']:
                    lifespans[nd.id] = (world, nd.born, wf - 1)
                    churn[mode][1] += 1
                else:
                    alive.append(nd)
        nodes = alive

        # --- spawn: grid-balanced corner picks
        if len(nodes) < P['cap']:
            ys, xs, _ = local_maxima(R, P['spawn_frac'])
            cand = list(zip(xs.tolist(), ys.tolist()))
            picked = []

            def far(x, y):
                return all((nd.x - x) ** 2 + (nd.y - y) ** 2
                           >= SPAWN_MIN_DIST ** 2 for nd in nodes) \
                    and all((qx - x) ** 2 + (qy - y) ** 2
                            >= SPAWN_MIN_DIST ** 2 for qx, qy in picked)

            cells = {}
            for (x, y) in cand:
                key = (min(GRID_COLS - 1, int(x / (W / GRID_COLS))),
                       min(GRID_ROWS - 1, int(y / (H / GRID_ROWS))))
                cells.setdefault(key, []).append((x, y))
            for cell in cells.values():
                for (x, y) in cell[:GRID_PER_CELL]:
                    if len(nodes) + len(picked) >= P['cap']:
                        break
                    if far(x, y):
                        picked.append((x, y))
            for (x, y) in cand:
                if len(nodes) + len(picked) >= P['cap']:
                    break
                if far(x, y):
                    picked.append((x, y))
            for (x, y) in picked:
                nodes.append(Node(next_id, x, y,
                                  patch_at(gray, x, y), wf))
                churn[mode][0] += 1
                next_id += 1

        # --- emit
        out_nodes = []
        for nd in nodes:
            if nd.age < P['prob']:
                continue
            jx = jy = 0.0
            if P['jitter']:
                s = 0.6 + 3.2 * float(flux[wf])
                jx, jy = rng.normal(0, s, 2)
            out_nodes.append({
                'id': nd.id, 'x': round(float(nd.x + jx), 1),
                'y': round(float(nd.y + jy), 1),
                'vx': round(float(nd.vx), 2),
                'vy': round(float(nd.vy), 2),
                'conf': round(float(nd.conf), 3), 'age': nd.age})
        frames_out.append({'wf': wf, 'row': r['row'],
                           'world': world, 'mode': mode,
                           'flux': round(float(flux[wf]), 3),
                           'nodes': out_nodes})
        if (wf + 1) % 120 == 0:
            print('  obj track %d/480' % (wf + 1), flush=True)
    bp.stdout.close(); bp.wait()
    for nd in nodes:
        lifespans[nd.id] = (cur_world, nd.born, N - 1)

    stats = {}
    for mode, wset in (('lock', ANIME), ('haywire', {'VT'})):
        ls = [d - b + 1 for (w, b, d) in lifespans.values()
              if w in wset]
        stats[mode] = {
            'tracks': len(ls),
            'lifespan_median_frames': float(np.median(ls)) if ls else 0,
            'lifespan_mean_frames': float(np.mean(ls)) if ls else 0,
            'births': churn[mode][0], 'deaths': churn[mode][1]}
    json.dump({'frames': frames_out, 'stats': stats},
              open(G2 + '/obj_graph.json', 'w'))
    print(json.dumps(stats, indent=1))
    print('OBJ TRACK DONE -> %s/obj_graph.json' % G2)


if __name__ == '__main__':
    main()
