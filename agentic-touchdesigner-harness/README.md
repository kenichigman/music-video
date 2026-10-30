# Agentic TouchDesigner Harness

A pattern for letting an external agent work inside a
TouchDesigner session: authoring networks, restructuring
them, and rendering from them — without the agent ever
touching the mouse, and without the human pasting code after
the first install.

## The division of labor, honestly

- **The human launches TouchDesigner.** The application
  lives in the human's logged-in, GPU-accelerated desktop
  session; nothing in this kit starts it, and if the machine
  restarts, the human relaunches it. One launch per session
  is the human's entire ongoing role.
- **The agent does everything after that.** Through the file
  bridge (below) the agent sends Python command files that
  execute inside the live session: building networks from
  scripts, reorganizing components, setting parameters,
  stepping frames and saving renders. Project files are
  copied, renamed, and backed up from the shell like any
  other files.

## How the bridge works

An Execute DAT installed in the session polls a command
file (`cmd.py`) in a bridge folder every frame. When the
file's modification time changes, its contents execute
inside the session (with the usual TD globals available)
and stdout + traceback land in `cmd_result.txt`. The shell
drivers make that a round trip:

- `send_command.sh <cmd.py>` — send a command, wait briefly,
  print the result.
- `send_command_long.sh <cmd.py> <max_wait_s>` — same, for
  renders and other long operations; it only accepts a
  *fresh* result file, so a stale reply is never mistaken
  for a new one.

**Security, stated plainly:** whoever can write `cmd.py`
can execute arbitrary Python inside the session. The bridge
folder must be a trusted, local-only folder on your own
machine. Do not point it at a shared or cloud-synced
location you do not control.

## The workspace: an effect pool

Networks built through the harness live in a single project
file organized as an **effect pool**: one top-level
component per effect, each self-contained, all reachable
through the one bridge. See `effect-pool.md` for the layout
this kit was developed against. The `.toe` project file
itself is not published — it is a binary that accumulates
session state and local paths; everything needed to rebuild
the workspace is in the build scripts.

## Quickstart

Requirements: TouchDesigner (the free Non-Commercial build
is sufficient; note it cannot GPU-encode H.264, so capture
is offline frame-stepping — the build script's comments
cover the production pattern), plus a shell that can write
to the bridge folder (the drivers assume a WSL-style mount
path mapping; set `TD_BRIDGE_DIR` to wherever the folder
appears from your shell).

1. In TouchDesigner, create or open the host component
   (default `/project1/blobnet`; set `TD_HOST_COMPONENT`
   to change it).
2. Run the installer once, in the Textport:
   `exec(open(r"<path>\install_file_bridge.py").read())`
   (set `TD_BRIDGE_DIR` first if you want a non-default
   bridge folder).
3. From the shell: `./send_command.sh my_command.py` —
   the command file is ordinary TD Python; start with
   `print(op('/project1').children)` to prove the round
   trip.
4. Build the blob-track instancing network by running
   `build_blob_network.py` the same way (it expects
   `source.mp4` and `bassdata.txt` in `TD_WORK_DIR`).

## Contents

- `install_file_bridge.py` — the one-time bridge installer.
- `send_command.sh`, `send_command_long.sh` — shell drivers.
- `build_blob_network.py` — programmatic build of the
  blob-track instancing network (matte → Blob Track →
  instanced, source-textured rectangles driven by a baked
  bass envelope), including the operational lessons learned
  bringing it up, in its comments. The network's grammar
  follows PPPANIK's "Blob Track Instancing" tutorial
  (https://www.youtube.com/@ppppanik007), rebuilt from the
  vendor's public documentation and forums.
- `effect-pool.md` — the effect-pool workspace structure.

## What is and is not in this shelf

Included: the complete harness kit — installer, drivers,
and a production network build script, parameterized by
environment variables (`TD_BRIDGE_DIR`, `TD_WORK_DIR`,
`TD_HOST_COMPONENT`). Not included: any project binary, any
captured output, and any of the session-specific repair
scripts written during the original bring-up (they are
fossils of one machine's history, not part of the pattern).
