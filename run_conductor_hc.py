import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Optional local-tier helper, same pattern as conductor.py: the
# ollama_local module is resolved via MUSIC_VIDEO_LOCAL_BIN.
_local_bin = os.environ.get("MUSIC_VIDEO_LOCAL_BIN")
if _local_bin:
    sys.path.insert(0, _local_bin)
import conductor
from ollama_local import generate

WORK_ROOT = os.environ.get("MUSIC_VIDEO_WORK_ROOT", ".")
feats = json.load(open(os.path.join(WORK_ROOT, "work/features_homecomputer.json")))
prompt = conductor.build_prompt(feats)
resp = generate(prompt, model="qwen2.5:14b", timeout=900, system=conductor.SYSTEM,
                temperature=0.0, num_ctx=8192, num_predict=2048,
                json_schema=conductor.EDL_SCHEMA)
edl = json.loads(resp.get("response", ""))
json.dump(edl, open(os.path.join(WORK_ROOT, "work/edl_raw.json"), "w"), indent=1)
for s in edl["sections"]:
    print(f"{s['start_s']:>4}-{s['end_s']:>4}s chaos {s['chaos_scale']:.2f} wet {s['wet_scale']:.2f} | {s['note'][:80]}")
print("RAW_EDL_WRITTEN")
