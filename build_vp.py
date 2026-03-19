"""
build_vp.py — Clean full rebuild of vp.html
Starts from veilpiercer-pitch-PUBLIC.html and injects:
  - z-index:-1 neural WebGL mesh (Three.js, 120 nodes, cap 30fps)
  - Faint 64px grid overlay
  - Opaque section backgrounds (text always readable)
  - Dual-canvas Observatory (wall canvas persistent, pheromone canvas decays)
  - Physarum 3-sensor swarm physics
  - Single $197 pricing block
  - Bottom news crawl bar
  - Correct Stripe link throughout
"""
import re, shutil

# ── Source ────────────────────────────────────────────────────────────────────
src = open(r'c:\Users\fyou1\Downloads\veilpiercer-pitch-PUBLIC.html', encoding='utf-8').read()

# ── 1. Fix all prices and Stripe links ───────────────────────────────────────
src = re.sub(r'\$47\b', '$197', src)
src = re.sub(r'\$97\b', '$197', src)
src = re.sub(r'https://buy\.stripe\.com/[^\s"\'<>]+',
             'https://buy.stripe.com/00w5kv0Q1dcVgCkgHSbsc03', src)

# ── 2. Strip localhost/nexus beacon calls (PUBLIC version) ────────────────────
src = re.sub(r'const IS_PUBLIC\s*=\s*false', 'const IS_PUBLIC = true', src)
src = re.sub(r'fetch\([^)]*localhost[^)]*\)\.catch[^;]*;', '', src)
src = re.sub(r'NX\.[a-zA-Z]+\([^)]*\);?', '', src)
# Remove the nexus status bar injection
src = re.sub(r'if\s*\(\s*!IS_PUBLIC\s*\).*?(?=\n\s*//|\n\s*const|\n\s*function|\n\s*window)',
             '', src, flags=re.DOTALL)

# ── 3. Remove LAUNCH50 coupon badges ─────────────────────────────────────────
src = re.sub(r'<[^>]*class="p-badge"[^>]*>.*?</[^>]+>', '', src, flags=re.DOTALL)
src = re.sub(r'LAUNCH50[^<"]*', '', src, flags=re.IGNORECASE)

# ── 4. Inject CSS additions before </style> ──────────────────────────────────
EXTRA_CSS = r"""
    /* ══════ NEURAL MESH + GRID ══════ */
    #neural-bg {
      position: fixed !important;
      top: 0; left: 0;
      width: 100vw; height: 100vh;
      z-index: -1 !important;
      pointer-events: none !important;
      opacity: 0.55;
      filter: contrast(1.65) brightness(1.1) saturate(1.25);
    }
    /* Faint structural grid — helps eye track nodes, reduces perceived choppiness */
    body::before {
      content: '';
      position: fixed;
      inset: 0;
      z-index: -1;
      pointer-events: none;
      background-image:
        linear-gradient(rgba(0,229,255,0.022) 1px, transparent 1px),
        linear-gradient(90deg, rgba(0,229,255,0.022) 1px, transparent 1px);
      background-size: 64px 64px;
    }

    /* ══════ SECTION BACKGROUNDS (always readable) ══════ */
    #why, #incidents, #features, #vision, #pricing, footer,
    #obs-section, .wave-strip {
      position: relative;
    }
    #why       { background: rgba(8,12,16,0.96)  !important; }
    #incidents { background: rgba(4,6,8,0.97)    !important; }
    #features  { background: rgba(8,12,16,0.96)  !important; }
    #vision    { background: rgba(4,6,8,0.95)    !important; }
    #pricing   { background: rgba(8,12,16,0.96)  !important; }
    footer     { background: rgba(4,6,8,0.97)    !important; }
    #obs-section { background: rgba(4,6,8,0.97)  !important; }
    .wave-strip  { background: rgba(8,12,16,0.98) !important; }

    /* Hero vignette so h1 pops */
    #hero::before {
      content: '';
      position: absolute; inset: 0;
      z-index: 1; pointer-events: none;
      background: radial-gradient(ellipse 80% 100% at 22% 50%,
        rgba(4,6,8,.80) 0%, transparent 100%);
    }
    .hero-content     { position: relative; z-index: 3; }
    .hero-grid        { z-index: 2; }
    .hero-ticker-wrap { position: relative; z-index: 3; }
    .h1-dim           { color: rgba(221,234,245,0.20) !important; }

    /* Body text contrast boost */
    .wc-body, .td-desc, .fc-body, .pc-desc, .pc-when, .vision-body {
      color: rgba(221,234,245,0.58) !important;
    }

    /* ══════ OBSERVATORY ══════ */
    #obs-section { border-top:1px solid var(--rim); border-bottom:1px solid var(--rim); }
    #obs-header-bar {
      display:flex; align-items:flex-end; justify-content:space-between;
      padding:72px 48px 0; flex-wrap:wrap; gap:24px;
    }
    #obs-canvas-wrap {
      position:relative; width:100%; height:72vh; min-height:520px; margin-top:32px;
    }
    /* Wall canvas: bottom layer, pointer-events:none */
    #obs-wall-canvas {
      position:absolute; top:0; left:0; width:100%; height:100%;
      z-index:1; pointer-events:none; cursor:crosshair;
    }
    /* Pheromone canvas: top layer, captures all mouse events */
    #obs-canvas {
      position:absolute; top:0; left:0; width:100%; height:100%;
      z-index:2; cursor:crosshair;
    }
    #obs-hud {
      position:absolute; top:20px; left:20px; width:286px;
      background:rgba(4,6,8,.96); border:1px solid rgba(0,229,255,.4);
      backdrop-filter:blur(20px); z-index:10; overflow:hidden;
    }
    .hud-title-bar {
      background:rgba(0,229,255,.08); border-bottom:1px solid rgba(0,229,255,.2);
      padding:10px 14px; display:flex; align-items:center; gap:8px;
    }
    .hud-dot{width:6px;height:6px;border-radius:50%}
    .hud-dot-r{background:var(--red)}.hud-dot-y{background:var(--warn)}.hud-dot-g{background:var(--saf)}
    .hud-brand{font-family:'Unbounded',sans-serif;font-size:8px;letter-spacing:3px;color:var(--vis);margin-left:4px}
    .hud-body{padding:14px}
    .hud-row{display:flex;justify-content:space-between;align-items:center;padding:5px 0;
      border-bottom:1px solid rgba(255,255,255,.04);font-size:9px;letter-spacing:1px;color:var(--t2)}
    .hud-row:last-child{border-bottom:none}
    .hud-val{font-family:'Unbounded',sans-serif;font-weight:700;font-size:11px;color:var(--vis)}
    .hud-val.warn{color:var(--warn)}.hud-val.crit{color:var(--red)}.hud-val.safe{color:var(--saf)}
    #obs-status-bar{
      background:rgba(255,31,61,.1); border-top:1px solid rgba(255,31,61,.3);
      padding:8px 12px; font-size:9px; color:#ff8899; letter-spacing:.5px;
      line-height:1.5; font-family:'Fira Code',monospace; min-height:36px; transition:all .3s;
    }
    #obs-status-bar.nominal{background:rgba(0,255,136,.07);border-top-color:rgba(0,255,136,.3);color:var(--saf)}
    #obs-status-bar.warning{background:rgba(255,149,0,.1);border-top-color:rgba(255,149,0,.4);color:var(--warn)}
    #obs-speed-wrap{
      position:absolute; top:20px; right:20px; z-index:10;
      background:rgba(4,6,8,.94); border:1px solid rgba(0,229,255,.25);
      padding:12px 16px; width:180px;
    }
    .speed-label{font-size:8px;letter-spacing:2px;color:var(--t2);text-transform:uppercase;margin-bottom:8px}
    #obs-speed{width:100%;accent-color:var(--vis);cursor:pointer}
    .speed-desc{font-size:8px;color:var(--t2);margin-top:6px;letter-spacing:.5px}
    #obs-controls{
      position:absolute; bottom:20px; left:50%; transform:translateX(-50%);
      display:flex; gap:8px; z-index:10; flex-wrap:wrap; justify-content:center;
    }
    .obs-btn{
      font-family:'Unbounded',sans-serif; font-size:8px; font-weight:700;
      letter-spacing:2px; text-transform:uppercase;
      background:rgba(4,6,8,.94); border:1px solid rgba(0,229,255,.35);
      color:var(--vis); padding:10px 16px; cursor:pointer; transition:all .15s;
    }
    .obs-btn:hover,.obs-btn.active{background:var(--vis);color:var(--black)}
    .obs-btn.danger{color:var(--red);border-color:rgba(255,31,61,.4)}
    .obs-btn.danger:hover{background:var(--red);color:#fff;border-color:var(--red)}
    .obs-btn.safe{color:var(--saf);border-color:rgba(0,255,136,.4)}
    .obs-btn.safe:hover{background:var(--saf);color:var(--black)}
    .obs-btn.warn-btn{color:var(--warn);border-color:rgba(255,149,0,.4)}
    .obs-btn.warn-btn:hover{background:var(--warn);color:var(--black)}
    #obs-legend{
      position:absolute; bottom:62px; right:20px; z-index:10;
      background:rgba(4,6,8,.9); border:1px solid var(--rim);
      padding:10px 14px; display:flex; flex-direction:column; gap:6px;
    }
    .leg-row{display:flex;align-items:center;gap:8px;font-size:8px;color:var(--t2);letter-spacing:1px}
    .leg-dot{width:8px;height:8px;border-radius:1px;flex-shrink:0}

    /* ══════ NEWS CRAWL ══════ */
    #news-crawl{
      position:fixed; bottom:0; left:0; right:0; z-index:9996;
      height:38px; background:rgba(0,229,255,1);
      display:flex; align-items:center; overflow:hidden;
      border-top:2px solid rgba(0,0,0,.18);
      box-shadow:0 -4px 24px rgba(0,229,255,.35);
    }
    #news-crawl .crawl-label{
      flex-shrink:0; background:#020408; color:var(--vis);
      font-family:'Unbounded',sans-serif; font-weight:900;
      font-size:9px; letter-spacing:3px;
      padding:0 18px; height:100%; display:flex; align-items:center;
      border-right:1px solid rgba(0,229,255,.3); white-space:nowrap;
    }
    #news-crawl .crawl-track{flex:1;overflow:hidden;height:100%;display:flex;align-items:center}
    #news-crawl .crawl-inner{
      display:flex; white-space:nowrap;
      animation:newscrawl 30s linear infinite;
      font-family:'Unbounded',sans-serif; font-weight:700;
      font-size:10px; letter-spacing:2px; color:#020408; text-transform:uppercase;
    }
    #news-crawl .crawl-inner span{margin:0 52px;flex-shrink:0}
    #news-crawl .crawl-inner .sep{color:rgba(0,0,0,.3);margin:0 10px}
    @keyframes newscrawl{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}
    body{padding-bottom:38px}

    /* ══════ REVEAL ══════ */
    .reveal{opacity:0;transform:translateY(16px);transition:opacity .6s ease,transform .6s ease}
    .reveal.in{opacity:1!important;transform:translateY(0)!important}
"""
src = src.replace('  </style>', EXTRA_CSS + '\n  </style>', 1)

# ── 5. Inject news crawl + custom cursor wrappers right after <body> ──────────
BODY_INJECT = r"""
<!-- Custom cursor -->
<div id="cur"></div>
<div id="cur-r"></div>

<!-- Bottom news crawl -->
<div id="news-crawl">
  <div class="crawl-label">&#9654;&nbsp;BREAKING</div>
  <div class="crawl-track">
    <div class="crawl-inner">
      <span>THIS WEEK ONLY &mdash; VEILPIERCER&rsquo;S LAUNCH PRICE IS 13.333% CHEAPER THAN IT WILL BE NEXT WEEK</span>
      <span class="sep">&#9632;</span>
      <span>VEILPIERCER LAUNCHES THIS WEEK AT $197 &mdash; PRICE INCREASES PERMANENTLY AFTER 7 DAYS</span>
      <span class="sep">&#9632;</span>
      <span>THIS WEEK ONLY &mdash; VEILPIERCER&rsquo;S LAUNCH PRICE IS 13.333% CHEAPER THAN IT WILL BE NEXT WEEK</span>
      <span class="sep">&#9632;</span>
      <span>VEILPIERCER LAUNCHES THIS WEEK AT $197 &mdash; PRICE INCREASES PERMANENTLY AFTER 7 DAYS</span>
      <span class="sep">&#9632;</span>
    </div>
  </div>
</div>

<!-- Three.js neural mesh canvas (z-index:-1) -->
<canvas id="neural-bg"></canvas>
"""
src = src.replace('<body>', '<body>\n' + BODY_INJECT, 1)

# ── 6. Replace the observatory section with dual-canvas version ───────────────
OBS_SECTION = r"""
<section id="obs-section" class="sec" style="padding-top:80px;padding-bottom:0">
  <div id="obs-header-bar">
    <div>
      <div class="sec-tag">Live Simulation &mdash; GTC 2026 Vera Rubin Tensor Mesh</div>
      <h2 style="font-family:'Unbounded',sans-serif;font-weight:900;font-size:clamp(32px,5vw,64px);letter-spacing:-2px;line-height:.92;margin-bottom:10px">
        AGENT FLOW<br><span style="color:var(--vis)">OBSERVATORY</span>
      </h2>
      <p style="font-family:'Cormorant Garamond',serif;font-style:italic;font-size:17px;color:rgba(221,234,245,.45);max-width:520px;line-height:1.7">
        Deploy agents. Draw walls. Define safe zones. Inject fault events. Watch Physarum tensor intelligence navigate in real time.
      </p>
    </div>
    <div style="display:flex;gap:12px;align-items:center;padding-bottom:4px">
      <span style="font-size:8px;letter-spacing:2px;color:var(--t2);text-transform:uppercase">Mode:</span>
      <span id="obs-mode-label" style="font-family:'Unbounded',sans-serif;font-size:9px;font-weight:700;color:var(--vis);letter-spacing:2px">SPAWN</span>
    </div>
  </div>

  <div id="obs-canvas-wrap">
    <!-- Wall canvas: persistent, never erased by pheromone decay -->
    <canvas id="obs-wall-canvas"></canvas>
    <!-- Pheromone canvas: decays each frame, captures mouse events -->
    <canvas id="obs-canvas"></canvas>

    <!-- HUD -->
    <div id="obs-hud">
      <div class="hud-title-bar">
        <div class="hud-dot hud-dot-r"></div>
        <div class="hud-dot hud-dot-y"></div>
        <div class="hud-dot hud-dot-g"></div>
        <span class="hud-brand">VEILPIERCER &middot; VERA RUBIN</span>
      </div>
      <div class="hud-body">
        <div class="hud-row">THROUGHPUT/SEC<span class="hud-val" id="obs-cap">0</span></div>
        <div class="hud-row">SURVIVABILITY<span class="hud-val safe" id="obs-surv">100%</span></div>
        <div class="hud-row">ACTIVE AGENTS<span class="hud-val" id="obs-count">0</span></div>
        <div class="hud-row">TENSOR CORES<span class="hud-val" id="obs-tensors">0</span></div>
        <div class="hud-row">FAULT ZONES<span class="hud-val crit" id="obs-faults">0</span></div>
        <div class="hud-row">FRAME<span class="hud-val" id="obs-frame">0</span></div>
      </div>
      <div id="obs-status-bar">VEILPIERCER: Awaiting Slime Flow deployment.</div>
    </div>

    <!-- Speed -->
    <div id="obs-speed-wrap">
      <div class="speed-label">Agent Speed</div>
      <input type="range" id="obs-speed" min="1" max="8" value="3" step="0.5"/>
      <div class="speed-desc" id="obs-speed-label">Speed: 3.0 px/f</div>
    </div>

    <!-- Legend -->
    <div id="obs-legend">
      <div class="leg-row"><div class="leg-dot" style="background:rgb(0,229,255)"></div>Mesh agent</div>
      <div class="leg-row"><div class="leg-dot" style="background:rgb(191,0,255);transform:rotate(45deg)"></div>Tensor Core</div>
      <div class="leg-row"><div class="leg-dot" style="background:rgba(0,229,255,.3);border:1px solid rgba(0,229,255,.6)"></div>Spawn</div>
      <div class="leg-row"><div class="leg-dot" style="background:rgba(0,255,136,.3);border:1px solid rgba(0,255,136,.7)"></div>Safe zone</div>
      <div class="leg-row"><div class="leg-dot" style="background:#ff2200;border-radius:50%"></div>Fault zone</div>
      <div class="leg-row"><div class="leg-dot" style="background:rgba(200,220,240,.6)"></div>Wall</div>
    </div>

    <!-- Controls -->
    <div id="obs-controls">
      <button class="obs-btn active" id="btn-spawn" onclick="setObs('source',this)">&#9654; SPAWN</button>
      <button class="obs-btn safe"   id="btn-sink"  onclick="setObs('sink',this)">&#9679; SAFE ZONE</button>
      <button class="obs-btn danger" id="btn-fire"  onclick="setObs('fire',this)">&#9889; FAULT</button>
      <button class="obs-btn warn-btn" id="btn-wall" onclick="setObs('wall',this)">&#9632; WALL</button>
      <button class="obs-btn" id="btn-reset" onclick="obsReset()" style="color:rgba(221,234,245,.3);border-color:rgba(221,234,245,.12)">&#8634; RESET</button>
    </div>
  </div>
</section>
"""

# Replace any existing observatory section
obs_re = re.compile(r'<section[^>]*id=["\']observatory["\'][^>]*>.*?</section>', re.DOTALL)
if obs_re.search(src):
    src = obs_re.sub(OBS_SECTION, src, count=1)
else:
    # Inject before the features section
    feat_re = re.compile(r'(<section[^>]*id=["\']features["\'][^>]*>)', re.DOTALL)
    src = feat_re.sub(OBS_SECTION + r'\n\1', src, count=1)

# ── 7. Collapse multi-tier pricing to single $197 block ───────────────────────
PRICE_BLOCK = r"""
<section id="pricing" class="sec">
  <div class="sec-tag">One-Time Access</div>
  <h2 class="price-h"><span class="v">$197</span><br>Yours forever.</h2>
  <p class="price-sub">No seats. No per-agent fees. No subscription. No renewal. Ever.</p>
  <div style="display:grid;grid-template-columns:1fr 1.85fr;gap:1px;background:var(--rim)">
    <div style="background:var(--panel);padding:52px 44px;display:flex;flex-direction:column;justify-content:center">
      <div style="font-size:9px;letter-spacing:3px;text-transform:uppercase;color:var(--vis);margin-bottom:14px">VeilPiercer</div>
      <div style="font-family:'Unbounded',sans-serif;font-weight:900;font-size:22px;margin-bottom:14px">Complete Bundle</div>
      <div style="font-family:'Unbounded',sans-serif;font-weight:900;font-size:80px;letter-spacing:-4px;line-height:1;color:var(--vis);margin-bottom:5px">$197</div>
      <div style="font-size:9px;color:var(--t2);letter-spacing:2px;text-transform:uppercase;margin-bottom:36px">one-time &middot; instant access &middot; yours forever</div>
      <a href="https://buy.stripe.com/00w5kv0Q1dcVgCkgHSbsc03" target="_blank" rel="noopener" class="btn-primary" style="text-align:center;display:block;text-decoration:none">
        Get VeilPiercer &rarr;
      </a>
      <p style="font-size:9px;color:var(--t2);letter-spacing:1px;margin-top:12px;text-align:center">Secure checkout via Stripe &middot; Access emailed instantly</p>
      <div style="margin-top:18px;padding:14px 16px;border:1px solid var(--rim);background:rgba(0,229,255,.022);font-size:9px;color:var(--t2);line-height:1.9">
        &#10003; 7-day no-questions refund<br>
        &#10003; Re-download any time<br>
        &#10003; One payment &mdash; no renewals ever
      </div>
    </div>
    <div style="background:var(--panel);padding:52px 44px">
      <ul style="list-style:none;display:grid;grid-template-columns:1fr 1fr;margin-bottom:36px">
        <li style="font-size:10px;color:rgba(221,234,245,.5);padding:10px 0;border-bottom:1px solid var(--rim);display:flex;gap:8px"><span style="color:var(--vis)">&#8594;</span>Full real-time agent dashboard</li>
        <li style="font-size:10px;color:rgba(221,234,245,.5);padding:10px 0;border-bottom:1px solid var(--rim);display:flex;gap:8px"><span style="color:var(--vis)">&#8594;</span>All 4 control protocols</li>
        <li style="font-size:10px;color:rgba(221,234,245,.5);padding:10px 0;border-bottom:1px solid var(--rim);display:flex;gap:8px"><span style="color:var(--vis)">&#8594;</span>9 tunable live control nodes</li>
        <li style="font-size:10px;color:rgba(221,234,245,.5);padding:10px 0;border-bottom:1px solid var(--rim);display:flex;gap:8px"><span style="color:var(--vis)">&#8594;</span>Vera Rubin neural mesh</li>
        <li style="font-size:10px;color:rgba(221,234,245,.5);padding:10px 0;border-bottom:1px solid var(--rim);display:flex;gap:8px"><span style="color:var(--vis)">&#8594;</span>Natural language commands</li>
        <li style="font-size:10px;color:rgba(221,234,245,.5);padding:10px 0;border-bottom:1px solid var(--rim);display:flex;gap:8px"><span style="color:var(--vis)">&#8594;</span>Physarum Slime Flow Observatory</li>
        <li style="font-size:10px;color:rgba(221,234,245,.5);padding:10px 0;border-bottom:1px solid var(--rim);display:flex;gap:8px"><span style="color:var(--vis)">&#8594;</span>100% offline — zero cloud</li>
        <li style="font-size:10px;color:rgba(221,234,245,.5);padding:10px 0;border-bottom:1px solid var(--rim);display:flex;gap:8px"><span style="color:var(--vis)">&#8594;</span>Full source code included</li>
        <li style="font-size:10px;color:rgba(221,234,245,.5);padding:10px 0;border-bottom:1px solid var(--rim);display:flex;gap:8px"><span style="color:var(--vis)">&#8594;</span>LangChain / AutoGPT / CrewAI</li>
        <li style="font-size:10px;color:rgba(221,234,245,.5);padding:10px 0;border-bottom:1px solid var(--rim);display:flex;gap:8px"><span style="color:var(--vis)">&#8594;</span>n8n workflow templates</li>
        <li style="font-size:10px;color:rgba(221,234,245,.5);padding:10px 0;border-bottom:1px solid var(--rim);display:flex;gap:8px"><span style="color:var(--vis)">&#8594;</span>NemoClaw protocol library</li>
        <li style="font-size:10px;color:rgba(221,234,245,.5);padding:10px 0;border-bottom:1px solid var(--rim);display:flex;gap:8px"><span style="color:var(--vis)">&#8594;</span>7-day no-questions refund</li>
      </ul>
      <a href="https://buy.stripe.com/00w5kv0Q1dcVgCkgHSbsc03" target="_blank" rel="noopener" class="btn-primary" style="text-align:center;display:block;width:100%;text-decoration:none;font-size:13px;padding:20px">
        GET VEILPIERCER &mdash; $197 &rarr;
      </a>
    </div>
  </div>
</section>
"""

price_re = re.compile(r'<section[^>]*id=["\']pricing["\'][^>]*>.*?</section>', re.DOTALL)
if price_re.search(src):
    src = price_re.sub(PRICE_BLOCK, src, count=1)

# ── 8. Inject all JavaScript before </body> ───────────────────────────────────
JS_BLOCK = r"""
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r134/three.min.js"></script>
<script>
// ══════════════════════════════════════════════════════════════════
// THREE.JS NEURAL MESH — performance-optimised, 30fps cap
// 120 nodes, connected by edges within CDIST, mouse gravity
// ══════════════════════════════════════════════════════════════════
(function(){
  var C = document.getElementById('neural-bg');
  if (!C || typeof THREE === 'undefined') return;
  var W = innerWidth, H = innerHeight;
  var scene  = new THREE.Scene();
  var cam    = new THREE.PerspectiveCamera(60, W/H, 1, 2000);
  cam.position.z = 500;
  var rend = new THREE.WebGLRenderer({canvas:C,alpha:true,antialias:false,powerPreference:'low-power'});
  rend.setSize(W,H);
  rend.setPixelRatio(Math.min(devicePixelRatio, 1.5));
  rend.setClearColor(0,0);

  function rr(a,b){return a+Math.random()*(b-a);}
  var CYAN=new THREE.Color(0x00e5ff), PURP=new THREE.Color(0xbf00ff), GRN=new THREE.Color(0x00ff88);
  var N=120, nodes=[];
  for(var i=0;i<N;i++){
    var t=Math.random();
    nodes.push({x:rr(-W*.55,W*.55),y:rr(-H*.55,H*.55),z:rr(-220,80),
      vx:rr(-.18,.18),vy:rr(-.18,.18),vz:rr(-.04,.04),
      col:t>.88?PURP:(t>.78?GRN:CYAN),sz:t>.88?5:(t>.78?3.6:2.2),
      p:Math.random()*Math.PI*2,ps:rr(.5,1.2),isTensor:t>.88});
  }
  var pPos=new Float32Array(N*3),pCol=new Float32Array(N*3),pSz=new Float32Array(N);
  var pGeo=new THREE.BufferGeometry();
  var pPA=new THREE.BufferAttribute(pPos,3);pPA.setUsage(THREE.DynamicDrawUsage);
  var pCA=new THREE.BufferAttribute(pCol,3);pCA.setUsage(THREE.DynamicDrawUsage);
  var pSA=new THREE.BufferAttribute(pSz,1);pSA.setUsage(THREE.DynamicDrawUsage);
  pGeo.setAttribute('position',pPA);pGeo.setAttribute('color',pCA);pGeo.setAttribute('size',pSA);
  var pMat=new THREE.ShaderMaterial({
    vertexShader:'attribute float size;attribute vec3 color;varying vec3 vC;void main(){vC=color;vec4 mv=modelViewMatrix*vec4(position,1.);gl_PointSize=size*(460./-mv.z);gl_Position=projectionMatrix*mv;}',
    fragmentShader:'varying vec3 vC;void main(){vec2 uv=gl_PointCoord-.5;float d=length(uv);if(d>.5)discard;float c=smoothstep(.5,.18,d)+smoothstep(.5,0.,d)*.3;gl_FragColor=vec4(vC,c);}',
    blending:THREE.AdditiveBlending,depthTest:false,transparent:true
  });
  scene.add(new THREE.Points(pGeo,pMat));

  var CDIST=148,MAXL=N*6;
  var lPos=new Float32Array(MAXL*6),lCol=new Float32Array(MAXL*6);
  var lGeo=new THREE.BufferGeometry();
  var lPA=new THREE.BufferAttribute(lPos,3);lPA.setUsage(THREE.DynamicDrawUsage);
  var lCA=new THREE.BufferAttribute(lCol,3);lCA.setUsage(THREE.DynamicDrawUsage);
  lGeo.setAttribute('position',lPA);lGeo.setAttribute('color',lCA);
  var lSeg=new THREE.LineSegments(lGeo,new THREE.LineBasicMaterial({vertexColors:true,blending:THREE.AdditiveBlending,depthTest:false,transparent:true}));
  scene.add(lSeg);

  var mx=0,my=0,tcx=0,tcy=0;
  document.addEventListener('mousemove',function(e){mx=(e.clientX-W/2)*1.05;my=(e.clientY-H/2)*1.05;tcx=(e.clientX-W/2)*.06;tcy=(e.clientY-H/2)*.06;});
  window.addEventListener('resize',function(){W=innerWidth;H=innerHeight;cam.aspect=W/H;cam.updateProjectionMatrix();rend.setSize(W,H);});

  // 30fps cap to reduce GPU load
  var lastT=0, FPS_INTERVAL=1000/30;
  var clk=new THREE.Clock();
  function tick(now){
    requestAnimationFrame(tick);
    if(now-lastT<FPS_INTERVAL)return;
    lastT=now;
    var t=clk.getElapsedTime();
    cam.position.x+=(tcx-cam.position.x)*.025;
    cam.position.y+=(-tcy-cam.position.y)*.025;
    cam.lookAt(scene.position);
    for(var i=0;i<N;i++){
      var nd=nodes[i];nd.p+=nd.ps*.033;
      nd.x+=nd.vx;nd.y+=nd.vy;nd.z+=nd.vz;
      var dx=mx-nd.x,dy=my-nd.y,d2=dx*dx+dy*dy,R2=170*170;
      if(d2<R2&&d2>1){var s=.006*(1-Math.sqrt(d2)/170);nd.vx+=dx*s;nd.vy+=dy*s;}
      nd.vx*=.988;nd.vy*=.988;nd.vz*=.993;
      var sp=Math.sqrt(nd.vx*nd.vx+nd.vy*nd.vy);if(sp>.5){nd.vx*=.5/sp;nd.vy*=.5/sp;}
      var BX=W*.62,BY=H*.62;
      if(nd.x<-BX){nd.x=-BX;nd.vx=Math.abs(nd.vx);}if(nd.x>BX){nd.x=BX;nd.vx=-Math.abs(nd.vx);}
      if(nd.y<-BY){nd.y=-BY;nd.vy=Math.abs(nd.vy);}if(nd.y>BY){nd.y=BY;nd.vy=-Math.abs(nd.vy);}
      if(nd.z<-220){nd.z=-220;nd.vz=Math.abs(nd.vz);}if(nd.z>80){nd.z=80;nd.vz=-Math.abs(nd.vz);}
      var pf=1+Math.sin(nd.p)*.16+(nd.isTensor?Math.sin(t*2+i)*.12:0);
      pPos[i*3]=nd.x;pPos[i*3+1]=nd.y;pPos[i*3+2]=nd.z;
      pCol[i*3]=nd.col.r;pCol[i*3+1]=nd.col.g;pCol[i*3+2]=nd.col.b;
      pSz[i]=nd.sz*pf;
    }
    var li=0;
    for(var a=0;a<N&&li<MAXL;a++){var na=nodes[a];
      for(var b=a+1;b<N&&li<MAXL;b++){var nb=nodes[b];
        var ex=na.x-nb.x,ey=na.y-nb.y,ez=na.z-nb.z,ed=Math.sqrt(ex*ex+ey*ey+ez*ez);
        if(ed<CDIST){var al=(1-ed/CDIST)*.45;
          var rc=(na.col.r+nb.col.r)*.5*al,gc=(na.col.g+nb.col.g)*.5*al,bc=(na.col.b+nb.col.b)*.5*al;
          var base=li*6;
          lPos[base]=na.x;lPos[base+1]=na.y;lPos[base+2]=na.z;lCol[base]=rc;lCol[base+1]=gc;lCol[base+2]=bc;
          lPos[base+3]=nb.x;lPos[base+4]=nb.y;lPos[base+5]=nb.z;lCol[base+3]=rc;lCol[base+4]=gc;lCol[base+5]=bc;
          li++;}}}
    for(var k=li;k<MAXL;k++){var b=k*6;lPos[b]=lPos[b+1]=lPos[b+2]=lPos[b+3]=lPos[b+4]=lPos[b+5]=0;}
    lGeo.setDrawRange(0,li*2);
    pPA.needsUpdate=true;pCA.needsUpdate=true;pSA.needsUpdate=true;
    lPA.needsUpdate=true;lCA.needsUpdate=true;
    rend.render(scene,cam);
  }
  requestAnimationFrame(tick);
})();

// ══════════════════════════════════════════════════════════════════
// PHYSARUM SLIME FLOW OBSERVATORY v4
// Dual-canvas: wall canvas (persistent) + pheromone canvas (decays)
// Physarum 3-sensor chemotaxis, mouse events on pheromone canvas
// ══════════════════════════════════════════════════════════════════
function setObs(mode, btn) {
  window.__obsMode = mode;
  document.querySelectorAll('.obs-btn').forEach(function(b){b.classList.remove('active');});
  if (btn) btn.classList.add('active');
  var lbl = document.getElementById('obs-mode-label');
  if (lbl) lbl.textContent = {source:'SPAWN',sink:'SAFE ZONE',fire:'FAULT',wall:'WALL'}[mode]||mode.toUpperCase();
}
function obsReset(){if(window.__obsResetFn)window.__obsResetFn();}

(function(){
  var pC = document.getElementById('obs-canvas');
  var wC = document.getElementById('obs-wall-canvas');
  if (!pC) return;
  var pX = pC.getContext('2d',{willReadFrequently:true});
  var wX = wC ? wC.getContext('2d') : null;
  var W,H, agents=[], spawnPt=null, exitPt=null;
  var frame=0, totalSv=0, totalLo=0, faultCt=0;
  window.__obsMode='source';

  function resize(){
    var wr=document.getElementById('obs-canvas-wrap');
    W=pC.width=wr.clientWidth; H=pC.height=wr.clientHeight;
    if(wC){wC.width=W;wC.height=H;}
    pX.fillStyle='#040608';pX.fillRect(0,0,W,H);
  }

  window.__obsResetFn=function(){
    agents=[];spawnPt=null;exitPt=null;frame=0;totalSv=0;totalLo=0;faultCt=0;
    resize();
    if(wX)wX.clearRect(0,0,W,H);
    var ids=['obs-cap','obs-count','obs-tensors','obs-faults','obs-frame'];
    ids.forEach(function(id){var e=document.getElementById(id);if(e)e.textContent='0';});
    var sv=document.getElementById('obs-surv');if(sv){sv.textContent='100%';sv.className='hud-val safe';}
    var sb=document.getElementById('obs-status-bar');
    if(sb){sb.textContent='VEILPIERCER: Awaiting Slime Flow deployment.';sb.className='';}
    document.querySelectorAll('.obs-btn').forEach(function(b){b.classList.remove('active');});
    var sp=document.getElementById('btn-spawn');if(sp)sp.classList.add('active');
    window.__obsMode='source';
    var ml=document.getElementById('obs-mode-label');if(ml)ml.textContent='SPAWN';
  };

  function hud(id,val){var e=document.getElementById(id);if(e)e.textContent=val;}

  // 3-sensor Physarum: sample wall canvas + pheromone canvas
  var SA=22.5*Math.PI/180, SD=26, RA=45*Math.PI/180;
  function sense(x,y){
    if(x<0||x>=W||y<0||y>=H)return 0;
    if(wX){var wd=wX.getImageData(x|0,y|0,1,1).data;if(wd[3]>100)return -999;}
    var d=pX.getImageData(x|0,y|0,1,1).data;
    if(d[0]>155&&d[1]<70)return -999;
    return (d[1]+d[2])*.5;
  }
  function spd(){var s=document.getElementById('obs-speed');return s?parseFloat(s.value):3;}

  function loop(){
    // Pheromone decay
    pX.fillStyle='rgba(4,6,8,0.08)';pX.fillRect(0,0,W,H);
    var speed=spd(), tc=0;

    // Spawn
    if(spawnPt&&agents.length<4500){
      var burst=Math.min(10,4500-agents.length);
      for(var i=0;i<burst;i++)agents.push({
        x:spawnPt.x+(Math.random()-.5)*22,y:spawnPt.y+(Math.random()-.5)*22,
        a:Math.random()*Math.PI*2,hp:100,isTensor:Math.random()>.88,age:0});
    }

    var saved=0,lost=0;
    for(var i=agents.length-1;i>=0;i--){
      var ag=agents[i];ag.age++;
      var sF=sense(ag.x+Math.cos(ag.a)*SD,     ag.y+Math.sin(ag.a)*SD);
      var sL=sense(ag.x+Math.cos(ag.a-SA)*SD,  ag.y+Math.sin(ag.a-SA)*SD);
      var sR=sense(ag.x+Math.cos(ag.a+SA)*SD,  ag.y+Math.sin(ag.a+SA)*SD);

      if(sF===-999&&sL===-999&&sR===-999){ag.a+=Math.PI+(Math.random()-.5)*.5;}
      else if(sF===-999){ag.a+=(sL>sR?-1:1)*(RA+(Math.random()*.25));ag.hp-=4;}
      else if(sL===-999){ag.a+=RA*.85;}
      else if(sR===-999){ag.a-=RA*.85;}
      else if(sF>sL&&sF>sR){ag.a+=(Math.random()-.5)*.06;}
      else if(sL>sR){ag.a-=RA*(.6+Math.random()*.35);}
      else if(sR>sL){ag.a+=RA*(.6+Math.random()*.35);}
      else{ag.a+=(Math.random()-.5)*RA;}

      if(exitPt){
        var te=Math.atan2(exitPt.y-ag.y,exitPt.x-ag.x),df=te-ag.a;
        while(df>Math.PI)df-=2*Math.PI;while(df<-Math.PI)df+=2*Math.PI;
        ag.a+=df*.032;
      }
      ag.x+=Math.cos(ag.a)*speed;ag.y+=Math.sin(ag.a)*speed;

      if(ag.x<0||ag.x>W||ag.y<0||ag.y>H||ag.hp<=0){agents.splice(i,1);lost++;totalLo++;continue;}

      var hp=ag.hp/100;
      if(ag.isTensor){tc++;
        pX.shadowBlur=4;pX.shadowColor='#bf00ff';
        pX.fillStyle='rgba(191,0,255,'+(0.45+hp*.55)+')';
        var s=2+(1-hp)*2.5;
        pX.beginPath();pX.moveTo(ag.x,ag.y-s);pX.lineTo(ag.x+s,ag.y);pX.lineTo(ag.x,ag.y+s);pX.lineTo(ag.x-s,ag.y);pX.closePath();pX.fill();
        pX.shadowBlur=0;
      }else{
        var r=Math.round((1-hp)*200),g=Math.round(hp*229),b=Math.round(hp*255);
        pX.fillStyle='rgba('+r+','+g+','+b+','+(0.6+hp*.25)+')';pX.fillRect(ag.x-1,ag.y-1,2.3,2.3);
      }
      if(exitPt&&Math.hypot(exitPt.x-ag.x,exitPt.y-ag.y)<28){agents.splice(i,1);saved++;totalSv++;continue;}
    }

    if(spawnPt){pX.strokeStyle='rgba(0,229,255,'+(0.4+.15*Math.sin(frame*.09))+')';pX.lineWidth=1.5;pX.beginPath();pX.arc(spawnPt.x,spawnPt.y,14+5*Math.sin(frame*.09),0,Math.PI*2);pX.stroke();}
    if(exitPt){pX.strokeStyle='rgba(0,255,136,'+(0.5+.2*Math.sin(frame*.07))+')';pX.lineWidth=2;pX.beginPath();pX.arc(exitPt.x,exitPt.y,18+6*Math.sin(frame*.06),0,Math.PI*2);pX.stroke();pX.fillStyle='rgba(0,255,136,.07)';pX.beginPath();pX.arc(exitPt.x,exitPt.y,24,0,Math.PI*2);pX.fill();}

    if(frame%45===0){
      var total=totalSv+totalLo||1,rate=Math.max(0,Math.round(totalSv/total*100));
      hud('obs-cap',saved);hud('obs-count',agents.length);hud('obs-tensors',tc);hud('obs-frame',frame);hud('obs-faults',faultCt);
      var sv=document.getElementById('obs-surv');
      if(sv){sv.textContent=rate+'%';sv.className='hud-val '+(rate>=70?'safe':rate>=40?'warn':'crit');}
      var sb=document.getElementById('obs-status-bar');
      if(sb){
        if(!spawnPt){sb.textContent='AWAITING DEPLOYMENT \u2014 Click SPAWN then click the canvas.';sb.className='';}
        else if(rate<40){sb.textContent='CRITICAL: '+(100-rate)+'% agent loss \u2014 LOCKDOWN recommended.';sb.className='critical';}
        else if(rate<70){sb.textContent='WARNING: Survivability '+rate+'% \u2014 tensor anomaly detected.';sb.className='warning';}
        else{sb.textContent='NOMINAL: '+rate+'% success \u2014 '+tc+' Tensor Cores active. Vera Rubin tolerance held.';sb.className='nominal';}
      }
    }
    frame++;requestAnimationFrame(loop);
  }

  // ── Pointer events on pheromone canvas ────────────────────────────
  function pos(e){var r=pC.getBoundingClientRect();return{x:(e.clientX-r.left)*(W/r.width),y:(e.clientY-r.top)*(H/r.height)};}
  var drawing=false,lastX=0,lastY=0;

  pC.addEventListener('mousedown',function(e){
    var p=pos(e), mode=window.__obsMode||'source';
    if(mode==='source'){spawnPt=p;}
    else if(mode==='sink'){exitPt=p;}
    else if(mode==='fire'){
      faultCt++;hud('obs-faults',faultCt);
      pX.shadowBlur=22;pX.shadowColor='#ff2200';pX.fillStyle='#ff2200';
      pX.beginPath();pX.arc(p.x,p.y,28,0,Math.PI*2);pX.fill();
      pX.shadowBlur=0;pX.fillStyle='rgba(255,60,0,.18)';
      pX.beginPath();pX.arc(p.x,p.y,52,0,Math.PI*2);pX.fill();
    }else if(mode==='wall'){
      drawing=true;lastX=p.x;lastY=p.y;
      if(wX){wX.fillStyle='rgba(200,220,240,0.9)';wX.beginPath();wX.arc(p.x,p.y,7,0,Math.PI*2);wX.fill();}
    }
  });
  pC.addEventListener('mousemove',function(e){
    if(!drawing||(window.__obsMode||'source')!=='wall'||!wX)return;
    var p=pos(e);
    wX.strokeStyle='rgba(200,220,240,0.92)';wX.lineWidth=14;wX.lineCap='round';wX.lineJoin='round';
    wX.beginPath();wX.moveTo(lastX,lastY);wX.lineTo(p.x,p.y);wX.stroke();
    lastX=p.x;lastY=p.y;
  });
  pC.addEventListener('mouseup',function(){drawing=false;});
  pC.addEventListener('mouseleave',function(){drawing=false;});

  // speed slider
  var sl=document.getElementById('obs-speed');
  if(sl)sl.addEventListener('input',function(){var l=document.getElementById('obs-speed-label');if(l)l.textContent='Speed: '+parseFloat(this.value).toFixed(1)+' px/f';});

  window.addEventListener('resize',resize);
  setTimeout(function(){resize();loop();},300);
})();

// ══════════════════════════════════════════════════════════════════
// CUSTOM CURSOR
// ══════════════════════════════════════════════════════════════════
(function(){
  var dot=document.getElementById('cur'),ring=document.getElementById('cur-r');
  if(!dot||!ring)return;
  var rx=0,ry=0;
  document.addEventListener('mousemove',function(e){
    dot.style.left=e.clientX+'px';dot.style.top=e.clientY+'px';
    rx+=(e.clientX-rx)*.15;ry+=(e.clientY-ry)*.15;
    ring.style.left=rx+'px';ring.style.top=ry+'px';
  });
  document.querySelectorAll('a,button,[onclick]').forEach(function(el){
    el.addEventListener('mouseenter',function(){dot.style.transform='translate(-50%,-50%) scale(2.2)';ring.style.transform='translate(-50%,-50%) scale(1.6)';});
    el.addEventListener('mouseleave',function(){dot.style.transform='translate(-50%,-50%) scale(1)';ring.style.transform='translate(-50%,-50%) scale(1)';});
  });
})();

// ══════════════════════════════════════════════════════════════════
// SCROLL REVEAL
// ══════════════════════════════════════════════════════════════════
(function(){
  var items=document.querySelectorAll('.reveal');
  if(!items.length)return;
  var io=new IntersectionObserver(function(entries){
    entries.forEach(function(e){if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target);}});
  },{threshold:0.07});
  items.forEach(function(el){io.observe(el);});
  setTimeout(function(){items.forEach(function(el){el.classList.add('in');});},1600);
})();
</script>
"""

src = src.replace('</body>', JS_BLOCK + '\n</body>', 1)

# ── Write output ──────────────────────────────────────────────────────────────
out = r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html'
open(out, 'w', encoding='utf-8').write(src)
shutil.copy(out, r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\public\vp.html')
print('DONE — bytes:', len(src), ' lines:', src.count('\n'))
