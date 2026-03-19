"""
patch_vp.py — Patches vp.html in-place:
  1. Fix text visibility: ensure all non-hero sections have solid opaque backgrounds
     and the neural bg canvas has a lower opacity so it doesn't bleed through content.
  2. Upgrade Observatory: new metrics panel, speed control, color-coding status.
"""
import re, shutil

src = open(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', encoding='utf-8').read()

# ─────────────────────────────────────────────────────────────────────────────
# 1. REDUCE neural mesh opacity so content text is always readable
# ─────────────────────────────────────────────────────────────────────────────
src = src.replace(
    'opacity: 0.72;\n      filter: contrast(1.7) brightness(1.15) saturate(1.3)',
    'opacity: 0.48;\n      filter: contrast(1.6) brightness(1.1) saturate(1.2)'
)
# Also try alternative format used in the injected canvas tag
src = src.replace(
    "opacity:0.72;filter:contrast(1.7) brightness(1.15) saturate(1.3)",
    "opacity:0.48;filter:contrast(1.6) brightness(1.1) saturate(1.2)"
)

# ─────────────────────────────────────────────────────────────────────────────
# 2. INJECT CSS patch block before </style> to fix z-index stacking + readability
# ─────────────────────────────────────────────────────────────────────────────
CSS_PATCH = """
    /* ══════════ VISIBILITY PATCH ══════════ */
    /* Neural mesh stays fixed behind all content */
    #neural-bg { z-index: 0 !important; }

    /* All page sections get isolation + opaque background so text is crisp */
    #why, #incidents, #features, #vision, #pricing, footer {
      position: relative;
      z-index: 1;
      isolation: isolate;
    }
    #why { background: rgba(8,12,16,0.97) !important; }
    #incidents { background: rgba(4,6,8,0.98) !important; }
    #features { background: rgba(8,12,16,0.97) !important; }
    #vision { background: rgba(4,6,8,0.96) !important; }
    #pricing { background: rgba(8,12,16,0.97) !important; }
    footer { background: rgba(4,6,8,0.98) !important; }

    /* Paper/cream sections (protocols, buyers) stay opaque white by nature */
    #protocols, #buyers { position: relative; z-index: 1; isolation: isolate; }

    /* Hero: gradient vignette so H1 text pops over the neural mesh */
    #hero::before {
      content: '';
      position: absolute;
      inset: 0;
      z-index: 1;
      background: radial-gradient(ellipse 80% 70% at 30% 50%,
        rgba(4,6,8,0.72) 0%, rgba(4,6,8,0.0) 100%);
      pointer-events: none;
    }
    .hero-content { position: relative; z-index: 3; }
    .hero-grid { z-index: 2; }
    .hero-ticker-wrap { position: relative; z-index: 3; }

    /* Boost body text brightness everywhere for contrast */
    .wc-body, .td-desc, .fc-body, .pc-desc, .pc-when, .vision-body, .why-lead {
      color: rgba(221,234,245,0.62) !important;
    }
    .wc-title { color: var(--t1) !important; }
    .t2-text { color: rgba(221,234,245,0.52) !important; }

    /* ══════════ UPGRADED OBSERVATORY ══════════ */
    #obs-section {
      background: rgba(4,6,8,0.98);
      position: relative;
      z-index: 1;
      border-top: 1px solid var(--rim);
      border-bottom: 1px solid var(--rim);
    }
    #obs-header-bar {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      padding: 72px 48px 0;
      flex-wrap: wrap;
      gap: 24px;
    }
    .obs-head-left {}
    .obs-head-right { display: flex; gap: 12px; align-items: center; padding-bottom: 4px; }

    #obs-canvas-wrap {
      position: relative;
      width: 100%;
      height: 75vh;
      min-height: 560px;
      margin-top: 32px;
    }
    #obs-canvas {
      display: block;
      width: 100%;
      height: 100%;
      cursor: crosshair;
    }

    /* Upgraded HUD panel */
    #obs-hud {
      position: absolute;
      top: 20px;
      left: 20px;
      width: 300px;
      background: rgba(4,6,8,0.96);
      border: 1px solid rgba(0,229,255,0.4);
      backdrop-filter: blur(20px);
      z-index: 10;
      overflow: hidden;
    }
    .hud-title-bar {
      background: rgba(0,229,255,0.08);
      border-bottom: 1px solid rgba(0,229,255,0.2);
      padding: 10px 14px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .hud-dot { width: 6px; height: 6px; border-radius: 50%; }
    .hud-dot-g { background: var(--saf); }
    .hud-dot-y { background: var(--warn); }
    .hud-dot-r { background: var(--red); }
    .hud-brand {
      font-family: 'Unbounded', sans-serif;
      font-size: 8px;
      letter-spacing: 3px;
      color: var(--vis);
      margin-left: 4px;
    }
    .hud-body { padding: 14px; }
    .hud-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 5px 0;
      border-bottom: 1px solid rgba(255,255,255,0.04);
      font-size: 9px;
      letter-spacing: 1px;
      color: var(--t2);
    }
    .hud-row:last-child { border-bottom: none; }
    .hud-val {
      font-family: 'Unbounded', sans-serif;
      font-weight: 700;
      font-size: 11px;
      color: var(--vis);
    }
    .hud-val.warn { color: var(--warn); }
    .hud-val.crit { color: var(--red); }
    .hud-val.safe { color: var(--saf); }
    #obs-status-bar {
      background: rgba(255,31,61,0.12);
      border-top: 1px solid rgba(255,31,61,0.3);
      padding: 8px 12px;
      font-size: 9px;
      color: #ff8899;
      letter-spacing: 0.5px;
      line-height: 1.5;
      transition: all 0.3s;
      font-family: 'Fira Code', monospace;
      min-height: 36px;
    }
    #obs-status-bar.nominal {
      background: rgba(0,255,136,0.07);
      border-top-color: rgba(0,255,136,0.3);
      color: var(--saf);
    }
    #obs-status-bar.warning {
      background: rgba(255,149,0,0.1);
      border-top-color: rgba(255,149,0,0.4);
      color: var(--warn);
    }

    /* Mode speed slider */
    #obs-speed-wrap {
      position: absolute;
      top: 20px;
      right: 20px;
      z-index: 10;
      background: rgba(4,6,8,0.94);
      border: 1px solid rgba(0,229,255,0.25);
      padding: 12px 16px;
      width: 180px;
    }
    .speed-label {
      font-size: 8px;
      letter-spacing: 2px;
      color: var(--t2);
      text-transform: uppercase;
      margin-bottom: 8px;
    }
    #obs-speed { width: 100%; accent-color: var(--vis); cursor: pointer; }
    .speed-desc {
      font-size: 8px;
      color: var(--t2);
      margin-top: 6px;
      letter-spacing: 0.5px;
    }

    /* Controls bottom bar */
    #obs-controls {
      position: absolute;
      bottom: 20px;
      left: 50%;
      transform: translateX(-50%);
      display: flex;
      gap: 8px;
      z-index: 10;
      flex-wrap: wrap;
      justify-content: center;
      align-items: center;
    }
    .obs-btn {
      font-family: 'Unbounded', sans-serif;
      font-size: 8px;
      font-weight: 700;
      letter-spacing: 2px;
      text-transform: uppercase;
      background: rgba(4,6,8,0.94);
      border: 1px solid rgba(0,229,255,0.35);
      color: var(--vis);
      padding: 10px 16px;
      cursor: pointer;
      transition: all .15s;
    }
    .obs-btn:hover { background: var(--vis); color: var(--black); }
    .obs-btn.active { background:rgba(0,229,255,0.18); border-color: var(--vis); }
    .obs-btn.danger { color: var(--red); border-color: rgba(255,31,61,0.4); }
    .obs-btn.danger:hover { background: var(--red); color: #fff; border-color: var(--red); }
    .obs-btn.safe { color: var(--saf); border-color: rgba(0,255,136,0.4); }
    .obs-btn.safe:hover { background: var(--saf); color: var(--black); border-color: var(--saf); }
    .obs-btn.warn-btn { color: var(--warn); border-color: rgba(255,149,0,0.4); }
    .obs-btn.warn-btn:hover { background: var(--warn); color: var(--black); }

    /* Legend strip */
    #obs-legend {
      position: absolute;
      bottom: 62px;
      right: 20px;
      z-index: 10;
      background: rgba(4,6,8,0.9);
      border: 1px solid var(--rim);
      padding: 10px 14px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .leg-row {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 8px;
      color: var(--t2);
      letter-spacing: 1px;
    }
    .leg-dot { width: 8px; height: 8px; border-radius: 1px; }
"""

src = src.replace('  </style>', CSS_PATCH + '\n  </style>', 1)

# ─────────────────────────────────────────────────────────────────────────────
# 3. REPLACE the Observatory section HTML with the upgraded version
# ─────────────────────────────────────────────────────────────────────────────
OLD_OBS_PATTERN = re.compile(
    r'<section[^>]*id=["\']observatory["\'][^>]*>.*?</section>',
    re.DOTALL
)

NEW_OBS = r"""<section id="obs-section">
  <div id="obs-header-bar">
    <div class="obs-head-left">
      <div class="sec-tag">Live Simulation — GTC 2026 Vera Rubin Tensor Mesh</div>
      <h2 style="font-family:'Unbounded',sans-serif;font-weight:900;font-size:clamp(32px,5vw,64px);letter-spacing:-2px;line-height:.92;margin-bottom:10px;">
        AGENT FLOW<br><span style="color:var(--vis)">OBSERVATORY</span>
      </h2>
      <p style="font-family:'Cormorant Garamond',serif;font-style:italic;font-size:17px;color:rgba(221,234,245,.45);max-width:540px;line-height:1.7">
        Deploy agents. Define safe zones. Inject fault events. Watch VeilPiercer's Vera Rubin tensor mesh detect and contain anomalies in real time.
      </p>
    </div>
    <div class="obs-head-right">
      <span style="font-size:8px;letter-spacing:2px;color:var(--t2);text-transform:uppercase">Mode:</span>
      <span id="obs-mode-label" style="font-family:'Unbounded',sans-serif;font-size:9px;font-weight:700;color:var(--vis);letter-spacing:2px">SPAWN</span>
    </div>
  </div>

  <div id="obs-canvas-wrap">
    <canvas id="obs-canvas"></canvas>

    <!-- HUD Panel -->
    <div id="obs-hud">
      <div class="hud-title-bar">
        <div class="hud-dot hud-dot-r" id="hud-dot-r"></div>
        <div class="hud-dot hud-dot-y" id="hud-dot-y"></div>
        <div class="hud-dot hud-dot-g" id="hud-dot-g"></div>
        <span class="hud-brand">VEILPIERCER &#183; VERA RUBIN</span>
      </div>
      <div class="hud-body">
        <div class="hud-row">
          THROUGHPUT / SEC
          <span class="hud-val" id="obs-cap">0</span>
        </div>
        <div class="hud-row">
          SURVIVABILITY
          <span class="hud-val safe" id="obs-surv">100%</span>
        </div>
        <div class="hud-row">
          ACTIVE AGENTS
          <span class="hud-val" id="obs-count">0</span>
        </div>
        <div class="hud-row">
          TENSOR CORES
          <span class="hud-val" id="obs-tensors">0</span>
        </div>
        <div class="hud-row">
          FAULT ZONES
          <span class="hud-val crit" id="obs-faults">0</span>
        </div>
        <div class="hud-row">
          FRAME
          <span class="hud-val" id="obs-frame">0</span>
        </div>
      </div>
      <div id="obs-status-bar">VEILPIERCER: Awaiting Slime Flow deployment.</div>
    </div>

    <!-- Speed Control -->
    <div id="obs-speed-wrap">
      <div class="speed-label">Agent Speed</div>
      <input type="range" id="obs-speed" min="1" max="8" value="3" step="0.5"/>
      <div class="speed-desc" id="obs-speed-label">Normal (3.0 px/f)</div>
    </div>

    <!-- Legend -->
    <div id="obs-legend">
      <div class="leg-row"><div class="leg-dot" style="background:rgb(0,229,255)"></div> Mesh agent</div>
      <div class="leg-row"><div class="leg-dot" style="background:rgb(191,0,255);transform:rotate(45deg)"></div> Tensor Core</div>
      <div class="leg-row"><div class="leg-dot" style="background:rgba(0,229,255,.3);border:1px solid rgba(0,229,255,.6)"></div> Spawn point</div>
      <div class="leg-row"><div class="leg-dot" style="background:rgba(0,255,136,.3);border:1px solid rgba(0,255,136,.7)"></div> Safe zone</div>
      <div class="leg-row"><div class="leg-dot" style="background:#ff2200;border-radius:50%"></div> Fault zone</div>
    </div>

    <!-- Controls -->
    <div id="obs-controls">
      <button class="obs-btn active" id="btn-spawn" onclick="setObs('source',this)">&#9654; SPAWN AGENTS</button>
      <button class="obs-btn safe" id="btn-sink" onclick="setObs('sink',this)">&#9679; SAFE ZONE</button>
      <button class="obs-btn danger" id="btn-fire" onclick="setObs('fire',this)">&#9889; FAULT INJECT</button>
      <button class="obs-btn warn-btn" id="btn-wall" onclick="setObs('wall',this)">&#9632; DRAW WALL</button>
      <button class="obs-btn" id="btn-reset" onclick="obsReset()" style="color:rgba(221,234,245,.35);border-color:rgba(221,234,245,.15)">&#8634; RESET</button>
    </div>
  </div>
</section>"""

match = OLD_OBS_PATTERN.search(src)
if match:
    src = src[:match.start()] + NEW_OBS + src[match.end():]
else:
    print("WARNING: observatory section not found by regex, trying ID fallback")

# ─────────────────────────────────────────────────────────────────────────────
# 4. REPLACE the old Observatory JS with the upgraded version
# ─────────────────────────────────────────────────────────────────────────────
# Remove any existing obs JS block
src = re.sub(
    r'// ── AGENT FLOW OBSERVATORY.*?}\)\(\);',
    '',
    src,
    flags=re.DOTALL
)
# Also remove old variable-based obs blocks
src = re.sub(
    r'\(function\(\)\{var canvas=document\.getElementById\(\'obs-canvas\'\).*?}\)\(\);',
    '',
    src,
    flags=re.DOTALL
)

NEW_OBS_JS = r"""
// ── UPGRADED AGENT FLOW OBSERVATORY (VeilPiercer v3) ─────────────────────────
function setObs(mode, btn) {
  window.__obsMode = mode;
  document.querySelectorAll('.obs-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  var lbl = document.getElementById('obs-mode-label');
  if (lbl) {
    var names = { source: 'SPAWN', sink: 'SAFE ZONE', fire: 'FAULT', wall: 'WALL' };
    lbl.textContent = names[mode] || mode.toUpperCase();
  }
}

function obsReset() {
  window.__obsReset && window.__obsReset();
}

(function () {
  var canvas = document.getElementById('obs-canvas');
  if (!canvas) return;
  var ctx = canvas.getContext('2d', { willReadFrequently: true });
  var w, h;
  var agents = [], spawnPoint = null, exitPoint = null;
  var frame = 0, totalSaved = 0, totalLost = 0, faultZones = 0;
  window.__obsMode = 'source';

  function obsInit() {
    var wrap = document.getElementById('obs-canvas-wrap');
    w = canvas.width = wrap.clientWidth;
    h = canvas.height = wrap.clientHeight;
    ctx.fillStyle = '#040608';
    ctx.fillRect(0, 0, w, h);
  }

  window.__obsReset = function () {
    agents = []; spawnPoint = null; exitPoint = null;
    frame = 0; totalSaved = 0; totalLost = 0; faultZones = 0;
    obsInit();
    set('obs-cap', '0'); set('obs-surv', '100%');
    set('obs-count', '0'); set('obs-tensors', '0');
    set('obs-frame', '0'); set('obs-faults', '0');
    var sb = document.getElementById('obs-status-bar');
    if (sb) { sb.textContent = 'VEILPIERCER: Awaiting Slime Flow deployment.'; sb.className = ''; }
    document.querySelectorAll('.obs-btn').forEach(b => b.classList.remove('active'));
    var s = document.getElementById('btn-spawn');
    if (s) { s.classList.add('active'); window.__obsMode = 'source'; }
    var ml = document.getElementById('obs-mode-label');
    if (ml) ml.textContent = 'SPAWN';
  };

  function set(id, val) {
    var el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  function look(ag, ang) {
    var px = ag.x + Math.cos(ang) * 22;
    var py = ag.y + Math.sin(ang) * 22;
    if (px < 0 || px > w || py < 0 || py > h) return -1;
    var d = ctx.getImageData(px | 0, py | 0, 1, 1).data;
    if (d[0] > 180 && d[1] < 80) return -2;   // fault zone (red)
    if (d[0] > 140 && d[1] > 140 && d[2] > 140) return -1; // wall (white)
    return d[1] + d[2]; // higher = more trail (good)
  }

  function getSpeed() {
    var sl = document.getElementById('obs-speed');
    return sl ? parseFloat(sl.value) : 3;
  }

  // Speed slider label update
  var speedSlider = document.getElementById('obs-speed');
  if (speedSlider) {
    speedSlider.addEventListener('input', function () {
      var lbl = document.getElementById('obs-speed-label');
      if (lbl) lbl.textContent = 'Speed: ' + parseFloat(this.value).toFixed(1) + ' px/f';
    });
  }

  function loop() {
    // trail decay
    ctx.fillStyle = 'rgba(4,6,8,0.09)';
    ctx.fillRect(0, 0, w, h);

    var spd = getSpeed();
    var mode = window.__obsMode || 'source';

    // spawn agents
    if (spawnPoint && agents.length < 4500) {
      var burst = Math.min(8, 4500 - agents.length);
      for (var i = 0; i < burst; i++) {
        agents.push({
          x: spawnPoint.x + (Math.random() - 0.5) * 20,
          y: spawnPoint.y + (Math.random() - 0.5) * 20,
          a: Math.random() * Math.PI * 2,
          hp: 100,
          isTensor: Math.random() > 0.88,
          age: 0
        });
      }
    }

    var saved = 0, lost = 0, tensorCount = 0;

    for (var i = agents.length - 1; i >= 0; i--) {
      var ag = agents[i];
      ag.age++;
      var vC = look(ag, ag.a);
      var vL = look(ag, ag.a - 0.45);
      var vR = look(ag, ag.a + 0.45);

      if (vC === -1 || vC === -2) {
        ag.a += Math.PI * 0.5 + (Math.random() - 0.5) * 0.4;
        if (vC === -2) ag.hp -= 5;
      } else {
        var wobble = (Math.random() - 0.5) * 0.08;
        if (vL > vR) ag.a -= 0.14 + wobble;
        else if (vR > vL) ag.a += 0.14 + wobble;
        else ag.a += wobble;
      }

      // Exit-point attraction
      if (exitPoint) {
        ag.a += Math.atan2(exitPoint.y - ag.y, exitPoint.x - ag.x) * 0.04;
      }

      ag.x += Math.cos(ag.a) * spd;
      ag.y += Math.sin(ag.a) * spd;

      // Despawn at boundary
      if (ag.x < 0 || ag.x > w || ag.y < 0 || ag.y > h || ag.hp <= 0) {
        agents.splice(i, 1); lost++; totalLost++; continue;
      }

      var hp = ag.hp / 100;
      if (ag.isTensor) {
        tensorCount++;
        // Purple diamond — Vera Rubin Tensor Core
        ctx.fillStyle = 'rgba(191,0,255,' + (0.45 + hp * 0.55) + ')';
        ctx.shadowBlur = 5; ctx.shadowColor = '#bf00ff';
        var s = 2.0 + (1 - hp) * 3;
        ctx.beginPath();
        ctx.moveTo(ag.x, ag.y - s); ctx.lineTo(ag.x + s, ag.y);
        ctx.lineTo(ag.x, ag.y + s); ctx.lineTo(ag.x - s, ag.y);
        ctx.closePath(); ctx.fill();
        ctx.shadowBlur = 0;
      } else {
        // Cyan mesh agent with health-based color shift
        var r = Math.round((1 - hp) * 200);
        var g = Math.round(hp * 229);
        var b = Math.round(hp * 255);
        ctx.fillStyle = 'rgba(' + r + ',' + g + ',' + b + ',0.72)';
        ctx.fillRect(ag.x - 1, ag.y - 1, 2.2, 2.2);
      }

      // Exit detection
      if (exitPoint && Math.hypot(exitPoint.x - ag.x, exitPoint.y - ag.y) < 26) {
        agents.splice(i, 1); saved++; totalSaved++; continue;
      }
    }

    // Draw spawn ring
    if (spawnPoint) {
      ctx.strokeStyle = 'rgba(0,229,255,0.5)'; ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(spawnPoint.x, spawnPoint.y, 16 + Math.sin(frame * 0.09) * 5, 0, Math.PI * 2);
      ctx.stroke();
      // Inner pulse
      ctx.strokeStyle = 'rgba(0,229,255,0.2)';
      ctx.beginPath();
      ctx.arc(spawnPoint.x, spawnPoint.y, 28 + Math.sin(frame * 0.07) * 8, 0, Math.PI * 2);
      ctx.stroke();
    }

    // Draw safe zone
    if (exitPoint) {
      ctx.strokeStyle = 'rgba(0,255,136,0.7)'; ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(exitPoint.x, exitPoint.y, 20 + Math.sin(frame * 0.06) * 6, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = 'rgba(0,255,136,0.1)';
      ctx.beginPath();
      ctx.arc(exitPoint.x, exitPoint.y, 26, 0, Math.PI * 2);
      ctx.fill();
    }

    // Update HUD every 45 frames
    if (frame % 45 === 0) {
      var total = totalSaved + totalLost || 1;
      var rate = Math.max(0, Math.round((totalSaved / total) * 100));
      set('obs-cap', saved);
      var survEl = document.getElementById('obs-surv');
      if (survEl) {
        survEl.textContent = rate + '%';
        survEl.className = 'hud-val ' +
          (rate >= 70 ? 'safe' : rate >= 40 ? 'warn' : 'crit');
      }
      set('obs-count', agents.length);
      set('obs-tensors', tensorCount);
      set('obs-frame', frame);

      var sb = document.getElementById('obs-status-bar');
      if (sb) {
        if (!spawnPoint) {
          sb.textContent = 'AWAITING DEPLOYMENT — Click SPAWN AGENTS then click the canvas to place.';
          sb.className = '';
        } else if (rate < 40) {
          sb.textContent = 'CRITICAL: ' + (100 - rate) + '% agent loss. Fault zone active. Recommend LOCKDOWN.';
          sb.className = 'critical';
        } else if (rate < 70) {
          sb.textContent = 'WARNING: Survivability at ' + rate + '%. Tensor array anomaly. Reroute recommended.';
          sb.className = 'warning';
        } else {
          sb.textContent = 'NOMINAL: ' + rate + '% success rate. ' + tensorCount + ' Tensor Cores active. Vera Rubin tolerance held.';
          sb.className = 'nominal';
        }
      }
    }

    frame++;
    requestAnimationFrame(loop);
  }

  // Canvas interaction
  canvas.addEventListener('mousedown', function (e) {
    var rect = canvas.getBoundingClientRect();
    var cx = (e.clientX - rect.left) * (w / rect.width);
    var cy = (e.clientY - rect.top) * (h / rect.height);
    var mode = window.__obsMode || 'source';

    if (mode === 'source') {
      spawnPoint = { x: cx, y: cy };
    } else if (mode === 'sink') {
      exitPoint = { x: cx, y: cy };
    } else if (mode === 'fire') {
      faultZones++;
      set('obs-faults', faultZones);
      // Draw fault zone with glow
      ctx.shadowBlur = 20; ctx.shadowColor = '#ff2200';
      ctx.fillStyle = '#ff2200';
      ctx.beginPath(); ctx.arc(cx, cy, 28, 0, Math.PI * 2); ctx.fill();
      ctx.shadowBlur = 0;
      ctx.fillStyle = 'rgba(255,60,0,0.22)';
      ctx.beginPath(); ctx.arc(cx, cy, 52, 0, Math.PI * 2); ctx.fill();
    } else if (mode === 'wall') {
      // Draw a white wall segment
      ctx.strokeStyle = 'rgba(200,220,240,0.8)';
      ctx.lineWidth = 14;
      ctx.lineCap = 'round';
      ctx.beginPath(); ctx.arc(cx, cy, 1, 0, Math.PI * 2); ctx.stroke();
    }
  });

  // Wall drawing on drag
  var drawing = false, lastX = 0, lastY = 0;
  canvas.addEventListener('mousedown', function (e) {
    if ((window.__obsMode || 'source') !== 'wall') return;
    drawing = true;
    var rect = canvas.getBoundingClientRect();
    lastX = (e.clientX - rect.left) * (w / rect.width);
    lastY = (e.clientY - rect.top) * (h / rect.height);
  });
  canvas.addEventListener('mousemove', function (e) {
    if (!drawing || (window.__obsMode || 'source') !== 'wall') return;
    var rect = canvas.getBoundingClientRect();
    var cx = (e.clientX - rect.left) * (w / rect.width);
    var cy = (e.clientY - rect.top) * (h / rect.height);
    ctx.strokeStyle = 'rgba(200,220,240,0.85)';
    ctx.lineWidth = 12; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(lastX, lastY); ctx.lineTo(cx, cy); ctx.stroke();
    lastX = cx; lastY = cy;
  });
  canvas.addEventListener('mouseup', function () { drawing = false; });

  window.addEventListener('resize', obsInit);
  setTimeout(function () { obsInit(); loop(); }, 200);
})();
"""

# Inject before last </script> before </body>
src = src.replace('</body>', '\n<script>\n' + NEW_OBS_JS + '\n</script>\n</body>', 1)

# ─────────────────────────────────────────────────────────────────────────────
# 5. Write and deploy
# ─────────────────────────────────────────────────────────────────────────────
out = r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html'
open(out, 'w', encoding='utf-8').write(src)
shutil.copy(out, r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\public\vp.html')
print('DONE — lines:', src.count('\n'), '  bytes:', len(src))
