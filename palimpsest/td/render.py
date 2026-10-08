# render.py — PALIMPSEST fragment reconstitution renderer
# Thesis: "Destruction as devotion."
# Archival footage destroyed and reconstructed from fragments sampled from
# itself. The real soundtrack drives every frame:
#   loud/sustained -> fragments cohere, image reveals and stabilizes
#   quiet          -> fragments disperse toward black (darkness intentional)
#   transients     -> tears, displacement, chromatic separation
import os

base = 'C:/k3n1/palimpsest'
proj = op('/project1')

def log(msg):
    open(base + '/render.log', 'a').write(msg + '\n')

log('=== render.py started ===')

# Clean previous network (keep bootstrap)
for o in proj.children:
    if o.name != 'bootstrap':
        try:
            o.destroy()
        except Exception:
            pass
log('cleaned')

# ---------------------------------------------------------------- footage
src = proj.create('moviefileinTOP', 'src')
src.par.file = base + '/ATripDownMarketStreet_HD.mp4'
src.par.play = 1
# loop the 751s footage across our 240s timeline (playmode: 0=once? use loop)
# We'll set explicit: play the full file; timeline is 240s so it just plays.
log('src created')

# ---------------------------------------------------------------- score
score = proj.create('audiofileinCHOP', 'score')
score.par.file = base + '/palimpsest_score.wav'
score.par.play = 1
log('score created')

# ---------------------------------------------------------------- envelope (loudness -> reveal)
env = proj.create('envelopeCHOP', 'env')
env.inputConnectors[0].connect(score)
# envelope method: default should track amplitude; widen the window for smoothness
try:
    env.par.width = 0.4
except Exception as e:
    log('env width: ' + str(e)[:60])
log('env created')

# normalize envelope to 0..1 (math: scale)
envN = proj.create('mathCHOP', 'envN')
envN.inputConnectors[0].connect(env)
# Use fromrange/torange to normalize. We don't know the env range yet;
# use a generous gain then limit. Start with gain 2.0 and clamp via limit.
try:
    envN.par.gain = 2.0
except Exception as e:
    log('envN gain: ' + str(e)[:60])
log('envN created')

envC = proj.create('limitCHOP', 'envC')
envC.inputConnectors[0].connect(envN)
try:
    envC.par.min = 0.0
    envC.par.max = 1.0
    envC.par.type = 'clamp'  # may need different value; guarded
except Exception as e:
    log('envC clamp: ' + str(e)[:60])
log('envC created')

# smooth the reveal (slow attack/release so the image breathes, not flickers)
smooth = proj.create('lagCHOP', 'smooth')
smooth.inputConnectors[0].connect(envC)
try:
    smooth.par.lag1 = 0.8   # attack (s)
    smooth.par.lag2 = 1.5   # release (s)
except Exception as e:
    log('smooth lag: ' + str(e)[:60])
log('smooth created')

# ---------------------------------------------------------------- transients (onsets -> tears)
trig = proj.create('triggerCHOP', 'trig')
trig.inputConnectors[0].connect(score)
try:
    trig.par.threshold = 0.25
    trig.par.attack = 0.005
    trig.par.decay = 0.35
    trig.par.sustain = 0.0
    trig.par.release = 0.4
except Exception as e:
    log('trig: ' + str(e)[:60])
log('trig created')

# clamp trigger to 0..1
trigC = proj.create('limitCHOP', 'trigC')
trigC.inputConnectors[0].connect(trig)
try:
    trigC.par.min = 0.0
    trigC.par.max = 1.0
except Exception as e:
    log('trigC: ' + str(e)[:60])
log('trigC created')

# ---------------------------------------------------------------- fragment shader
frag = proj.create('glslTOP', 'frag')
frag.inputConnectors[0].connect(src)
# 1280x720 output
try:
    frag.par.resolutionw = 1280
    frag.par.resolutionh = 720
except Exception as e:
    log('frag res: ' + str(e)[:60])

fragShader = '''
out vec4 fragColor;

uniform vec4 uAudio;  // x=uReveal, y=uTear, z=uTime, w=unused

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

    // Destruction as devotion: fragments disperse when quiet, cohere when loud
    float dispAmt = (1.0 - uReveal) * 0.45;
    vec2 disp = vec2(h1 - 0.5, h2 - 0.5) * 2.0 * dispAmt;

    // Tears: horizontal bands ripped on transients
    float band = floor(blockId.y / 2.0);
    float tearSel = step(0.72, hash(vec2(band, floor(uTime * 8.0))));
    disp.x += tearSel * uTear * (h3 - 0.5) * 0.9;

    // Fragments are sampled from the footage itself (fract = wrap)
    vec2 sampleUV = fract(uv + disp);
    vec4 col = texture(sTD2DInputs[0], sampleUV);

    // Chromatic separation on tears and in fragmentation
    float ab = uTear * 0.012 + (1.0 - uReveal) * 0.004;
    col.r = texture(sTD2DInputs[0], fract(sampleUV + vec2(ab, 0.0))).r;
    col.b = texture(sTD2DInputs[0], fract(sampleUV - vec2(ab, 0.0))).b;

    // Darkness is intentional: quiet passages fade toward black
    float brightness = mix(0.12, 1.0, uReveal);
    float edge = smoothstep(0.0, 0.15, uReveal) * 0.1;
    col.rgb *= (brightness + edge);

    // Subtle grain
    float grain = (hash(uv * 913.7 + uTime) - 0.5) * 0.06;
    col.rgb += grain * (0.3 + 0.7 * uReveal);

    fragColor = TDOutputSwizzle(col);
}
'''
# Write the shader via a Text DAT and reference it, or set directly.
# glslTOP pixel shader is set via the 'pixeldat' parameter (DAT reference).
# Create a Text DAT holding the shader.
shDat = proj.create('textDAT', 'frag_pixel')
# textDAT content: use its text via .text? For DATs created via script,
# we can set the text with op('...').text = ...
try:
    shDat.text = fragShader
    log('shader text set, len=' + str(len(fragShader)))
except Exception as e:
    log('shader text FAIL: ' + str(e)[:100])

try:
    frag.par.pixeldat = shDat
    log('pixeldat linked')
except Exception as e:
    log('pixeldat FAIL: ' + str(e)[:100])

# Name the uniform and bind xyz to CHOP channels via expressions
# uAudio.x = reveal (smoothed envelope 0..1)
# uAudio.y = tear (trigger 0..1)
# uAudio.z = time (seconds)
try:
    frag.par.vec0name = 'uAudio'
    frag.par.vec0valuex.expr = "op('smooth')['chan1']"
    frag.par.vec0valuey.expr = "op('trigC')['chan1']"
    frag.par.vec0valuez.expr = "absTime.seconds"
    log('uniforms bound')
except Exception as e:
    log('uniforms FAIL: ' + str(e)[:100])
log('frag created')

# ---------------------------------------------------------------- feedback (persistence)
fb = proj.create('feedbackTOP', 'fb')
try:
    fb.par.top = frag
except Exception as e:
    log('fb top: ' + str(e)[:60])
# feedbackTOP takes input from... actually it references via 'top' param.
# It also needs an input? The feedback loop: frag -> fb (fb outputs previous frame)
log('fb created')

# composite: blend current fragments with feedback trails
mix = proj.create('compositeTOP', 'mix')
mix.inputConnectors[0].connect(frag)
try:
    mix.inputConnectors[1].connect(fb)
except Exception as e:
    log('mix input1: ' + str(e)[:60])
try:
    mix.par.operand = 'add'
except Exception as e:
    log('mix operand: ' + str(e)[:60])
log('mix created')

# ---------------------------------------------------------------- grade (black-preserving)
grade = proj.create('levelTOP', 'grade')
grade.inputConnectors[0].connect(mix)
try:
    grade.par.blacklevel = 0.0
    grade.par.brightness1 = 1.0
    grade.par.contrast = 1.05
    grade.par.gamma1 = 1.0
except Exception as e:
    log('grade: ' + str(e)[:60])
log('grade created')

# ---------------------------------------------------------------- output
# PNG image sequence (safe for external stop; transcode after)
out = proj.create('moviefileoutTOP', 'out')
out.inputConnectors[0].connect(grade)
seqPath = base + '/test_seq/palimpsest_test_'
out.par.file = seqPath
try:
    out.par.type = 'image'
except Exception as e:
    log('out type: ' + str(e)[:60])
try:
    out.par.imagefiletype = 'png'
except Exception as e:
    log('out imagefiletype: ' + str(e)[:60])
try:
    out.par.fps = 30
except Exception as e:
    log('out fps: ' + str(e)[:60])
log('out created, file=' + seqPath)

# Force a cook to validate the network before recording
try:
    frag.cook(force=True)
    log('frag cook ok, res=' + str(frag.width) + 'x' + str(frag.height))
except Exception as e:
    log('frag cook FAIL: ' + str(e)[:120])

# Record (realtime; stopped externally after N seconds)
try:
    out.par.record = 1
    log('record=1 set')
except Exception as e:
    log('record FAIL: ' + str(e)[:100])

open(base + '/RENDER_STARTED', 'w').write('ok')
log('=== render.py done, recording ===')
