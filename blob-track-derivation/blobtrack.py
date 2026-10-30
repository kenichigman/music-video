#!/usr/bin/env python3
"""blobtrack.py — clean-room behavioral derivation of the Blob Track
TOP (the subset the the reference production rig uses), per
projects/production/work/derive/SPEC.md.

Pipeline: luminance -> contrast -> soft-threshold matte -> binarize
-> connected components -> size gate -> per-frame greedy association
with lifecycle (active/lost/revived/expired) -> tracks table in the
oracle's tracks.csv schema (frame,id,u,v,width,height,age; no header).

The numpy reference implementation for the browser port: every cost
driver is a named parameter (see Params), nothing desktop-tuned is
hard-coded. Requires numpy + scipy; video decode via ffmpeg.

Usage:
  python3 blobtrack.py INPUT.mp4 --preset e2 --out tracks.csv
  python3 blobtrack.py INPUT.mp4 --matte-threshold 0.35 \
      --min-blob-size 0.004 --out tracks.csv --full-out full.csv
"""
import argparse, json, math, subprocess, sys
from dataclasses import dataclass, asdict

import numpy as np
from scipy import ndimage


@dataclass
class Params:
    # --- matte (content calibration; E2 vs VT values from the rig) ---
    matte_threshold: float = 0.22     # MATTE_THRESHOLD
    contrast: float = 1.35            # CONTRAST (Level TOP)
    threshold_smooth: float = 0.10    # THRESHOLD_SMOOTH
    # --- size gate (frame fractions; gate measure per size_measure) ---
    min_blob_size: float = 0.0015     # MIN_BLOB_SIZE
    max_blob_size: float = 0.9        # MAX_BLOB_SIZE
    size_measure: str = "height"      # 'height' | 'max_dim'  (SPEC §4)
    # --- association / lifecycle ---
    max_move_distance: float = 0.25   # MAX_MOVE_DISTANCE, (u,v) units
    expired_time_s: float = 0.5       # EXPIRED_TIME_S at timeline_fps
    timeline_fps: float = 60.0        # TIMELINE_FPS (age rate, oracle semantic)
    # --- cost drivers (browser dials) ---
    res_scale: float = 1.0            # RES_SCALE working-resolution dial
    cc_connectivity: int = 8          # CC_CONNECTIVITY (4 or 8)
    max_blobs_per_frame: int = 0      # MAX_BLOBS_PER_FRAME (0 = no cap)
    # --- behavior variants (SPEC §4 + validation round 2) ---
    center_mode: str = "centroid"     # 'centroid' | 'bbox_center'
    bg_mode: str = "gauss"            # 'off' | 'ema' | 'gauss'
                                      # (derived model; SPEC v1's
                                      # 'off' remains selectable)
    bg_learn_rate: float = 0.02       # BG_LEARN_RATE (ema only)
    # 'gauss': per-pixel running mean/variance background over the
    # soft matte (OpenCV-style background model, per the forum
    # record that the TOP's detection is OpenCV-based). Foreground
    # = brightening beyond k sigma (floored), on matte >= 0.5.
    bg_history: float = 200.0         # alpha = 1/history
    bg_sigma_k: float = 2.5
    bg_sigma0: float = 0.10
    bg_abs_thresh: float = 0.25
    # Emitted (width,height) semantics. 'bbox' = measured bbox
    matte_invert: bool = False        # MATTE_INVERT — track the DARK
                                      # regions of the matte instead of
                                      # the bright ones (validation
                                      # round 3: oracle positions sit
                                      # on dark pixels; sizes anti-
                                      # correlate with bright regions)
    # (SPEC v1, falsified in validation: the oracle's h == w*aspect
    # exactly, i.e. one-input mode reports SQUARE blobs — forum
    # record concurs). 'square_*' emit w = s/W, h = s/H with the
    # square side s (px) from the named component statistic.
    size_source: str = "square_sqrt_area"
                                      # 'bbox' (SPEC v1) |
                                      # 'square_sqrt_area' (derived) |
                                      # 'square_sqrt_soft_area' |
                                      # 'square_equiv_diam' |
                                      # 'square_bbox_w' | 'square_bbox_max'

    def expiry_frames(self):
        return max(1, int(round(self.expired_time_s * self.timeline_fps)))


PRESETS = {
    # Rig calibrations (stage 1): E2 worlds (CP/TR/SR) and VT.
    "e2": dict(matte_threshold=0.22, min_blob_size=0.0015),
    "vt": dict(matte_threshold=0.35, min_blob_size=0.004),
    # Recorded mobile preset (SPEC §5) — values only, for the port.
    "e2-mobile": dict(matte_threshold=0.22, min_blob_size=0.003,
                      res_scale=0.5, max_blobs_per_frame=800),
    "vt-mobile": dict(matte_threshold=0.35, min_blob_size=0.008,
                      res_scale=0.5, max_blobs_per_frame=800),
}


# ---------------------------------------------------------------- frames
def decode_frames(path, res_scale=1.0):
    """Yield (width, height, rgb uint8 array) per frame via ffmpeg."""
    info = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True).stdout.strip().split(",")
    w0, h0 = int(info[0]), int(info[1])
    w = max(2, int(round(w0 * res_scale))) & ~1
    h = max(2, int(round(h0 * res_scale))) & ~1
    cmd = ["ffmpeg", "-v", "error", "-i", path]
    if (w, h) != (w0, h0):
        cmd += ["-vf", f"scale={w}:{h}"]
    cmd += ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    nbytes = w * h * 3
    try:
        while True:
            buf = proc.stdout.read(nbytes)
            if len(buf) < nbytes:
                break
            yield w, h, np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 3)
    finally:
        proc.stdout.close()
        proc.wait()


def luminance(rgb):
    """Rec.601 luma in [0,1] (float32)."""
    f = rgb.astype(np.float32) / 255.0
    return 0.299 * f[..., 0] + 0.587 * f[..., 1] + 0.114 * f[..., 2]


def matte_soft(y, p: Params):
    """The Threshold TOP's output image (what the Blob Track TOP
    actually receives): contrast -> smoothstep ramp around T."""
    yc = np.clip((y - 0.5) * p.contrast + 0.5, 0.0, 1.0)
    t = np.clip((yc - (p.matte_threshold - p.threshold_smooth / 2.0))
                / p.threshold_smooth, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def matte_mask(y, p: Params):
    """Binary matte: soft >= 0.5, exactly Y' >= T."""
    yc = np.clip((y - 0.5) * p.contrast + 0.5, 0.0, 1.0)
    return yc >= p.matte_threshold


# ---------------------------------------------------------------- components
_STRUCT = {4: np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]]),
           8: np.ones((3, 3), dtype=int)}


def extract_components(mask, connectivity=8, soft=None):
    """Connected components of a binary mask.
    Returns list of dicts: u, v (centroid, pixel-center convention),
    bu, bv (bbox center), w, h (frame fractions), npix, and — when a
    soft matte is supplied — npix_soft (soft area) and su, sv
    (soft-weighted centroid).
    Positions are sub-pixel: centroid = mean of pixel-center coords.
    """
    lab, n = ndimage.label(mask, structure=_STRUCT[connectivity])
    if n == 0:
        return []
    H, W = mask.shape
    flat = lab.ravel()
    counts = np.bincount(flat, minlength=n + 1)
    ys, xs = np.nonzero(lab)
    ids = lab[ys, xs]
    sx = np.bincount(ids, weights=xs.astype(np.float64), minlength=n + 1)
    sy = np.bincount(ids, weights=ys.astype(np.float64), minlength=n + 1)
    if soft is not None:
        wts = soft[ys, xs].astype(np.float64)
        ssum = np.bincount(ids, weights=wts, minlength=n + 1)
        ssx = np.bincount(ids, weights=wts * xs, minlength=n + 1)
        ssy = np.bincount(ids, weights=wts * ys, minlength=n + 1)
    slices = ndimage.find_objects(lab)
    comps = []
    for i in range(1, n + 1):
        sl = slices[i - 1]
        if sl is None or counts[i] == 0:
            continue
        y0, y1 = sl[0].start, sl[0].stop
        x0, x1 = sl[1].start, sl[1].stop
        c = dict(
            u=(sx[i] / counts[i] + 0.5) / W,
            v=(sy[i] / counts[i] + 0.5) / H,
            bu=(x0 + x1) / 2.0 / W,
            bv=(y0 + y1) / 2.0 / H,
            w=(x1 - x0) / W,
            h=(y1 - y0) / H,
            npix=int(counts[i]),
            W=W, H=H,
        )
        if soft is not None and ssum[i] > 0:
            c["npix_soft"] = float(ssum[i])
            c["su"] = (ssx[i] / ssum[i] + 0.5) / W
            c["sv"] = (ssy[i] / ssum[i] + 0.5) / H
        comps.append(c)
    return comps


def gate_components(comps, p: Params):
    out = []
    for c in comps:
        c = dict(c)
        if p.size_source == "bbox":
            size = c["h"] if p.size_measure == "height" \
                else max(c["w"], c["h"])
            if not (p.min_blob_size <= size <= p.max_blob_size):
                continue
            c["size"] = size
        else:
            # square-size modes (oracle's one-input semantics): one
            # square side s (px) generates both emitted columns.
            if p.size_source == "square_sqrt_area":
                s = float(np.sqrt(c["npix"]))
            elif p.size_source == "square_sqrt_soft_area":
                s = float(np.sqrt(c.get("npix_soft", c["npix"])))
            elif p.size_source == "square_equiv_diam":
                s = float(2.0 * np.sqrt(c["npix"] / np.pi))
            elif p.size_source == "square_bbox_w":
                s = c["w"] * c["W"]
            elif p.size_source == "square_bbox_max":
                s = max(c["w"] * c["W"], c["h"] * c["H"])
            else:
                raise ValueError(p.size_source)
            # gate per the oracle evidence: min binds on the height
            # fraction (s/H), max on the width fraction (s/W)
            if not (s / c["H"] >= p.min_blob_size
                    and s / c["W"] <= p.max_blob_size):
                continue
            c["w"] = s / c["W"]
            c["h"] = s / c["H"]
            c["size"] = s / c["H"]
        if p.center_mode == "centroid":
            c["pos"] = (c["u"], c["v"])
        elif p.center_mode == "soft_centroid" and "su" in c:
            c["pos"] = (c["su"], c["sv"])
        else:
            c["pos"] = (c["bu"], c["bv"])
        out.append(c)
    if p.max_blobs_per_frame and len(out) > p.max_blobs_per_frame:
        out.sort(key=lambda c: -c["npix"])
        out = out[:p.max_blobs_per_frame]
    return out


# ---------------------------------------------------------------- tracker
class Track:
    __slots__ = ("tid", "birth", "u", "v", "state", "last_seen")

    def __init__(self, tid, birth, u, v):
        self.tid, self.birth = tid, birth
        self.u, self.v = u, v
        self.state = "active"          # 'active' | 'lost'
        self.last_seen = birth


def associate(frame_components, p: Params):
    """Run lifecycle association over per-frame gated component lists.
    Returns (rows, full_rows, events):
      rows      — oracle schema: (frame,id,u,v,w,h,age) for active tracks
      full_rows — DAT-style extension incl. lost tracks + flags:
                  (frame,id,u,v,w,h,active,revived,lost,expired,age,
                   lost_time,expired_time)
      events    — internal counters {births, losses, revivals, expiries}
    """
    rows, full_rows = [], []
    events = dict(births=0, losses=0, revivals=0, expiries=0)
    tracks = {}          # tid -> Track (active + lost-unexpired)
    next_id = 0
    exp_frames = p.expiry_frames()
    for f, comps in enumerate(frame_components):
        # expire lost tracks past their window
        for tid in [t for t, tr in tracks.items()
                    if tr.state == "lost" and f - tr.last_seen > exp_frames]:
            tr = tracks.pop(tid)
            events["expiries"] += 1
            full_rows.append((f, tid, tr.u, tr.v, 0.0, 0.0, 0, 0, 0, 1,
                              (f - tr.birth) / p.timeline_fps,
                              (f - tr.last_seen) / p.timeline_fps,
                              (f - tr.birth) / p.timeline_fps))
        # candidate matches: known tracks x detections within radius.
        # Greedy ascending-distance one-to-one assignment (SPEC §3.7);
        # candidates are pruned to mutual 8-nearest pairs, which is
        # where greedy matches can occur in practice.
        cand = []
        tids = list(tracks.keys())
        if tids and comps:
            from scipy.spatial import cKDTree
            tpos = [(tracks[t].u, tracks[t].v) for t in tids]
            tree = cKDTree(tpos)
            cpos = [c["pos"] for c in comps]
            pairs = set()
            k = min(8, len(tids))
            for ci, js in enumerate(tree.query(cpos, k=k)[1]):
                for j in np.atleast_1d(js):
                    pairs.add((tids[j], ci))
            k2 = min(8, len(comps))
            ctree = cKDTree(cpos)
            for ti, js in enumerate(ctree.query(tpos, k=k2)[1]):
                for j in np.atleast_1d(js):
                    pairs.add((tids[ti], int(j)))
            for tid, ci in pairs:
                cu, cv = comps[ci]["pos"]
                d = math.hypot(cu - tracks[tid].u, cv - tracks[tid].v)
                if d <= p.max_move_distance:
                    cand.append((d, tid, ci))
        cand.sort()
        used_t, used_c, match = set(), set(), {}
        for d, tid, ci in cand:
            if tid in used_t or ci in used_c:
                continue
            used_t.add(tid); used_c.add(ci)
            match[ci] = tid
        revived_now = set()
        for ci, c in enumerate(comps):
            cu, cv = c["pos"]
            if ci in match:
                tid = match[ci]
                tr = tracks[tid]
                if tr.state == "lost":
                    events["revivals"] += 1
                    revived_now.add(tid)
                tr.state = "active"
                tr.u, tr.v = cu, cv
                tr.last_seen = f
            else:
                tid = next_id; next_id += 1
                tr = Track(tid, f, cu, cv)
                tracks[tid] = tr
                events["births"] += 1
            age = (f - tr.birth) / p.timeline_fps
            rows.append((f, tid, cu, cv, c["w"], c["h"], age))
            full_rows.append((f, tid, cu, cv, c["w"], c["h"], 1,
                              1 if tid in revived_now else 0, 0, 0,
                              age, 0.0, 0.0))
        for tid in tids:
            tr = tracks.get(tid)
            if tr is not None and tr.state == "active" and tr.last_seen < f:
                tr.state = "lost"
                events["losses"] += 1
        # lost tracks also appear in the full (DAT-style) table
        for tid, tr in tracks.items():
            if tr.state == "lost" and tr.last_seen < f:
                full_rows.append((f, tid, tr.u, tr.v, 0.0, 0.0, 0, 0, 1, 0,
                                  (f - tr.birth) / p.timeline_fps,
                                  (f - tr.last_seen) / p.timeline_fps, 0.0))
    return rows, full_rows, events


def track_video(path, p: Params):
    """Full pipeline on a video file. Returns (rows, full_rows, events,
    n_frames)."""
    bg = None
    mu = var = None
    per_frame = []
    nf = 0
    for w, h, rgb in decode_frames(path, p.res_scale):
        y = luminance(rgb)
        mask = matte_mask(y, p)
        soft = matte_soft(y, p) if (p.bg_mode == "gauss"
                                    or p.size_source
                                    == "square_sqrt_soft_area"
                                    or p.center_mode == "soft_centroid") \
            else None
        if p.matte_invert:
            mask = ~mask
            if soft is not None:
                soft = 1.0 - soft
        if p.bg_mode == "ema":
            if bg is None:
                bg = mask.astype(np.float32)
            fg = mask & (bg < 0.5)
            bg += p.bg_learn_rate * (mask.astype(np.float32) - bg)
            mask = fg
        elif p.bg_mode == "gauss":
            x = soft
            if mu is None:
                mu = x.copy()
                var = np.full_like(x, p.bg_sigma0 ** 2)
                mask = np.zeros_like(mask)
            else:
                sig = np.sqrt(var)
                fg = (x >= 0.5) & ((x - mu) > np.maximum(
                    p.bg_sigma_k * sig, p.bg_abs_thresh))
                a = 1.0 / p.bg_history
                d = x - mu
                mu = mu + a * d
                var = var + a * (d * d - var)
                mask = fg
        per_frame.append(gate_components(
            extract_components(mask, p.cc_connectivity, soft=soft), p))
        nf += 1
    rows, full_rows, events = associate(per_frame, p)
    return rows, full_rows, events, nf


# ---------------------------------------------------------------- io
def fmt(x):
    return "%.7g" % float(np.float32(x))


def write_tracks_csv(rows, fh):
    for f, tid, u, v, w, h, age in rows:
        fh.write("%d,%d,%s,%s,%s,%s,%s\n" %
                 (f, tid, fmt(u), fmt(v), fmt(w), fmt(h), fmt(age)))


def write_full_csv(full_rows, fh):
    fh.write("frame,id,u,v,width,height,active,revived,lost,expired,"
             "age,lost_time,expired_time\n")
    for r in full_rows:
        fh.write("%d,%d,%s,%s,%s,%s,%d,%d,%d,%d,%s,%s,%s\n" %
                 (r[0], r[1], fmt(r[2]), fmt(r[3]), fmt(r[4]), fmt(r[5]),
                  r[6], r[7], r[8], r[9], fmt(r[10]), fmt(r[11]),
                  fmt(r[12])))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("input")
    ap.add_argument("--out", default="-", help="tracks.csv path ('-' = stdout)")
    ap.add_argument("--full-out", help="optional DAT-style full table path")
    ap.add_argument("--sidecar", help="optional JSON stats path")
    ap.add_argument("--preset", choices=sorted(PRESETS))
    for name in ("matte_threshold", "contrast", "threshold_smooth",
                 "min_blob_size", "max_blob_size", "max_move_distance",
                 "expired_time_s", "timeline_fps", "res_scale",
                 "bg_learn_rate", "bg_history", "bg_sigma_k", "bg_sigma0",
                 "bg_abs_thresh"):
        ap.add_argument("--" + name.replace("_", "-"), type=float)
    ap.add_argument("--size-measure", choices=("height", "max_dim"))
    ap.add_argument("--size-source",
                    choices=("bbox", "square_sqrt_area",
                             "square_sqrt_soft_area", "square_equiv_diam",
                             "square_bbox_w", "square_bbox_max"))
    ap.add_argument("--center-mode",
                    choices=("centroid", "bbox_center", "soft_centroid"))
    ap.add_argument("--bg-mode", choices=("off", "ema", "gauss"))
    ap.add_argument("--cc-connectivity", type=int, choices=(4, 8))
    ap.add_argument("--max-blobs-per-frame", type=int)
    a = ap.parse_args(argv)

    kw = dict(PRESETS[a.preset]) if a.preset else {}
    for name in ("matte_threshold", "contrast", "threshold_smooth",
                 "min_blob_size", "max_blob_size", "max_move_distance",
                 "expired_time_s", "timeline_fps", "res_scale",
                 "bg_learn_rate", "bg_history", "bg_sigma_k", "bg_sigma0",
                 "bg_abs_thresh", "size_measure", "size_source",
                 "center_mode", "bg_mode", "cc_connectivity",
                 "max_blobs_per_frame"):
        v = getattr(a, name)
        if v is not None:
            kw[name] = v
    p = Params(**kw)
    rows, full_rows, events, nf = track_video(a.input, p)
    out = sys.stdout if a.out == "-" else open(a.out, "w")
    write_tracks_csv(rows, out)
    if out is not sys.stdout:
        out.close()
    if a.full_out:
        with open(a.full_out, "w") as fh:
            write_full_csv(full_rows, fh)
    stats = dict(frames=nf, blob_rows=len(rows), events=events,
                 params=asdict(p))
    if a.sidecar:
        with open(a.sidecar, "w") as fh:
            json.dump(stats, fh, indent=1)
    print(json.dumps(stats), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
