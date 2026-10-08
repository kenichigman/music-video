#!/usr/bin/env python3
"""Conductor: qwen2.5:14b on gdesk reads per-second audio features and writes
an edit decision list (EDL) for the mosaic render.

The EDL is a slow dynamics envelope over the fast frame-by-frame audio
signal: each section carries chaos_scale and wet_scale multipliers that shape
the mosaic's intensity. The waveform still drives every frame; the conductor
only marks the dynamics, like bowings on a score.

Usage: python3 conductor.py --features work_conductor/features.json \
           --out work_conductor/edl.json [--model qwen2.5:14b]
Exit 0 on valid EDL, 1 if the model output fails validation.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.expanduser(
    "~/workspace/goals/10-polymarket-experiment/bin"))
from ollama_local import generate  # noqa: E402

SYSTEM = (
    "You are the conductor for an audio-reactive music video edit. "
    "The video is a photomosaic effect laid over recognizable footage, "
    "and the house rule is: quiet passages keep the footage clear and "
    "readable, loud passages let the mosaic take over and dissolve it."
)

EDL_SCHEMA = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_s": {"type": "integer"},
                    "end_s": {"type": "integer"},
                    "chaos_scale": {"type": "number"},
                    "wet_scale": {"type": "number"},
                    "note": {"type": "string"},
                },
                "required": ["start_s", "end_s", "chaos_scale",
                             "wet_scale", "note"],
            },
        }
    },
    "required": ["sections"],
}


def build_prompt(feats):
    dur = feats["duration_s"]
    lines = ["t energy bright flux vox"]
    for r in feats["seconds"]:
        lines.append(f"{r['t']} {r['energy']} {r['bright']} "
                     f"{r['flux']} {r['vox']}")
    table = "\n".join(lines)
    return f"""Per-second audio descriptors for a {dur:.0f}-second track, each 0..1 normalized to the track peak:
- energy: RMS loudness
- bright: spectral brightness
- flux: onset density (how busy the hits are)
- vox: vocal-band (300-3400 Hz) energy share

{table}

Divide the track into 6 to 12 contiguous sections that follow its musical structure (intro, build, verse, lift, drop, breakdown, outro — name what the features show, not what you assume).
For each section give:
- chaos_scale 0.3..1.5 — tile-mismatch intensity multiplier
- wet_scale 0.3..1.3 — mosaic blend-strength multiplier
- note — one line naming what you hear in the features for this section

Rules:
- Sections must tile {dur:.0f}s contiguously: first starts at 0, last ends at {int(dur)}, no gaps, no overlaps.
- Low-energy sparse sections get low scales (footage stays readable); high-energy dense sections get high scales (mosaic takes over).
- A section where vox is high and energy is moderate is a vocal moment: keep it readable (scales <= 1.0).
- Return JSON only, matching the schema."""


def validate(edl, dur):
    secs = edl.get("sections")
    assert isinstance(secs, list) and 6 <= len(secs) <= 12, "section count"
    prev_end = 0
    for i, s in enumerate(secs):
        assert s["start_s"] == prev_end, f"gap/overlap at section {i}"
        assert s["end_s"] > s["start_s"], f"empty section {i}"
        assert 0.3 <= s["chaos_scale"] <= 1.5, f"chaos_scale {i}"
        assert 0.3 <= s["wet_scale"] <= 1.3, f"wet_scale {i}"
        prev_end = s["end_s"]
    assert prev_end == int(dur), f"last end {prev_end} != {int(dur)}"
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="qwen2.5:14b")
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args()

    feats = json.load(open(args.features))
    prompt = build_prompt(feats)
    resp = generate(prompt, model=args.model, timeout=args.timeout,
                    system=SYSTEM, temperature=0.0, num_ctx=8192,
                    num_predict=2048, json_schema=EDL_SCHEMA)
    text = resp.get("response", "")
    edl = json.loads(text)
    validate(edl, feats["duration_s"])
    json.dump(edl, open(args.out, "w"), indent=1)
    print(f"conductor OK: {len(edl['sections'])} sections -> {args.out}")
    for s in edl["sections"]:
        print(f"  {s['start_s']:3d}-{s['end_s']:3d}s chaos {s['chaos_scale']:.2f} "
              f"wet {s['wet_scale']:.2f} | {s['note'][:70]}")


if __name__ == "__main__":
    sys.exit(main())
