#!/usr/bin/env python3
"""supercut_qa.py — standing pre-delivery QA gate for supercut renders.

A render does not ship until this gate passes. It exists because three
defects in the 2026-10-27 Song Six run were caught by human eyes and ears
after delivery; each is now a mechanical check:

  1. DECODE — full ffmpeg -xerror pass must be clean (rc 0, no errors).
  2. FLASH — inside spans the manifest declares CLEAN (no intended cut:
     an opening hold, a legible section), any frame-diff above the
     threshold is an unintended insert / internal source cut.
     Known positive: Song Six v1/v2 head — diff 59 at frames 71 and 90
     (an anime-internal bridge scene repainting) inside the clean head
     window; fixed v3 head maxes at 3.9 in the same window.
     Why manifest-declared windows instead of pixel-only detection:
     an A->B->A "snap-back" test was tried first and false-fires all
     over this grammar — IDR-anchor refresh cycles over looping source
     (a walk cycle) genuinely return to near-identical frames. Intent
     lives in the manifest; inside a declared-clean span the check is
     exact. Outside clean windows, all spike candidates are listed in
     the JSON report for cross-checking against the manifest's declared
     cuts/bridges — they do not gate.
  3. PHASE — boundary detonation gates; the onset table informs.
     a. Detonation: at a DROP boundary (declared section chaos >= 1.0)
        the cut must detonate — the biggest frame-diff within ±0.5s of
        the boundary must reach >= 50% of the biggest diff in the 2.5s
        after it (and that follow-up energy must itself be real, >= the
        flash threshold). Song Six Drop II, every version through v3:
        18.8 vs 46.0 — the energy ramps ~2s late, which is what "audio
        seems late" actually was. The healthy drop at 183s: 57.7/42.6.
     b. Onset table (informational): per section, the 3 strongest audio
        onsets plus the onset nearest the section boundary, each vs the
        nearest video-diff accent (largest diff within ±3s), flagged at
        |offset| > tol. Per-onset lag is endemic to this grammar —
        accents are anchor-driven, not beat-driven — so the table is a
        review surface, not a gate. The rows a listener's ear caught read
        exactly: onset 119.4 -> +1.60s, onset 130.0 -> +2.00s.
  4. HEAD SHEET — frames at 0/0.5/1/2/3/5s in a contact sheet PNG for
     visual review (composition, stray inserts).

EVIDENCE RULE (hard): all frame extraction is SEQUENTIAL DECODE from
t=0. Never -ss seeks: on this file family the mp4 demuxer seek lands a
full GOP early, which produced a wrong diagnosis and burned a whole
revision cycle (2026-10-27, v2->v3). Seeks are not evidence.

Usage:
  python3 supercut_qa.py <file.mp4> [--sections sections.json]
      [--json out.json] [--sheet out.png] [--no-sheet]
      [--phase-tol 0.25] [--flash-abs 20]

sections.json — any of:
  {"sections": [{"start": 0, "end": 45, "chaos": 1.3}, ...],
   "bridges": [47.0, ...], "clean_windows": [[0, 6.0], ...]}
  {"boundaries": [45, 66, ...], "bridges": [...]}
  [45, 66, ...]                      (bare boundary list)
"bridges" declares intended in-section mosaic-bridge times (excluded
inside clean windows). "chaos" enables the detonation gate per drop
section. "clean_windows" declares spans with no intended discontinuity.
Exit code 0 = PASS, 1 = FAIL, 2 = usage/tool error.

Dependencies: ffmpeg/ffprobe + numpy only.
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np

DW, DH = 212, 116            # diff-probe frame size (seed geometry)
SR = 22050                   # audio probe rate
HOP = SR // 10               # 0.1s onset hops
HEAD_TIMES = [0.0, 0.5, 1.0, 2.0, 3.0, 5.0]


# ---------------------------------------------------------------- ffmpeg
def ffprobe_info(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate,width,height",
         "-show_entries", "format=duration", "-of", "json", path],
        capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {out.stderr.strip()}")
    info = json.loads(out.stdout)
    st = info["streams"][0]
    num, den = st["r_frame_rate"].split("/")
    fps = float(num) / float(den)
    return fps, float(info["format"]["duration"]), st["width"], st["height"]


def decode_check(path):
    """Full -xerror decode. Returns (ok, first_errors)."""
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-xerror", "-i", path,
         "-f", "null", "-"], capture_output=True, text=True)
    errs = [ln for ln in p.stderr.splitlines() if ln.strip()]
    return p.returncode == 0 and not errs, errs[:5]


def frame_diffs(path):
    """Per-frame mean-abs-diff, SEQUENTIAL decode from t=0, small gray."""
    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", path, "-an",
         "-vf", f"scale={DW}:{DH},format=gray", "-f", "rawvideo", "-"],
        stdout=subprocess.PIPE)
    prev, diffs = None, []
    fs = DW * DH
    while True:
        b = p.stdout.read(fs)
        if len(b) < fs:
            break
        fr = np.frombuffer(b, dtype=np.uint8).astype(np.float32)
        diffs.append(0.0 if prev is None
                     else float(np.mean(np.abs(fr - prev))))
        prev = fr
    p.wait()
    return np.array(diffs)


def onset_envelope(path):
    """Audio onset strength per 0.1s hop (positive RMS diff), from t=0."""
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1",
         "-ar", str(SR), "-f", "f32le", "-"], capture_output=True)
    a = np.frombuffer(p.stdout, dtype=np.float32)
    n = len(a) // HOP
    a = a[:n * HOP].reshape(n, HOP)
    rms = np.sqrt(np.mean(a ** 2, axis=1) + 1e-12)
    return np.maximum(np.diff(rms, prepend=rms[0]), 0.0)


def contact_sheet(path, fps, out_png):
    """Head frames by SEQUENTIAL decode (select on frame index, no seek)."""
    idx = sorted({int(round(t * fps)) for t in HEAD_TIMES})
    sel = "+".join(f"eq(n\\,{i})" for i in idx)
    cols = 3
    rows = (len(idx) + cols - 1) // cols
    vf = (f"select='{sel}',scale=424:232,"
          f"tile={cols}x{rows}:padding=4:margin=4")
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-vf", vf,
         "-frames:v", "1", "-y", out_png], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"contact sheet failed: {p.stderr.strip()}")
    return idx


# ---------------------------------------------------------------- helpers
def rolling_median(x, win):
    if win % 2 == 0:
        win += 1
    pad = win // 2
    xp = np.pad(x, pad, mode="edge")
    sw = np.lib.stride_tricks.sliding_window_view(xp, win)
    return np.median(sw, axis=1)


def load_sections(path, duration):
    """Returns (boundaries, sections, bridges, clean_windows)."""
    if not path:
        return [0.0], [{"start": 0.0, "end": duration, "chaos": None}], [], []
    with open(path) as f:
        data = json.load(f)
    bridges, clean = [], []
    secs = []
    if isinstance(data, dict):
        bridges = [float(b) for b in data.get("bridges", [])]
        clean = [[float(a), float(b)] for a, b in data.get("clean_windows", [])]
        raw = data.get("sections")
        if raw is None:
            raw = [{"start": b} for b in
                   (data.get("boundaries") or data.get("cuts") or [])]
    else:
        raw = data
    for item in raw:
        if isinstance(item, (int, float)):
            secs.append({"start": float(item), "chaos": None})
        elif isinstance(item, dict):
            secs.append({"start": float(item["start"]),
                         "chaos": item.get("chaos")})
    secs.sort(key=lambda s: s["start"])
    if not secs or secs[0]["start"] > 0.0:
        secs.insert(0, {"start": 0.0, "chaos": None})
    for i, s in enumerate(secs):
        s["end"] = (secs[i + 1]["start"] if i + 1 < len(secs) else duration)
    return [s["start"] for s in secs], secs, bridges, clean


# ---------------------------------------------------------------- checks
def clean_window_violations(diffs, fps, clean_windows, bridges, thr):
    """Frames inside declared-clean spans whose diff exceeds thr."""
    out = []
    for a, b in clean_windows:
        f0, f1 = max(1, int(a * fps)), min(len(diffs), int(b * fps))
        for i in range(f0, f1):
            if diffs[i] > thr:
                t = i / fps
                if bridges and min(abs(t - x) for x in bridges) <= 0.5:
                    continue
                out.append({"t": round(t, 2), "frame": i,
                            "diff": round(float(diffs[i]), 1)})
    return out


def spike_candidates(diffs, fps, boundaries, abs_min, factor=5.0):
    """All big discontinuities outside declared boundaries (info only)."""
    med = rolling_median(diffs, int(5 * fps) | 1)
    out = []
    for i in range(1, len(diffs)):
        if diffs[i] >= abs_min and diffs[i] > factor * med[i]:
            t = i / fps
            if min(abs(t - b) for b in boundaries) <= 1.0:
                continue
            out.append({"t": round(t, 2), "frame": i,
                        "diff": round(float(diffs[i]), 1)})
    return out


def detonation_rows(sections, diffs, fps, energy_floor):
    rows = []
    for s in sections:
        b = s["start"]
        fb = int(round(b * fps))
        if fb >= len(diffs):
            continue
        at = diffs[max(0, fb - int(0.5 * fps)):fb + int(0.5 * fps) + 1]
        after = diffs[fb:fb + int(2.5 * fps)]
        if not len(at) or not len(after):
            continue
        ratio = float(at.max() / after.max()) if after.max() > 0 else 1.0
        gated = s["chaos"] is not None and s["chaos"] >= 1.0
        if not gated:
            status = "info"
        elif after.max() < energy_floor:
            status = "skip"      # no real energy follows to detonate into
        else:
            status = "FAIL" if ratio < 0.5 else "OK"
        rows.append({
            "boundary_t": round(b, 2), "chaos": s["chaos"],
            "at_max": round(float(at.max()), 1),
            "after_max": round(float(after.max()), 1),
            "ratio": round(ratio, 2), "gated": gated, "status": status})
    return rows


def onset_rows(sections, onset, diffs, fps, tol, topk=3):
    """Informational: strongest onsets per section + boundary onset."""
    rows = []
    for si, s in enumerate(sections):
        lo, hi = int(s["start"] * 10), int(s["end"] * 10)
        seg = onset[lo:hi]
        if len(seg) < 5 or seg.max() <= 0:
            continue
        order = np.argsort(seg)[::-1]
        picked = []
        for i in order:
            if seg[i] < 0.25 * seg.max():
                break
            if all(abs(int(i) - j) >= 15 for j in picked):
                picked.append(int(i))
            if len(picked) == topk:
                break
        # boundary onset: strongest onset within +/-1.5s of section start
        b0 = max(0, int((s["start"] - 1.5) * 10))
        b1 = min(len(onset), int((s["start"] + 1.5) * 10))
        if b1 > b0:
            bi = b0 + int(np.argmax(onset[b0:b1]))
            bt = bi / 10.0
            if all(abs(bt - (s["start"] + j / 10.0)) > 0.75 for j in picked):
                picked.append(bi - lo)
        for i in sorted(set(picked)):
            if i < 0 or i >= len(seg):
                continue
            t = s["start"] + i / 10.0
            f0 = max(1, int((t - 3) * fps))
            f1 = min(len(diffs), int((t + 3) * fps))
            fi = f0 + int(np.argmax(diffs[f0:f1]))
            off = fi / fps - t
            status = ("LATE" if off > tol else
                      "EARLY" if off < -tol else "OK")
            rows.append({"section": si, "onset_t": round(t, 2),
                         "strength": round(float(seg[i]), 3),
                         "accent_t": round(fi / fps, 2),
                         "offset_s": round(off, 2), "status": status,
                         "boundary": abs(t - s["start"]) <= 1.5})
    return rows


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--sections", help="JSON: sections/boundaries/bridges/"
                    "clean_windows")
    ap.add_argument("--json", dest="json_out", help="write JSON report here")
    ap.add_argument("--sheet", help="contact sheet PNG path "
                    "(default: <file>_qa_sheet.png)")
    ap.add_argument("--no-sheet", action="store_true")
    ap.add_argument("--phase-tol", type=float, default=0.25,
                    help="onset-table flag threshold in s (default 0.25)")
    ap.add_argument("--flash-abs", type=float, default=20.0,
                    help="frame-diff threshold: clean-window violations "
                    "and spike candidates (default 20)")
    a = ap.parse_args()

    if not os.path.isfile(a.file):
        print(f"no such file: {a.file}", file=sys.stderr)
        return 2
    try:
        fps, dur, w, h = ffprobe_info(a.file)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 2
    boundaries, sections, bridges, clean = load_sections(a.sections, dur)
    name = os.path.basename(a.file)
    print(f"== supercut QA: {name} ({w}x{h} @ {fps:g}fps, {dur:.1f}s) ==")

    ok, errs = decode_check(a.file)
    print(f"[decode]  {'CLEAN' if ok else 'ERRORS: ' + '; '.join(errs)}")

    diffs = frame_diffs(a.file)
    viols = clean_window_violations(diffs, fps, clean, bridges, a.flash_abs)
    cand = spike_candidates(diffs, fps, boundaries, a.flash_abs)
    if clean:
        print(f"[flash]   clean windows {clean}: "
              f"{len(viols)} violation(s) (diff > {a.flash_abs:g})")
        for v in viols:
            print(f"        ** t={v['t']:7.2f}s frame {v['frame']} "
                  f"diff {v['diff']}")
    else:
        print("[flash]   no clean windows declared — violation check "
              "skipped (declare clean_windows in the manifest)")
    print(f"          {len(cand)} spike candidate(s) outside boundaries "
          f"(informational; full list in JSON)")

    det = detonation_rows(sections, diffs, fps, a.flash_abs)
    det_fail = [r for r in det if r["status"] == "FAIL"]
    print("[phase]   boundary detonation (drop sections gate at "
          "ratio >= 0.5):")
    for r in det:
        print(f"          boundary {r['boundary_t']:7.2f}s "
              f"chaos {r['chaos']}  at ±0.5s {r['at_max']:6.1f} vs "
              f"+2.5s {r['after_max']:6.1f}  ratio {r['ratio']:.2f}  "
              f"[{r['status']}]")

    onset = onset_envelope(a.file)
    orows = onset_rows(sections, onset, diffs, fps, a.phase_tol)
    nflag = sum(1 for r in orows if r["status"] != "OK")
    print(f"[phase]   onset table (informational; {nflag} of "
          f"{len(orows)} rows outside ±{a.phase_tol:g}s):")
    for r in orows:
        mark = "**" if r["status"] != "OK" else "  "
        bnd = " (boundary)" if r["boundary"] else ""
        print(f"        {mark} sec{r['section']} onset {r['onset_t']:7.2f}s "
              f"-> accent {r['accent_t']:7.2f}s  "
              f"offset {r['offset_s']:+.2f}s  [{r['status']}]{bnd}")

    sheet_path, sheet_frames = None, []
    if not a.no_sheet:
        sheet_path = a.sheet or os.path.splitext(a.file)[0] + "_qa_sheet.png"
        try:
            sheet_frames = contact_sheet(a.file, fps, sheet_path)
            print(f"[sheet]   {sheet_path} (frames {sheet_frames} = "
                  f"{HEAD_TIMES}s, sequential decode)")
        except RuntimeError as e:
            print(f"[sheet]   FAILED: {e}")
            sheet_path = None

    verdict = (ok and not viols and not det_fail
               and sheet_path is not None)
    print(f"VERDICT: {'PASS' if verdict else 'FAIL'}")

    if a.json_out:
        report = {
            "file": a.file, "fps": fps, "duration_s": dur, "size": [w, h],
            "boundaries": boundaries, "bridges": bridges,
            "clean_windows": clean,
            "decode_clean": ok, "decode_errors": errs,
            "clean_window_violations": viols,
            "spike_candidates": cand,
            "detonation": det, "onsets": orows,
            "contact_sheet": sheet_path, "sheet_frames": sheet_frames,
            "thresholds": {"phase_tol_s": a.phase_tol,
                           "flash_abs": a.flash_abs},
            "verdict": "PASS" if verdict else "FAIL",
        }
        with open(a.json_out, "w") as f:
            json.dump(report, f, indent=1)
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
