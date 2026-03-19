
    // ══ CURSOR ═══════════════════════════════════════════════
    const cur = document.getElementById('cur'), ring = document.getElementById('cur-r');
    let mx = 0, my = 0, rx = 0, ry = 0;
    document.addEventListener('mousemove', e => {
      mx = e.clientX; my = e.clientY;
      cur.style.left = mx + 'px'; cur.style.top = my + 'px';
    });
    (function a() {
      rx += (mx - rx) * .12; ry += (my - ry) * .12;
      ring.style.left = rx + 'px'; ring.style.top = ry + 'px';
      requestAnimationFrame(a);
    })();
    document.querySelectorAll('a,button,.buyer-row,.why-card,.feat-card,.proto-card,.p-card,.sb-item').forEach(el => {
      el.addEventListener('mouseenter', () => {
        cur.style.transform = 'translate(-50%,-50%) scale(2.2)';
        ring.style.transform = 'translate(-50%,-50%) scale(1.6)';
        ring.style.borderColor = 'rgba(0,229,255,.6)';
      });
      el.addEventListener('mouseleave', () => {
        cur.style.transform = 'translate(-50%,-50%) scale(1)';
        ring.style.transform = 'translate(-50%,-50%) scale(1)';
        ring.style.borderColor = 'rgba(0,229,255,.35)';
      });
    });

    // ══ SCROLL REVEAL ════════════════════════════════════════
    const obs = new IntersectionObserver(e => e.forEach(x => {
      if (x.isIntersecting) { x.target.classList.add('in'); obs.unobserve(x.target); }
    }), { threshold: .07 });
    document.querySelectorAll('.reveal').forEach(el => obs.observe(el));

    // ══ HERO CANVAS — orbital node cluster ══════════════════
    (function () {
      const c = document.getElementById('hero-canvas'), x = c.getContext('2d');
      function sz() { c.width = c.parentElement.clientWidth; c.height = c.parentElement.clientHeight; }
      sz(); window.addEventListener('resize', sz);
      const NODES = [
        { l: 'TRACE', col: '#00e5ff', ang: 0, r: .28, sp: .0006, pw: .78 },
        { l: 'SIGNAL', col: '#00aaff', ang: 2.1, r: .28, sp: -.0005, pw: .65 },
        { l: 'DRIFT', col: '#0077ff', ang: 4.2, r: .28, sp: .0007, pw: .70 },
        { l: 'CATCH', col: '#00ff88', ang: .7, r: .22, sp: -.0005, pw: .82 },
        { l: 'HEAL', col: '#00dd66', ang: 2.8, r: .22, sp: .0008, pw: .60 },
        { l: 'ANOMALY', col: '#88ff44', ang: 4.9, r: .22, sp: -.0007, pw: .72 },
        { l: 'GATE', col: '#c84dff', ang: 1.4, r: .17, sp: .0005, pw: .88 },
        { l: 'REDACT', col: '#9922ff', ang: 3.5, r: .17, sp: -.0006, pw: .91 },
        { l: 'SHIELD', col: '#6600cc', ang: 5.6, r: .17, sp: .0004, pw: 1.0 },
      ];
      const pts = [];
      function sp(nd) {
        const a = Math.random() * Math.PI * 2, s = .6 + Math.random() * 1.4;
        pts.push({ x: nd.px, y: nd.py, vx: Math.cos(a) * s, vy: Math.sin(a) * s, life: 1, dec: .025 + Math.random() * .02, col: nd.col, sz: 1.2 + Math.random() * 1.8 });
      }
      let t = 0;
      function draw() {
        t++;
        const W = c.width, H = c.height, cx = W * .62, cy = H * .52;
        const br = Math.min(W, H) * .32;
        x.clearRect(0, 0, W, H);
        const g = x.createRadialGradient(cx, cy, 0, cx, cy, br * .8);
        g.addColorStop(0, 'rgba(0,229,255,.07)'); g.addColorStop(1, 'transparent');
        x.fillStyle = g; x.fillRect(0, 0, W, H);
        x.beginPath(); x.arc(cx, cy, 20, 0, Math.PI * 2);
        x.fillStyle = 'rgba(0,229,255,.08)'; x.fill();
        x.strokeStyle = 'rgba(0,229,255,.35)'; x.lineWidth = 1.5; x.stroke();
        x.font = 'bold 9px "Fira Code"'; x.fillStyle = 'rgba(0,229,255,.5)';
        x.textAlign = 'center'; x.textBaseline = 'middle'; x.fillText('VP', cx, cy);
        NODES.forEach(nd => {
          nd.ang += nd.sp;
          const r = br * nd.r;
          nd.px = cx + Math.cos(nd.ang) * r; nd.py = cy + Math.sin(nd.ang) * r;
          x.beginPath(); x.moveTo(cx, cy); x.lineTo(nd.px, nd.py);
          x.strokeStyle = nd.col + '15'; x.lineWidth = 1; x.setLineDash([2, 8]); x.stroke(); x.setLineDash([]);
          const R = 20;
          x.beginPath(); x.arc(nd.px, nd.py, R + 4, -Math.PI / 2, -Math.PI / 2 + nd.pw * Math.PI * 2);
          x.strokeStyle = nd.col; x.lineWidth = 4; x.lineCap = 'round';
          x.shadowColor = nd.col; x.shadowBlur = 10; x.stroke(); x.shadowBlur = 0; x.lineCap = 'butt';
          const bg = x.createRadialGradient(nd.px, nd.py, 0, nd.px, nd.py, R);
          bg.addColorStop(0, '#0d1e30'); bg.addColorStop(1, '#030810');
          x.beginPath(); x.arc(nd.px, nd.py, R, 0, Math.PI * 2);
          x.fillStyle = bg; x.fill(); x.strokeStyle = nd.col + '44'; x.lineWidth = 1.5; x.stroke();
          x.font = '7px "Fira Code"'; x.fillStyle = nd.col + 'bb';
          x.textAlign = 'center'; x.textBaseline = 'middle';
          x.fillText(nd.l, nd.px, nd.py);
          if (Math.random() < .04) sp(nd);
        });
        for (let i = pts.length - 1; i >= 0; i--) {
          const p = pts[i]; p.x += p.vx; p.y += p.vy; p.life -= p.dec;
          if (p.life <= 0) { pts.splice(i, 1); continue; }
          x.beginPath(); x.arc(p.x, p.y, p.sz * p.life, 0, Math.PI * 2);
          x.fillStyle = p.col + Math.round(p.life * 140).toString(16).padStart(2, '0'); x.fill();
        }
        requestAnimationFrame(draw);
      }
      draw();
    })();

    // ══ WAVE STRIP 1 ═════════════════════════════════════════
    (function () {
      const c = document.getElementById('strip1'), x = c.getContext('2d');
      function sz() { c.width = window.innerWidth; c.height = 90; } sz();
      window.addEventListener('resize', sz);
      const streams = [
        { col: '#00e5ff', ph: 0, sp: .018, fr: .024, am: .38 },
        { col: '#00ff88', ph: 2.1, sp: .024, fr: .034, am: .30 },
        { col: '#c84dff', ph: 4.2, sp: .016, fr: .028, am: .34 },
      ];
      let t = 0;
      function draw() {
        t++; x.fillStyle = '#080c10'; x.fillRect(0, 0, c.width, c.height);
        streams.forEach((s, si) => {
          x.beginPath();
          for (let px = 0; px < c.width; px++) {
            const spk = Math.random() < .003 ? (Math.random() * .5 + .3) : 0;
            const py = 45 + Math.sin(px * s.fr + t * s.sp + s.ph) * 45 * s.am + spk * 22;
            px === 0 ? x.moveTo(px, py) : x.lineTo(px, py);
          }
          x.strokeStyle = s.col + (si === 1 ? 'cc' : '77'); x.lineWidth = si === 1 ? 2 : 1.5; x.stroke();
        });
        requestAnimationFrame(draw);
      }
      draw();
    })();

    // ══ WAVE STRIP 2 ═════════════════════════════════════════
    (function () {
      const c = document.getElementById('strip2'), x = c.getContext('2d');
      function sz() { c.width = window.innerWidth; c.height = 90; } sz();
      window.addEventListener('resize', sz);
      const pts = Array.from({ length: 80 }, () => ({
        x: Math.random() * window.innerWidth, y: Math.random() * 90,
        sp: 1 + Math.random() * 3, col: ['#00e5ff', '#00ff88', '#c84dff'][Math.floor(Math.random() * 3)],
        sz: Math.random() * 1.8 + .4, trail: [],
      }));
      function draw() {
        x.fillStyle = 'rgba(8,12,16,.35)'; x.fillRect(0, 0, c.width, c.height);
        pts.forEach(p => {
          p.trail.unshift({ x: p.x, y: p.y }); if (p.trail.length > 10) p.trail.pop();
          p.x += p.sp; if (p.x > c.width + 20) p.x = -20;
          p.trail.forEach((pt, i) => {
            const a = 1 - i / p.trail.length;
            x.beginPath(); x.arc(pt.x, pt.y, p.sz * a, 0, Math.PI * 2);
            x.fillStyle = p.col + Math.round(a * 160).toString(16).padStart(2, '0'); x.fill();
          });
        });
        requestAnimationFrame(draw);
      }
      draw();
    })();

    // ══ VISION CANVAS — deep space ═══════════════════════════
    (function () {
      const c = document.getElementById('vision-canvas'), x = c.getContext('2d');
      function sz() { c.width = c.parentElement.clientWidth; c.height = c.parentElement.clientHeight; }
      sz(); window.addEventListener('resize', sz);
      const stars = Array.from({ length: 300 }, () => ({
        x: Math.random(), y: Math.random(), r: Math.random() * 1.3 + .2,
        ph: Math.random() * Math.PI * 2, sp: .0008 + Math.random() * .002,
      }));
      let t = 0;
      function draw() {
        t++; x.fillStyle = 'rgba(4,6,8,.25)'; x.fillRect(0, 0, c.width, c.height);
        stars.forEach(s => {
          const a = (Math.sin(s.ph + t * s.sp) * .35 + .55) * .6;
          x.beginPath(); x.arc(s.x * c.width, s.y * c.height, s.r, 0, Math.PI * 2);
          x.fillStyle = `rgba(160,210,240,${a})`; x.fill();
        });
        requestAnimationFrame(draw);
      }
      draw();
    })();

    // ══ OBSERVATORY ══════════════════════════════════════════
    (function () {
      const canvas = document.getElementById('obs-canvas');
      const ctx = canvas.getContext('2d', { willReadFrequently: true });
      let w, h, agents = [], obsMode = 'source', spawnPoint = null, exitPoint = null, frame = 0;
      let totalSaved = 0, totalLost = 0;
      function obsInit() {
        const wrap = document.getElementById('obs-canvas-wrap');
        w = canvas.width = wrap.clientWidth; h = canvas.height = wrap.clientHeight;
        ctx.fillStyle = '#020205'; ctx.fillRect(0, 0, w, h);
      }
      function obsReset() {
        agents = []; spawnPoint = null; exitPoint = null; totalSaved = 0; totalLost = 0; frame = 0;
        obsInit();
        document.getElementById('obs-cap').textContent = '0';
        document.getElementById('obs-surv').textContent = '100%';
        document.getElementById('obs-count').textContent = '0';
        const alert = document.getElementById('obs-alert');
        alert.textContent = 'VEILPIERCER: System reset. Awaiting agent deployment.';
        alert.className = '';
      }
      window.obsReset = obsReset;
      window.obsMode = 'source';
      Object.defineProperty(window, 'obsMode', { get: () => obsMode, set: (v) => { obsMode = v; } });
      function look(agent, ang) {
        const px = agent.x + Math.cos(ang) * 20, py = agent.y + Math.sin(ang) * 20;
        if (px < 0 || px > w || py < 0 || py > h) return -1;
        const d = ctx.getImageData(px | 0, py | 0, 1, 1).data;
        if (d[0] > 180 && d[1] < 100) return -2;
        if (d[0] > 100 && d[1] > 100 && d[2] > 100) return -1;
        return d[1] + d[2];
      }
      function obsLoop() {
        ctx.fillStyle = 'rgba(2, 2, 5, 0.09)'; ctx.fillRect(0, 0, w, h);
        if (spawnPoint && agents.length < 3200) {
          for (let i = 0; i < 5; i++) agents.push({ x: spawnPoint.x, y: spawnPoint.y, a: Math.random() * 6.28, hp: 100 });
        }
        let saved = 0, lost = 0;
        for (let i = agents.length - 1; i >= 0; i--) {
          const ag = agents[i];
          const vC = look(ag, ag.a), vL = look(ag, ag.a - 0.5), vR = look(ag, ag.a + 0.5);
          if (vC === -1 || vC === -2) { ag.a += 1.5; if (vC === -2) ag.hp -= 4; }
          else { if (vL > vR) ag.a -= 0.12; else if (vR > vL) ag.a += 0.12; }
          if (exitPoint) ag.a += Math.atan2(exitPoint.y - ag.y, exitPoint.x - ag.x) * 0.03;
          ag.x += Math.cos(ag.a) * 2.8; ag.y += Math.sin(ag.a) * 2.8;
          if (ag.hp <= 0) { agents.splice(i, 1); lost++; totalLost++; continue; }
          const hp = ag.hp / 100, r = Math.round((1 - hp) * 255), g = Math.round(hp * 200);
          ctx.fillStyle = `rgba(${r}, ${g}, ${hp > 0.6 ? 242 : 80}, 0.55)`;
          ctx.fillRect(ag.x, ag.y, 1.5, 1.5);
          if (exitPoint && Math.hypot(exitPoint.x - ag.x, exitPoint.y - ag.y) < 22) { agents.splice(i, 1); saved++; totalSaved++; }
        }
        if (spawnPoint) {
          ctx.strokeStyle = 'rgba(0, 229, 255, 0.5)'; ctx.lineWidth = 1;
          ctx.beginPath(); ctx.arc(spawnPoint.x, spawnPoint.y, 14 + Math.sin(frame * 0.1) * 4, 0, Math.PI * 2); ctx.stroke();
        }
        if (exitPoint) {
          ctx.strokeStyle = 'rgba(0, 255, 136, 0.6)'; ctx.lineWidth = 1.5;
          ctx.beginPath(); ctx.arc(exitPoint.x, exitPoint.y, 18 + Math.sin(frame * 0.08) * 5, 0, Math.PI * 2); ctx.stroke();
          ctx.fillStyle = 'rgba(0, 255, 136, 0.12)'; ctx.beginPath(); ctx.arc(exitPoint.x, exitPoint.y, 22, 0, Math.PI * 2); ctx.fill();
        }
        if (frame % 45 === 0) {
          const total = totalSaved + totalLost || 1, rate = Math.max(0, Math.round((totalSaved / total) * 100));
          document.getElementById('obs-cap').textContent = saved;
          document.getElementById('obs-surv').textContent = rate + '%';
          document.getElementById('obs-count').textContent = agents.length;
          document.getElementById('obs-surv').style.color = rate >= 70 ? 'var(--saf)' : (rate >= 40 ? 'var(--warn)' : 'var(--red)');
          const alert = document.getElementById('obs-alert');
          if (!spawnPoint) { alert.textContent = 'VEILPIERCER: No agents deployed. Click canvas with SPAWN AGENTS active.'; alert.className = ''; }
          else if (rate < 40) { alert.textContent = `CRITICAL: ${100 - rate}% agent loss. LOCKDOWN recommended. Fault zone compromising flow.`; alert.className = ''; }
          else if (rate < 70) { alert.textContent = `WARNING: Survivability at ${rate}%. Anomaly detected — consider rerouting.`; alert.className = ''; }
          else { alert.textContent = `VEILPIERCER: Flow nominal. ${rate}% success rate. All agents within tolerance.`; alert.className = 'stable'; }
        }
        frame++; requestAnimationFrame(obsLoop);
      }
      canvas.addEventListener('mousedown', (e) => {
        const rect = canvas.getBoundingClientRect();
        const cx = (e.clientX - rect.left) * (w / rect.width);
        const cy = (e.clientY - rect.top) * (h / rect.height);
        if (obsMode === 'source') spawnPoint = { x: cx, y: cy };
        else if (obsMode === 'sink') exitPoint = { x: cx, y: cy };
        else if (obsMode === 'fire') {
          ctx.fillStyle = '#ff2200'; ctx.beginPath(); ctx.arc(cx, cy, 28, 0, Math.PI * 2); ctx.fill();
          ctx.fillStyle = 'rgba(255, 60, 0, 0.25)'; ctx.beginPath(); ctx.arc(cx, cy, 48, 0, Math.PI * 2); ctx.fill();
        }
      });
      window.addEventListener('resize', obsInit);
      obsInit(); obsLoop();
    })();

    // ══ SLIME NEURAL BACKGROUND (hero) ═══════════════════════
    (function () {
      const canvas = document.getElementById('hero-canvas');
      const ctx = canvas.getContext('2d', { willReadFrequently: true });
      const SENSOR_ANGLE = Math.PI / 4, SENSOR_DIST = 22, TURN_SPEED = 0.28, MOVE_SPEED = 1.9, PARTICLE_N = 3000;
      let width, height, trailData, particles = [];
      function slimeInit() {
        width = canvas.width = canvas.offsetWidth || window.innerWidth;
        height = canvas.height = canvas.offsetHeight || window.innerHeight;
        ctx.fillStyle = 'black'; ctx.fillRect(0, 0, width, height);
        particles = [];
        for (let i = 0; i < PARTICLE_N; i++) particles.push({ x: Math.random() * width, y: Math.random() * height, angle: Math.random() * Math.PI * 2 });
      }
      function getPixel(x, y) {
        if (x < 0 || x >= width || y < 0 || y >= height) return 0;
        const idx = (Math.floor(y) * width + Math.floor(x)) * 4;
        return trailData[idx + 1];
      }
      function slimeLoop() {
        trailData = ctx.getImageData(0, 0, width, height).data;
        for (let i = 0; i < particles.length; i++) {
          const p = particles[i];
          const v1 = getPixel(p.x + Math.cos(p.angle - SENSOR_ANGLE) * SENSOR_DIST, p.y + Math.sin(p.angle - SENSOR_ANGLE) * SENSOR_DIST);
          const v2 = getPixel(p.x + Math.cos(p.angle) * SENSOR_DIST, p.y + Math.sin(p.angle) * SENSOR_DIST);
          const v3 = getPixel(p.x + Math.cos(p.angle + SENSOR_ANGLE) * SENSOR_DIST, p.y + Math.sin(p.angle + SENSOR_ANGLE) * SENSOR_DIST);
          if (v2 > v1 && v2 > v3) { }
          else if (v2 < v1 && v2 < v3) p.angle += (Math.random() - 0.5) * 2 * TURN_SPEED;
          else if (v1 > v3) p.angle -= TURN_SPEED;
          else if (v3 > v1) p.angle += TURN_SPEED;
          p.x += Math.cos(p.angle) * MOVE_SPEED; p.y += Math.sin(p.angle) * MOVE_SPEED;
          if (p.x < 0 || p.x >= width) p.angle = Math.PI - p.angle;
          if (p.y < 0 || p.y >= height) p.angle = -p.angle;
          ctx.fillStyle = 'rgba(0, 229, 255, 0.45)';
          ctx.fillRect(p.x | 0, p.y | 0, 1, 1);
        }
        ctx.fillStyle = 'rgba(0, 0, 0, 0.048)'; ctx.fillRect(0, 0, width, height);
        requestAnimationFrame(slimeLoop);
      }
      window.addEventListener('resize', slimeInit);
      slimeInit(); slimeLoop();
    })();

    // ══ PARALLAX ═════════════════════════════════════════════
    window.addEventListener('scroll', () => {
      const s = window.scrollY;
      document.querySelectorAll('.hero-h1').forEach(el => { el.style.transform = 'translateY(' + s * .08 + 'px)'; });
    });

    
    // Protocol buttons (local only)
      [
        { cls: 'pc-lock', label: '⬛ ACTIVATE LOCK DOWN', mode: 'LOCK DOWN' },
        { cls: 'pc-amp', label: '🟢 ACTIVATE AMPLIFY', mode: 'AMPLIFY' },
        { cls: 'pc-sel', label: '🟡 ACTIVATE SELECTIVE', mode: 'SELECTIVE' },
        { cls: 'pc-nom', label: '🔵 ACTIVATE NOMINAL', mode: 'NOMINAL' },
      ].forEach(({ cls, label, mode }) => {
        const card = document.querySelector('.' + cls); if (!card) return;
        const btn = document.createElement('button');
        btn.className = 'nx-proto-btn'; btn.textContent = label;
        card.appendChild(btn);
        btn.addEventListener('click', async (e) => {
          e.stopPropagation();
          btn.textContent = '⟳ Activating…'; btn.classList.add('nx-running');
          const res = await 
          btn.classList.remove('nx-running');
          if (res.ok) { btn.textContent = '✓ ' + mode + ' Applied'; btn.classList.add('nx-success'); showToast(mode + ' protocol activated via NEXUS'); }
          else { btn.textContent = '✕ Server error'; btn.classList.add('nx-fail'); showToast('NEXUS: ' + (res.error || 'unknown error'), true); }
          setTimeout(() => { btn.textContent = label; btn.className = 'nx-proto-btn'; }, 3500);
          renderLogs(null);
        });
      });

      
    // END IS_PUBLIC gate — nothing below this line touches localhost
  