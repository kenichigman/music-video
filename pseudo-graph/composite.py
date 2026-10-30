#!/usr/bin/env python3
"""EFFECT 2 TEST 3 — PSEUDO-GRAPH v2 composite (local WSL).

Stack (director's order): base film = test 3's SEAM-moshed leg
(preview_graph3_base.mp4 — world-swap boundaries force-moshed,
interior at test-2 density); the picture is displaced along the
OBJECT graph's edges (the graph derived from the CLEAN layer —
see object_graph.py); then the MOSH graph (acid green — tracks
the finished picture's own smear flow, mosh_graph.py); then the
OBJECT graph on top (blue-white anime / red-magenta VT): nodes
locked to object structure, persistent ids, confidence labels,
and corner-tick cluster brackets — "OBJ-07 93%" — the language
of a vision system detecting things. Both graphs crisp, drawn
last, never displaced or moshed (the standing rule).
"""
import os
RIG_ROOT = os.environ.get("RIG_ROOT", os.path.join(os.getcwd(), "rig-data"))
import argparse, json, os, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont

G2 = RIG_ROOT + '/rig2/graph3prev'
G1 = RIG_ROOT + '/rig2/graph3prev'
G_OBJ = RIG_ROOT + '/rig2/graph2prev'
W, H = 848, 464
FSZ = W * H * 3
F_START = int(os.environ.get("GRAPH_F_START", "990"))
F_END = int(os.environ.get("GRAPH_F_END", "1470"))
# --- COST DRIVERS (desktop preset as shipped; see README.md
# for the full table + suggested mobile preset) ---
RES_SCALE = 1.0        # composite at native 848x464 x RES_SCALE
LABEL_FONT_PX = 9
BRACKET_FONT_PX = 10
CLUSTER_MAXLEN = 120.0  # cluster-only edge length, px
BRACKET_MAX = 3         # brackets drawn per frame
BRACKET_MIN_AGE = {'A': 6, 'V': 3}
MOSH_LABEL_MAX = 10
MOSH_LABEL_MIN_SP = 60  # px/s residual speed for a mosh label
LABEL_PAD_X = 2         # label collision box padding
LABEL_H = 12            # label collision box height
FONT = ImageFont.truetype(
    '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
    LABEL_FONT_PX)
FONT_B = ImageFont.truetype(
    '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf',
    BRACKET_FONT_PX)
ANIME = {'CP', 'TR', 'SR'}
COL_LINE = {'A': (110, 165, 255), 'V': (255, 60, 115)}
COL_LAB = {'A': (195, 222, 255), 'V': (255, 145, 180)}
COL_MOSH = (140, 255, 70)
COL_MOSH_LAB = (205, 255, 175)
FALLOFF_R = 7.0
EDGE_MAXLEN = 340.0
FLOW_CAP = 10.0
TAPS = [0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0]
TAP_W = [0.34, 0.27, 0.22, 0.17]
CHAN_SCALE = [1.3, 1.0, 0.7]
MIN_CLUSTER = 4

XG, YG = np.meshgrid(np.arange(W, dtype=np.float32),
                     np.arange(H, dtype=np.float32))


def sample(img, xs, ys):
    xs = np.clip(xs, 0, W - 1.001)
    ys = np.clip(ys, 0, H - 1.001)
    x0 = xs.astype(np.int32); y0 = ys.astype(np.int32)
    wx = (xs - x0)[..., None]; wy = (ys - y0)[..., None]
    flat = img.reshape(-1, 3)
    i00 = (y0 * W + x0).ravel(); i01 = (y0 * W + x0 + 1).ravel()
    i10 = ((y0 + 1) * W + x0).ravel(); i11 = ((y0 + 1) * W + x0 + 1).ravel()
    top = flat[i00] * (1 - wx.reshape(-1, 1)) + flat[i01] * wx.reshape(-1, 1)
    bot = flat[i10] * (1 - wx.reshape(-1, 1)) + flat[i11] * wx.reshape(-1, 1)
    return (top * (1 - wy.reshape(-1, 1))
            + bot * wy.reshape(-1, 1)).reshape(H, W, 3)


def build_edges(nodes, maxlen=EDGE_MAXLEN, k=3):
    E = set()
    n = len(nodes)
    for i in range(n):
        ds = []
        for j in range(n):
            if i == j:
                continue
            dx = nodes[j]['x'] - nodes[i]['x']
            dy = nodes[j]['y'] - nodes[i]['y']
            d = (dx * dx + dy * dy) ** 0.5
            if 1e-3 < d <= maxlen:
                ds.append((d, j))
        ds.sort()
        for d, j in ds[:k]:
            E.add((min(i, j), max(i, j)))
    return sorted(E)


def flow_field(nodes, edges):
    FX = np.zeros((H, W), np.float32)
    FY = np.zeros((H, W), np.float32)
    WT = np.zeros((H, W), np.float32)
    R = FALLOFF_R
    for (i, j) in edges:
        a, b = nodes[i], nodes[j]
        dx, dy = b['x'] - a['x'], b['y'] - a['y']
        L = (dx * dx + dy * dy) ** 0.5
        if L < 1e-3:
            continue
        ux, uy = dx / L, dy / L
        along = ((a['vx'] + b['vx']) / 2.0) * ux \
            + ((a['vy'] + b['vy']) / 2.0) * uy
        stretch = (b['vx'] - a['vx']) * ux + (b['vy'] - a['vy']) * uy
        m = along + 0.5 * stretch
        if abs(m) > FLOW_CAP:
            m = np.sign(m) * FLOW_CAP
        fx, fy = ux * m, uy * m
        x0 = int(max(0, min(a['x'], b['x']) - R - 1))
        x1 = int(min(W, max(a['x'], b['x']) + R + 2))
        y0 = int(max(0, min(a['y'], b['y']) - R - 1))
        y1 = int(min(H, max(a['y'], b['y']) + R + 2))
        if x1 <= x0 or y1 <= y0:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1]
        px, py = xx - a['x'], yy - a['y']
        t = np.clip((px * dx + py * dy) / (L * L), 0, 1)
        d2 = (xx - (a['x'] + t * dx)) ** 2 + (yy - (a['y'] + t * dy)) ** 2
        wgt = np.clip(1.0 - np.sqrt(d2) / R, 0, 1) ** 2
        FX[y0:y1, x0:x1] += fx * wgt
        FY[y0:y1, x0:x1] += fy * wgt
        WT[y0:y1, x0:x1] += wgt
    F = np.zeros((H, W, 2), np.float32)
    msk = WT > 1e-6
    F[:, :, 0][msk] = FX[msk] / WT[msk]
    F[:, :, 1][msk] = FY[msk] / WT[msk]
    return F


def displace(base, D):
    out = np.zeros_like(base)
    for c in range(3):
        acc = np.zeros((H, W), np.float32)
        for s, wgt in zip(TAPS, TAP_W):
            smp = sample(base, XG - D[:, :, 0] * CHAN_SCALE[c] * s,
                         YG - D[:, :, 1] * CHAN_SCALE[c] * s)
            acc += wgt * smp[:, :, c]
        out[:, :, c] = acc
    return out


class Clusters:
    """Connected components of the object graph, persisted
    across frames by centroid matching — stable OBJ ids."""

    def __init__(self):
        self.prev = []
        self.counter = 0

    def update(self, nodes, edges):
        parent = list(range(len(nodes)))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        for i, j in edges:
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[ri] = rj
        comps = {}
        for i in range(len(nodes)):
            comps.setdefault(find(i), []).append(i)
        out = []
        new_prev = []
        for members in comps.values():
            if len(members) < MIN_CLUSTER:
                continue
            xs = [nodes[i]['x'] for i in members]
            ys = [nodes[i]['y'] for i in members]
            cx, cy = float(np.mean(xs)), float(np.mean(ys))
            best, bd = None, 70.0
            for p in self.prev:
                d = ((p['cx'] - cx) ** 2 + (p['cy'] - cy) ** 2) ** 0.5
                if d < bd:
                    best, bd = p, d
            if best is not None:
                oid, age = best['oid'], best['age'] + 1
                self.prev.remove(best)
            else:
                self.counter += 1
                oid, age = self.counter, 1
            conf = float(np.mean([nodes[i]['conf'] for i in members]))
            cl = {'oid': oid, 'age': age, 'conf': conf,
                  'x0': min(xs) - 12, 'y0': min(ys) - 12,
                  'x1': max(xs) + 12, 'y1': max(ys) + 12,
                  'cx': cx, 'cy': cy, 'n': len(members)}
            out.append(cl)
            new_prev.append({'oid': oid, 'cx': cx, 'cy': cy,
                             'age': age})
        self.prev = new_prev
        out.sort(key=lambda c: -c['n'])
        return out


def draw_bracket(dr, cl, col, lab_col):
    x0, y0, x1, y1 = cl['x0'], cl['y0'], cl['x1'], cl['y1']
    a = 10
    for (cx, cy, sx, sy) in ((x0, y0, 1, 1), (x1, y0, -1, 1),
                             (x0, y1, 1, -1), (x1, y1, -1, -1)):
        dr.line([cx, cy, cx + sx * a, cy], fill=col, width=2)
        dr.line([cx, cy, cx, cy + sy * a], fill=col, width=2)
    txt = 'OBJ-%02d %d%%' % (cl['oid'] % 100, round(cl['conf'] * 100))
    dr.text((x0, max(0, y0 - 14)), txt, font=FONT_B, fill=lab_col,
            stroke_width=1, stroke_fill=(0, 0, 0))


def draw_mosh(dr, mnodes):
    idx = {(n['gx'], n['gy']): i for i, n in enumerate(mnodes)}
    for i, n in enumerate(mnodes):
        for dgx, dgy in ((44, 0), (0, 44), (44, 44), (44, -44)):
            j = idx.get((n['gx'] + dgx, n['gy'] + dgy))
            if j is None:
                continue
            m = mnodes[j]
            # coherence of the RESIDUAL (front) flow, not raw flow
            cos = (n['rdx'] * m['rdx'] + n['rdy'] * m['rdy']) / max(
                1e-6, (n['rdx'] ** 2 + n['rdy'] ** 2) ** 0.5
                * (m['rdx'] ** 2 + m['rdy'] ** 2) ** 0.5)
            if cos >= 0.35:
                dr.line([n['x'], n['y'], m['x'], m['y']],
                        fill=COL_MOSH, width=1)
    labeled = []
    for n in sorted(mnodes, key=lambda n: -n['sp'])[:40]:
        x, y = n['x'], n['y']
        dr.polygon([(x, y - 5), (x + 5, y), (x, y + 5), (x - 5, y)],
                   outline=COL_MOSH, width=1)
        sp = (n['rdx'] ** 2 + n['rdy'] ** 2) ** 0.5
        if sp > 1e-6:
            tl = min(14.0, sp * 1.2)
            dr.line([x, y, x + n['rdx'] / sp * tl,
                     y + n['rdy'] / sp * tl], fill=COL_MOSH, width=1)
        if n['sp'] >= MOSH_LABEL_MIN_SP and len(labeled) < MOSH_LABEL_MAX:
            bx, by = x + 8, y - 5
            if any(abs(bx - ox) < 46 and abs(by - oy) < 13
                   for ox, oy in labeled):
                continue
            labeled.append((bx, by))
            dr.text((bx, by), '%d' % round(n['sp']), font=FONT,
                    fill=COL_MOSH_LAB, stroke_width=1,
                    stroke_fill=(0, 0, 0))


def draw_object(dr, nodes, edges, clusters, world):
    key = 'A' if world in ANIME else 'V'
    lc, tc = COL_LINE[key], COL_LAB[key]
    for (i, j) in edges:
        dr.line([nodes[i]['x'], nodes[i]['y'],
                 nodes[j]['x'], nodes[j]['y']], fill=lc, width=1)
    min_age = BRACKET_MIN_AGE[key]
    for cl in clusters[:BRACKET_MAX]:
        if cl['age'] >= min_age:
            draw_bracket(dr, cl, lc, tc)
    boxes = []
    for nd in nodes:
        x, y = nd['x'], nd['y']
        dr.rectangle([x - 5, y - 5, x + 5, y + 5], outline=lc,
                     width=1)
        dr.point((x, y), fill=tc)
        txt = '%.2f' % nd['conf']
        bx, by = x + 8, y - 5
        bw = 6 * len(txt) + 2
        if any(bx < ox + ow + LABEL_PAD_X and ox < bx + bw + LABEL_PAD_X
               and by < oy + LABEL_H and oy < by + LABEL_H
               for (ox, oy, ow) in boxes):
            continue
        boxes.append((bx, by, bw))
        dr.text((bx, by), txt, font=FONT, fill=tc,
                stroke_width=1, stroke_fill=(0, 0, 0))


def load_all():
    env = json.load(open(RIG_ROOT + '/rig2/bass_env.json'))
    bass = np.asarray(env['bass'], dtype=np.float64)
    seg = bass[F_START:F_END]
    I = np.clip((bass - seg.min()) / (seg.max() - seg.min()), 0, 1)
    obj = json.load(open(G_OBJ + '/obj_graph.json'))
    mosh = json.load(open(G2 + '/mosh_graph.json'))
    return I, obj, mosh


def render_frame(base, oframe, mframe, I, film_f, gain_base, cl_state):
    nodes = oframe['nodes']
    edges = build_edges(nodes)
    F = flow_field(nodes, edges)
    gt = gain_base * (0.3 + 1.2 * float(I[film_f]))
    D = F * gt
    out = displace(base, D)
    # clusters use SHORT edges (140px): a bracket must hug one
    # object, not chain face+ceiling into a single component
    clusters = cl_state.update(nodes, build_edges(nodes, CLUSTER_MAXLEN))
    im = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
    dr = ImageDraw.Draw(im)
    draw_mosh(dr, mframe['nodes'])
    draw_object(dr, nodes, edges, clusters, oframe['world'])
    dmax = float(np.sqrt(D[:, :, 0] ** 2 + D[:, :, 1] ** 2).max())
    return np.asarray(im).astype(np.float32), {
        'row': oframe['row'], 'world': oframe['world'],
        'obj_nodes': len(nodes), 'obj_edges': len(edges),
        'mosh_nodes': len(mframe['nodes']), 'clusters': len(clusters),
        'gain_t': gt, 'D_max': dmax}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--gain', type=float, default=3.0)
    ap.add_argument('--test', default=None)
    ap.add_argument('--out', default=os.path.join(G2, 'graph3_only.mp4'))
    a = ap.parse_args()
    I, obj, mosh = load_all()
    oframes, mframes = obj['frames'], mosh['frames']
    print('obj stats:', json.dumps(obj['stats']))
    print('mosh stats:', json.dumps(mosh['stats']), flush=True)
    bp = subprocess.Popen(
        ['ffmpeg', '-v', 'error', '-i',
         os.path.join(G1, 'preview_graph3_base.mp4'),
         '-an', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
        stdout=subprocess.PIPE)

    if a.test:
        want = sorted(int(x) for x in a.test.split(','))
        cl = Clusters()
        stats = {}
        wi = 0
        for wf in range(F_END - F_START):
            buf = bp.stdout.read(FSZ)
            assert len(buf) == FSZ
            frame = (np.frombuffer(buf, dtype=np.uint8)
                     .reshape(H, W, 3).astype(np.float32))
            out, st = render_frame(frame, oframes[wf], mframes[wf],
                                   I, F_START + wf, a.gain, cl)
            if wi < len(want) and wf == want[wi] - F_START:
                p = os.path.join(G2, 'test_graph3_%d.png' % want[wi])
                Image.fromarray(np.clip(out, 0, 255)
                                .astype(np.uint8)).save(p)
                stats[want[wi]] = st
                print('test %d -> %s %s' % (want[wi], p, st),
                      flush=True)
                wi += 1
                if wi >= len(want):
                    break
        bp.stdout.close(); bp.wait()
        print('TEST DONE')
        return

    enc = subprocess.Popen(
        ['ffmpeg', '-y', '-v', 'error', '-f', 'rawvideo',
         '-pix_fmt', 'rgb24', '-s', '%dx%d' % (W, H), '-r', '30',
         '-i', '-', '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
         '-preset', 'medium', '-crf', '17', a.out],
        stdin=subprocess.PIPE)
    cl = Clusters()
    stats = []
    for wf in range(F_END - F_START):
        buf = bp.stdout.read(FSZ)
        assert len(buf) == FSZ, 'base short at %d' % wf
        frame = (np.frombuffer(buf, dtype=np.uint8)
                 .reshape(H, W, 3).astype(np.float32))
        out, st = render_frame(frame, oframes[wf], mframes[wf], I,
                               F_START + wf, a.gain, cl)
        st['wf'] = wf
        stats.append(st)
        enc.stdin.write(np.clip(out, 0, 255).astype(np.uint8).tobytes())
        if (wf + 1) % 120 == 0:
            print('  frame %d/480' % (wf + 1), flush=True)
    bp.stdout.close(); bp.wait()
    enc.stdin.close(); enc.wait()
    # both graphs alone on black at t=37 (window frame 120)
    cl2 = Clusters()
    clusters = []
    for wf in range(121):
        of = oframes[wf]
        clusters = cl2.update(of['nodes'],
                              build_edges(of['nodes'], CLUSTER_MAXLEN))
    black = np.zeros((H, W, 3), np.float32)
    im = Image.fromarray(black.astype(np.uint8))
    dr = ImageDraw.Draw(im)
    draw_mosh(dr, mframes[120]['nodes'])
    draw_object(dr, oframes[120]['nodes'],
                build_edges(oframes[120]['nodes']), clusters,
                oframes[120]['world'])
    im.save(os.path.join(G2, 'still_graph3_overlay.png'))
    agg = {}
    for st in stats:
        e = agg.setdefault(st['world'], {'frames': 0, 'obj': 0.0,
                                         'mosh': 0.0, 'D_max': 0.0})
        e['frames'] += 1
        e['obj'] += st['obj_nodes']
        e['mosh'] += st['mosh_nodes']
        e['D_max'] = max(e['D_max'], st['D_max'])
    for e in agg.values():
        e['obj'] /= e['frames']
        e['mosh'] /= e['frames']
    params = {'variant': 'graph3', 'gain_base': a.gain,
              'object_graph': 'Shi-Tomasi corners on CLEAN assembly '
              'frames, dual-template (anchor+prev) NCC propagation '
              'with corner snap, stable ids; anime lock discipline '
              '(anchor>=0.45 / prev>=0.55, die<0.50, 3-miss '
              'tolerance, 1-frame probation), VT haywire '
              '(anchor>=0.35 / prev>=0.45, 1-miss death, no '
              'probation, flux jitter on drawn positions)',
              'mosh_graph': 'grid probes (44px, 21px patch, '
              '+-13 NCC, texture gate std>=3) on finished moshed '
              'frames; ego-motion (frame median flow) subtracted '
              '— nodes = residual/front flow, capped 64/frame; '
              'acid green',
              'obj_stats': obj['stats'], 'mosh_stats': mosh['stats'],
              'per_world': agg}
    json.dump(params, open(os.path.join(
        G2, 'composite_graph3_params.json'), 'w'), indent=1)
    json.dump(stats, open(os.path.join(
        G2, 'graph3_frame_stats.json'), 'w'))
    print('render done -> %s' % a.out)
    print(json.dumps(agg, indent=1))
    print('ALL DONE')


if __name__ == '__main__':
    main()
