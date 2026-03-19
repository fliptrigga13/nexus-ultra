"""
mega_patch.py — Three fixes in one pass:
  1. Persistent wall canvas (walls don't fade with pheromone decay)
  2. Physarum-class swarm physics (3-sensor chemotaxis, smooth gradient follow)
  3. Single $197 pricing block — remove all multi-tier cards
"""
import re, shutil

src = open(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', encoding='utf-8').read()

# ─────────────────────────────────────────────────────────────────────────────
# 1. ADD WALL CANVAS to Observatory HTML (layer underneath obs-canvas)
# ─────────────────────────────────────────────────────────────────────────────
# Replace single canvas with two: wall-canvas (persistent) + obs-canvas (pheromone)
src = src.replace(
    '<canvas id="obs-canvas"></canvas>',
    '''<canvas id="obs-wall-canvas" style="position:absolute;top:0;left:0;width:100%;height:100%;z-index:1;pointer-events:none"></canvas>
    <canvas id="obs-canvas" style="position:absolute;top:0;left:0;width:100%;height:100%;z-index:2;cursor:crosshair"></canvas>'''
)

# ─────────────────────────────────────────────────────────────────────────────
# 2. REMOVE old observatory JS, inject new Physarum-class engine
# ─────────────────────────────────────────────────────────────────────────────
# Strip existing obs JS blocks
src = re.sub(r'// ── UPGRADED AGENT FLOW OBSERVATORY.*?</script>', '', src, flags=re.DOTALL, count=1)
src = re.sub(r'function setObs\(.*?}\s*\}\s*\)\(\);', '', src, flags=re.DOTALL)
src = re.sub(r'function obsReset\(\).*?window\.__obsReset.*?;\s*}', '', src, flags=re.DOTALL)

NEW_OBS_JS = r"""
// ══════════════════════════════════════════════════════════════════════
// VEILPIERCER OBSERVATORY — PHYSARUM SWARM ENGINE v4
// GTC 2026 Vera Rubin Tensor Architecture
// Persistent wall canvas + 3-sensor chemotaxis slime physics
// ══════════════════════════════════════════════════════════════════════
function setObs(mode, btn) {
  window.__obsMode = mode;
  document.querySelectorAll('.obs-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  var lbl = document.getElementById('obs-mode-label');
  if (lbl) {
    lbl.textContent = {source:'SPAWN',sink:'SAFE ZONE',fire:'FAULT',wall:'WALL'}[mode] || mode.toUpperCase();
  }
}
function obsReset() { window.__obsReset && window.__obsReset(); }

(function () {
  var pCanvas = document.getElementById('obs-canvas');       // pheromone layer
  var wCanvas = document.getElementById('obs-wall-canvas');  // persistent wall layer
  if (!pCanvas) return;
  var pCtx = pCanvas.getContext('2d', { willReadFrequently: true });
  var wCtx = wCanvas ? wCanvas.getContext('2d') : null;

  var W, H;
  var agents = [], spawnPoint = null, exitPoint = null;
  var frame = 0, totalSaved = 0, totalLost = 0, faultCount = 0;
  var tensorCount = 0;
  window.__obsMode = 'source';

  // ── Physarum config ─────────────────────────────────────────────────
  var SA  = 22.5 * Math.PI / 180;  // sensor angle offset from heading
  var SD  = 28;                    // sensor distance (px)
  var RA  = 45  * Math.PI / 180;   // rotation amount when turning
  var DEP = 8;                     // trail deposit amount
  var EVP = 0.05;                  // pheromone evaporation per frame

  function resize() {
    var wrap = document.getElementById('obs-canvas-wrap');
    W = pCanvas.width  = wrap.clientWidth;
    H = pCanvas.height = wrap.clientHeight;
    if (wCanvas) { wCanvas.width = W; wCanvas.height = H; }
    pCtx.fillStyle = '#040608';
    pCtx.fillRect(0, 0, W, H);
  }

  window.__obsReset = function () {
    agents = []; spawnPoint = null; exitPoint = null;
    frame = 0; totalSaved = 0; totalLost = 0; faultCount = 0; tensorCount = 0;
    resize();
    if (wCtx) { wCtx.clearRect(0, 0, W, H); }
    ['obs-cap','obs-surv','obs-count','obs-tensors','obs-faults','obs-frame']
      .forEach(function(id){ var e=document.getElementById(id); if(e) e.textContent='0'; });
    var sv = document.getElementById('obs-surv'); if(sv){ sv.textContent='100%'; sv.className='hud-val safe'; }
    var sb = document.getElementById('obs-status-bar');
    if (sb) { sb.textContent='VEILPIERCER: Awaiting Slime Flow deployment.'; sb.className=''; }
    document.querySelectorAll('.obs-btn').forEach(b=>b.classList.remove('active'));
    var sp = document.getElementById('btn-spawn'); if(sp){ sp.classList.add('active'); }
    window.__obsMode = 'source';
    var ml = document.getElementById('obs-mode-label'); if(ml) ml.textContent='SPAWN';
  };

  function set(id, val) { var e=document.getElementById(id); if(e) e.textContent=val; }

  // ── Physarum sensor: sample trail at a point ─────────────────────────
  function sense(x, y) {
    if (x < 0 || x >= W || y < 0 || y >= H) return 0;
    var d = pCtx.getImageData(x | 0, y | 0, 1, 1).data;
    // Wall detection — pure white on wall canvas returns -999 (blocker)
    if (wCtx) {
      var wd = wCtx.getImageData(x | 0, y | 0, 1, 1).data;
      if (wd[3] > 120) return -999; // wall pixel blocks
    }
    // Fault zone = red channel dominant
    if (d[0] > 160 && d[1] < 80) return -999;
    // Pheromone is encoded in green+blue channels
    return (d[1] + d[2]) * 0.5;
  }

  function getSpeed() {
    var sl = document.getElementById('obs-speed');
    return sl ? parseFloat(sl.value) : 3;
  }

  function loop() {
    // ── Pheromone decay (only on pheromone canvas) ───────────────────
    pCtx.fillStyle = 'rgba(4,6,8,' + EVP + ')';
    pCtx.fillRect(0, 0, W, H);

    var spd = getSpeed();
    var tc = 0;

    // ── Spawn agents ─────────────────────────────────────────────────
    if (spawnPoint && agents.length < 5000) {
      var burst = Math.min(10, 5000 - agents.length);
      for (var i = 0; i < burst; i++) {
        agents.push({
          x: spawnPoint.x + (Math.random() - 0.5) * 24,
          y: spawnPoint.y + (Math.random() - 0.5) * 24,
          a: Math.random() * Math.PI * 2,
          hp: 100,
          isTensor: Math.random() > 0.88,
          age: 0
        });
      }
    }

    var saved = 0, lost = 0;
    for (var i = agents.length - 1; i >= 0; i--) {
      var ag = agents[i];
      ag.age++;
      var hp = ag.hp / 100;

      // ── 3-sensor Physarum chemotaxis ───────────────────────────────
      var sF = sense(ag.x + Math.cos(ag.a)       * SD, ag.y + Math.sin(ag.a)       * SD); // forward
      var sL = sense(ag.x + Math.cos(ag.a - SA)  * SD, ag.y + Math.sin(ag.a - SA)  * SD); // left
      var sR = sense(ag.x + Math.cos(ag.a + SA)  * SD, ag.y + Math.sin(ag.a + SA)  * SD); // right

      if (sF === -999 && sL === -999 && sR === -999) {
        // Fully blocked — reverse
        ag.a += Math.PI + (Math.random() - 0.5) * 0.4;
      } else if (sF === -999) {
        // Wall/fault ahead — turn away
        ag.a += (sL > sR ? -1 : 1) * (RA + Math.random() * 0.3);
        if (ag.x < 0 || sF < -900) ag.hp -= 6;
      } else if (sL === -999 || sR === -999) {
        // Wall on one side — steer away
        ag.a += (sL === -999 ? 1 : -1) * RA * 0.8;
      } else if (sF > sL && sF > sR) {
        // Go straight — add tiny wobble
        ag.a += (Math.random() - 0.5) * 0.07;
      } else if (sL > sR) {
        ag.a -= RA * (0.6 + Math.random() * 0.4);
      } else if (sR > sL) {
        ag.a += RA * (0.6 + Math.random() * 0.4);
      } else {
        // Random walk when equal
        ag.a += (Math.random() - 0.5) * RA;
      }

      // Exit-point attraction (adds to chemotaxis, doesn't override)
      if (exitPoint) {
        var toExit = Math.atan2(exitPoint.y - ag.y, exitPoint.x - ag.x);
        var diff = toExit - ag.a;
        while (diff >  Math.PI) diff -= 2 * Math.PI;
        while (diff < -Math.PI) diff += 2 * Math.PI;
        ag.a += diff * 0.035;
      }

      ag.x += Math.cos(ag.a) * spd;
      ag.y += Math.sin(ag.a) * spd;

      // Boundary kill
      if (ag.x < 0 || ag.x > W || ag.y < 0 || ag.y > H || ag.hp <= 0) {
        agents.splice(i, 1); lost++; totalLost++; continue;
      }

      // ── Deposit pheromone trail ────────────────────────────────────
      var depColor;
      if (ag.isTensor) {
        tc++;
        depColor = 'rgba(191,0,255,' + (0.5 + hp * 0.5) + ')';
      } else {
        var r = Math.round((1 - hp) * 200);
        var g = Math.round(hp * 229);
        var b = Math.round(hp * 255);
        depColor = 'rgba(' + r + ',' + g + ',' + b + ',' + (0.6 + hp * 0.25) + ')';
      }
      pCtx.fillStyle = depColor;

      if (ag.isTensor) {
        pCtx.shadowBlur = 4; pCtx.shadowColor = '#bf00ff';
        var s = 2.2 + (1 - hp) * 2.8;
        pCtx.beginPath();
        pCtx.moveTo(ag.x, ag.y - s); pCtx.lineTo(ag.x + s, ag.y);
        pCtx.lineTo(ag.x, ag.y + s); pCtx.lineTo(ag.x - s, ag.y);
        pCtx.closePath(); pCtx.fill();
        pCtx.shadowBlur = 0;
      } else {
        pCtx.fillRect(ag.x - 1, ag.y - 1, 2.4, 2.4);
      }

      // Exit detection
      if (exitPoint && Math.hypot(exitPoint.x - ag.x, exitPoint.y - ag.y) < 28) {
        agents.splice(i, 1); saved++; totalSaved++; continue;
      }
    }

    tensorCount = tc;

    // ── Redraw spawn / exit indicators on pheromone canvas ───────────
    if (spawnPoint) {
      pCtx.strokeStyle = 'rgba(0,229,255,' + (0.4 + 0.15 * Math.sin(frame * 0.09)) + ')';
      pCtx.lineWidth = 1.5;
      pCtx.beginPath(); pCtx.arc(spawnPoint.x, spawnPoint.y, 14 + 5*Math.sin(frame*.09), 0, Math.PI*2); pCtx.stroke();
      pCtx.strokeStyle = 'rgba(0,229,255,0.15)';
      pCtx.beginPath(); pCtx.arc(spawnPoint.x, spawnPoint.y, 28 + 8*Math.sin(frame*.07), 0, Math.PI*2); pCtx.stroke();
    }
    if (exitPoint) {
      pCtx.strokeStyle = 'rgba(0,255,136,' + (0.5 + 0.2*Math.sin(frame*.07)) + ')';
      pCtx.lineWidth = 2;
      pCtx.beginPath(); pCtx.arc(exitPoint.x, exitPoint.y, 18 + 6*Math.sin(frame*.06), 0, Math.PI*2); pCtx.stroke();
      pCtx.fillStyle = 'rgba(0,255,136,0.08)';
      pCtx.beginPath(); pCtx.arc(exitPoint.x, exitPoint.y, 24, 0, Math.PI*2); pCtx.fill();
    }

    // ── HUD update every 45 frames ────────────────────────────────────
    if (frame % 45 === 0) {
      var total = totalSaved + totalLost || 1;
      var rate = Math.max(0, Math.round(totalSaved / total * 100));
      set('obs-cap', saved);
      set('obs-count', agents.length);
      set('obs-tensors', tc);
      set('obs-frame', frame);
      set('obs-faults', faultCount);
      var sv = document.getElementById('obs-surv');
      if (sv) {
        sv.textContent = rate + '%';
        sv.className = 'hud-val ' + (rate >= 70 ? 'safe' : rate >= 40 ? 'warn' : 'crit');
      }
      var sb = document.getElementById('obs-status-bar');
      if (sb) {
        if (!spawnPoint) {
          sb.textContent = 'AWAITING DEPLOYMENT — Click SPAWN AGENTS then click canvas.'; sb.className = '';
        } else if (rate < 40) {
          sb.textContent = 'CRITICAL: ' + (100-rate) + '% agent loss — fault containment failing. LOCKDOWN recommended.'; sb.className = 'critical';
        } else if (rate < 70) {
          sb.textContent = 'WARNING: Survivability ' + rate + '% — tensor array anomaly detected. Reroute advised.'; sb.className = 'warning';
        } else {
          sb.textContent = 'NOMINAL: ' + rate + '% success — ' + tc + ' Tensor Cores active. Vera Rubin tolerance held.'; sb.className = 'nominal';
        }
      }
    }

    frame++;
    requestAnimationFrame(loop);
  }// end loop

  // ── Canvas interaction ─────────────────────────────────────────────
  var drawing = false, lastWX = 0, lastWY = 0;

  function getCanvasPos(e) {
    var rect = pCanvas.getBoundingClientRect();
    return {
      x: (e.clientX - rect.left) * (W / rect.width),
      y: (e.clientY - rect.top)  * (H / rect.height)
    };
  }

  pCanvas.addEventListener('mousedown', function(e) {
    var p = getCanvasPos(e);
    var mode = window.__obsMode || 'source';
    if (mode === 'source') {
      spawnPoint = p;
    } else if (mode === 'sink') {
      exitPoint = p;
    } else if (mode === 'fire') {
      faultCount++;
      set('obs-faults', faultCount);
      // Draw fault on PHEROMONE canvas (will slowly fade — but that's realistic)
      pCtx.shadowBlur = 24; pCtx.shadowColor = '#ff2200';
      pCtx.fillStyle = '#ff2200';
      pCtx.beginPath(); pCtx.arc(p.x, p.y, 30, 0, Math.PI*2); pCtx.fill();
      pCtx.shadowBlur = 0;
      pCtx.fillStyle = 'rgba(255,60,0,0.2)';
      pCtx.beginPath(); pCtx.arc(p.x, p.y, 55, 0, Math.PI*2); pCtx.fill();
    } else if (mode === 'wall') {
      // Draw wall on PERSISTENT wall canvas
      drawing = true;
      lastWX = p.x; lastWY = p.y;
      if (wCtx) {
        wCtx.strokeStyle = 'rgba(200,220,240,0.9)';
        wCtx.lineWidth = 14; wCtx.lineCap = 'round'; wCtx.lineJoin = 'round';
        wCtx.beginPath(); wCtx.arc(p.x, p.y, 7, 0, Math.PI*2); wCtx.fill();
      }
    }
  });

  pCanvas.addEventListener('mousemove', function(e) {
    if (!drawing || (window.__obsMode || 'source') !== 'wall' || !wCtx) return;
    var p = getCanvasPos(e);
    wCtx.strokeStyle = 'rgba(200,220,240,0.9)';
    wCtx.lineWidth = 14; wCtx.lineCap = 'round'; wCtx.lineJoin = 'round';
    wCtx.beginPath(); wCtx.moveTo(lastWX, lastWY); wCtx.lineTo(p.x, p.y); wCtx.stroke();
    lastWX = p.x; lastWY = p.y;
  });

  pCanvas.addEventListener('mouseup',    function() { drawing = false; });
  pCanvas.addEventListener('mouseleave', function() { drawing = false; });

  // Speed slider label
  var sl = document.getElementById('obs-speed');
  if (sl) sl.addEventListener('input', function() {
    var l = document.getElementById('obs-speed-label');
    if (l) l.textContent = 'Speed: ' + parseFloat(this.value).toFixed(1) + ' px/f';
  });

  window.addEventListener('resize', resize);
  setTimeout(function() { resize(); loop(); }, 250);
})();
"""

src = src.replace('</body>', '<script>\n' + NEW_OBS_JS + '\n</script>\n</body>', 1)


# ─────────────────────────────────────────────────────────────────────────────
# 3. REPLACE multi-tier pricing with single $197 block
# ─────────────────────────────────────────────────────────────────────────────
# Find pricing section and replace its inner content
SINGLE_PRICE_HTML = r"""
<div class="sec-tag">One-Time Access</div>
<h2 class="price-h"><span class="v">$197</span><br>One time. Yours forever.</h2>
<p class="price-sub">No seats. No per-agent fees. No subscription. No renewal. Ever.</p>

<div style="display:grid;grid-template-columns:1fr 1.8fr;gap:1px;background:var(--rim);margin-top:0">
  <div style="background:var(--panel);padding:56px 44px;display:flex;flex-direction:column;justify-content:center">
    <div style="font-size:9px;letter-spacing:3px;text-transform:uppercase;color:var(--vis);margin-bottom:16px">VeilPiercer</div>
    <div style="font-family:'Unbounded',sans-serif;font-weight:900;font-size:22px;margin-bottom:12px">Complete Bundle</div>
    <div style="font-family:'Unbounded',sans-serif;font-weight:900;font-size:88px;letter-spacing:-4px;line-height:1;color:var(--vis);margin-bottom:4px">$197</div>
    <div style="font-size:9px;color:var(--t2);letter-spacing:2px;text-transform:uppercase;margin-bottom:40px">one-time &middot; instant access &middot; yours forever</div>
    <a href="https://buy.stripe.com/00w5kv0Q1dcVgCkgHSbsc03" target="_blank" rel="noopener"
       style="font-family:'Unbounded',sans-serif;font-weight:900;font-size:11px;letter-spacing:2px;text-align:center;display:block;padding:18px;background:var(--vis);color:var(--black);text-decoration:none;text-transform:uppercase;transition:all .15s"
       onmouseover="this.style.background='#fff'" onmouseout="this.style.background='var(--vis)'">
      Get VeilPiercer &rarr;
    </a>
    <p style="font-size:9px;color:var(--t2);letter-spacing:1px;margin-top:14px;text-align:center">Secure checkout via Stripe &middot; Access link emailed instantly</p>
    <div style="margin-top:18px;padding:14px 16px;border:1px solid var(--rim);background:rgba(0,229,255,.02);font-size:9px;color:var(--t2);line-height:1.9">
      &#10003; 7-day no-questions refund<br>
      &#10003; Re-download any time<br>
      &#10003; One payment &mdash; no renewals ever
    </div>
  </div>
  <div style="background:var(--panel);padding:56px 44px">
    <ul style="list-style:none;display:grid;grid-template-columns:1fr 1fr;margin-bottom:40px">
      <li style="font-size:10px;color:rgba(221,234,245,.5);padding:11px 0;border-bottom:1px solid var(--rim);display:flex;gap:9px"><span style="color:var(--vis)">&#8594;</span>Full real-time agent dashboard</li>
      <li style="font-size:10px;color:rgba(221,234,245,.5);padding:11px 0;border-bottom:1px solid var(--rim);display:flex;gap:9px"><span style="color:var(--vis)">&#8594;</span>All 4 control protocols</li>
      <li style="font-size:10px;color:rgba(221,234,245,.5);padding:11px 0;border-bottom:1px solid var(--rim);display:flex;gap:9px"><span style="color:var(--vis)">&#8594;</span>9 live tunable control nodes</li>
      <li style="font-size:10px;color:rgba(221,234,245,.5);padding:11px 0;border-bottom:1px solid var(--rim);display:flex;gap:9px"><span style="color:var(--vis)">&#8594;</span>Vera Rubin neural mesh background</li>
      <li style="font-size:10px;color:rgba(221,234,245,.5);padding:11px 0;border-bottom:1px solid var(--rim);display:flex;gap:9px"><span style="color:var(--vis)">&#8594;</span>Natural language command interface</li>
      <li style="font-size:10px;color:rgba(221,234,245,.5);padding:11px 0;border-bottom:1px solid var(--rim);display:flex;gap:9px"><span style="color:var(--vis)">&#8594;</span>Physarum Slime Flow Observatory</li>
      <li style="font-size:10px;color:rgba(221,234,245,.5);padding:11px 0;border-bottom:1px solid var(--rim);display:flex;gap:9px"><span style="color:var(--vis)">&#8594;</span>100% offline &mdash; zero data leaves machine</li>
      <li style="font-size:10px;color:rgba(221,234,245,.5);padding:11px 0;border-bottom:1px solid var(--rim);display:flex;gap:9px"><span style="color:var(--vis)">&#8594;</span>Full source code included</li>
      <li style="font-size:10px;color:rgba(221,234,245,.5);padding:11px 0;border-bottom:1px solid var(--rim);display:flex;gap:9px"><span style="color:var(--vis)">&#8594;</span>LangChain + AutoGPT + CrewAI support</li>
      <li style="font-size:10px;color:rgba(221,234,245,.5);padding:11px 0;border-bottom:1px solid var(--rim);display:flex;gap:9px"><span style="color:var(--vis)">&#8594;</span>n8n workflow templates</li>
      <li style="font-size:10px;color:rgba(221,234,245,.5);padding:11px 0;border-bottom:1px solid var(--rim);display:flex;gap:9px"><span style="color:var(--vis)">&#8594;</span>NemoClaw agentic protocol library</li>
      <li style="font-size:10px;color:rgba(221,234,245,.5);padding:11px 0;border-bottom:1px solid var(--rim);display:flex;gap:9px"><span style="color:var(--vis)">&#8594;</span>7-day no-questions refund</li>
    </ul>
    <a href="https://buy.stripe.com/00w5kv0Q1dcVgCkgHSbsc03" target="_blank" rel="noopener"
       style="font-family:'Unbounded',sans-serif;font-weight:900;font-size:12px;letter-spacing:3px;text-align:center;display:block;width:100%;padding:20px;background:var(--vis);color:var(--black);text-decoration:none;text-transform:uppercase;transition:all .15s"
       onmouseover="this.style.background='#fff';this.style.transform='translateY(-1px)'" onmouseout="this.style.background='var(--vis)';this.style.transform='none'">
      GET VEILPIERCER &mdash; $197 &rarr;
    </a>
  </div>
</div>
"""

# Replace the pricing section body (between the opening tag and closing tag)
PRICE_SEC_RE = re.compile(
    r'(<section[^>]*id=["\']pricing["\'][^>]*>|<div[^>]*id=["\']pricing["\'][^>]*>).*?(</section>|</div>)',
    re.DOTALL
)
def patch_pricing(m):
    tag = m.group(1)
    close = m.group(2)
    return tag + '\n<div class="sec">\n' + SINGLE_PRICE_HTML + '\n</div>\n' + close

src = PRICE_SEC_RE.sub(patch_pricing, src, count=1)

# Also ensure Stripe link is consistent everywhere
src = re.sub(
    r'https://buy\.stripe\.com/[a-zA-Z0-9_/]+',
    'https://buy.stripe.com/00w5kv0Q1dcVgCkgHSbsc03',
    src
)

# ── Write and deploy ──────────────────────────────────────────────────────────
out = r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html'
open(out, 'w', encoding='utf-8').write(src)
shutil.copy(out, r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\public\vp.html')
print('DONE — bytes:', len(src), ' lines:', src.count('\n'))
