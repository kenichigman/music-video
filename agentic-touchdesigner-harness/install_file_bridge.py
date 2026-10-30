# ============================================================
# File-bridge installer — Agentic TouchDesigner Harness.
#
# Run ONCE inside a TouchDesigner session (Textport):
#   exec(open(r"<path-to>\install_file_bridge.py").read())
#
# It installs an Execute DAT ("filebridge") inside a host
# component. The DAT polls a command file (cmd.py) in a bridge
# folder on every frame; when the file's modification time
# changes, the file is executed inside the live TD session and
# its stdout + traceback are written to cmd_result.txt in the
# same folder. From then on, an external agent (or a human with
# a shell) drives the session by writing command files — see
# send_command.sh / send_command_long.sh.
#
# SECURITY, stated plainly: anything that can write cmd.py in
# the bridge folder can execute arbitrary Python inside your
# TD session. Treat the bridge folder as trusted-local-only:
# a private folder on your own machine, never a shared or
# synced location you do not control.
#
# Configuration (environment, set before launching TD, or edit
# the defaults below):
#   TD_BRIDGE_DIR      bridge folder (default below)
#   TD_HOST_COMPONENT  component that will hold the DAT
#                      (default /project1/blobnet)
# ============================================================
import os

BRIDGE_DIR = os.environ.get(
    "TD_BRIDGE_DIR", r"C:\TouchDesigner\agent-bridge")
HOST_COMPONENT = os.environ.get(
    "TD_HOST_COMPONENT", "/project1/blobnet")

CALLBACK_TEMPLATE = r'''
import os, io, contextlib, traceback
CMD = __CMD_PATH__
DONE = __DONE_PATH__

def onFrameStart(frame):
    try:
        mt = os.path.getmtime(CMD)
    except Exception:
        return
    if mt == me.fetch('last_mtime', 0):
        return
    me.store('last_mtime', mt)
    buf = io.StringIO()
    try:
        code = open(CMD).read()
        g = {'op': op, 'me': me, 'parent': parent, 'td': td}
        try:
            g['project'] = project
        except Exception:
            pass
        with contextlib.redirect_stdout(buf):
            exec(compile(code, CMD, 'exec'), g)
        buf.write('\n__OK__\n')
    except Exception:
        buf.write(traceback.format_exc())
    try:
        tmp = DONE + '.tmp'
        with open(tmp, 'w') as f:
            f.write(buf.getvalue())
        os.replace(tmp, DONE)
    except Exception:
        pass
'''

CALLBACK = (CALLBACK_TEMPLATE
            .replace("__CMD_PATH__", repr(os.path.join(BRIDGE_DIR, "cmd.py")))
            .replace("__DONE_PATH__", repr(os.path.join(BRIDGE_DIR, "cmd_result.txt"))))

host = op(HOST_COMPONENT)
if host is None:
    raise RuntimeError("host component not found: %s" % HOST_COMPONENT)
old = host.op('filebridge')
if old:
    old.destroy()
ex = host.create('executeDAT', 'filebridge')
cb = host.op('filebridge_callbacks')
if cb is None:
    cb = host.create('textDAT', 'filebridge_callbacks')
try:
    ex.par.callbacks.val = cb.path
except Exception:
    pass
cb.text = CALLBACK
# The executing node must carry its own text in this build:
# bridge code lives in the Execute DAT itself, not only in its
# callbacks DAT.
try:
    ex.text = CALLBACK
except Exception:
    pass
try:
    ex.par.framestart.val = 1
except Exception:
    pass
try:
    ex.active = True
except Exception:
    pass
print('BRIDGE_INSTALLED host:', host.path, 'bridge_dir:', BRIDGE_DIR)
