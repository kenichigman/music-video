# ============================================================
# Blob Track Instancing network — programmatic build script.
# Part of the Agentic TouchDesigner Harness: run inside a
# TouchDesigner session (Textport or the file bridge) to build
# the blob-network component from scratch. Architecture after
# PPPANIK's Blob Track Instancing tutorial (see README),
# rebuilt from the vendor's public documentation and forums.
#
# TD_WORK_DIR (environment) selects the working folder that
# holds source.mp4 and bassdata.txt and receives output.
# Operational notes are kept in the shelf README.
# ============================================================
import os
TD_WORK_DIR = os.environ.get('TD_WORK_DIR', r'C:\TouchDesigner\agent-workspace')

SRC   = TD_WORK_DIR + r"\source.mp4"
BASS  = TD_WORK_DIR + r"\bassdata.txt"
OUT   = TD_WORK_DIR + r"\out\blob-layer.mp4"
ASPECT = 848.0 / 464.0

CALLBACK = r'''
import math
try:
    import numpy as _np
except Exception:
    _np = None
CFG = dict(ASPECT=848.0/464.0, FLIP_V=0, BASS_GAIN=1.0)

def _hash(a, b):
    x = math.sin(a * 127.1 + b * 311.7) * 43758.5453
    return x - math.floor(x)

def onCook(scriptOp):
    scriptOp.clear()
    bass = 0.5
    try:
        vals = list(scriptOp.inputs[0][0].vals)
        lo = vals[:8]
        if lo:
            bass = max(0.0, min(1.0, (sum(lo) / len(lo)) * CFG['BASS_GAIN']))
    except Exception:
        pass
    chans = {k: [] for k in ('tx','ty','tz','sx','sy','sz','rz','ou','ov','tw','th')}
    rows_seen = -1
    try:
        dat = op('/project1/blobnet/blobinfo')
        rows_seen = dat.numRows
        hdr = {}
        for c in range(dat.numCols):
            try: hdr[str(dat[0, c].val)] = c
            except Exception: pass
        iu = hdr.get('u', 1); iv = hdr.get('v', 2)
        iw = hdr.get('width', 3); ih = hdr.get('height', 4)
        A = CFG['ASPECT']; mul = 0.8 + 1.6 * bass
        for r in range(1, dat.numRows):
            try:
                u = float(dat[r, iu].val); v = float(dat[r, iv].val)
                w = float(dat[r, iw].val); h = float(dat[r, ih].val)
            except Exception:
                continue
            vv = (1.0 - v) if CFG['FLIP_V'] else v
            h1 = _hash(u, v); h2 = _hash(v, u)
            chans['tx'].append((u - 0.5) * A)
            chans['ty'].append((vv - 0.5))
            chans['tz'].append((h1 - 0.5) * 0.7 * (0.3 + bass))
            chans['sx'].append(max(0.01, w * A * mul))
            chans['sy'].append(max(0.01, h * mul))
            chans['sz'].append(1.0)
            chans['rz'].append((h2 - 0.5) * 55.0 * bass)
            chans['ou'].append(min(0.7, max(0.0, u - w / 2.0)))
            chans['ov'].append(min(0.7, max(0.0, vv - h / 2.0)))
            chans['tw'].append(w); chans['th'].append(h)
    except Exception:
        pass
    if not chans['tx']:
        for k in chans: chans[k] = [0.0]
        chans['sx'] = [0.0]; chans['sy'] = [0.0]
    try:
        _d = op('/project1/blobnet/dbg')
        if _d is not None:
            _d.text = 'seen_rows=%s parsed=%s bass=%.3f' % (rows_seen, len(chans['tx']), bass)
    except Exception:
        pass
    scriptOp.numSamples = len(chans['tx'])
    for name, arr in chans.items():
        ch = scriptOp.appendChan(name)
        try:
            if _np is not None:
                ch.vals = _np.array(arr, dtype=_np.float64)
            else:
                ch.vals = arr
        except Exception:
            pass
'''

BASSCB = r'''
def onCook(scriptOp):
    scriptOp.clear()
    scriptOp.numSamples = 1
    val = 0.0
    try:
        f = int(float(op('/project1/blobnet/frameidx').text.strip() or 0))
        env = scriptOp.fetch('env', None)
        if env is None:
            env = [float(x) for x in op('/project1/blobnet/bassdata').text.split()]
            scriptOp.store('env', env)
        val = env[max(0, min(len(env) - 1, f))]
    except Exception:
        val = 0.0
    ch = scriptOp.appendChan('bass')
    try:
        import numpy as _np
        ch.vals = _np.array([val])
    except Exception:
        pass
'''

def setp(o, name, val):
    try:
        p = getattr(o.par, name)
        p.val = val
        return True
    except Exception:
        return False


def wire(dst, idx, src):
    if dst is None or src is None:
        return
    try:
        dst.inputConnectors[idx].connect(src)
        return
    except Exception:
        pass
    try:
        src.outputConnectors[0].connect(dst)
    except Exception:
        pass

def mk(parent, typ, name):
    o = parent.create(typ, name)
    return o

root = op('/project1')
old = root.op('blobnet')
if old:
    old.destroy()
net = mk(root, 'containerCOMP', 'blobnet')

# --- source + tracking matte ---
src = mk(net, 'moviefileinTOP', 'src')
setp(src, 'file', SRC)
lvl = mk(net, 'levelTOP', 'matte_level'); wire(lvl, 0, src)
setp(lvl, 'contrast', 1.35)
thr = mk(net, 'thresholdTOP', 'matte_thr'); wire(thr, 0, lvl)
setp(thr, 'threshold', 0.35); setp(thr, 'smooth', 0.10)
bt = mk(net, 'blobtrackTOP', 'blobtrack'); wire(bt, 0, thr)
setp(bt, 'drawblobs', 0)
setp(bt, 'minblobsize', 0.002); setp(bt, 'maxblobsize', 0.9)
setp(bt, 'maxmovedistance', 0.25)
matte_out = mk(net, 'nullTOP', 'matte_out'); wire(matte_out, 0, bt)

info = mk(net, 'infoDAT', 'blobinfo')
setp(info, 'op', bt.path)

# --- baked bass: bassdata DAT + frameidx DAT -> basssrc CHOP ---
bd = mk(net, 'textDAT', 'bassdata')
try:
    bd.text = open(BASS).read()
except Exception:
    pass
fi = mk(net, 'textDAT', 'frameidx'); fi.text = '0'
bcb = mk(net, 'textDAT', 'basssrc_cb'); bcb.text = BASSCB
bs = mk(net, 'scriptCHOP', 'basssrc')
setp(bs, 'callbacks', bcb.path)

dbg = mk(net, 'textDAT', 'dbg')

cb = mk(net, 'textDAT', 'instancer_cb'); cb.text = CALLBACK
inst = mk(net, 'scriptCHOP', 'instancer'); wire(inst, 0, bs)
setp(inst, 'callbacks', cb.path)

# --- geometry: instanced rectangles textured by the clean source ---
geo = mk(net, 'geometryCOMP', 'geo')
_default = geo.op('torus1')
if _default is not None:
    _default.destroy()
rect = mk(geo, 'rectangleSOP', 'rect')
texuv = mk(geo, 'textureSOP', 'texuv'); wire(texuv, 0, rect)
setp(texuv, 'su', 0.3); setp(texuv, 'sv', 0.3)
try: texuv.render = True
except Exception: pass
mat = mk(net, 'constantMAT', 'mat')
setp(mat, 'colormap', src.path)
setp(geo, 'material', mat.path)
setp(geo, 'instancing', True)
setp(geo, 'instanceop', inst.path)
for par, chn in (('instancetx','tx'), ('instancety','ty'), ('instancetz','tz'),
                 ('instancesx','sx'), ('instancesy','sy'), ('instancesz','sz'),
                 ('instancerz','rz')):
    setp(geo, par, chn)
setp(geo, 'instancetexmode', 'transform')
setp(geo, 'instanceu', 'ou'); setp(geo, 'instancev', 'ov')
setp(geo, 'instancescaleu', 'tw'); setp(geo, 'instancescalev', 'th')

cam = mk(net, 'cameraCOMP', 'cam')
setp(cam, 'projection', 'ortho')
setp(cam, 'orthowidth', ASPECT)
setp(cam, 'tz', 5.0)

ren = mk(net, 'renderTOP', 'render')
setp(ren, 'camera', cam.path); setp(ren, 'objects', geo.path)
setp(ren, 'lights', '')
setp(ren, 'outputresolution', 'custom')
setp(ren, 'resolutionw', 848); setp(ren, 'resolutionh', 464)
setp(ren, 'bgcolorr', 0.0); setp(ren, 'bgcolorg', 0.0)
setp(ren, 'bgcolorb', 0.0); setp(ren, 'bgcolora', 1.0)

fade = mk(net, 'levelTOP', 'matte_fade'); wire(fade, 0, matte_out)
setp(fade, 'opacity', 0.0)
layer = mk(net, 'overTOP', 'blob_layer')
wire(layer, 0, ren); wire(layer, 1, fade)

# Movie File Out kept for interactive use only - NC cannot encode
# H.264 (Commercial gate). Production capture is the frame-stepped
# TOP.save loop described in the header.
rec = mk(net, 'moviefileoutTOP', 'rec'); wire(rec, 0, layer)
setp(rec, 'file', OUT)
setp(rec, 'record', 0)

net.nodeX, net.nodeY = 0, 0
print('BUILD_OK v2: /project1/blobnet built (instancing on, baked bass, 848x464).')
