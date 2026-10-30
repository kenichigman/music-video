#!/usr/bin/env python3
"""the reference production — FUSE-3 taste preview composite (local WSL).

Round 3: the director picked LEG 2 (object boxes above the mosh) and asked
for "more crazy blending between the two [worlds] to match
oscillation of song." Chassis = the no-blob build verbatim (halved
warp gains, clamp 24, flux gate, decay 0.90, cadence mult, NO
layers in the composite, NO cross-field, NO boundary bias). The
new ingredient lives in the composite stage, PRE-mosh:

  BASE CROSS-BLEND: each frame is blended toward the temporally
  nearest opposite-world row's WARPED base frame (anime <-> VT17;
  donor chosen by row-center distance over the full EDL — this
  reproduces leg 2's shipped cross mapping exactly; donor frames
  loop cyclically over the own row's local index) with
      alpha(t) = 0.55 * I(t)                    for I < 0.9
               = 0.495 + (I-0.9)/0.1 * 0.205    for I >= 0.9
  so alpha peaks at 0.70 on the window's strongest accents and
  returns to ~0 at troughs: the worlds visibly breathe into each
  other on the bass oscillation. I(t) = bass_env (film-aligned
  30fps) normalized over THIS window to 0..1, floor 0.

Implementation: pass 1 renders every needed row's warped frames
(window rows + donor rows; donor row 17 sits just past the window)
into a uint8 cache via the noblob RowEngine (per-row D integration
is independent, so cached warps are identical to the no-blob
leg's). Pass 2 blends from cache and encodes with the noblob
settings (crf 16, keyint 30).
"""
import os
RIG_ROOT = os.environ.get("RIG_ROOT", os.path.join(os.getcwd(), "rig-data"))
import argparse, json, os, subprocess
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 848, 464
FSZ = W * H * 3
BASE = RIG_ROOT + '/assembly/assembly.mp4'
SCALE_DEFAULT = 1.1390137893109515
GAIN_MULT = 0.5
CLAMP = 24.0
ANIME = ('TR', 'CP', 'SR')


def fields_path(row):
    return os.path.join(HERE, 'fields', 'row%02d' % row, 'fields.npy')


def load_setup():
    edl = json.load(open(os.path.join(HERE, 'edl.json')))
    man = json.load(open(os.path.join(HERE, 'rows_manifest.json')))
    mp = os.path.join(HERE, 'manifest_stage1.json')
    gains_full = {w: v['gain'] for w, v in
                  json.load(open(mp))['gains_to_6px'].items()}
    gains = {w: g * GAIN_MULT for w, g in gains_full.items()}
    sig = np.load(os.path.join(HERE, 'signals.npz'))
    rows = []
    f0 = 0
    mmap = {r['row']: r for r in man['rows']}
    for r in edl['rows']:
        m = mmap[r['row']]
        rows.append({'row': r['row'], 'world': r['world'],
                     'frames': r['frames'], 'f0': f0,
                     'f1': f0 + r['frames'],
                     'bridge_in': r['bridge_in'], 'clean': r['clean'],
                     'src_fps': m['src_fps'],
                     'src_frames': m['src_frames']})
        f0 += r['frames']
    assert f0 == 4974, f0
    return rows, gains, gains_full, sig


def grp(w):
    return 'A' if w in ANIME else 'V'


def donor_map(rows):
    out = {}
    for r in rows:
        c = 0.5 * (r['f0'] + r['f1'])
        cands = [q for q in rows if grp(q['world']) != grp(r['world'])]
        out[r['row']] = min(
            cands, key=lambda q: abs(0.5 * (q['f0'] + q['f1']) - c))['row']
    return out


def load_curves(f_start, f_end):
    """I(t): bass_env normalized over the window; alpha(t) and the
    cross-box weight w(t) = 0.9*I(t). Full-film-length arrays,
    indexed by film frame."""
    env = json.load(open(os.path.join(HERE, 'bass_env.json')))
    bass = np.asarray(env['bass'], dtype=np.float64)
    assert len(bass) == 4974, len(bass)
    seg = bass[f_start:f_end]
    mn, mx = float(seg.min()), float(seg.max())
    I = np.clip((bass - mn) / (mx - mn), 0.0, 1.0)
    alpha = np.where(I < 0.9, 0.55 * I,
                     0.495 + (I - 0.9) / 0.1 * 0.205)
    alpha = np.clip(alpha, 0.0, 0.70)
    w = 0.9 * I
    return I, alpha, w


XG, YG = np.meshgrid(np.arange(W, dtype=np.float32),
                     np.arange(H, dtype=np.float32))


def warp(img, D):
    xs = np.clip(XG - D[:, :, 0], 0, W - 1.001)
    ys = np.clip(YG - D[:, :, 1], 0, H - 1.001)
    x0 = xs.astype(np.int32); y0 = ys.astype(np.int32)
    wx = (xs - x0)[..., None]; wy = (ys - y0)[..., None]
    flat = img.reshape(-1, 3)
    i00 = (y0 * W + x0).ravel(); i01 = (y0 * W + x0 + 1).ravel()
    i10 = ((y0 + 1) * W + x0).ravel(); i11 = ((y0 + 1) * W + x0 + 1).ravel()
    top = flat[i00] * (1 - wx.reshape(-1, 1)) + flat[i01] * wx.reshape(-1, 1)
    bot = flat[i10] * (1 - wx.reshape(-1, 1)) + flat[i11] * wx.reshape(-1, 1)
    return (top * (1 - wy.reshape(-1, 1))
            + bot * wy.reshape(-1, 1)).reshape(H, W, 3)


class RowEngine:
    """Per-row D integration, warp only — verbatim from the
    no-blob composite (halved gains applied in load_setup)."""
    def __init__(self, r, gains, sig, scale):
        self.r = r
        self.sig = sig
        self.F = np.load(fields_path(r['row']), mmap_mode='r')
        self.D = np.zeros((H, W, 2), dtype=np.float32)
        self.gw = gains[r['world']] * scale

    def step(self, k, frame):
        r = self.r
        f = r['f0'] + k
        gate = self.sig['gate']; u = self.sig['u']
        V = np.asarray(self.F[k], dtype=np.float32)
        mult = float(gate[f]) * (0.75 + 0.25 * float(u[f]))
        if r['clean']:
            mult *= 0.35
        incr = (self.gw * mult) * V
        self.D = 0.90 * self.D + incr
        if r['clean']:
            mag = np.sqrt(self.D[:, :, 0] ** 2 + self.D[:, :, 1] ** 2)
            over = mag > 10.0
            if over.any():
                s = np.ones_like(mag); s[over] = 10.0 / mag[over]
                self.D[:, :, 0] *= s; self.D[:, :, 1] *= s
        else:
            self.D = np.clip(self.D, -CLAMP, CLAMP)
        dmean = float(np.sqrt(self.D[:, :, 0] ** 2
                              + self.D[:, :, 1] ** 2).mean())
        if frame is None:
            return None, dmean
        return warp(frame, self.D), dmean


def open_base():
    return subprocess.Popen(['ffmpeg', '-v', 'error', '-i', BASE, '-an',
                             '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                            stdout=subprocess.PIPE)


def read_base(bp):
    buf = bp.stdout.read(FSZ)
    assert len(buf) == FSZ, 'base pipe short'
    return (np.frombuffer(buf, dtype=np.uint8)
            .reshape(H, W, 3).astype(np.float32) / 255.0)


def run(rows, gains, sig, scale, f_start, f_end, alpha, dmap, out_path):
    win = [r for r in rows if r['f1'] > f_start and r['f0'] < f_end]
    for r in win:
        assert r['f0'] >= f_start and r['f1'] <= f_end, \
            'window must contain whole rows'
    need_ids = set(r['row'] for r in win)
    for r in win:
        need_ids.add(dmap[r['row']])
    need = [r for r in rows if r['row'] in need_ids]
    need.sort(key=lambda r: r['f0'])
    r_start, r_end = need[0]['f0'], need[-1]['f1']
    for a, b in zip(need, need[1:]):
        assert a['f1'] == b['f0'], 'render set must be contiguous'
    print('render set: rows %s [%d,%d)' % (
        [r['row'] for r in need], r_start, r_end), flush=True)
    # ---- pass 1: warp every needed row into a uint8 cache ----
    bp = open_base()
    for _ in range(r_start):
        buf = bp.stdout.read(FSZ)
        assert len(buf) == FSZ, 'base short during skip'
    cache = {}
    dstats = np.zeros(f_end - f_start, dtype=np.float32)
    for r in need:
        eng = RowEngine(r, gains, sig, scale)
        print('  pass1 row %02d %s gw=%.4f' % (r['row'], r['world'],
                                               eng.gw), flush=True)
        frames = []
        for k in range(r['frames']):
            f = r['f0'] + k
            frame = read_base(bp)
            out, dm = eng.step(k, frame)
            frames.append((np.clip(out, 0, 1) * 255).astype(np.uint8))
            if f_start <= f < f_end:
                dstats[f - f_start] = dm
        cache[r['row']] = frames
    bp.stdout.close(); bp.wait()
    print('pass1 done: cached %d frames' %
          sum(len(v) for v in cache.values()), flush=True)
    # ---- pass 2: cross-blend from cache, encode ----
    enc = subprocess.Popen(
        ['ffmpeg', '-y', '-v', 'error', '-f', 'rawvideo',
         '-pix_fmt', 'rgb24', '-s', '%dx%d' % (W, H), '-r', '30',
         '-i', '-', '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
         '-preset', 'medium', '-crf', '16', '-g', '30',
         '-x264-params',
         'keyint=30:min-keyint=30:scenecut=0:bframes=0:weightp=0',
         '-f', 'h264', out_path], stdin=subprocess.PIPE)
    n_written = 0
    for r in win:
        don = cache[dmap[r['row']]]
        own = cache[r['row']]
        for k in range(r['frames']):
            f = r['f0'] + k
            a = float(alpha[f])
            o = own[k].astype(np.float32) / 255.0
            if a > 0.0:
                d = don[k % len(don)].astype(np.float32) / 255.0
                o = (1.0 - a) * o + a * d
            enc.stdin.write(
                (np.clip(o, 0, 1) * 255).astype(np.uint8).tobytes())
            n_written += 1
            if n_written % 300 == 0:
                print('  frame %d/%d' % (f + 1, f_end), flush=True)
    enc.stdin.close(); enc.wait()
    np.save(out_path + '.dstats.npy', dstats)
    print('render done: %d frames -> %s; own-warp mean|D| median '
          '%.2f mean %.2f max %.2f' % (
              n_written, out_path, float(np.median(dstats)),
              float(dstats.mean()), float(dstats.max())), flush=True)
    return n_written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scale', type=float, default=SCALE_DEFAULT)
    ap.add_argument('--f-start', type=int, default=990)
    ap.add_argument('--f-end', type=int, default=1470)
    ap.add_argument('--out', required=True)
    ap.add_argument('--params-dir', default=None)
    a = ap.parse_args()
    rows, gains, gains_full, sig = load_setup()
    I, alpha, w = load_curves(a.f_start, a.f_end)
    dmap = donor_map(rows)
    print('stage-1 gains:', gains_full, flush=True)
    print('halved gains (x%.2f):' % GAIN_MULT, gains, flush=True)
    print('scale %.6f clamp %.0f layers OFF bias OFF cross-field OFF'
          % (a.scale, CLAMP), flush=True)
    win_ids = [r['row'] for r in rows
               if r['f1'] > a.f_start and r['f0'] < a.f_end]
    print('window rows:', win_ids, flush=True)
    print('donor map (window):', {i: dmap[i] for i in win_ids},
          flush=True)
    Iw = I[a.f_start:a.f_end]; aw = alpha[a.f_start:a.f_end]
    ww = w[a.f_start:a.f_end]
    stats = {
        'I_mean': float(Iw.mean()), 'I_max': float(Iw.max()),
        'pct_frames_I_ge_0.9': float(100.0 * (Iw >= 0.9).mean()),
        'n_frames_I_ge_0.9': int((Iw >= 0.9).sum()),
        'alpha_mean': float(aw.mean()), 'alpha_max': float(aw.max()),
        'alpha_mean_at_peaks': float(aw[Iw >= 0.9].mean())
        if (Iw >= 0.9).any() else 0.0,
        'w_cross_mean': float(ww.mean()), 'w_cross_max': float(ww.max()),
        'at_stills': {str(f): {'I': float(I[f]),
                               'alpha': float(alpha[f]),
                               'w_cross': float(w[f])}
                      for f in (1110, 1240, 1245, 1320)},
    }
    print('curve stats:', json.dumps(stats, indent=1), flush=True)
    n = run(rows, gains, sig, a.scale, a.f_start, a.f_end, alpha,
            dmap, a.out)
    assert n == a.f_end - a.f_start, n
    params = {'mode': 'render', 'variant': 'fuse3', 'out': a.out,
              'world_gains_full': gains_full,
              'gain_mult': GAIN_MULT, 'world_gains': gains,
              'scale': a.scale, 'clamp_px': CLAMP,
              'layers': 'off (boxes are post-mosh)',
              'bias': 'off', 'cross_field': 'off',
              'gate': '0.25+1.5*clip(flux/p97.5,0,1)',
              'cadence_gain_mult': '0.75+0.25*u',
              'base_cross_blend': 'alpha=0.55*I (I<0.9), rising to '
                                  '0.70 at I=1; donor=nearest '
                                  'opposite-world row by center '
                                  'distance; donor frames loop',
              'donor_map_window': {str(i): dmap[i] for i in win_ids},
              'curves': stats,
              'f_start': a.f_start, 'f_end': a.f_end}
    pd = a.params_dir or os.path.dirname(os.path.abspath(a.out))
    json.dump(params, open(os.path.join(
        pd, 'composite_fuse3_params.json'), 'w'), indent=1)
    print('params written', flush=True)


if __name__ == '__main__':
    main()
