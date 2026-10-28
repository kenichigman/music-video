# render_fb.py — PALIMPSEST deterministic frame-by-frame renderer
# Thesis: "Destruction as devotion."
# For each frame: cue footage, set audio-driven uniforms, cook, save PNG.
# Audio analysis (uReveal, uTear) pre-computed from the real score.
import os

base = os.environ.get('PALIMPSEST_BASE', 'C:/palimpsest')
proj = op('/project1')

def log(msg):
    open(base + '/render.log', 'a').write(msg + '\n')

log('=== render_fb.py started ===')

# Load audio analysis (7200x2: uReveal, uTear)
import numpy as np
audio = np.load(base + '/audio_analysis.npy')
nframes_total = audio.shape[0]
log('audio loaded: ' + str(audio.shape))

# TEST_MODE: set to False for full 4:00 render
TEST_MODE = True
if TEST_MODE:
    frame_start = 0
    frame_end = 30  # 1 second test
    out_dir = base + '/test_seq'
else:
    frame_start = 0
    frame_end = nframes_total  # 7200 frames = 4:00
    out_dir = base + '/full_seq'

# Clean previous network (keep bootstrap)
for o in proj.children:
    if o.name != 'bootstrap':
        try:
            o.destroy()
        except Exception:
            pass
log('cleaned')

# --- footage ---
src = proj.create('moviefileinTOP', 'src')
src.par.file = base + '/ATripDownMarketStreet_HD.mp4'
src.par.play = 0  # manual cue, not timeline
log('src created')

# --- fragment shader ---
frag = proj.create('glslTOP', 'frag')
frag.inputConnectors[0].connect(src)

fragShader = '''
out vec4 fragColor;
uniform vec4 uAudio;
float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}
void main() {
    float uReveal = uAudio.x;
    float uTear = uAudio.y;
    float uTime = uAudio.z;
    vec2 uv = vUV.st;
    vec2 grid = vec2(40.0, 22.5);
    vec2 blockId = floor(uv * grid);
    float h1 = hash(blockId);
    float h2 = hash(blockId + 19.7);
    float h3 = hash(blockId + 47.3);
    float dispAmt = (1.0 - uReveal) * 0.45;
    vec2 disp = vec2(h1 - 0.5, h2 - 0.5) * 2.0 * dispAmt;
    float band = floor(blockId.y / 2.0);
    float tearSel = step(0.72, hash(vec2(band, floor(uTime * 8.0))));
    disp.x += tearSel * uTear * (h3 - 0.5) * 0.9;
    vec2 sampleUV = fract(uv + disp);
    vec4 col = texture(sTD2DInputs[0], sampleUV);
    float ab = uTear * 0.012 + (1.0 - uReveal) * 0.004;
    col.r = texture(sTD2DInputs[0], fract(sampleUV + vec2(ab, 0.0))).r;
    col.b = texture(sTD2DInputs[0], fract(sampleUV - vec2(ab, 0.0))).b;
    float brightness = mix(0.12, 1.0, uReveal);
    float edge = smoothstep(0.0, 0.15, uReveal) * 0.1;
    col.rgb *= (brightness + edge);
    float grain = (hash(uv * 913.7 + uTime) - 0.5) * 0.06;
    col.rgb += grain * (0.3 + 0.7 * uReveal);
    fragColor = TDOutputSwizzle(col);
}
'''
shDat = proj.create('textDAT', 'frag_pixel')
shDat.text = fragShader
frag.par.pixeldat = shDat
frag.par.vec0name = 'uAudio'
log('frag created')

# --- grade (black-preserving) ---
grade = proj.create('levelTOP', 'grade')
grade.inputConnectors[0].connect(frag)
try:
    grade.par.blacklevel = 0.0
    grade.par.contrast = 1.05
except Exception as e:
    log('grade: ' + str(e)[:60])
log('grade created')

# --- render loop ---
# Footage is 640x360 @ 29.97fps, ~751s. We need 240s of it.
# Map our 7200 frames (30fps) to footage time: use the first 240s.
# cuepoint is in... (from probe6: cuepoint=30.0 gave frame=16.0, so it's seconds? 30s * 29.97fps = 899 frames, not 16. Hmm.)
# Actually frame=16.0 suggests cuepoint might be in a different unit. Let me use cuepoint as seconds and verify.
# For safety, I'll cue by seconds: t = frame / 30.0

import time
t0 = time.time()
for i in range(frame_start, frame_end):
    t_sec = float(i) / 30.0
    # Cue footage to t_sec
    src.par.cuepoint = t_sec
    try:
        src.par.cuepulse.pulse()
    except Exception:
        pass
    # Set uniforms from pre-computed audio
    uR = float(audio[i, 0])
    uT = float(audio[i, 1])
    frag.par.vec0valuex = uR
    frag.par.vec0valuey = uT
    frag.par.vec0valuez = t_sec
    # Cook and save
    grade.cook(force=True)
    fname = out_dir + '/palimpsest_%05d.png' % i
    grade.save(fname)
    if (i - frame_start) % 10 == 0:
        log('frame %d/%d done (uR=%.2f uT=%.2f)' % (i, frame_end, uR, uT))

t1 = time.time()
log('rendered %d frames in %.1fs (%.1f fps)' % (frame_end - frame_start, t1 - t0, (frame_end - frame_start) / max(0.1, t1 - t0)))
open(base + '/RENDER_DONE', 'w').write('frames=%d' % (frame_end - frame_start))
log('=== render_fb.py done ===')
