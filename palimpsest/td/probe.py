# PALIMPSEST probe — runs INSIDE TouchDesigner via the bootstrap Execute DAT.
# Creates one of each operator type we need, dumps par names, writes report + sentinel.
import os

base = os.environ.get("PALIMPSEST_BASE", r'C:\palimpsest')  # override via PALIMPSEST_BASE
out = []
proj = op('/project1')

types = ['moviefilein', 'audiofilein', 'envelope', 'trigger', 'lag', 'limit',
         'filter', 'audiofilter', 'math', 'noise', 'resolution', 'displace',
         'threshold', 'blur', 'composite', 'feedback', 'level', 'moviefileout',
         'info', 'rename', 'time', 'execute', 'text', 'null', 'select']

for t in types:
    try:
        o = proj.create(t, 'pb_' + t)
        pars = sorted([p.name for p in o.pars()])
        out.append(t + ' OK [' + ' '.join(pars) + ']')
        o.destroy()
    except Exception as e:
        out.append(t + ' FAIL ' + str(e)[:100].replace(chr(10), ' '))

open(os.path.join(base, 'probe_report.txt'), 'w').write('\n'.join(out))
open(os.path.join(base, 'PROBE_DONE'), 'w').write('ok')
