#!/usr/bin/env python3
"""Fuse-3 preview: window mosh (film 33-49) — verbatim from the
no-blob leg. Transitions land as CLEAN cuts -> fresh IDR anchors
at EVERY row boundary in the window, NO bridge exemptions: film
35.0 / 36.5 / 40.0 / 41.3333 / 43.0667 / 45.0 / 46.0 = window-rel
2.0 / 3.5 / 7.0 / 8.3333 / 10.0667 / 12.0 / 13.0. Thresh 0.58 on
this drive == shipped film density. max_gap 8.0."""
import os
RIG_ROOT = os.environ.get("RIG_ROOT", os.path.join(os.getcwd(), "rig-data"))
import sys, json, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..'))
import datamosh

B = os.environ.get('FUSION_WORK_DIR', RIG_ROOT + '/fusion-work')
os.makedirs(B, exist_ok=True)
drive_full = np.load(os.environ.get(
    'FUSION_DRIVE', RIG_ROOT + '/drive.npy'))
drive = drive_full[66:100]  # 0.5s windows for film 33.0-50.0
RESETS = [2.0, 3.5, 7.0, 8.3333, 10.0667, 12.0, 13.0]
kept, moshed = datamosh.corrupt_stream(
    f'{B}/comp_win_fuse3.h264', f'{B}/comp_win_fuse3_mosh.h264',
    drive, 30, 480, drop_thresh=0.58, max_gap_s=8.0, reset_times=RESETS)
print('mosh done: kept', kept, 'moshed', moshed, flush=True)
json.dump({'reset_times_rel': RESETS,
           'reset_film_times': [35.0, 36.5, 40.0, 41.3333, 43.0667,
                                45.0, 46.0],
           'bridges_kept_film': [],
           'drop_thresh': 0.58, 'max_gap_s': 8.0,
           'kept': kept, 'moshed': moshed},
          open(f'{B}/mosh_fuse3_record.json', 'w'), indent=1)
print('ALL DONE')
