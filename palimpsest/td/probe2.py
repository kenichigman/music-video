import os
base = os.environ.get("PALIMPSEST_BASE", r'C:\palimpsest')  # override via PALIMPSEST_BASE
out = []
proj = op('/project1')

# Test 1: string with TOP/CHOP suffix
for t in ['moviefileinTOP', 'audiofileinCHOP']:
    try:
        o = proj.create(t, 'pb2_' + t)
        out.append(t + ' STR_OK')
        o.destroy()
    except Exception as e:
        out.append(t + ' STR_FAIL ' + str(e)[:80])

# Test 2: type objects from TD namespace
import sys
tdmod = sys.modules.get('td')
out.append('td module: ' + str(tdmod is not None))
if tdmod:
    for attr in ['moviefileinTOP', 'audiofileinCHOP', 'mathCHOP', 'levelTOP']:
        has = hasattr(tdmod, attr)
        out.append('td.' + attr + ' exists=' + str(has))
        if has:
            try:
                o = proj.create(getattr(tdmod, attr), 'pb2_' + attr)
                out.append('td.' + attr + ' CREATE_OK pars=' + str(len(o.pars())))
                o.destroy()
            except Exception as e:
                out.append('td.' + attr + ' CREATE_FAIL ' + str(e)[:80])

# Test 3: bare names in globals
for name in ['moviefileinTOP', 'audiofileinCHOP']:
    g = globals()
    out.append(name + ' in globals=' + str(name in g))

open(base + r'\probe2_report.txt', 'w').write('\n'.join(out))
open(base + r'\PROBE2_DONE', 'w').write('ok')
