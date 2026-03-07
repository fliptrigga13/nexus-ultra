// ╔══════════════════════════════════════════╗
// ║      NEXUS ULTRA v2 // SERVER CORE       ║
// ╚══════════════════════════════════════════╝
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const express = require('express');
const cors = require('cors');
const { exec } = require('child_process');
const cron = require('node-cron');
const nodemailer = require('nodemailer');

// ─── Load .env ────────────────────────────
try {
  const envPath = path.join(__dirname, '.env');
  if (fs.existsSync(envPath)) {
    fs.readFileSync(envPath, 'utf8').split('\n').forEach(line => {
      const [k, ...v] = line.split('=');
      if (k && !k.startsWith('#') && v.length) process.env[k.trim()] = v.join('=').trim();
    });
  }
} catch (_) { }

// ─── Stripe ───────────────────────────────
const STRIPE_SK = process.env.STRIPE_SECRET_KEY || '';
const STRIPE_PK = process.env.STRIPE_PUBLISHABLE_KEY || '';
let stripe = null;
if (STRIPE_SK && !STRIPE_SK.includes('PASTE_YOUR')) {
  try { stripe = require('stripe')(STRIPE_SK); } catch (e) { console.warn('Stripe init failed:', e.message); }
}

const SECRET = process.env.API_SECRET || "Burton";
const HOST = process.env.HOST || "0.0.0.0";
const PORT = parseInt(process.env.PORT || "3000", 10);
const N8N_URL = "http://localhost:5678";

// PUBLIC_URL is resolved dynamically after boot (set by ngrok detection)
let PUBLIC_URL = process.env.PUBLIC_URL || `http://127.0.0.1:${PORT}`;

// ─── Paths ────────────────────────────────
const ROOT = __dirname;
const LOG_FILE = path.join(ROOT, 'nexus.log');
const DROP_DIR = path.join(ROOT, 'drop-zone');
const CAPTURE_DIR = path.join(ROOT, 'captures');
const TABS_FILE = path.join(ROOT, 'tabs.json');
const ACCESS_DB = path.join(ROOT, 'access-tokens.json');

// ─── Bootstrap dirs ───────────────────────
for (const d of [DROP_DIR, CAPTURE_DIR]) {
  if (!fs.existsSync(d)) fs.mkdirSync(d, { recursive: true });
}

// ─── Access Token Store ───────────────────
function loadAccessDB() {
  try { return JSON.parse(fs.readFileSync(ACCESS_DB, 'utf8')); } catch { return {}; }
}
function saveAccessDB(db) {
  fs.writeFileSync(ACCESS_DB, JSON.stringify(db, null, 2));
}
function createAccessToken(email, tier, amount, sessionId) {
  const token = crypto.randomBytes(32).toString('hex');
  const db = loadAccessDB();
  db[token] = { email, tier, amount, sessionId, createdAt: new Date().toISOString(), used: 0 };
  saveAccessDB(db);
  log(`ACCESS TOKEN created for ${email} [${tier}]`);
  return token;
}

// ─── Email Transporter ───────────────────
const EMAIL_USER = process.env.EMAIL_USER || '';
const EMAIL_PASS = process.env.EMAIL_PASS || '';
const EMAIL_FROM = process.env.EMAIL_FROM || 'NEXUS ULTRA <noreply@veilpiercer.com>';

let transporter = null;
if (EMAIL_USER && EMAIL_PASS) {
  transporter = nodemailer.createTransport({
    service: 'gmail',
    auth: { user: EMAIL_USER, pass: EMAIL_PASS }
  });
  log(`Email transport ready: ${EMAIL_USER}`);
}

async function sendAccessEmail(email, tier, amount, token, aiEmailText) {
  if (!transporter) { log('EMAIL SKIP: no email credentials configured'); return false; }
  const accessUrl = `${PUBLIC_URL}/access.html?token=${token}`;
  const subject = `Your VeilPiercer ${tier} Access Is Ready`;
  const text = `${aiEmailText || `Welcome to VeilPiercer ${tier}!`}\n\nAccess your portal here:\n${accessUrl}\n\nThis link is unique to you — keep it safe.\n\n— The NEXUS ULTRA Team`;
  const html = `
    <div style="font-family:Inter,sans-serif;max-width:560px;margin:0 auto;background:#050508;color:#e2e8f0;padding:40px;border-radius:16px;">
      <div style="text-align:center;margin-bottom:32px;">
        <p style="font-size:12px;letter-spacing:0.2em;color:#7c3aed;text-transform:uppercase;font-weight:700;">NEXUS ULTRA</p>
        <h1 style="font-size:28px;font-weight:900;margin:8px 0;">VeilPiercer ${tier}</h1>
        <p style="color:#64748b;">Your access is confirmed</p>
      </div>
      <div style="background:#0d0d14;border:1px solid rgba(255,255,255,0.07);border-radius:12px;padding:24px;margin:24px 0;white-space:pre-wrap;line-height:1.7;font-size:15px;">${aiEmailText || 'Welcome — your access is now active.'}</div>
      <div style="text-align:center;margin:32px 0;">
        <a href="${accessUrl}" style="display:inline-block;padding:16px 32px;background:linear-gradient(135deg,#7c3aed,#9333ea);color:white;text-decoration:none;border-radius:12px;font-weight:700;font-size:16px;">🔓 Open Your Access Portal</a>
      </div>
      <p style="text-align:center;color:#64748b;font-size:12px;">Amount paid: $${((amount || 0) / 100).toFixed(2)} &nbsp;|&nbsp; Tier: ${tier}</p>
    </div>`;
  try {
    await transporter.sendMail({ from: EMAIL_FROM, to: email, subject, text, html });
    log(`EMAIL SENT to ${email} (${tier}) — access link included`);
    return true;
  } catch (e) {
    log(`EMAIL ERROR: ${e.message}`);
    return false;
  }
}

// ─── Logging ──────────────────────────────
function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}`;
  console.log(line);
  try { fs.appendFileSync(LOG_FILE, line + '\n'); } catch (_) { }
}

// ─── VeilPiercer Real-Time Agent Event Engine ───────────────────────────────
// All real system activity is captured here and fed to the dashboard as live data
const AGENT_EVENTS = [];  // ring buffer, max 200
const VP_METRICS = {
  // Visibility — tracks AI call success rates and log throughput
  vis: { total: 0, success: 0, failures: 0, lastEvent: '', latencies: [] },
  // Safety — tracks error catches, recoveries, anomalies
  saf: { catches: 0, failures: 0, recoveries: 0, lastEvent: '' },
  // Privacy — tracks local-only AI calls vs external, token issuance
  priv: { localCalls: 0, externalCalls: 0, tokensIssued: 0, emailsSent: 0, lastEvent: '' },
  startTime: Date.now(),
  totalRuns: 0,
};

function agentEvent(type, pillar, msg, data = {}) {
  VP_METRICS.totalRuns++;
  const ev = { type, pillar, msg, data, ts: new Date().toISOString(), id: VP_METRICS.totalRuns };
  AGENT_EVENTS.push(ev);
  if (AGENT_EVENTS.length > 200) AGENT_EVENTS.shift();

  if (pillar === 'vis') {
    VP_METRICS.vis.total++;
    if (data.ok !== false) VP_METRICS.vis.success++;
    else VP_METRICS.vis.failures++;
    if (data.ms) VP_METRICS.vis.latencies.push(data.ms);
    if (VP_METRICS.vis.latencies.length > 50) VP_METRICS.vis.latencies.shift();
    VP_METRICS.vis.lastEvent = msg;
  } else if (pillar === 'saf') {
    if (data.ok !== false) VP_METRICS.saf.catches++;
    else { VP_METRICS.saf.failures++; VP_METRICS.saf.recoveries++; }
    VP_METRICS.saf.lastEvent = msg;
  } else if (pillar === 'priv') {
    if (data.local) VP_METRICS.priv.localCalls++;
    else VP_METRICS.priv.externalCalls++;
    if (type === 'token_issued') VP_METRICS.priv.tokensIssued++;
    if (type === 'email_sent') VP_METRICS.priv.emailsSent++;
    VP_METRICS.priv.lastEvent = msg;
  }
}

function calcVPScores() {
  const vis = VP_METRICS.vis;
  const saf = VP_METRICS.saf;
  const priv = VP_METRICS.priv;

  // VISIBILITY: success rate + log throughput + latency health
  const visRate = vis.total > 0 ? vis.success / vis.total : 0.78;
  const avgLatMs = vis.latencies.length > 0 ? vis.latencies.reduce((a, b) => a + b, 0) / vis.latencies.length : 0;
  const latScore = avgLatMs > 0 ? Math.max(0.4, 1 - (avgLatMs / 30000)) : 0.78; // 30s = bad
  const visScore = Math.min(1.0, (visRate * 0.6 + latScore * 0.4));

  // SAFETY: catch rate - failure rate
  const safTotal = saf.catches + saf.failures;
  const safRate = safTotal > 0 ? saf.catches / safTotal : 0.82;
  const recovRate = saf.failures > 0 ? Math.min(1, saf.recoveries / saf.failures) : 1.0;
  const safScore = Math.min(1.0, safRate * 0.6 + recovRate * 0.4);

  // PRIVACY: % of AI calls that stayed local (Ollama = perfect privacy)
  const privTotal = priv.localCalls + priv.externalCalls;
  const localRate = privTotal > 0 ? priv.localCalls / privTotal : 1.0;
  const privScore = Math.min(1.0, localRate * 0.85 + 0.15); // min 15% even with all external

  return {
    vis: { score: parseFloat((visScore * 100).toFixed(1)), total: vis.total, success: vis.success, failures: vis.failures, avgLatMs: Math.round(avgLatMs), lastEvent: vis.lastEvent },
    saf: { score: parseFloat((safScore * 100).toFixed(1)), catches: saf.catches, failures: saf.failures, recoveries: saf.recoveries, lastEvent: saf.lastEvent },
    priv: { score: parseFloat((privScore * 100).toFixed(1)), localCalls: priv.localCalls, externalCalls: priv.externalCalls, tokensIssued: priv.tokensIssued, emailsSent: priv.emailsSent, lastEvent: priv.lastEvent },
    uptime: Math.floor((Date.now() - VP_METRICS.startTime) / 1000),
    totalEvents: AGENT_EVENTS.length,
    totalRuns: VP_METRICS.totalRuns,
  };
}

// GET /veilpiercer/metrics — live scores for dashboard
// Public endpoint so dashboard can read without API key


// ─── Script whitelist (declared early — used by scheduler + routes) ──
const SCRIPTS = {
  'force-stabilize': 'force-stabilize.ps1',
  'execute': 'execute.ps1',
  'trigger-n8n': 'trigger-n8n.ps1',
  'capture': 'capture.ps1',
  'watch-trigger': 'watch-trigger.ps1',
  'setup-autostart': 'setup-autostart.ps1',
};

function scriptPath(action) {
  if (!SCRIPTS[action]) return null;
  const p = path.resolve(ROOT, 'local-scripts', SCRIPTS[action]);
  return p.startsWith(path.resolve(ROOT)) ? p : null;
}

// ─── Drop Zone Watcher ────────────────────
const dropLog = [];
try {
  fs.watch(DROP_DIR, { persistent: false }, (event, filename) => {
    if (!filename || event !== 'rename') return;
    const fp = path.join(DROP_DIR, filename);
    if (!fs.existsSync(fp)) return;
    const entry = { file: filename, time: new Date().toISOString(), processed: false, output: '' };
    dropLog.push(entry);
    log(`DROP_ZONE: ${filename}`);
    const script = path.join(ROOT, 'local-scripts', 'watch-trigger.ps1');
    exec(`powershell -NoProfile -ExecutionPolicy Bypass -File "${script}" -FilePath "${fp}"`,
      { timeout: 30000 }, (err, stdout) => {
        entry.processed = true;
        entry.output = err ? err.message : stdout.trim();
        log(`DROP_ZONE processed: ${filename}`);
      });
  });
  log('Drop zone watcher: ACTIVE');
} catch (e) { log('Drop zone watcher error: ' + e.message); }

// ─── Scheduler ────────────────────────────
const jobs = {};
let jid = 1;

function addJob(expression, action, label) {
  const id = jid++;
  const script = path.join(ROOT, 'local-scripts', (SCRIPTS[action] || 'force-stabilize.ps1'));
  const task = cron.schedule(expression, () => {
    log(`SCHED job#${id} "${label}" → ${action}`);
    exec(`powershell -NoProfile -ExecutionPolicy Bypass -File "${script}"`,
      { timeout: 60000 }, (err, stdout) => {
        log(`SCHED job#${id} done: ${err ? err.message : stdout.trim().split('\n')[0]}`);
      });
  });
  jobs[id] = { id, expression, action, label, created: new Date().toISOString() };
  jobs[id]._task = task;
  log(`SCHED registered job#${id} "${label}" (${expression})`);
  return id;
}

// Default: hourly scan
addJob('0 * * * *', 'force-stabilize', 'Hourly System Scan');

// ─── Express ──────────────────────────────
const app = express();
app.use(cors());
app.use(express.json());
app.use(express.static(ROOT));

function auth(req, res, next) {
  if (req.headers['x-api-key'] !== SECRET)
    return res.status(403).json({ ok: false, error: 'Forbidden' });
  next();
}

// ── POST /run ────────────────────────────
app.post('/run', auth, (req, res) => {
  const action = req.body?.action;
  const sp = scriptPath(action);
  if (!sp) return res.status(400).json({ ok: false, error: 'Invalid action' });
  log(`RUN: ${action}`);
  exec(`powershell -NoProfile -ExecutionPolicy Bypass -File "${sp}"`,
    { timeout: 60000 }, (err, stdout, stderr) => {
      if (err) { log(`RUN ERR ${action}: ${stderr || err.message}`); return res.status(500).json({ ok: false, error: stderr || err.message }); }
      log(`RUN OK: ${action}`);
      return res.json({ ok: true, output: stdout.trim() });
    });
});

// ── GET /status ──────────────────────────
let storedTabs = null;
try { if (fs.existsSync(TABS_FILE)) storedTabs = JSON.parse(fs.readFileSync(TABS_FILE, 'utf8')); } catch (_) { }

app.get('/status', (req, res) => {
  res.json({
    ok: true,
    status: 'NEXUS ULTRA ONLINE',
    port: PORT,
    timestamp: new Date().toISOString(),
    uptime: process.uptime().toFixed(1) + 's',
    tabs_loaded: Array.isArray(storedTabs) ? storedTabs.length : 0,
    scheduled_jobs: Object.keys(jobs).length,
    drop_zone_files: (() => { try { return fs.readdirSync(DROP_DIR).length; } catch (_) { return 0; } })(),
    captures: (() => { try { return fs.readdirSync(CAPTURE_DIR).length; } catch (_) { return 0; } })(),
    log_size_kb: (() => { try { return (fs.statSync(LOG_FILE).size / 1024).toFixed(1); } catch (_) { return 0; } })(),
    access_tokens: (() => { try { return Object.keys(loadAccessDB()).length; } catch { return 0; } })(),
    email_configured: !!(EMAIL_USER && EMAIL_PASS),
  });
});

// ── GET /access/verify ───────────────────
// Called by access.html to verify a token and return buyer data
app.get('/access/verify', (req, res) => {
  const { token } = req.query;
  if (!token) return res.status(400).json({ ok: false, error: 'token required' });
  const db = loadAccessDB();
  const entry = db[token];
  if (!entry) return res.status(404).json({ ok: false, error: 'Token not found or expired' });
  // Increment usage count
  entry.used = (entry.used || 0) + 1;
  entry.lastAccessed = new Date().toISOString();
  saveAccessDB(db);
  log(`ACCESS VERIFIED: ${entry.email} [${entry.tier}] (visit #${entry.used})`);
  res.json({ ok: true, email: entry.email, tier: entry.tier, amount: entry.amount, welcomeEmail: entry.welcomeEmail || null });
});

// ── POST /access/create ──────────────────
// Create an access token manually (for testing or admin use)
app.post('/access/create', auth, async (req, res) => {
  const { email, tier, amount, sessionId, sendEmail } = req.body || {};
  if (!email || !tier) return res.status(400).json({ ok: false, error: 'email and tier required' });
  const token = createAccessToken(email, tier, amount || 0, sessionId || 'manual');
  let emailSent = false;
  let aiEmail = '';
  if (sendEmail) {
    // Generate AI welcome email
    try {
      const payload = JSON.stringify({ model: 'llama3.2:1b', system: 'You are a friendly VeilPiercer assistant. Write concise welcome emails. No markdown.', prompt: `Write a short welcome email (max 100 words) for a new VeilPiercer ${tier} customer (${email}). They paid $${((amount || 0) / 100).toFixed(2)}. Sign off as "The NEXUS ULTRA Team".`, stream: false });
      const http = require('http');
      const result = await new Promise((resolve, reject) => {
        const r = http.request({ hostname: 'localhost', port: 11434, path: '/api/generate', method: 'POST', headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) } }, resp => { let b = ''; resp.on('data', d => b += d); resp.on('end', () => { try { resolve(JSON.parse(b)); } catch { resolve({}); } }); });
        r.on('error', reject); r.setTimeout(30000, () => { r.destroy(); reject(new Error('timeout')); }); r.write(payload); r.end();
      });
      aiEmail = result.response || '';
      // Store AI email in token
      const db = loadAccessDB(); if (db[token]) { db[token].welcomeEmail = aiEmail; saveAccessDB(db); }
    } catch (e) { log(`AI email error: ${e.message}`); }
    emailSent = await sendAccessEmail(email, tier, amount || 0, token, aiEmail);
  }
  const accessUrl = `${PUBLIC_URL}/access.html?token=${token}`;
  res.json({ ok: true, token, accessUrl, emailSent });
});

// ── GET /access/list ─────────────────────
// Admin view of all issued access tokens
app.get('/access/list', auth, (req, res) => {
  const db = loadAccessDB();
  const list = Object.entries(db).map(([token, d]) => ({ token: token.substring(0, 8) + '...', email: d.email, tier: d.tier, amount: d.amount, used: d.used, createdAt: d.createdAt }));
  res.json({ ok: true, count: list.length, tokens: list });
});



// ── GET /logs ────────────────────────────
app.get('/logs', (req, res) => {
  const lines = Math.min(parseInt(req.query.lines) || 100, 500);
  try {
    if (!fs.existsSync(LOG_FILE)) return res.json({ ok: true, lines: [] });
    const all = fs.readFileSync(LOG_FILE, 'utf8').split('\n').filter(Boolean);
    res.json({ ok: true, lines: all.slice(-lines), total: all.length });
  } catch (e) { res.status(500).json({ ok: false, error: e.message }); }
});

// ── POST /capture ────────────────────────
app.post('/capture', auth, (req, res) => {
  const sp = path.join(ROOT, 'local-scripts', 'capture.ps1');
  log('CAPTURE triggered');
  exec(`powershell -NoProfile -ExecutionPolicy Bypass -File "${sp}"`,
    { timeout: 30000 }, (err, stdout, stderr) => {
      if (err) return res.status(500).json({ ok: false, error: stderr || err.message });
      res.json({ ok: true, output: stdout.trim() });
    });
});

// ── GET /captures ────────────────────────
app.get('/captures', auth, (req, res) => {
  try {
    const files = fs.readdirSync(CAPTURE_DIR).map(f => {
      const s = fs.statSync(path.join(CAPTURE_DIR, f));
      return { name: f, size: s.size, modified: s.mtime };
    }).sort((a, b) => new Date(b.modified) - new Date(a.modified));
    res.json({ ok: true, files });
  } catch (e) { res.status(500).json({ ok: false, error: e.message }); }
});

// ── GET /n8n/status ──────────────────────
app.get('/n8n/status', async (req, res) => {
  try {
    const r = await fetch(`${N8N_URL}/healthz`, { signal: AbortSignal.timeout(4000) });
    const text = await r.text();
    res.json({ ok: true, online: r.ok, health: text, url: N8N_URL });
  } catch (e) {
    res.json({ ok: false, online: false, error: 'n8n not reachable on port 5678', url: N8N_URL });
  }
});

// ── GET /dropzone ────────────────────────
app.get('/dropzone', (req, res) => {
  try {
    const files = fs.readdirSync(DROP_DIR).map(f => {
      const s = fs.statSync(path.join(DROP_DIR, f));
      return { name: f, size: s.size, modified: s.mtime };
    }).sort((a, b) => new Date(b.modified) - new Date(a.modified));
    res.json({ ok: true, files, recent: dropLog.slice(-20) });
  } catch (e) { res.status(500).json({ ok: false, error: e.message }); }
});

// ── POST /dropzone/upload ────────────────
app.post('/dropzone/upload', auth, express.raw({ type: '*/*', limit: '50mb' }), (req, res) => {
  const name = req.query.name || `upload_${Date.now()}.bin`;
  const safe = path.basename(name);
  const fp = path.join(DROP_DIR, safe);
  try {
    fs.writeFileSync(fp, req.body);
    log(`DROPZONE upload: ${safe} (${req.body.length} bytes)`);
    res.json({ ok: true, file: safe, size: req.body.length });
  } catch (e) { res.status(500).json({ ok: false, error: e.message }); }
});

// ── DELETE /dropzone/:file ───────────────
app.delete('/dropzone/:file', auth, (req, res) => {
  const fp = path.join(DROP_DIR, path.basename(req.params.file));
  try { fs.unlinkSync(fp); res.json({ ok: true }); }
  catch (e) { res.status(500).json({ ok: false, error: e.message }); }
});

// ── GET /schedule ────────────────────────
app.get('/schedule', auth, (req, res) => {
  const list = Object.values(jobs).map(({ id, expression, action, label, created }) =>
    ({ id, expression, action, label, created }));
  res.json({ ok: true, jobs: list });
});

// ── POST /schedule ───────────────────────
app.post('/schedule', auth, (req, res) => {
  const { expression, action = 'force-stabilize', label } = req.body || {};
  if (!expression || !label) return res.status(400).json({ ok: false, error: 'expression and label required' });
  if (!cron.validate(expression)) return res.status(400).json({ ok: false, error: 'Invalid cron expression' });
  const id = addJob(expression, action, label);
  res.json({ ok: true, id });
});

// ── DELETE /schedule/:id ─────────────────
app.delete('/schedule/:id', auth, (req, res) => {
  const id = parseInt(req.params.id);
  if (!jobs[id]) return res.status(404).json({ ok: false, error: 'Job not found' });
  jobs[id]._task.stop();
  delete jobs[id];
  log(`SCHED removed job#${id}`);
  res.json({ ok: true, deleted: id });
});

// ── Tabs ─────────────────────────────────
app.post('/tabs', auth, (req, res) => {
  if (!req.body?.edge_all_open_tabs) return res.status(400).json({ ok: false, error: 'missing edge_all_open_tabs' });
  storedTabs = req.body.edge_all_open_tabs;
  try { const t = TABS_FILE + '.tmp'; fs.writeFileSync(t, JSON.stringify(storedTabs, null, 2)); fs.renameSync(t, TABS_FILE); } catch (_) { }
  res.json({ ok: true, stored: Array.isArray(storedTabs) ? storedTabs.length : 0 });
});
app.get('/tabs', (req, res) => res.json({ ok: true, edge_all_open_tabs: storedTabs || [] }));
app.delete('/tabs', auth, (req, res) => {
  storedTabs = null;
  try { if (fs.existsSync(TABS_FILE)) fs.unlinkSync(TABS_FILE); } catch (_) { }
  res.json({ ok: true, cleared: true });
});

// ── CMD whitelist ────────────────────────
const CMD_WL = ['dir', 'type', 'echo', 'whoami', 'hostname', 'git --version', 'node --version', 'npm --version', 'ipconfig /all', 'tasklist', 'systeminfo'];
app.post('/cmd', auth, (req, res) => {
  const cmd = String(req.body?.cmd || '').trim();
  if (!CMD_WL.some(p => cmd === p || cmd.startsWith(p + ' ')))
    return res.status(400).json({ ok: false, error: 'command not allowed' });
  log(`CMD: ${cmd}`);
  exec(cmd, { windowsHide: true, timeout: 30000 }, (err, stdout, stderr) => {
    if (err) return res.status(500).json({ ok: false, error: stderr || err.message });
    res.json({ ok: true, output: stdout.trim() });
  });
});

// ── n8n integration ──────────────────────

// helper: fire a named n8n webhook (NEXUS → n8n)
async function nexusTrigger(name, payload = {}) {
  const url = `${N8N_URL}/webhook/${name}`;
  try {
    const http = require('http');
    const body = JSON.stringify({ source: 'nexus-ultra', event: name, ts: new Date().toISOString(), ...payload });
    await new Promise((resolve, reject) => {
      const req = http.request(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) }
      }, res => { res.resume(); res.on('end', resolve); });
      req.on('error', reject);
      req.setTimeout(3000, () => { req.destroy(); reject(new Error('timeout')); });
      req.write(body); req.end();
    });
    log(`N8N → ${name}: OK`);
    return true;
  } catch (e) {
    log(`N8N → ${name}: ${e.message}`);
    return false;
  }
}

// GET /n8n/status — check if n8n is running
app.get('/n8n/status', async (req, res) => {
  try {
    const http = require('http');
    await new Promise((resolve, reject) => {
      const r = http.get(`${N8N_URL}/healthz`, resp => { resp.resume(); resolve(); });
      r.on('error', reject);
      r.setTimeout(2000, () => { r.destroy(); reject(new Error('timeout')); });
    });
    res.json({ ok: true, status: 'online', url: N8N_URL });
  } catch {
    res.json({ ok: false, status: 'offline', url: N8N_URL });
  }
});

// POST /n8n/trigger — manually fire any n8n webhook from NEXUS dashboard
// Body: { "webhook": "payment-confirmed", "data": { ... } }
app.post('/n8n/trigger', auth, async (req, res) => {
  const { webhook, data } = req.body || {};
  if (!webhook) return res.status(400).json({ ok: false, error: 'webhook name required' });
  const fired = await nexusTrigger(webhook, data || {});
  res.json({ ok: fired, webhook });
});

// POST /n8n/action — n8n calls NEXUS to run a script or action
// n8n HTTP Request node → POST http://127.0.0.1:3000/n8n/action
// Body: { "action": "force-stabilize" | "capture" }
app.post('/n8n/action', async (req, res) => {
  const { action, params } = req.body || {};
  log(`N8N ACTION: ${action}`);
  if (action === 'capture') {
    const ts = new Date().toISOString();
    const file = path.join(CAPTURE_DIR, `n8n-capture-${ts.replace(/[:.]/g, '-')}.json`);
    fs.writeFileSync(file, JSON.stringify({ ts, source: 'n8n', params }, null, 2));
    log(`N8N CAPTURE saved: ${file}`);
    return res.json({ ok: true, action, file });
  }
  const allowed = ['force-stabilize', 'system-scan'];
  if (!allowed.includes(action)) return res.status(400).json({ ok: false, error: 'action not allowed' });
  const ps1 = path.join(ROOT, 'local-scripts', `${action}.ps1`);
  exec(`powershell -ExecutionPolicy Bypass -File "${ps1}"`, { windowsHide: true, timeout: 30000 }, (err, out, stderr) => {
    if (err) return res.status(500).json({ ok: false, error: stderr || err.message });
    res.json({ ok: true, action, output: out.trim() });
  });
});

// ── Stripe: public key ────────────────────
app.get('/stripe/config', (req, res) => {
  if (!STRIPE_PK) return res.status(503).json({ ok: false, error: 'Stripe not configured' });
  res.json({ ok: true, publishableKey: STRIPE_PK });
});


// ── Stripe: Checkout Session ──────────────
const PRODUCTS = {
  Starter: { name: 'VeilPiercer Starter', amount: 4700, description: 'Full dashboard + 4 protocol modes + source code' },
  Pro: { name: 'VeilPiercer Pro', amount: 9700, description: 'Everything in Starter + safeLog + simulation model + all buyer decks' },
  Agency: { name: 'VeilPiercer Agency', amount: 19700, description: 'Everything in Pro + white-label rights + client pitch deck' },
};

app.post('/stripe/create-checkout-session', async (req, res) => {
  if (!stripe) return res.status(503).json({ ok: false, error: 'Stripe secret key not configured. Add sk_live_... to .env and restart.' });
  const { tier, email } = req.body || {};
  const product = PRODUCTS[tier];
  if (!product) return res.status(400).json({ ok: false, error: 'Invalid tier' });

  try {
    const session = await stripe.checkout.sessions.create({
      payment_method_types: ['card'],
      customer_email: email || undefined,
      line_items: [{
        price_data: {
          currency: 'usd',
          product_data: {
            name: product.name,
            description: product.description,
            images: [],
          },
          unit_amount: product.amount,
        },
        quantity: 1,
      }],
      mode: 'payment',
      success_url: `${PUBLIC_URL}/access.html?session_id={CHECKOUT_SESSION_ID}&tier=${tier}`,
      cancel_url: `${PUBLIC_URL}/veilpiercer-pitch.html#pricing`,
      metadata: { tier, source: 'veilpiercer-pitch' },
    });

    log(`STRIPE CHECKOUT: session created — ${tier} $${(product.amount / 100).toFixed(2)} — ${email || 'no email'}`);
    res.json({ ok: true, url: session.url, sessionId: session.id });
  } catch (e) {
    log(`STRIPE ERROR: ${e.message}`);
    res.status(500).json({ ok: false, error: e.message });
  }
});

// ── Stripe: Confirm session (called from success page) ──
app.get('/stripe/confirm-session', async (req, res) => {
  if (!stripe) return res.status(503).json({ ok: false, error: 'Stripe not configured' });
  const { session_id } = req.query;
  if (!session_id) return res.status(400).json({ ok: false, error: 'No session_id' });
  try {
    const session = await stripe.checkout.sessions.retrieve(session_id);
    const paid = session.payment_status === 'paid';
    if (paid) log(`STRIPE PAID: ${session.customer_email} — ${session.metadata?.tier} — $${(session.amount_total / 100).toFixed(2)}`);
    res.json({ ok: true, paid, email: session.customer_email, tier: session.metadata?.tier, amount: session.amount_total });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

// ── Stripe: Webhook ───────────────────────
// Raw body needed for signature verification
app.post('/stripe/webhook', express.raw({ type: 'application/json' }), (req, res) => {
  const sig = req.headers['stripe-signature'];
  const secret = process.env.STRIPE_WEBHOOK_SECRET || '';
  let event;

  if (secret) {
    try {
      event = stripe.webhooks.constructEvent(req.body, sig, secret);
    } catch (e) {
      log(`WEBHOOK signature error: ${e.message}`);
      return res.status(400).send(`Webhook Error: ${e.message}`);
    }
  } else {
    // No webhook secret configured — parse directly (not verified)
    try { event = JSON.parse(req.body.toString()); } catch { return res.status(400).send('Bad payload'); }
  }

  switch (event.type) {
    case 'checkout.session.completed': {
      const s = event.data.object;
      log(`WEBHOOK: checkout.session.completed — ${s.customer_email} — $${(s.amount_total / 100).toFixed(2)} — ${s.metadata?.tier}`);
      // Fire n8n workflow for post-payment automation
      nexusTrigger('payment-confirmed', {
        email: s.customer_email,
        tier: s.metadata?.tier,
        amount: s.amount_total,
        sessionId: s.id,
      });
      break;
    }
    case 'payment_intent.succeeded':
      log(`WEBHOOK: payment_intent.succeeded — ${event.data.object.id}`);
      break;
    case 'payment_intent.payment_failed':
      log(`WEBHOOK: payment_intent.payment_failed — ${event.data.object.id}`);
      break;
    default:
      log(`WEBHOOK: unhandled event ${event.type}`);
  }

  res.json({ received: true });
});

// ── Ollama Integration ────────────────────
const OLLAMA_URL = process.env.OLLAMA_URL || 'http://localhost:11434';
const OLLAMA_MODEL = process.env.OLLAMA_MODEL || 'llama3:latest';

// ── VeilPiercer Live API ──────────────────
// GET /veilpiercer/metrics — live pillar scores from real system activity
app.get('/veilpiercer/metrics', (req, res) => {
  res.json({ ok: true, ...calcVPScores(), timestamp: new Date().toISOString() });
});

// GET /veilpiercer/events — last N real agent events
app.get('/veilpiercer/events', (req, res) => {
  const n = Math.min(parseInt(req.query.n) || 50, 200);
  res.json({ ok: true, events: AGENT_EVENTS.slice(-n).reverse(), total: AGENT_EVENTS.length });
});

// POST /veilpiercer/event — allow external systems to push agent events
app.post('/veilpiercer/event', (req, res) => {
  const { type = 'external', pillar = 'vis', msg = 'external_event', data = {} } = req.body || {};
  agentEvent(type, pillar, msg, data);
  res.json({ ok: true, totalEvents: AGENT_EVENTS.length });
});


// GET /ollama/status
app.get('/ollama/status', async (req, res) => {
  try {
    const http = require('http');
    await new Promise((resolve, reject) => {
      const r = http.get(OLLAMA_URL, resp => { resp.resume(); resolve(); });
      r.on('error', reject);
      r.setTimeout(2000, () => { r.destroy(); reject(new Error('timeout')); });
    });
    res.json({ ok: true, status: 'online', url: OLLAMA_URL, model: OLLAMA_MODEL });
  } catch {
    res.json({ ok: false, status: 'offline', url: OLLAMA_URL });
  }
});

// GET /ollama/models
app.get('/ollama/models', async (req, res) => {
  try {
    const http = require('http');
    const data = await new Promise((resolve, reject) => {
      const r = http.get(`${OLLAMA_URL}/api/tags`, resp => {
        let body = '';
        resp.on('data', d => body += d);
        resp.on('end', () => resolve(JSON.parse(body)));
      });
      r.on('error', reject);
    });
    res.json({ ok: true, models: data.models.map(m => ({ name: m.name, size: m.size })) });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

// POST /ollama/chat — STREAMING proxy for /api/chat (used by Bot Mind)
// Browser hits port 3000 (same origin) → NEXUS pipes to Ollama 11434 → streams NDJSON back
app.post('/ollama/chat', (req, res) => {
  const http = require('http');
  const payload = JSON.stringify(req.body);
  const payloadBuf = Buffer.from(payload, 'utf8');
  res.setHeader('Content-Type', 'application/x-ndjson');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('X-Accel-Buffering', 'no');
  res.setHeader('Content-Encoding', 'identity');
  const options = {
    hostname: '127.0.0.1',
    port: 11434,
    path: '/api/chat',
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Content-Length': payloadBuf.length
    }
  };
  const ollamaReq = http.request(options, (ollamaRes) => {
    res.flushHeaders();
    ollamaRes.pipe(res);
    ollamaRes.on('error', (e) => { log('OLLAMA CHAT PIPE ERR: ' + e.message); res.end(); });
  });
  ollamaReq.on('error', (e) => {
    log('OLLAMA CHAT CONNECT ERR: ' + e.message);
    if (!res.headersSent) res.status(502).end(JSON.stringify({ error: e.message }));
    else res.end();
  });
  ollamaReq.setTimeout(300000, () => {
    log('OLLAMA CHAT TIMEOUT');
    ollamaReq.destroy();
  });
  ollamaReq.write(payloadBuf);
  ollamaReq.end();
});

// POST /ollama/generate — proxy a prompt to local Ollama LLM
// Body: { "prompt": "...", "model": "llama3:latest", "system": "..." }
app.post('/ollama/generate', async (req, res) => {
  const { prompt, model, system } = req.body || {};
  if (!prompt) return res.status(400).json({ ok: false, error: 'prompt required' });
  const useModel = model || OLLAMA_MODEL;
  try {
    const t0 = Date.now();
    const https = require('http');
    const payload = JSON.stringify({ model: useModel, prompt, system: system || '', stream: false });
    const data = await new Promise((resolve, reject) => {
      const options = {
        hostname: '127.0.0.1', port: 11434, path: '/api/generate', method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) }
      };
      const r = https.request(options, resp => {
        let body = '';
        resp.on('data', d => body += d);
        resp.on('end', () => { try { resolve(JSON.parse(body)); } catch { reject(new Error('Bad JSON')); } });
      });
      r.on('error', reject);
      r.setTimeout(60000, () => { r.destroy(); reject(new Error('Ollama timeout after 60s')); });
      r.write(payload); r.end();
    });
    const ms = Date.now() - t0;
    log(`OLLAMA [${useModel}]: "${prompt.substring(0, 60)}..." → ${data.response?.length} chars in ${ms}ms`);
    agentEvent('ollama_generate', 'vis', `chain_trace: ollama [${useModel}] → ${data.response?.length || 0} chars | ${ms}ms`, { ok: true, ms, local: true });
    agentEvent('ollama_local', 'priv', `pii_safe: Ollama local call — zero data left device`, { local: true });
    res.json({ ok: true, response: data.response, model: useModel, done: data.done });
  } catch (e) {
    log(`OLLAMA ERROR: ${e.message}`);
    agentEvent('ollama_error', 'vis', `signal_gap: ollama error — ${e.message}`, { ok: false });
    agentEvent('ollama_error', 'saf', `catch_gate: ollama failure caught → error returned safely`, { ok: false });
    res.status(500).json({ ok: false, error: e.message });
  }
});

// POST /ollama/agent — run a structured AI agent task
// Body: { "task": "write-welcome-email", "data": { email, tier, amount } }
const AGENT_PROMPTS = {
  'write-welcome-email': (d) => ({
    system: 'You are a friendly but authoritative AI assistant for VeilPiercer, an elite AI agent observatory. Write concise, compelling emails. No markdown.',
    prompt: `Write a short welcome email (max 150 words) for a new VeilPiercer ${d.tier} customer. Their email is ${d.email}. They paid $${((d.amount || 0) / 100).toFixed(2)}. Make it feel exclusive and exciting. Include: welcome, what they unlocked, a hint about next steps. Sign off as "The NEXUS ULTRA Team".`
  }),
  'analyze-logs': (d) => ({
    system: 'You are a system analyst. Summarize logs concisely, flag issues, and suggest actions.',
    prompt: `Analyze these NEXUS system logs and give a 3-bullet summary with any warnings:\n\n${(d.logs || []).slice(-20).join('\n')}`
  }),
  'sales-summary': (d) => ({
    system: 'You are a business analyst. Give sharp, data-driven summaries.',
    prompt: `Write a daily sales summary for VeilPiercer. Data: ${JSON.stringify(d)}. Include total revenue, top tier, and one actionable insight. Max 100 words.`
  }),
};

app.post('/ollama/agent', async (req, res) => {
  const { task, data, model } = req.body || {};
  const promptFn = AGENT_PROMPTS[task];
  if (!promptFn) return res.status(400).json({ ok: false, error: `Unknown task. Available: ${Object.keys(AGENT_PROMPTS).join(', ')}` });
  const { system, prompt } = promptFn(data || {});
  const useModel = model || OLLAMA_MODEL;
  try {
    const payload = JSON.stringify({ model: useModel, system, prompt, stream: false });
    const http = require('http');
    const result = await new Promise((resolve, reject) => {
      const options = {
        hostname: 'localhost', port: 11434, path: '/api/generate', method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) }
      };
      const r = http.request(options, resp => {
        let body = '';
        resp.on('data', d => body += d);
        resp.on('end', () => { try { resolve(JSON.parse(body)); } catch { reject(new Error('Bad JSON')); } });
      });
      r.on('error', reject);
      r.setTimeout(60000, () => { r.destroy(); reject(new Error('timeout')); });
      r.write(payload); r.end();
    });
    log(`OLLAMA AGENT [${task}]: complete (${result.response?.length} chars)`);
    res.json({ ok: true, task, response: result.response, model: useModel });
  } catch (e) {
    log(`OLLAMA AGENT ERROR: ${e.message}`);
    res.status(500).json({ ok: false, error: e.message });
  }
});

// ── Gemini Integration ──────────────────
const GEMINI_API_KEY = process.env.GEMINI_API_KEY || '';
const GEMINI_MODEL = process.env.GEMINI_MODEL || 'gemini-2.0-flash';
const GEMINI_BASE = 'https://generativelanguage.googleapis.com/v1beta';

// GET /gemini/status
app.get('/gemini/status', (req, res) => {
  const configured = !!(GEMINI_API_KEY && !GEMINI_API_KEY.includes('PASTE'));
  res.json({ ok: configured, status: configured ? 'configured' : 'missing_key', model: GEMINI_MODEL });
});

// POST /gemini/generate — send prompt to Gemini free API
// Body: { "prompt": "...", "system": "..." }
app.post('/gemini/generate', async (req, res) => {
  if (!GEMINI_API_KEY) return res.status(503).json({ ok: false, error: 'GEMINI_API_KEY not set in .env' });
  const { prompt, system } = req.body || {};
  if (!prompt) return res.status(400).json({ ok: false, error: 'prompt required' });
  try {
    const https = require('https');
    const payload = JSON.stringify({
      system_instruction: system ? { parts: [{ text: system }] } : undefined,
      contents: [{ parts: [{ text: prompt }] }],
      generationConfig: { maxOutputTokens: 1024, temperature: 0.7 }
    });
    const data = await new Promise((resolve, reject) => {
      const url = `${GEMINI_BASE}/models/${GEMINI_MODEL}:generateContent?key=${GEMINI_API_KEY}`;
      const u = new URL(url);
      const options = {
        hostname: u.hostname, path: u.pathname + u.search, method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) }
      };
      const r = https.request(options, resp => {
        let body = '';
        resp.on('data', d => body += d);
        resp.on('end', () => { try { resolve(JSON.parse(body)); } catch { reject(new Error('Bad JSON')); } });
      });
      r.on('error', reject);
      r.setTimeout(30000, () => { r.destroy(); reject(new Error('Gemini timeout')); });
      r.write(payload); r.end();
    });
    if (data.error) throw new Error(data.error.message);
    const text = data.candidates?.[0]?.content?.parts?.[0]?.text || '';
    log(`GEMINI [${GEMINI_MODEL}]: "${prompt.substring(0, 50)}..." → ${text.length} chars`);
    res.json({ ok: true, response: text, model: GEMINI_MODEL });
  } catch (e) {
    log(`GEMINI ERROR: ${e.message}`);
    res.status(500).json({ ok: false, error: e.message });
  }
});

// POST /gemini/agent — same structured tasks as Ollama but via Gemini
app.post('/gemini/agent', async (req, res) => {
  if (!GEMINI_API_KEY) return res.status(503).json({ ok: false, error: 'GEMINI_API_KEY not set in .env' });
  const { task, data } = req.body || {};
  const promptFn = AGENT_PROMPTS[task];
  if (!promptFn) return res.status(400).json({ ok: false, error: `Unknown task. Available: ${Object.keys(AGENT_PROMPTS).join(', ')}` });
  const { system, prompt } = promptFn(data || {});
  try {
    const https = require('https');
    const payload = JSON.stringify({
      system_instruction: { parts: [{ text: system }] },
      contents: [{ parts: [{ text: prompt }] }],
      generationConfig: { maxOutputTokens: 1024, temperature: 0.7 }
    });
    const result = await new Promise((resolve, reject) => {
      const url = `${GEMINI_BASE}/models/${GEMINI_MODEL}:generateContent?key=${GEMINI_API_KEY}`;
      const u = new URL(url);
      const options = {
        hostname: u.hostname, path: u.pathname + u.search, method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) }
      };
      const r = https.request(options, resp => {
        let body = '';
        resp.on('data', d => body += d);
        resp.on('end', () => { try { resolve(JSON.parse(body)); } catch { reject(new Error('Bad JSON')); } });
      });
      r.on('error', reject);
      r.setTimeout(30000, () => { r.destroy(); reject(new Error('timeout')); });
      r.write(payload); r.end();
    });
    if (result.error) throw new Error(result.error.message);
    const text = result.candidates?.[0]?.content?.parts?.[0]?.text || '';
    log(`GEMINI AGENT [${task}]: complete (${text.length} chars)`);
    res.json({ ok: true, task, response: text, model: GEMINI_MODEL });
  } catch (e) {
    log(`GEMINI AGENT ERROR: ${e.message}`);
    res.status(500).json({ ok: false, error: e.message });
  }
});

// ── Boot ─────────────────────────────────
app.listen(PORT, HOST, async () => {
  log('╔══════════════════════════════════════════╗');
  log('║      NEXUS ULTRA v2 // ONLINE            ║');
  log('╚══════════════════════════════════════════╝');
  log(`Dashboard   → http://${HOST}:${PORT}`);
  log(`Stripe cfg  → ${STRIPE_PK ? 'pk loaded (' + (STRIPE_PK.startsWith('pk_live') ? 'LIVE' : 'TEST') + ')' : 'NOT SET'}`);
  log(`Stripe sk   → ${stripe ? 'ACTIVE' : 'NOT SET'}`);
  log(`Ollama      → ${OLLAMA_URL} (model: ${OLLAMA_MODEL})`);
  log(`n8n         → ${N8N_URL}`);
  log(`Email       → ${EMAIL_USER || 'NOT SET'}`);
  log(`Scheduled   → ${Object.keys(jobs).length} job(s) active`);

  // ── Auto-detect ngrok public URL + resend broken links ──
  setTimeout(async () => {
    try {
      const http = require('http');
      const ngrokData = await new Promise((resolve, reject) => {
        const r = http.get('http://localhost:4040/api/tunnels', resp => {
          let body = ''; resp.on('data', d => body += d); resp.on('end', () => { try { resolve(JSON.parse(body)); } catch { reject(); } });
        });
        r.on('error', reject); r.setTimeout(2000, () => { r.destroy(); reject(); });
      });
      const tunnel = ngrokData.tunnels?.find(t => t.proto === 'https');
      if (tunnel) {
        PUBLIC_URL = tunnel.public_url;
        log(`PUBLIC URL  → ${PUBLIC_URL} (ngrok live)`);

        // Save to Desktop
        const desktopFile = require('path').join(require('os').homedir(), 'Desktop', 'VEILPIERCER-LIVE-URL.txt');
        require('fs').writeFileSync(desktopFile,
          `NEXUS PUBLIC URL\n${PUBLIC_URL}\n\nAccess Portal: ${PUBLIC_URL}/access.html\nDashboard: ${PUBLIC_URL}\n\nUpdated: ${new Date().toISOString()}`);
        log(`URL saved   → Desktop/VEILPIERCER-LIVE-URL.txt`);

        // ── Resend fresh links to buyers who haven't opened their portal yet ──
        if (transporter) {
          const db = loadAccessDB();
          const unseen = Object.entries(db).filter(([, d]) => (d.used || 0) < 2 && d.email);
          if (unseen.length > 0) {
            log(`RESEND: ${unseen.length} buyer(s) with unvisited portals — refreshing links...`);
            for (const [token, d] of unseen) {
              const accessUrl = `${PUBLIC_URL}/access.html?token=${token}`;
              const subject = `Your VeilPiercer ${d.tier} Access Link (Updated)`;
              const html = `
                <div style="font-family:Inter,sans-serif;max-width:560px;margin:0 auto;background:#050508;color:#e2e8f0;padding:40px;border-radius:16px;">
                  <p style="font-size:12px;letter-spacing:0.2em;color:#7c3aed;text-transform:uppercase;font-weight:700;text-align:center;">NEXUS ULTRA</p>
                  <h2 style="text-align:center;margin:16px 0 8px;">Your access link has been refreshed</h2>
                  <p style="color:#64748b;text-align:center;margin-bottom:32px;">Use this updated link to access your VeilPiercer ${d.tier} portal</p>
                  <div style="text-align:center;">
                    <a href="${accessUrl}" style="display:inline-block;padding:16px 32px;background:linear-gradient(135deg,#7c3aed,#9333ea);color:white;text-decoration:none;border-radius:12px;font-weight:700;font-size:16px;">🔓 Open Access Portal</a>
                  </div>
                  <p style="text-align:center;color:#64748b;font-size:12px;margin-top:24px;">Tier: ${d.tier} — this link is unique to you</p>
                </div>`;
              try {
                await transporter.sendMail({ from: EMAIL_FROM, to: d.email, subject, html, text: `Your updated VeilPiercer ${d.tier} portal: ${accessUrl}` });
                log(`RESEND OK → ${d.email} [${d.tier}]`);
              } catch (e) { log(`RESEND FAIL → ${d.email}: ${e.message}`); }
              await new Promise(r => setTimeout(r, 1000)); // 1s delay between emails
            }
          } else {
            log(`RESEND: all buyers have visited their portal — no resend needed`);
          }
        }
      } else {
        log(`PUBLIC URL  → ${PUBLIC_URL} (ngrok not detected, using local)`);
      }
    } catch {
      log(`PUBLIC URL  → ${PUBLIC_URL} (ngrok offline, using local)`);
    }
  }, 3000);
});

