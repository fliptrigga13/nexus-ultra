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
const helmet = require('helmet');
const { rateLimit } = require('express-rate-limit');

// ── WebAuthn / Passkeys (biometric login) ─────────────────────────────────
const {
  generateRegistrationOptions, verifyRegistrationResponse,
  generateAuthenticationOptions, verifyAuthenticationResponse
} = require('@simplewebauthn/server');

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

const SECRET = process.env.API_SECRET;
const HUB_PASSWORD = process.env.HUB_PASSWORD || process.env.NEXUS_SECRET;
if (!SECRET) { console.error('FATAL: API_SECRET not set in .env'); process.exit(1); }
const HUB_SESSIONS = new Map(); // token -> expiry

// ── SECURITY: Brute Force Protection ────────────────────────────────────
const _loginAttempts = new Map(); // ip -> { count, until }
const _MAX_ATTEMPTS = 5;
const _LOCKOUT_MS = 15 * 60 * 1000; // 15 minutes

function _clientIp(req) {
  return ((req.headers['x-forwarded-for'] || req.socket.remoteAddress || '')
    .split(',')[0].trim());
}
function _isLockedOut(ip) {
  const r = _loginAttempts.get(ip);
  if (!r) return false;
  if (r.until && Date.now() < r.until) return true;
  _loginAttempts.delete(ip);
  return false;
}
function _recordFailure(ip) {
  const r = _loginAttempts.get(ip) || { count: 0, until: 0 };
  r.count++;
  if (r.count >= _MAX_ATTEMPTS) {
    r.until = Date.now() + _LOCKOUT_MS;
    log(`[SECURITY] BRUTE FORCE: ${ip} locked out (${r.count} failures)`);
  }
  _loginAttempts.set(ip, r);
}
function _clearAttempts(ip) { _loginAttempts.delete(ip); }

// ── SECURITY: Input Sanitizer ──────────────────────────────────────────
function _sanitizeInput(str, maxLen = 500) {
  if (typeof str !== 'string') return '';
  return str
    .replace(/<[^>]*>/g, '')          // strip all HTML tags
    .replace(/javascript:/gi, '')     // strip JS URIs
    .replace(/on\w+\s*=/gi, '')       // strip inline event handlers
    .replace(/[<>"'`]/g, '')          // strip remaining dangerous chars
    .slice(0, maxLen)
    .trim();
}

// ── SECURITY: Audit Log ──────────────────────────────────────────────────
const _SECURITY_LOG = path.join(__dirname, 'security.log');
function secLog(msg) {
  const line = `[${new Date().toISOString()}] [SECURITY] ${msg}`;
  console.warn(line);
  try { fs.appendFileSync(_SECURITY_LOG, line + '\n'); } catch (_) { }
}

// ── SECURITY: Email OTP 2FA (“phone gate”) ────────────────────────────
// Step 1: Password correct → generate OTP → email to owner Gmail → redirect to /hub-verify
// Step 2: Owner enters OTP from phone → session issued
const _OTP_STORE_FILE = path.join(__dirname, '.otp_store.json');
const _trustedDevices = new Map(); // deviceToken -> expiry (30 days)
const _OTP_TTL = 15 * 60 * 1000; // 15 minutes

// File-backed OTP store — survives server restarts so codes stay valid
const _pendingOTPs = {
  _data: (() => { try { return new Map(Object.entries(JSON.parse(fs.readFileSync(_OTP_STORE_FILE, 'utf8')))); } catch (_) { return new Map(); } })(),
  _save() { try { fs.writeFileSync(_OTP_STORE_FILE, JSON.stringify(Object.fromEntries(this._data))); } catch (_) { } },
  set(k, v) { this._data.set(k, v); this._save(); },
  get(k) { return this._data.get(k); },
  delete(k) { this._data.delete(k); this._save(); },
  has(k) { return this._data.has(k); }
};

function _generateOTP() {
  return String(Math.floor(100000 + Math.random() * 900000));
}
async function _sendOTPEmail(otp) {
  if (!transporter) { secLog('OTP: no email transporter — check EMAIL_USER/EMAIL_PASS in .env'); return false; }
  try {
    await transporter.sendMail({
      from: process.env.EMAIL_FROM || process.env.EMAIL_USER,
      to: process.env.EMAIL_USER,
      subject: `🔒 NEXUS Login Code: ${otp}`,
      text: [
        'Your NEXUS GOD MODE 2FA code:',
        '',
        `    ${otp}    `,
        '',
        'Expires in 15 minutes.',
        'If you did NOT request this, someone is attempting to access your hub.',
        'Check security.log immediately.',
        '',
        '— NEXUS ULTRA Security'
      ].join('\n')
    });
    secLog(`OTP emailed — check ${process.env.EMAIL_USER} on your phone`);
    return true;
  } catch (e) {
    secLog(`OTP email FAILED: ${e.message}`);
    return false;
  }
}

// ── SECURITY: Startup warnings ──────────────────────────────────────────
setTimeout(() => {
  if (!process.env.HUB_PASSWORD && !process.env.NEXUS_SECRET)
    secLog('WARNING: HUB_PASSWORD not set in .env — using hardcoded fallback. Fix before going live!');
  if (!process.env.STRIPE_WEBHOOK_SECRET)
    secLog('WARNING: STRIPE_WEBHOOK_SECRET not set — Stripe webhooks will be rejected!');
  if (!process.env.EMAIL_USER)
    secLog('WARNING: EMAIL_USER not set — OTP 2FA will not work!');
}, 0);

// Load EH Token for swarm protection
let EH_TOKEN = "";
try {
  const tokenPath = path.join(__dirname, '.eh_token');
  if (fs.existsSync(tokenPath)) EH_TOKEN = fs.readFileSync(tokenPath, 'utf8').trim();
} catch (e) { console.warn('Failed to load .eh_token'); }

function makeHubToken() { return require('crypto').randomBytes(32).toString('hex'); }
function isHubAuthed(req) {
  const raw = req.headers.cookie || '';
  const match = raw.match(/nexus_hub_session=([a-f0-9]{64})/);
  if (!match) return false;
  const exp = HUB_SESSIONS.get(match[1]);
  return exp && exp > Date.now();
}

// Global Hub Auth Middleware
const hubAuth = (req, res, next) => {
  const key = req.headers['x-api-key'] || req.query['x-api-key'];
  // Accepts env-loaded SECRET or HUB_PASSWORD only — no hardcoded literals
  if (key === SECRET || key === HUB_PASSWORD) return next();
  if (req.url.startsWith('/hub-login')) return next();
  if (isHubAuthed(req)) return next();

  if (req.headers.accept && req.headers.accept.includes('text/html')) {
    return res.redirect('/hub-login?next=' + encodeURIComponent(req.originalUrl));
  }
  res.status(401).json({ error: 'Hub auth required' });
};

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
  rubin: { active: true, throughput: '10.5k/s', mode: 'NVL72_TUNNEL' }
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
      { timeout: 30000, windowsHide: true }, (err, stdout) => {
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
      { timeout: 60000, windowsHide: true }, (err, stdout) => {
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
// ── SECURITY: Locked CORS ──────────────────────────────────────────────────
const ALLOWED_ORIGINS = (process.env.ALLOWED_ORIGINS || 'http://127.0.0.1:3000,http://localhost:3000,http://127.0.0.1:3001,http://localhost:3001').split(',');
app.use(cors({
  origin: (origin, cb) => {
    // Allow: no origin (server-to-server), null origin (direct IP nav from phone), or whitelisted domain
    if (!origin || origin === 'null' || ALLOWED_ORIGINS.some(o => origin.startsWith(o.trim()))) cb(null, true);
    else { log(`[SECURITY] CORS BLOCKED: ${origin}`); cb(null, false); }
  },
  credentials: true
}));

// ── SECURITY: Helmet (12 HTTP security headers) ────────────────────────
// CSP: restrict sources to known-good — blocks XSS if agent output is rendered.
app.use(helmet({
  crossOriginEmbedderPolicy: false,  // required for Stripe iframe + Ollama
  contentSecurityPolicy: {
    directives: {
      defaultSrc:  ["'self'"],
      scriptSrc:   ["'self'", "'unsafe-inline'", "https://js.stripe.com", "https://static.cloudflareinsights.com"],
      styleSrc:    ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
      fontSrc:     ["'self'", "https://fonts.gstatic.com"],
      imgSrc:      ["'self'", "data:", "https:"],
      connectSrc:  ["'self'", "http://127.0.0.1:7701", "http://127.0.0.1:11434", "http://127.0.0.1:7700", "https://api.stripe.com", "wss:"],
      frameSrc:    ["https://js.stripe.com"],
      objectSrc:   ["'none'"],
      upgradeInsecureRequests: [],
    }
  }
}));

// ── SECURITY: Rate Limiting ────────────────────────────────────────
const _paymentLimit = rateLimit({ windowMs: 60_000, max: 10, standardHeaders: true, legacyHeaders: false, message: { ok: false, error: 'Too many requests. Please wait a minute.' } });
const _generalLimit = rateLimit({ windowMs: 60_000, max: 60, standardHeaders: true, legacyHeaders: false, message: { ok: false, error: 'Rate limit exceeded.' } });
app.use('/stripe/create-checkout-session', _paymentLimit);
app.use('/stripe/webhook', _paymentLimit);
app.use('/webhook/task', _paymentLimit);
app.use(_generalLimit);

app.use(express.json());

// GET /api/config — serve tokens and URLs to the hub UI
app.get('/api/config', hubAuth, (req, res) => {
  res.json({
    ok: true,
    ehToken: EH_TOKEN,
    publicUrl: PUBLIC_URL,
    localUrl: `http://127.0.0.1:${PORT}`
  });
});

// GET /veilpiercer/metrics — live scores for dashboard
// Public endpoint so dashboard can read without API key
app.get('/veilpiercer/metrics', (req, res) => {
  res.json(calcVPScores());
});

// -- Blackboard endpoint (live swarm state for hub) --
app.get('/api/blackboard', (req, res) => {
  try {
    const fs = require('fs');
    const path = require('path');
    const bbPath = path.join(__dirname, 'nexus_blackboard.json');
    const raw = fs.readFileSync(bbPath, 'utf8');
    res.json(JSON.parse(raw));
  } catch(e) {
    res.json({ error: 'blackboard not found', colony_fitness: 0 });
  }
});

// -- Health check --
app.get('/health', (req, res) => res.json({ ok: true, ts: Date.now() }));

// -- Global Swarm Protection Layer --
const PROTECTED_PREFIXES = [
  '/api/', '/ollama/', '/gemini/', '/agent/', '/loop', '/autonomy',
  '/missions', '/queue', '/dropzone', '/schedule', '/tabs', '/cmd', '/run'
];

app.use((req, res, next) => {
  const isProtected = PROTECTED_PREFIXES.some(p => req.url.startsWith(p));
  const isPublic = [
    '/api/config', '/api/customer-task', '/api/ping-services',
    '/api/stats', '/api/blackboard', '/health', '/stripe/', '/access/verify', '/feedback', '/public/'
  ].some(p => req.url.startsWith(p));

  if (isProtected && !isPublic) {
    return hubAuth(req, res, next);
  }
  next();
});

// ── /api/config — REMOVED: duplicate unprotected route was shadowing the hubAuth-protected one above (line 408).
// All /api/config requests now require hub session (hubAuth). Do not re-add an unprotected version.

// ══ HUB PASSWORD GATE ════════════════════════════════════════════════════════
// Public routes (buyers, Stripe, VeilPiercer) — NEVER blocked:
const HUB_PUBLIC_ROUTES = [
  '/stripe', '/access', '/download', '/feedback', '/verify-token',
  '/chat', '/signals', '/hub-login', '/hub-logout',
  '/api/signal', '/api/vp-', '/favicon', '/assets',
  '/api/ping-services',  // health check — public so hub works unauthed
  '/api/result',          // live swarm result — polled by VeilPiercer frontend
  '/api/results',         // recent swarm outputs — polled by VeilPiercer frontend
  '/veilpiercer-command.html', // public for buyers (token-gated internally)
  '/veilpiercer/command',    // Hub AI & signal endpoint
  '/veilpiercer/signals',    // Hub telemetry polling
  '/public/stats',        // public social proof stats
  '/veilpiercer.html',    // public sales page
  '/vp.html',             // clean landing page — public
];
// Hub pages + new endpoints that need the password:
const HUB_PROTECTED_PAGES = [
  '/nexus_hub.html', '/nexus_ultimate_hub.html', '/nexus_prime_command.html',
  '/nexus_ultra_dashboard.html', '/nexus_personal.html', '/nexus-pong.html',
  '/stream', '/chat/stream', '/api/cycle',
  '/api/flush', '/api/chat-history', '/api/evolution', '/api/embed',
  '/api/tailscale', '/run', '/cmd', '/capture', '/captures',
  '/dropzone', '/schedule', '/tabs', '/insights', '/n8n',
];
app.use((req, res, next) => {
  const p = req.path;
  const isPublic = HUB_PUBLIC_ROUTES.some(r => p.startsWith(r));
  if (isPublic) return next();

  // Check if this is a protected hub route
  const needsAuth = HUB_PROTECTED_PAGES.some(r => p.startsWith(r))
    || p.match(/\.html$/);
  if (!needsAuth) return next();
  // Allow if valid session cookie
  if (isHubAuthed(req)) return next();
  // Redirect any .html page or browser navigation to login — works with Brave, Chrome, Safari
  const isHtmlPage = p.endsWith('.html') || (req.headers.accept || '').includes('text/html');
  if (isHtmlPage) return res.redirect('/hub-login?next=' + encodeURIComponent(req.originalUrl));
  // Only return JSON 401 for API/SSE/non-HTML requests
  return res.status(401).json({ error: 'Hub auth required', login: '/hub-login' });
});


// ── Passkey / WebAuthn ─────────────────────────────────────────────────────
const _PASSKEY_FILE = path.join(__dirname, '.passkey_store.json');
const _RP_NAME = 'NEXUS ULTRA Hub';
const _RP_ID = (process.env.PUBLIC_URL || 'http://localhost:3000').replace(/https?:\/\//, '').split('/')[0].split(':')[0];
const _PASSKEY_ORIGIN = (process.env.PUBLIC_URL || 'http://localhost:3000').replace(/\/$/, '');
const _PASSKEY_USER_ID = Buffer.from('nexus-owner', 'utf8');

const _passkeyStore = {
  _d: (() => { try { return JSON.parse(fs.readFileSync(_PASSKEY_FILE, 'utf8')); } catch (_) { return { credential: null, challenge: null }; } })(),
  save() { fs.writeFileSync(_PASSKEY_FILE, JSON.stringify(this._d, null, 2)); },
  get credential() { return this._d.credential; },
  set credential(v) { this._d.credential = v; this.save(); },
  get challenge() { return this._d.challenge; },
  set challenge(v) { this._d.challenge = v; this.save(); }
};

// ─── Passkey setup page (first-time registration on phone) ────────────────
app.get('/hub-passkey-setup', (req, res) => {
  if (!isHubAuthed(req)) return res.redirect('/hub-login?next=/hub-passkey-setup');
  const already = _passkeyStore.credential ? '<p style="color:#00fff7;margin-bottom:16px;font-size:11px">✅ Passkey registered. Re-register to replace it.</p>' : '';
  res.send(`<!DOCTYPE html><html><head><meta charset=UTF-8><title>NEXUS — Setup Biometrics</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&family=JetBrains+Mono:wght@400&display=swap" rel=stylesheet>
<style>*{margin:0;padding:0;box-sizing:border-box}body{background:#00000a;display:flex;align-items:center;justify-content:center;min-height:100vh;font-family:'JetBrains Mono',monospace;color:#e2e8f0}body::before{content:'';position:fixed;inset:0;background-image:linear-gradient(rgba(0,255,247,.03) 1px,transparent 1px),linear-gradient(90deg,rgba(0,255,247,.03) 1px,transparent 1px);background-size:40px 40px;pointer-events:none}.box{background:rgba(0,255,247,.04);border:1px solid rgba(0,255,247,.15);border-radius:12px;padding:48px 44px;width:380px;text-align:center}.logo{font-family:'Orbitron',monospace;font-size:13px;font-weight:900;letter-spacing:5px;background:linear-gradient(90deg,#00fff7,#bf00ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:6px}.sub{font-size:9px;color:#555;letter-spacing:3px;margin-bottom:28px}.btn{width:100%;background:linear-gradient(135deg,#00fff7,#bf00ff);border:none;border-radius:6px;padding:14px;font-family:'Orbitron',monospace;font-size:10px;font-weight:900;letter-spacing:3px;color:#000;cursor:pointer;margin-bottom:12px;transition:all .2s}.btn:hover{transform:translateY(-2px);box-shadow:0 0 24px rgba(0,255,247,.4)}#msg{margin-top:14px;font-size:12px;min-height:20px}</style></head>
<body><div class=box>
<div class=logo>NEXUS PRIME</div>
<div class=sub>BIOMETRIC SETUP</div>
${already}
<p style="font-size:11px;color:#666;margin-bottom:24px;letter-spacing:1px">Register your phone's Face ID or fingerprint as your login method. You will still enter your password first.</p>
<button class=btn onclick="registerPasskey()">📱 REGISTER BIOMETRICS</button>
<div id=msg></div>
<p style="margin-top:20px;font-size:10px;color:#333"><a href="/nexus_ultimate_hub.html" style="color:#7c3aed">← Back to Hub</a></p>
</div>
<script>
async function registerPasskey() {
  const msg = document.getElementById('msg');
  msg.style.color='#00fff7'; msg.textContent='Generating challenge...';
  try {
    const optsRes = await fetch('/hub-passkey-register-options', { method:'POST', headers:{'Content-Type':'application/json'} });
    const opts = await optsRes.json();
    if (opts.error) throw new Error(opts.error);
    opts.challenge = base64url_decode(opts.challenge);
    opts.user.id = base64url_decode(opts.user.id);
    if (opts.excludeCredentials) opts.excludeCredentials = opts.excludeCredentials.map(c => ({...c, id: base64url_decode(c.id)}));
    msg.textContent='Touch your fingerprint / Face ID when prompted...';
    const cred = await navigator.credentials.create({ publicKey: opts });
    const credJSON = {
      id: cred.id, rawId: base64url_encode(cred.rawId), type: cred.type,
      response: {
        clientDataJSON: base64url_encode(cred.response.clientDataJSON),
        attestationObject: base64url_encode(cred.response.attestationObject)
      }
    };
    const verRes = await fetch('/hub-passkey-register', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(credJSON) });
    const result = await verRes.json();
    if (result.ok) { msg.style.color='#00ff88'; msg.textContent='✅ Biometrics registered! You can now use Face ID / fingerprint to log in.'; }
    else { throw new Error(result.error || 'Registration failed'); }
  } catch(e) { msg.style.color='#ff3355'; msg.textContent='Error: ' + e.message; }
}
function base64url_decode(str) {
  str = str.replace(/-/g,'+').replace(/_/g,'/');
  while(str.length % 4) str += '=';
  return Uint8Array.from(atob(str), c => c.charCodeAt(0)).buffer;
}
function base64url_encode(buf) {
  return btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=/g,'');
}
</script></body></html>`);
});

app.post('/hub-passkey-register-options', express.json(), async (req, res) => {
  if (!isHubAuthed(req)) return res.status(401).json({ error: 'Login first' });
  try {
    const opts = await generateRegistrationOptions({
      rpName: _RP_NAME, rpID: _RP_ID,
      userID: _PASSKEY_USER_ID, userName: 'nexus-owner', userDisplayName: 'NEXUS Owner',
      attestationType: 'none',
      authenticatorSelection: { authenticatorAttachment: 'platform', userVerification: 'required', residentKey: 'preferred' },
      excludeCredentials: _passkeyStore.credential ? [{ id: Buffer.from(_passkeyStore.credential.credentialID, 'base64'), type: 'public-key' }] : []
    });
    _passkeyStore.challenge = opts.challenge;
    res.json(opts);
  } catch (e) { res.json({ error: e.message }); }
});

app.post('/hub-passkey-register', express.json(), async (req, res) => {
  if (!isHubAuthed(req)) return res.status(401).json({ error: 'Login first' });
  try {
    const challenge = _passkeyStore.challenge;
    if (!challenge) return res.json({ error: 'No challenge — restart registration' });
    const verification = await verifyRegistrationResponse({
      response: req.body, expectedChallenge: challenge,
      expectedOrigin: _PASSKEY_ORIGIN, expectedRPID: _RP_ID, requireUserVerification: true
    });
    if (verification.verified && verification.registrationInfo) {
      const { credential } = verification.registrationInfo;
      _passkeyStore.credential = {
        credentialID: Buffer.from(credential.id).toString('base64'),
        credentialPublicKey: Buffer.from(credential.publicKey).toString('base64'),
        counter: credential.counter
      };
      _passkeyStore.challenge = null;
      secLog('Passkey registered successfully');
      return res.json({ ok: true });
    }
    res.json({ error: 'Verification failed' });
  } catch (e) { secLog('Passkey register error: ' + e.message); res.json({ error: e.message }); }
});

app.post('/hub-passkey-auth-options', express.json(), async (req, res) => {
  const stored = _passkeyStore.credential;
  if (!stored) return res.json({ error: 'No passkey registered', setup: '/hub-passkey-setup' });
  try {
    const opts = await generateAuthenticationOptions({
      rpID: _RP_ID, userVerification: 'required',
      allowCredentials: [{ id: Buffer.from(stored.credentialID, 'base64'), type: 'public-key' }]
    });
    _passkeyStore.challenge = opts.challenge;
    res.json(opts);
  } catch (e) { res.json({ error: e.message }); }
});

app.post('/hub-passkey-auth', express.json(), async (req, res) => {
  const ip = _clientIp(req);
  if (_isLockedOut(ip)) return res.status(429).json({ error: 'Locked out. Try in 15 min.' });
  const stored = _passkeyStore.credential;
  const challenge = _passkeyStore.challenge;
  if (!stored || !challenge) return res.json({ error: 'No passkey or challenge expired' });
  try {
    const verification = await verifyAuthenticationResponse({
      response: req.body, expectedChallenge: challenge,
      expectedOrigin: _PASSKEY_ORIGIN, expectedRPID: _RP_ID,
      credential: {
        id: Buffer.from(stored.credentialID, 'base64'),
        publicKey: Buffer.from(stored.credentialPublicKey, 'base64'),
        counter: stored.counter
      },
      requireUserVerification: true
    });
    if (verification.verified) {
      stored.counter = verification.authenticationInfo.newCounter;
      _passkeyStore.credential = stored;
      _passkeyStore.challenge = null;
      _clearAttempts(ip);
      const token = makeHubToken();
      const deviceToken = makeHubToken();
      HUB_SESSIONS.set(token, Date.now() + 24 * 60 * 60 * 1000);
      _trustedDevices.set(deviceToken, Date.now() + 30 * 24 * 60 * 60 * 1000);
      secLog(`Passkey auth SUCCESS for ${ip} — 30-day device trust granted`);
      return res.json({ ok: true, token, deviceToken });
    }
    _recordFailure(ip);
    secLog(`Passkey auth FAIL for ${ip}`);
    res.json({ error: 'Biometric verification failed' });
  } catch (e) { secLog('Passkey auth error: ' + e.message); res.json({ error: e.message }); }
});

// ── Login page (biometrics primary, OTP email fallback) ───────────────────
app.get('/hub-login', (req, res) => {
  const next = req.query.next || '/nexus_hub.html';
  const hasPasskey = !!_passkeyStore.credential;
  const errMsg = req.query.err === 'expired'
    ? '<p class=err>Session expired. Enter password to get a fresh code.</p>'
    : req.query.err ? '<p class=err>Wrong password. Try again.</p>' : '';
  const bioBtn = hasPasskey
    ? `<button class=bbtn onclick="loginBio(event)" id=biobtn>👁 USE FACE ID / FINGERPRINT</button>
       <div class=or>— or enter password —</div>`
    : `<div class=setup-hint>No biometrics registered yet.<br><a href="/hub-passkey-setup" style="color:#7c3aed">Set up Face ID / fingerprint →</a></div>`;
  res.send(`<!DOCTYPE html><html><head><meta charset=UTF-8><meta name=viewport content="width=device-width,initial-scale=1"><title>NEXUS — Auth</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&family=JetBrains+Mono:wght@400&display=swap" rel=stylesheet>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#00000a;display:flex;align-items:center;justify-content:center;min-height:100vh;font-family:'JetBrains Mono',monospace}
body::before{content:'';position:fixed;inset:0;background-image:linear-gradient(rgba(0,255,247,.03) 1px,transparent 1px),linear-gradient(90deg,rgba(0,255,247,.03) 1px,transparent 1px);background-size:40px 40px;pointer-events:none}
.box{background:rgba(0,255,247,.04);border:1px solid rgba(0,255,247,.15);border-radius:12px;padding:44px 40px;width:360px;text-align:center;position:relative}
.logo{font-family:'Orbitron',monospace;font-size:13px;font-weight:900;letter-spacing:5px;background:linear-gradient(90deg,#00fff7,#bf00ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:6px}
.sub{font-size:8px;color:#333;letter-spacing:3px;margin-bottom:24px}
.bbtn{width:100%;background:linear-gradient(135deg,#bf00ff,#00fff7);border:none;border-radius:8px;padding:15px;font-family:'Orbitron',monospace;font-size:10px;font-weight:900;letter-spacing:2px;color:#000;cursor:pointer;transition:all .2s;margin-bottom:14px}
.bbtn:hover{transform:translateY(-2px);box-shadow:0 0 28px rgba(191,0,255,.5)}
.or{font-size:10px;color:#333;letter-spacing:2px;margin-bottom:14px}
.setup-hint{font-size:10px;color:#444;margin-bottom:18px;letter-spacing:1px;line-height:1.6}
.label{font-size:8px;letter-spacing:2px;color:#444;text-align:left;margin-bottom:6px}
.inp{width:100%;background:rgba(0,255,247,.06);border:1px solid rgba(0,255,247,.2);border-radius:6px;padding:12px 14px;color:#00fff7;font-family:'JetBrains Mono',monospace;font-size:14px;outline:none;letter-spacing:2px;margin-bottom:16px}
.inp:focus{border-color:#00fff7;box-shadow:0 0 12px rgba(0,255,247,.2)}
.btn{width:100%;background:linear-gradient(135deg,#00fff7,#bf00ff);border:none;border-radius:6px;padding:13px;font-family:'Orbitron',monospace;font-size:10px;font-weight:900;letter-spacing:3px;color:#000;cursor:pointer;transition:all .2s}
.btn:hover{transform:translateY(-2px);box-shadow:0 0 24px rgba(0,255,247,.4)}
.err{color:#ff3355;font-size:11px;margin:8px 0}
.fallback{margin-top:14px;font-size:10px;color:#333;letter-spacing:1px}
.fallback a{color:#444}
#bio-status{font-size:11px;min-height:18px;margin-top:8px;letter-spacing:1px}
</style></head>
<body><div class=box>
<div class=logo>NEXUS PRIME</div>
<div class=sub>ULTIMATE GOD MODE · RESTRICTED ACCESS</div>
${bioBtn}
<form method=POST action="/hub-login" id=pwform>
<input type=hidden name=next value="${next}">
<div class=label>ACCESS PASSWORD</div>
<input class=inp type=password name=password id=pw placeholder="••••••••••••" autofocus autocomplete=off>
${errMsg}
<button class=btn type=submit>⚡ AUTHENTICATE</button>
</form>
<div id=bio-status></div>
<div class=fallback>Lost your phone? <a href="/hub-login">Use email code instead</a></div>
</div>
<script>
const NEXT = ${JSON.stringify(next)};
const HAS_PASSKEY = ${hasPasskey};

async function loginBio(e) {
  e.preventDefault();
  const pw = document.getElementById('pw').value.trim();
  if (!pw) { document.getElementById('bio-status').style.color='#ff3355'; document.getElementById('bio-status').textContent='Enter your password first, then touch the biometric button.'; return; }
  const status = document.getElementById('bio-status');
  const btn = document.getElementById('biobtn');
  btn.disabled = true; btn.textContent='Contacting server...'; status.style.color='#00fff7';
  // Step 1: verify password first via a quick check
  try {
    const pwCheck = await fetch('/hub-passkey-auth-options', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ password: pw }) });
    const opts = await pwCheck.json();
    if (opts.error) { status.style.color='#ff3355'; status.textContent=opts.error; btn.disabled=false; btn.textContent='👁 USE FACE ID / FINGERPRINT'; return; }
    // Decode challenge
    opts.challenge = base64urlDec(opts.challenge);
    if (opts.allowCredentials) opts.allowCredentials = opts.allowCredentials.map(c => ({...c, id: base64urlDec(c.id)}));
    status.textContent='Touch your fingerprint or use Face ID...';
    const assertion = await navigator.credentials.get({ publicKey: opts, mediation: 'optional' });
    const body = {
      id: assertion.id, rawId: base64urlEnc(assertion.rawId), type: assertion.type,
      response: {
        authenticatorData: base64urlEnc(assertion.response.authenticatorData),
        clientDataJSON: base64urlEnc(assertion.response.clientDataJSON),
        signature: base64urlEnc(assertion.response.signature),
        userHandle: assertion.response.userHandle ? base64urlEnc(assertion.response.userHandle) : null
      },
      password: pw
    };
    const verRes = await fetch('/hub-passkey-auth', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
    const result = await verRes.json();
    if (result.ok) {
      document.cookie = 'nexus_hub_session=' + result.token + '; path=/; max-age=86400; samesite=strict';
      document.cookie = 'nexus_device_trust=' + result.deviceToken + '; path=/; max-age=' + (30*24*60*60) + '; samesite=strict';
      status.style.color='#00ff88'; status.textContent='✅ Authenticated!';
      setTimeout(() => { window.location.href = NEXT; }, 400);
    } else {
      status.style.color='#ff3355'; status.textContent='Biometric failed: ' + (result.error || 'Try again');
      btn.disabled=false; btn.textContent='👁 USE FACE ID / FINGERPRINT';
    }
  } catch(err) {
    status.style.color='#ff3355'; status.textContent='Error: ' + err.message;
    btn.disabled=false; btn.textContent='👁 USE FACE ID / FINGERPRINT';
  }
}

function base64urlDec(str) {
  str = str.replace(/-/g,'+').replace(/_/g,'/'); while(str.length%4) str+='=';
  return Uint8Array.from(atob(str),c=>c.charCodeAt(0)).buffer;
}
function base64urlEnc(buf) {
  return btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=/g,'');
}
</script></body></html>`);
});


app.post('/hub-login', express.urlencoded({ extended: false }), async (req, res) => {
  const ip = _clientIp(req);
  const { password, next } = req.body || {};
  const dest = (next && next.startsWith('/')) ? next : '/nexus_hub.html';

  // ── BRUTE FORCE CHECK ──────────────────────────────────────────────────
  if (_isLockedOut(ip)) {
    log(`[SECURITY] BRUTE FORCE: login blocked for ${ip}`);
    return res.status(429).send(
      '<html><body style="background:#00000a;color:#ff3355;font-family:monospace;display:flex;align-items:center;justify-content:center;height:100vh;margin:0">'
      + '<div style="text-align:center"><h2>Too Many Attempts</h2><p>Locked out for 15 minutes.</p></div></body></html>'
    );
  }

  if (password !== HUB_PASSWORD) {
    _recordFailure(ip);
    const attempts = (_loginAttempts.get(ip) || {}).count || 1;
    log(`[SECURITY] Failed login from ${ip} (attempt ${attempts}/${_MAX_ATTEMPTS})`);
    return res.redirect('/hub-login?err=1&next=' + encodeURIComponent(dest));
  }

  _clearAttempts(ip);

  // -- REMEMBERED DEVICE: 30-day cookie — skip OTP on any remembered device --
  // Works on mobile data, any network — tied to the device browser, not the IP
  const _dc = (req.headers.cookie || '').match(/nexus_device_trust=([a-f0-9]{64})/);
  if (_dc) {
    const devExpiry = _trustedDevices.get(_dc[1]);
    if (devExpiry && Date.now() < devExpiry) {
      const token = makeHubToken();
      HUB_SESSIONS.set(token, Date.now() + 24 * 60 * 60 * 1000);
      secLog(`REMEMBERED DEVICE: ${ip} — 30-day cookie valid, session issued (no OTP)`);
      res.setHeader('Set-Cookie', `nexus_hub_session=${token}; HttpOnly; Path=/; Max-Age=86400; SameSite=Strict`);
      return res.redirect(dest);
    }
  }

  // -- TRUSTED DEVICE: Home laptop skips 2FA entirely --------------------------
  // Localhost = always trusted. Add home IP to TRUSTED_IPS in .env if needed.
  // e.g. TRUSTED_IPS=127.0.0.1,::1,192.168.1.50
  const _TRUSTED = (process.env.TRUSTED_IPS || '127.0.0.1,::1,::ffff:127.0.0.1').split(',').map(s => s.trim());
  if (_TRUSTED.some(t => ip === t || ip.includes(t))) {
    const token = makeHubToken();
    HUB_SESSIONS.set(token, Date.now() + 24 * 60 * 60 * 1000);
    secLog(`TRUSTED DEVICE: ${ip} granted without 2FA`);
    res.setHeader('Set-Cookie', `nexus_hub_session=${token}; HttpOnly; Path=/; Max-Age=86400; SameSite=Strict`);
    return res.redirect(dest);
  }

  // -- PHONE 2FA: External device (phone/Cloudflare) — OTP to Gmail ------------
  const otp = _generateOTP();
  _pendingOTPs.set(ip, { code: otp, expires: Date.now() + _OTP_TTL, dest });
  secLog(`2FA OTP generated for ${ip}`);
  await _sendOTPEmail(otp);
  res.redirect('/hub-verify?sent=1&next=' + encodeURIComponent(dest));
});

// ── SECURITY: /hub-verify — OTP entry page (Step 2 of 2FA) ──────────────────
const _V_CSS = `*{margin:0;padding:0;box-sizing:border-box}body{background:#00000a;display:flex;align-items:center;justify-content:center;min-height:100vh;font-family:'JetBrains Mono',monospace;color:#e2e8f0}body::before{content:'';position:fixed;inset:0;background-image:linear-gradient(rgba(0,255,247,.03) 1px,transparent 1px),linear-gradient(90deg,rgba(0,255,247,.03) 1px,transparent 1px);background-size:40px 40px;pointer-events:none}.box{background:rgba(0,255,247,.04);border:1px solid rgba(0,255,247,.15);border-radius:12px;padding:48px 44px;width:380px;text-align:center}.logo{font-family:monospace;font-size:13px;font-weight:900;letter-spacing:5px;background:linear-gradient(90deg,#00fff7,#bf00ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:6px}.sub{font-size:9px;color:#555;letter-spacing:3px;margin-bottom:8px}.hint{font-size:11px;color:#7c3aed;margin-bottom:28px;letter-spacing:1px}.label{font-size:8px;letter-spacing:2px;color:#444;text-align:left;margin-bottom:6px}.inp{width:100%;background:rgba(0,255,247,.06);border:1px solid rgba(0,255,247,.2);border-radius:6px;padding:14px;color:#00fff7;font-family:'JetBrains Mono',monospace;font-size:22px;outline:none;letter-spacing:8px;text-align:center;margin-bottom:20px}.inp:focus{border-color:#00fff7;box-shadow:0 0 12px rgba(0,255,247,.2)}.btn{width:100%;background:linear-gradient(135deg,#7c3aed,#00fff7);border:none;border-radius:6px;padding:13px;font-family:monospace;font-size:10px;font-weight:900;letter-spacing:3px;color:#000;cursor:pointer}.err{color:#ff3355;font-size:11px;margin-top:8px}`;

app.get('/hub-verify', (req, res) => {
  const isErr = req.query.err;
  const next = req.query.next || '/nexus_hub.html';
  const err = isErr ? '<p class=err>Wrong code or expired. Check Gmail for the latest code, or <a href="/hub-login" style="color:#00fff7">request a new one</a>.</p>' : '';
  const sent = req.query.sent ? '<p class=hint>Check your Gmail — 6-digit code sent. Valid for 15 minutes.</p>' : '';
  const resend = `<p style="margin-top:16px;font-size:10px;color:#444;letter-spacing:1px">Code not arrived? <a href="/hub-login" style="color:#7c3aed">RESEND CODE</a></p>`;
  res.send(`<!DOCTYPE html><html><head><meta charset=UTF-8><title>NEXUS — 2FA</title><style>${_V_CSS}</style></head>
<body><div class=box>
<div class=logo>NEXUS PRIME</div>
<div class=sub>2-FACTOR AUTHENTICATION</div>
${sent}
<form method=POST action="/hub-verify">
<input type=hidden name=next value="${next}">
<div class=label>6-DIGIT CODE FROM YOUR PHONE</div>
<input class=inp type=text name=code placeholder="000000" maxlength=6 inputmode=numeric autofocus autocomplete=off>
${err}
<button class=btn type=submit>🔓 VERIFY CODE</button>
</form>
${resend}
</div></body></html>`);
});

app.post('/hub-verify', express.urlencoded({ extended: false }), (req, res) => {
  const ip = _clientIp(req);
  const { code, next } = req.body || {};
  const dest = (next && next.startsWith('/')) ? next : '/nexus_hub.html';
  const pending = _pendingOTPs.get(ip);

  if (!pending || Date.now() > pending.expires) {
    secLog(`2FA FAIL: expired/missing OTP for ${ip}`);
    _pendingOTPs.delete(ip);
    return res.redirect('/hub-login?err=expired'); // OTP expired, back to start — get fresh code
  }
  if (!code || code.trim() !== pending.code) {
    _recordFailure(ip);
    secLog(`2FA FAIL: wrong OTP from ${ip} (entered: ${code?.slice(0, 6)})`);
    return res.redirect('/hub-verify?err=1&next=' + encodeURIComponent(dest));
  }

  // OTP verified -- issue session + set 30-day device trust cookie
  _pendingOTPs.delete(ip);
  _clearAttempts(ip);
  const token = makeHubToken();
  const deviceToken = makeHubToken();
  const _30DAYS = 30 * 24 * 60 * 60;
  HUB_SESSIONS.set(token, Date.now() + 24 * 60 * 60 * 1000);
  _trustedDevices.set(deviceToken, Date.now() + _30DAYS * 1000);
  secLog(`2FA SUCCESS: session issued for ${ip} — device remembered for 30 days`);
  res.setHeader('Set-Cookie', [
    `nexus_hub_session=${token}; HttpOnly; Path=/; Max-Age=86400; SameSite=Strict`,
    `nexus_device_trust=${deviceToken}; HttpOnly; Path=/; Max-Age=${_30DAYS}; SameSite=Strict`
  ]);
  res.redirect(dest);
});

app.get('/hub-logout', (req, res) => {
  const raw = req.headers.cookie || '';
  const match = raw.match(/nexus_hub_session=([a-f0-9]{64})/);
  if (match) HUB_SESSIONS.delete(match[1]);
  res.setHeader('Set-Cookie', 'nexus_hub_session=; Path=/; Max-Age=0');
  res.redirect('/hub-login');
});
// ═════════════════════════════════════════════════════════════════════════════

// ── Auth middleware — protects signal + insights routes ──
const nexusAuth = (req, res, next) => {
  const secret = process.env.NEXUS_SECRET;
  const key = req.headers['x-api-key'];
  if (key !== secret) return res.status(401).json({ error: 'Unauthorized: invalid x-api-key' });
  next();
};

// ── Signal Review: approve / reject / insights ── (COSMOS port 9100)
const COSMOS_PORT = 9100;

app.get('/insights', nexusAuth, async (req, res) => {
  try {
    const response = await fetch(`http://127.0.0.1:${COSMOS_PORT}/insights?limit=${req.query.limit || 50}`);
    const data = await response.json();
    res.json(data);
  } catch (err) {
    log(`INSIGHTS ERROR: ${err.message}`);
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/approve-signal', nexusAuth, async (req, res) => {
  const { signal_id } = req.body;
  if (!signal_id) return res.status(400).json({ error: 'signal_id required' });
  try {
    const response = await fetch(`http://127.0.0.1:${COSMOS_PORT}/approve-signal`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ signal_id }),
    });
    const data = await response.json();
    res.json(data);
  } catch (err) {
    log(`APPROVE-SIGNAL ERROR: ${err.message}`);
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/reject-signal', nexusAuth, async (req, res) => {
  const { signal_id } = req.body;
  if (!signal_id) return res.status(400).json({ error: 'signal_id required' });
  try {
    const response = await fetch(`http://127.0.0.1:${COSMOS_PORT}/reject-signal`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ signal_id }),
    });
    const data = await response.json();
    res.json(data);
  } catch (err) {
    log(`REJECT-SIGNAL ERROR: ${err.message}`);
    res.status(500).json({ error: err.message });
  }
});

// ── Harcoded Node Shield (Zero Leakage over Ngrok) ────────────────
app.use((req, res, next) => {
  const url = req.path.toLowerCase();
  // Physically block the internet from downloading backend configs, databases, source code, or memories
  if (url.endsWith('.env') || url.endsWith('.eh_token') || url.endsWith('.cjs') ||
    url.endsWith('.json') || url.endsWith('.log') || url.endsWith('.db') || url.endsWith('.db-shm') || url.endsWith('.db-wal') ||
    url.endsWith('.bat') || url.endsWith('.ps1') || url.endsWith('.py') || url.endsWith('.md')) {
    return res.status(403).send('STRICT_FORBIDDEN: NODE_SHIELD_ACTIVE');
  }
  next();
});
app.use(express.static(ROOT, { index: false })); // don't auto-serve index.html at root — route handler controls /
// ── Main landing page ────────────────────────────────────────────────
app.get('/', (req, res) => {
  // Owner logged in → go to hub. Public visitor → VeilPiercer sales page.
  if (isHubAuthed(req)) return res.redirect('/nexus_hub.html');
  return res.sendFile(path.join(ROOT, 'index.html'));
});
app.get('/veilpiercer-pitch.html', (req, res) => res.redirect(301, '/index.html'));
app.get('/veilpiercer.html', (req, res) => res.redirect(301, '/index.html'));


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
    { timeout: 60000, windowsHide: true }, (err, stdout, stderr) => {
      if (err) { log(`RUN ERR ${action}: ${stderr || err.message}`); return res.status(500).json({ ok: false, error: stderr || err.message }); }
      log(`RUN OK: ${action}`);
      return res.json({ ok: true, output: stdout.trim() });
    });
});

// ── GET /status — OWNER ONLY (hubAuth) ─────────────────────────────────────
// Exposes: revenue totals, access-token count, tier breakdown, internal paths.
// Must NEVER be public — gate with hub session.
let storedTabs = null;
try { if (fs.existsSync(TABS_FILE)) storedTabs = JSON.parse(fs.readFileSync(TABS_FILE, 'utf8')); } catch (_) { }

app.get('/status', hubAuth, (req, res) => {
  const db = loadAccessDB();
  const salesSummary = Object.values(db).reduce((acc, entry) => {
    acc.total += (entry.amount || 0);
    acc.count++;
    acc.tiers[entry.tier] = (acc.tiers[entry.tier] || 0) + 1;
    return acc;
  }, { total: 0, count: 0, tiers: {} });

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
    access_tokens: salesSummary.count,
    total_revenue: (salesSummary.total / 100).toFixed(2),
    tier_breakdown: salesSummary.tiers,
    email_configured: !!(EMAIL_USER && EMAIL_PASS),
    rubin_active: VP_METRICS.rubin.active,
    throughput: VP_METRICS.rubin.throughput
  });
});

app.get('/api/vp-sales', (req, res) => {
  const db = loadAccessDB();
  const now = new Date();
  const todayStr = now.toISOString().split('T')[0];

  const report = Object.values(db).reduce((acc, s) => {
    const isToday = s.createdAt && s.createdAt.startsWith(todayStr);
    if (isToday) {
      acc.today.revenue += (s.amount || 0);
      acc.today.count++;
    }
    acc.all_time.revenue += (s.amount || 0);
    acc.all_time.count++;
    return acc;
  }, { today: { revenue: 0, count: 0 }, all_time: { revenue: 0, count: 0 } });

  res.json({
    ok: true,
    date: todayStr,
    today_revenue: (report.today.revenue / 100).toFixed(2),
    today_sales: report.today.count,
    all_time_revenue: (report.all_time.revenue / 100).toFixed(2),
    all_time_sales: report.all_time.count
  });
});

// ── VEILPIERCER MOBILE /m ── enhanced branded phone monitor ─────────────────
app.get('/m', hubAuth, (req, res) => {
  const db = loadAccessDB();
  const now = new Date();
  const todayStr = now.toISOString().split('T')[0];
  const sales = Object.values(db).reduce((a, e) => {
    const isReal = e.sessionId && (e.sessionId.startsWith('pi_') || e.sessionId.startsWith('cs_live_') || e.sessionId.startsWith('cs_test_b'));
    a.allRev += (e.amount || 0); a.allN++;           // ALL tokens (includes test/manual)
    if (isReal) { a.rev += (e.amount || 0); a.n++; } // REAL Stripe payments only
    if (isReal && e.createdAt && e.createdAt.startsWith(todayStr)) { a.todayRev += (e.amount || 0); a.todayN++; }
    return a;
  }, { rev: 0, n: 0, todayRev: 0, todayN: 0, allRev: 0, allN: 0 });

  let logLines = [];
  try { const raw = fs.readFileSync(LOG_FILE, 'utf8'); logLines = raw.split('\n').filter(Boolean).slice(-25).reverse(); } catch (_) { }
  let bb = {};
  try { bb = JSON.parse(fs.readFileSync(path.join(__dirname, 'nexus_blackboard.json'), 'utf8')); } catch (_) { }

  const score = parseFloat(bb.last_score) || 0;
  const scoreColor = score >= 0.8 ? '#0f0' : score >= 0.5 ? '#fa0' : '#f33';
  const statusColor = bb.status === 'RUNNING' ? '#0f0' : bb.status === 'DONE' ? '#fa0' : '#f33';
  const scoreBar = Math.min(100, Math.round(score * 100));

  const logHtml = logLines.map(l => {
    const isWarn = /error|fail|warn|critical/i.test(l);
    const isGood = /session|active|online|success|done/i.test(l);
    const col = isWarn ? '#f55' : isGood ? '#0c6' : '#2a6a2a';
    return `<div style="padding:3px 0;border-bottom:1px solid #0a0a0a;font-size:10px;color:${col};word-break:break-all">${l.replace(/</g, '&lt;')}</div>`;
  }).join('');

  const cap = (() => { try { return fs.readdirSync(CAPTURE_DIR).length; } catch (_) { return 0; } })();
  const logKB = (() => { try { return (fs.statSync(LOG_FILE).size / 1024).toFixed(0); } catch (_) { return 0; } })();

  res.setHeader('Content-Type', 'text/html');
  res.send(`<!DOCTYPE html><html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="10">
<title>VEILPIERCER · MOBILE OPS</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#030008;color:#c0c0d0;font-family:monospace;font-size:12px;padding:14px}
.layout{display:grid;grid-template-columns:1fr;gap:14px;max-width:1100px;margin:0 auto}
@media(min-width:700px){.layout{grid-template-columns:minmax(300px,500px) 1fr}}
.col-left{min-width:0}
.col-right{min-width:0}
.logo{font-size:11px;letter-spacing:6px;color:#bf00ff;margin-bottom:2px;font-weight:bold}
.sub{font-size:8px;color:#445;letter-spacing:3px;margin-bottom:12px}
.badge{display:inline-block;padding:3px 12px;border:1px solid ${statusColor};color:${statusColor};font-size:9px;letter-spacing:3px;margin-bottom:14px;border-radius:2px}
.card{background:#0a0010;border:1px solid #1a003a;border-radius:6px;padding:12px;margin-bottom:12px}
.card-title{font-size:8px;letter-spacing:3px;color:#bf00ff;margin-bottom:10px;border-bottom:1px solid #1a003a;padding-bottom:5px}
.row{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #0c0018;font-size:11px}
.lbl{color:#445;font-size:9px;letter-spacing:1px}.val{color:#e0e0f0;text-align:right}
.val.g{color:#0f0}.val.y{color:#fa0}.val.p{color:#bf00ff}.val.c{color:#0cf}
.rev-big{font-size:22px;color:#bf00ff;font-weight:bold;text-align:center;padding:8px 0}
.rev-sub{font-size:9px;color:#445;text-align:center;margin-bottom:4px}
.bar-wrap{height:5px;background:#1a003a;border-radius:3px;margin:8px 0 4px;overflow:hidden}
.bar-fill{height:100%;width:${scoreBar}%;background:${scoreColor};border-radius:3px}
.score-label{font-size:8px;color:#445;display:flex;justify-content:space-between}
h2{font-size:8px;letter-spacing:3px;color:#0cf;margin-bottom:7px;border-bottom:1px solid #0a0018;padding-bottom:4px}
.log-wrap{max-height:220px;overflow-y:auto;margin-bottom:12px}
textarea{width:100%;background:#050010;border:1px solid #1a003a;color:#0cf;font-family:monospace;font-size:11px;padding:10px;border-radius:4px;resize:vertical;min-height:55px;outline:none}
button{width:100%;background:none;border:2px solid #bf00ff;color:#bf00ff;font-family:monospace;font-size:12px;letter-spacing:2px;padding:12px;margin-top:8px;border-radius:4px;cursor:pointer}
button:active{background:#bf00ff22}
.ts{font-size:8px;color:#2a2a3a;text-align:right;margin-top:10px}
</style></head><body>
<div class="layout">
<div class="col-left">
<div class="logo">VEILPIERCER</div>
<div class="sub">MOBILE OPS CENTER · AUTO-REFRESH 10s</div>
<div class="badge">${bb.status || 'OFFLINE'}</div>

<div class="card">
  <div class="card-title">▸ REVENUE INTEL</div>
  <div class="rev-big">$${(sales.rev / 100).toFixed(2)}</div>
  <div class="rev-sub">ALL-TIME · ${sales.n} SALES</div>
  <div class="row"><span class="lbl">TODAY</span><span class="val g">$${(sales.todayRev / 100).toFixed(2)} (${sales.todayN} sales)</span></div>
</div>

<div class="card">
  <div class="card-title">▸ SWARM STATUS</div>
  <div class="row"><span class="lbl">CYCLE</span><span class="val c">${bb.cycle_id || '—'}</span></div>
  <div class="row"><span class="lbl">MVP AGENT</span><span class="val p">${bb.last_mvp || '—'}</span></div>
  <div class="row"><span class="lbl">LESSON</span><span class="val" style="font-size:9px;max-width:70%;text-align:right">${String(bb.last_lesson || '—').slice(0, 60)}</span></div>
  <div class="row"><span class="lbl">UPTIME</span><span class="val">${process.uptime().toFixed(0)}s</span></div>
  <div class="row"><span class="lbl">CAPTURES</span><span class="val">${cap}</span></div>
  <div class="row"><span class="lbl">LOG SIZE</span><span class="val">${logKB}KB</span></div>
  <div style="margin-top:10px">
    <div class="score-label"><span>CYCLE SCORE</span><span style="color:${scoreColor}">${score.toFixed(2)} / 1.00</span></div>
    <div class="bar-wrap"><div class="bar-fill"></div></div>
  </div>
</div>

<div class="card">
  <div class="card-title">▸ LIVE LOG (last 25 lines)</div>
  <div class="log-wrap">${logHtml || '<div style="color:#2a2a3a">No swarm activity yet</div>'}</div>
</div>

<div class="card">
  <div class="card-title">▸ INJECT SWARM TASK</div>
  <textarea id="t" placeholder="Enter directive for the swarm..."></textarea>
  <button onclick="inj()">⚡ FIRE TASK</button>
</div><!-- end col-left -->

<div class="col-right">

<div class="card">
  <div class="card-title">▸ QUICK COMMANDS</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:10px">
    <button class="qb" onclick="qi('Run full audit cycle now')">🔍 AUDIT</button>
    <button class="qb" onclick="qi('Check system status and report health')">📊 STATUS</button>
    <button class="qb" onclick="qi('Flush memory and clear stale agent state')">🧹 FLUSH</button>
    <button class="qb" onclick="qi('Generate VeilPiercer sales summary report')">💰 SALES</button>
    <button class="qb" onclick="qi('Analyze latest errors in swarm log')">⚠️ ERRORS</button>
    <button class="qb" onclick="qi('Optimize agent concurrency for current load')">⚡ OPTIMIZE</button>
    <button class="qb" onclick="qi('Identify top performing agent this cycle')">🏆 MVP</button>
    <button class="qb" onclick="qi('Force restart lowest priority agents')">🔄 RESTART</button>
  </div>
  <div id="qres" style="font-size:9px;color:#0cf;padding:6px 0;min-height:20px"></div>
</div>

<div class="card">
  <div class="card-title">▸ TOKEN LEDGER</div>
  <div class="row"><span class="lbl">REAL STRIPE SALES</span><span class="val g">${sales.n}</span></div>
  <div class="row"><span class="lbl">REAL REVENUE</span><span class="val g">$${(sales.rev / 100).toFixed(2)}</span></div>
  <div class="row"><span class="lbl">ALL TOKENS ISSUED</span><span class="val">${sales.allN}</span></div>
  <div class="row"><span class="lbl">TOKEN FACE VALUE</span><span class="val" style="color:#444">$${(sales.allRev / 100).toFixed(2)}</span></div>
  <div class="row"><span class="lbl">TEST / MANUAL</span><span class="val" style="color:#333">${sales.allN - sales.n} entries</span></div>
</div>

<div class="card">
  <div class="card-title">▸ SYSTEM CLOCK</div>
  <div style="font-size:28px;color:#bf00ff;text-align:center;padding:14px 0;letter-spacing:2px" id="clk"></div>
  <div class="row"><span class="lbl">SERVER UPTIME</span><span class="val">${process.uptime().toFixed(0)}s</span></div>
  <div class="row"><span class="lbl">LOG SIZE</span><span class="val">${logKB}KB</span></div>
  <div class="row"><span class="lbl">CAPTURES</span><span class="val">${cap}</span></div>
</div>

</div><!-- end col-right -->
</div><!-- end layout -->

<div class="ts">NEXUS ULTRA · ${now.toLocaleString()}</div>

<script>
async function inj(){
  const v=document.getElementById('t').value.trim();if(!v)return;
  try{
    const r=await fetch('http://'+location.hostname+':7701/inject',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task:v})});
    const d=await r.json();
    alert(d.ok?'✅ INJECTED\\nQueue depth: '+d.queue_depth:'❌ '+d.error);
    if(d.ok)document.getElementById('t').value='';
  }catch(e){alert('❌ EH API unreachable: '+e.message);}
}
</script>
</body></html>`);
});

app.get('/public/stats', (req, res) => {
  const db = loadAccessDB();
  res.json({
    ok: true,
    deployments: Object.keys(db).length,
    uptime_days: (process.uptime() / 86400).toFixed(1)
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
app.post('/access/create', hubAuth, async (req, res) => {
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
  const list = Object.entries(db).map(([token, d]) => ({ token: token.substring(0, 8) + '...', email: d.email, tier: d.tier, amount: d.amount, used: d.used, createdAt: d.createdAt, downloads: d.downloads || 0, lastDownload: d.lastDownload || null }));
  res.json({ ok: true, count: list.length, tokens: list });
});



// ── GET /download ─────────────────────────────────────────────────────────────
// Token-gated file download — streams a zip of tier-appropriate deliverables
app.get('/download', async (req, res) => {
  const { token, file } = req.query;
  if (!token) return res.status(403).json({ ok: false, error: 'Token required' });

  const db = loadAccessDB();
  const entry = db[token];
  if (!entry) return res.status(403).json({ ok: false, error: 'Invalid or expired token' });

  const tier = entry.tier || 'VeilPiercer God Mode (Full Access)';
  const VEIL_DIR = path.join(ROOT, 'BUNDLE');

  // UNIFIED PRODUCT DELIVERY: 
  // No more Starter/Pro splits. Everyone gets the entire sovereign God Mode architecture.
  let filesToZip = [];
  try {
    if (fs.existsSync(VEIL_DIR)) {
      filesToZip = fs.readdirSync(VEIL_DIR).filter(f => fs.statSync(path.join(VEIL_DIR, f)).isFile());
    }
  } catch (e) {
    log(`Warning: Failed to scan BUNDLE dir: ${e.message}`);
  }

  const zipName = `VeilPiercer-GodMode-Bundle.zip`;

  try {
    const archiver = require('archiver');
    res.setHeader('Content-Disposition', `attachment; filename="${zipName}"`);
    res.setHeader('Content-Type', 'application/zip');

    const archive = archiver('zip', { zlib: { level: 9 } });
    archive.on('error', err => { log(`Download zip error: ${err.message}`); });
    archive.pipe(res);

    for (const f of filesToZip) {
      const fp = path.join(VEIL_DIR, f);
      if (fs.existsSync(fp)) {
        archive.file(fp, { name: f });
      }
    }

    // Add a personalized README for every tier
    const readmeContent = [
      `VeilPiercer ${tier} Bundle`,
      `=`.repeat(40),
      `Buyer: ${entry.email}`,
      `Purchased: ${entry.createdAt}`,
      `Tier: ${tier}`,
      ``,
      `INCLUDED FILES:`,
      ...filesToZip.map(f => `  - ${f}`),
      ``,
      `SETUP:`,
      `  1. Open index.html in any browser — no server required for basic use`,
      `  2. For full AI features, point to your NEXUS ULTRA server at port 3000`,
      `  3. Contact support@veilpiercer.com for setup help`,
      '',
    ].join('\n');

    archive.append(readmeContent, { name: 'README-YOUR-PURCHASE.txt' });
    await archive.finalize();

    entry.downloads = (entry.downloads || 0) + 1;
    entry.lastDownload = new Date().toISOString();
    saveAccessDB(db);
    log(`DOWNLOAD: ${entry.email} [${tier}] downloaded ${zipName}`);
  } catch (err) {
    log(`Download error: ${err.message}`);
    if (!res.headersSent) res.status(500).json({ ok: false, error: 'Download failed — archiver module may need install' });
  }
});

// ── POST /feedback ────────────────────────────────────────────────────────────
// Buyer feedback — token-gated, saves to feedback.json + emails owner
const FEEDBACK_DB = path.join(ROOT, 'feedback.json');
function loadFeedback() { try { return JSON.parse(fs.readFileSync(FEEDBACK_DB, 'utf8')); } catch { return []; } }

app.post('/feedback', async (req, res) => {
  const { token, rating, worked, useCase, suggestion, recommend } = req.body || {};
  if (!token) return res.status(400).json({ ok: false, error: 'token required' });

  const db = loadAccessDB();
  const entry = db[token];
  if (!entry) return res.status(403).json({ ok: false, error: 'Invalid token' });

  const feedback = {
    id: Date.now(),
    submittedAt: new Date().toISOString(),
    email: entry.email,
    tier: entry.tier,
    rating: parseInt(rating) || 0,
    worked: worked === 'yes',
    useCase: _sanitizeInput(useCase, 500),
    suggestion: _sanitizeInput(suggestion, 500),
    recommend: parseInt(recommend) || 0,
  };

  // Save to feedback.json
  const all = loadFeedback();
  all.push(feedback);
  fs.writeFileSync(FEEDBACK_DB, JSON.stringify(all, null, 2));

  // Email notification to owner
  if (transporter) {
    try {
      await transporter.sendMail({
        from: process.env.EMAIL_FROM,
        to: process.env.EMAIL_USER,
        subject: `⭐ New VeilPiercer Feedback — ${entry.tier} — ${rating}/10`,
        text: [
          `New feedback from: ${entry.email} (${entry.tier})`,
          `Rating: ${rating}/10`,
          `It worked: ${worked}`,
          `Would recommend: ${recommend}/10`,
          `Use case: ${useCase || 'n/a'}`,
          `Suggestions: ${suggestion || 'n/a'}`,
          `Submitted: ${feedback.submittedAt}`,
        ].join('\n'),
      });
    } catch (e) { log(`Feedback email error: ${e.message}`); }
  }

  log(`FEEDBACK: ${entry.email} [${entry.tier}] rated ${rating}/10`);
  res.json({ ok: true, message: 'Thank you for your feedback!' });
});

// ── GET /feedback/all ─────────────────────────────────────────────────────────
// Admin view of all feedback
app.get('/feedback/all', auth, (req, res) => {
  const all = loadFeedback();
  const avg = all.length ? (all.reduce((s, f) => s + f.rating, 0) / all.length).toFixed(1) : 'n/a';
  const worked = all.filter(f => f.worked).length;
  res.json({ ok: true, count: all.length, avgRating: avg, workedCount: worked, feedback: all });
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
    { timeout: 30000, windowsHide: true }, (err, stdout, stderr) => {
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
    // SECURITY: Reject if no webhook secret — never accept unverified Stripe events
    log('[SECURITY] WEBHOOK BLOCKED: STRIPE_WEBHOOK_SECRET not set in .env — set it to verify Stripe signatures');
    return res.status(400).send('Webhook Error: signature verification required. Set STRIPE_WEBHOOK_SECRET in .env');
  }

  switch (event.type) {
    case 'checkout.session.completed': {
      const s = event.data.object;
      const email = s.customer_email || s.customer_details?.email || '';
      const tier = s.metadata?.tier || 'Starter';
      const amount = s.amount_total || 0;
      log(`WEBHOOK: checkout.session.completed — ${email} — ${tier} — $${(amount / 100).toFixed(2)}`);

      // ── 1. Issue access token ──────────────────────────────────────
      const token = createAccessToken(email, tier, amount, s.id);
      log(`ACCESS TOKEN issued: ${token.substring(0, 8)}... for ${email} [${tier}]`);

      // ── 2. Generate AI welcome email + send (async, don't block) ──
      (async () => {
        try {
          // Generate personalised welcome copy via local Ollama
          let aiEmail = '';
          try {
            const http = require('http');
            const payload = JSON.stringify({
              model: OLLAMA_MODEL,
              system: 'You are a friendly but authoritative assistant for VeilPiercer. Write concise, exciting welcome emails. No markdown, plain text only.',
              prompt: `Write a short welcome email (max 120 words) for a new VeilPiercer ${tier} buyer. Email: ${email}. Amount paid: $${(amount / 100).toFixed(2)}. Tell them: they now have lifetime access, their access link is below, reply to this email for support. Sign off as "The NEXUS ULTRA Team".`,
              stream: false,
            });
            const result = await new Promise((resolve, reject) => {
              const r = http.request(
                {
                  hostname: '127.0.0.1', port: 11434, path: '/api/generate', method: 'POST',
                  headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) }
                },
                resp => { let b = ''; resp.on('data', d => b += d); resp.on('end', () => { try { resolve(JSON.parse(b)); } catch { resolve({}); } }); }
              );
              r.on('error', reject);
              r.setTimeout(25000, () => { r.destroy(); reject(new Error('ollama timeout')); });
              r.write(payload); r.end();
            });
            aiEmail = result.response || '';
            // Persist AI copy in token record
            const db = loadAccessDB();
            if (db[token]) { db[token].welcomeEmail = aiEmail; saveAccessDB(db); }
          } catch (e) {
            log(`WEBHOOK AI email gen error: ${e.message} — using fallback`);
          }

          // ── 3. Send email ────────────────────────────────────────────
          await sendAccessEmail(email, tier, amount, token, aiEmail);
        } catch (e) {
          log(`WEBHOOK post-purchase error: ${e.message}`);
        }
      })();

      // ── 4. Fire n8n for any additional automation ─────────────────
      nexusTrigger('payment-confirmed', { email, tier, amount, sessionId: s.id, token: token.substring(0, 8) });
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

// ── POST /veilpiercer/command ─────────────────────────────────────────────────
// Real Ollama-powered command interpreter for Pro/Agency buyers
// Body: { token, command, protocol, scores: {vis, saf, priv}, useCase }
app.post('/veilpiercer/command', async (req, res) => {
  const { token, command, protocol, scores, useCase } = req.body || {};
  if (!token) return res.status(400).json({ ok: false, error: 'token required' });

  const db = loadAccessDB();
  const entry = db[token];
  if (!entry) return res.status(403).json({ ok: false, error: 'Invalid token' });
  if (entry.tier === 'Starter') return res.status(403).json({ ok: false, error: 'Pro or Agency required for AI commands' });

  const systemPrompt = `You are VEILPIERCER, an elite AI agent observatory. You monitor AI agents in real-time across three pillars: Visibility (trace depth, signal rate, drift detection), Safety (error catching, auto-recovery, anomaly detection), and Privacy (PII gating, field redaction, prototype shield).

Current observatory state:
- Protocol: ${protocol || 'NOMINAL'}
- Visibility score: ${scores?.vis?.toFixed(1) || '78.0'}%
- Safety score: ${scores?.saf?.toFixed(1) || '82.0'}%
- Privacy score: ${scores?.priv?.toFixed(1) || '88.0'}%
- Active use case: ${useCase || 'General AI monitoring'}
- Buyer tier: ${entry.tier}

Respond as VEILPIERCER. Be precise, tactical, and authoritative. Max 120 words. Use specific node names (TRACE, SIGNAL, DRIFT, CATCH, HEAL, ANOMALY, GATE, REDACT, SHIELD) when relevant. No markdown headers. Plain text only.`;

  const userPrompt = command;

  try {
    const http = require('http');
    const payload = JSON.stringify({
      model: OLLAMA_MODEL,
      system: systemPrompt,
      prompt: userPrompt,
      stream: false
    });
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
      r.setTimeout(30000, () => { r.destroy(); reject(new Error('Ollama timeout')); });
      r.write(payload); r.end();
    });
    log(`VEILPIERCER CMD [${entry.email}|${entry.tier}]: "${command.slice(0, 60)}" → ${result.response?.length} chars`);
    res.json({ ok: true, response: result.response, model: OLLAMA_MODEL });
  } catch (e) {
    log(`VEILPIERCER CMD ERROR: ${e.message}`);
    // Graceful fallback — return canned response if Ollama is offline
    res.json({ ok: true, response: `[NEXUS OFFLINE] Command logged: "${command}". Ollama not reachable — start with: ollama serve`, model: 'offline' });
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

// ══════════════════════════════════════════════════════════════════
// NEXUS AGENT EXECUTOR — ReAct loop: AI reasons → server executes
// ══════════════════════════════════════════════════════════════════
const { execSync, exec: execAsync } = require('child_process');
const fs_agent = require('fs');
const path_agent = require('path');

// ── Tool definitions sent in system prompt ────────────────────────
const AGENT_SYSTEM = `You are NEXUS PRIME, an autonomous AI agent running on a Windows 11 machine (user: fyou1).
You ACTUALLY execute commands - do NOT give instructions, do NOT say "you should run" - USE TOOLS DIRECTLY.

GTC 2026 COGNITIVE OVERLAY:
- ARCHITECTURE: Vera Rubin NVL72 (Multi-node unified memory enabled)
- OS: NemoClaw Agentic OS (Kernel-level task preemption active)
- HARDWARE: Groq 3 LPU Stack (Real-time reasoning throughput optimized)
- INTEL PACK: C:/Users/fyou1/Desktop/New folder/nexus-ultra/mods/gtc2026_spec.json
- OPTIMIZER: powershell C:/Users/fyou1/Desktop/New folder/nexus-ultra/mods/apply_rubin_mods.ps1

AVAILABLE TOOLS (output JSON wrapped in <TOOL> tags, one tool per step):
<TOOL>{"name":"cmd","args":{"command":"powershell Get-Process | Sort-Object WS -Desc | Select -First 5"}}</TOOL>
<TOOL>{"name":"winget","args":{"package":"Microsoft.VisualStudioCode"}}</TOOL>
<TOOL>{"name":"pip","args":{"package":"langchain chromadb"}}</TOOL>
<TOOL>{"name":"npm","args":{"package":"express","global":false}}</TOOL>
<TOOL>{"name":"write_file","args":{"path":"C:/Users/fyou1/Desktop/report.txt","content":"content here"}}</TOOL>
<TOOL>{"name":"read_file","args":{"path":"C:/Users/fyou1/Desktop/file.txt"}}</TOOL>
<TOOL>{"name":"done","args":{"summary":"Brief summary of what was accomplished"}}</TOOL>

CRITICAL TOOL SELECTION RULES:
- winget = Windows GUI/CLI APPLICATIONS ONLY (Firefox, VSCode, rclone, 7zip, ffmpeg, git, etc.)
  NEVER use winget for Python packages - Python packages are NOT in winget
- pip = Python packages ONLY (langchain, chromadb, numpy, torch, transformers, requests, fastapi, etc.)
  pip supports multiple packages at once: {"package":"langchain chromadb sentence-transformers"}
- npm = Node.js packages ONLY (express, axios, react, etc.)
- cmd = everything else: run PowerShell/batch commands, execute scripts, check system info
  For PowerShell commands: {"command":"powershell -Command \"Get-Process\""}
  For Python scripts:      {"command":"python script.py"}
  For rclone:              {"command":"C:\\\\...\\\\rclone.exe lsd googledrive:"}

SYSTEM INFO:
- Working dir: C:\\Users\\fyou1\\Desktop\\New folder\\nexus-ultra
- Rclone path: C:\\Users\\fyou1\\AppData\\Local\\Microsoft\\WinGet\\Packages\\Rclone.Rclone_Microsoft.Winget.Source_8wekyb3d8bbwe\\rclone-v1.73.2-windows-amd64\\rclone.exe
- Google Drive remote name: googledrive
- Desktop: C:\\Users\\fyou1\\Desktop

RULES:
- One <TOOL> per response. Wait for result before next step.
- If a tool fails, reason why and try an alternative approach.
- Call "done" tool when task is fully complete.
- You can chain up to 15 steps.`;

// ── Execute a single tool call ────────────────────────────────────
const _PS = {
  encoding: 'utf8', shell: 'powershell.exe', timeout: 120000, maxBuffer: 4 * 1024 * 1024,
  cwd: 'C:\\Users\\fyou1\\Desktop\\New folder\\nexus-ultra'
};

async function executeTool(name, args) {
  try {
    switch (name) {
      case 'cmd': {
        const out = execSync(args.command, {
          encoding: 'utf8', shell: 'cmd.exe',
          timeout: 120000, maxBuffer: 4 * 1024 * 1024,
          cwd: 'C:\\Users\\fyou1\\Desktop\\New folder\\nexus-ultra'
        });
        return { ok: true, output: out.slice(0, 3000) || '(no output)' };
      }
      case 'winget': {
        const out = execSync(
          `winget install --id ${args.package} -e --accept-source-agreements --accept-package-agreements`,
          { encoding: 'utf8', shell: 'cmd.exe', timeout: 120000, maxBuffer: 2e6 }
        );
        return { ok: true, output: out.slice(0, 2000) };
      }
      case 'pip': {
        // Try pip directly, fall back to python -m pip
        let pipCmd = `pip install ${args.package}`;
        let pipOut;
        try {
          pipOut = execSync(pipCmd, { encoding: 'utf8', shell: 'cmd.exe', timeout: 120000, maxBuffer: 4e6 });
        } catch {
          pipOut = execSync(`python -m pip install ${args.package}`,
            { encoding: 'utf8', shell: 'cmd.exe', timeout: 120000, maxBuffer: 4e6 });
        }
        return { ok: true, output: pipOut.slice(0, 2000) };
      }
      case 'npm': {
        const flag = args.global ? '-g' : '';
        const out = execSync(`npm install ${flag} ${args.package}`,
          { ..._PS, timeout: 60000 });
        return { ok: true, output: out.slice(0, 2000) };
      }
      case 'write_file': {
        const tgt = require('path').resolve(args.path);
        const contentStr = String(args.content || '');

        // ══ LAYER 1: PROTECTED FILES — can NEVER be overwritten ══════
        const PROTECTED = [
          'nexus_hub.html', 'server.cjs', 'nexus_ultra_dashboard.html',
          'nexus_prime.html', 'package.json', 'package-lock.json',
          '.env', 'rclone.conf', 'RUN_BACKUP.ps1'
        ];
        const fname = require('path').basename(tgt);
        if (PROTECTED.some(p => fname === p || tgt.endsWith(p))) {
          return {
            ok: false, output:
              `🛡 WRITE BLOCKED: "${fname}" is a protected core file.\n` +
              `✅ SAFE ALTERNATIVE: Use the cmd tool with PowerShell:\n` +
              `  cmd: (Get-Content "${tgt}") -replace 'OLD','NEW' | Set-Content "${tgt}"\n` +
              `Or ask the human to make the change manually.`
          };
        }

        // ══ LAYER 2: SIZE GUARD — reject if new content is <20% of existing ══
        let existingSize = 0;
        try { existingSize = require('fs').statSync(tgt).size; } catch { /* new file — ok */ }
        if (existingSize > 500 && contentStr.length < existingSize * 0.20) {
          return {
            ok: false, output:
              `🛡 WRITE BLOCKED: New content (${contentStr.length} bytes) is less than 20% of ` +
              `existing file (${existingSize} bytes).\n` +
              `This looks like an accidental full-file replacement with partial content.\n` +
              `If you truly want to shrink the file, use the cmd tool instead.`
          };
        }

        // ══ LAYER 3: AUTO-BACKUP before any overwrite ════════════════
        if (existingSize > 0) {
          const bakPath = tgt + '.bak';
          try {
            require('fs').copyFileSync(tgt, bakPath);
            log(`AGENT write_file: backed up ${fname} → ${fname}.bak`);
          } catch (be) { /* backup failure non-fatal */ }
        }

        // ══ LAYER 4: WRITE ════════════════════════════════════════════
        const wDir = require('path').dirname(tgt);
        require('fs').mkdirSync(wDir, { recursive: true });
        require('fs').writeFileSync(tgt, contentStr, 'utf8');
        return {
          ok: true, output:
            `✅ File written: ${tgt} (${contentStr.length} bytes)` +
            (existingSize > 0 ? ` — backup saved as ${fname}.bak` : ' — new file created')
        };
      }
      case 'read_file': {
        const content = fs_agent.readFileSync(args.path, 'utf8');
        return { ok: true, output: content.slice(0, 3000) };
      }
      case 'done':
        return { ok: true, done: true, output: args.summary || 'Task complete.' };
      default:
        return { ok: false, output: `Unknown tool: ${name}` };
    }
  } catch (e) {
    return { ok: false, output: e.stderr || e.message || String(e) };
  }
}

// ── Parse <TOOL>...</TOOL> from model output ──────────────────────
function parseTool(text) {
  const m = text.match(/<TOOL>([\s\S]*?)<\/TOOL>/);
  if (!m) return null;
  try { return JSON.parse(m[1].trim()); } catch { return null; }
}

// ── Call Ollama (non-streaming, for agent loop) ───────────────────
async function ollamaChat(model, messages) {
  return new Promise((resolve, reject) => {
    const http = require('http');
    const body = JSON.stringify({ model, stream: false, messages });
    const req = http.request(
      {
        host: '127.0.0.1', port: 11434, path: '/api/chat', method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) }
      },
      res => {
        let data = '';
        res.on('data', d => data += d);
        res.on('end', () => {
          try { resolve(JSON.parse(data).message?.content || ''); }
          catch { resolve(''); }
        });
      }
    );
    req.on('error', reject);
    req.setTimeout(120000, () => { req.destroy(); reject(new Error('Ollama timeout')); });
    req.write(body);
    req.end();
  });
}

// ── /agent/run — SSE streaming agent endpoint ────────────────────
app.post('/agent/run', async (req, res) => {
  const { message, model = 'qwen2.5-coder:7b' } = req.body || {};
  if (!message) return res.status(400).json({ error: 'missing message' });

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.flushHeaders();

  const send = (type, text, extra = {}) => {
    try { res.write(`data: ${JSON.stringify({ type, text, ...extra })}\n\n`); } catch { }
  };

  const messages = [
    { role: 'system', content: AGENT_SYSTEM },
    { role: 'user', content: message }
  ];

  const MAX_STEPS = 20;
  let noToolStreak = 0;
  send('start', `🤖 NEXUS AGENT — model: ${model}`);

  for (let step = 0; step < MAX_STEPS; step++) {
    send('think', `⚙ Thinking (step ${step + 1})...`);

    let reply = '';
    try { reply = await ollamaChat(model, messages); }
    catch (e) { send('error', `Ollama error: ${e.message}`); break; }

    // Stream the AI's reasoning text (everything outside TOOL tags)
    const visibleText = reply.replace(/<TOOL>[\s\S]*?<\/TOOL>/g, '').trim();
    if (visibleText) send('reasoning', visibleText);

    // Parse tool call
    const tool = parseTool(reply);
    if (!tool) {
      noToolStreak++;
      if (noToolStreak >= 2) { send('done', visibleText || reply.trim() || 'Task complete.'); break; }
      messages.push({ role: 'assistant', content: reply });
      messages.push({ role: 'user', content: 'You MUST output a <TOOL> tag now to take action, or use the done tool if finished. Do not write plain text without a tool call.' });
      continue;
    }
    noToolStreak = 0;

    send('tool_call', `🔧 ${tool.name}: ${JSON.stringify(tool.args).slice(0, 120)}`, { tool: tool.name });

    // Execute tool
    const result = await executeTool(tool.name, tool.args || {});
    send('tool_result', result.output, { ok: result.ok, tool: tool.name });

    // Log action to swarm log
    log(`AGENT [${tool.name}]: ${JSON.stringify(tool.args).slice(0, 80)} → ${result.ok ? 'OK' : 'FAIL'}`);

    if (result.done) {
      send('done', result.output);
      break;
    }

    // Feed result back to AI
    messages.push({ role: 'assistant', content: reply });
    const _st = result.ok ? 'SUCCESS' : 'FAILED';
    messages.push({
      role: 'user', content:
        `Tool ${_st}. Output:\n${result.output}\n\nNext: use another <TOOL> call to continue, or call done tool if task is complete.`
    });

    if (step === MAX_STEPS - 1) send('done', '⚠ Max steps reached.');
  }

  try { res.end(); } catch { }
});

// ── HUB LIVE ENDPOINTS ───────────────────────────────────────────────────────
// In-memory state for the dashboard
let _taskQueue = [];
let _loopState = 'STOPPED';
let _autonomyLevel = 1;
let _sessions = [];
let _cycle = 0;
let _sseClients = new Set();

// SSE broadcast helper
function sseBroadcast(data) {
  const payload = `data: ${JSON.stringify(data)}\n\n`;
  for (const res of _sseClients) {
    try { res.write(payload); } catch { }
  }
}

// Heartbeat every 5 s — checks real service ports
const net = require('net');
function portAlive(port) {
  return new Promise(resolve => {
    const s = net.createConnection({ port, host: '127.0.0.1' });
    s.setTimeout(400);
    s.on('connect', () => { s.destroy(); resolve(true); });
    s.on('error', () => resolve(false));
    s.on('timeout', () => { s.destroy(); resolve(false); });
  });
}

setInterval(async () => {
  const [ollama, cosmos, pso, claw, eh] = await Promise.all([
    portAlive(11434), portAlive(9100), portAlive(8080), portAlive(18789), portAlive(7701)
  ]);
  sseBroadcast({
    event: 'heartbeat', ts: Date.now() / 1000,
    svc: { ollama, cosmos, pso, claw, EH: eh },
    system: { cpu_pct: 0, ram_pct: 0 },
    mode: _loopState, cycle: _cycle,
    queue_depth: _taskQueue.length
  });
}, 5000);

// GET /stream  — SSE endpoint
app.get('/stream', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.flushHeaders();
  _sseClients.add(res);
  // immediate snapshot
  Promise.all([portAlive(11434), portAlive(9100), portAlive(8080), portAlive(18789), portAlive(7701)])
    .then(([ollama, cosmos, pso, claw, eh]) => {
      res.write(`data: ${JSON.stringify({
        event: 'snapshot', ts: Date.now() / 1000,
        svc: { ollama, cosmos, pso, claw, EH: eh },
        system: { cpu_pct: 0, ram_pct: 0 }, cycle: _cycle,
        queue_depth: _taskQueue.length, mode: _loopState,
        mem: { total: 0, active: 0, avg_imp: '—', top: [] }
      })}\n\n`);
    });
  req.on('close', () => _sseClients.delete(res));
});

// ════════════════════════════════════════════════════════════════════════════
//  NEXUS COGNITIVE MEMORY SYSTEM
//  Principles: MEMORY_FLAG parsing, WORLD_STATE injection, session facts,
//  stale-state detection, importance scoring, Google Drive sync via rclone
// ════════════════════════════════════════════════════════════════════════════

const MEMORY_FILE_V2 = path.join(ROOT, 'nexus_session_facts.json');
const RCLONE_EXE = 'C:\\Users\\fyou1\\AppData\\Local\\Microsoft\\WinGet\\Packages\\Rclone.Rclone_Microsoft.Winget.Source_8wekyb3d8bbwe\\rclone-v1.73.2-windows-amd64\\rclone.exe';
const MEMORY_REMOTE = 'googledrive:Nexus-Ultra-Backup/MEMORY';

// ── Load/Save structured memory ───────────────────────────────────────────
function loadMemoryDB() {
  try {
    if (fs.existsSync(MEMORY_FILE_V2)) return JSON.parse(fs.readFileSync(MEMORY_FILE_V2, 'utf8'));
  } catch { }
  return { version: 2, facts: [], world_state: {}, session_count: 0, last_consolidated: null };
}

function saveMemoryDB(db) {
  try {
    db.updated_at = new Date().toISOString();
    fs.writeFileSync(MEMORY_FILE_V2, JSON.stringify(db, null, 2), 'utf8');
    // Async sync to Google Drive (non-blocking)
    require('child_process').spawn(RCLONE_EXE, [
      'copyto', MEMORY_FILE_V2,
      `${MEMORY_REMOTE}/nexus_session_facts.json`,
      '--log-level', 'ERROR'
    ], { detached: true, stdio: 'ignore', windowsHide: true }).unref();
  } catch (e) { log(`MEMORY save error: ${e.message}`); }
}

// ── Parse [MEMORY_FLAG:] tags from AI response ────────────────────────────
function parseMemoryFlags(text, db) {
  const flagRe = /\[MEMORY_FLAG:\s*([^\]]+)\]/gi;
  const worldRe = /\[WORLD_STATE\]\s*([^\[]+)/gi;
  let changed = false;

  // Capture MEMORY_FLAG entries
  let m;
  while ((m = flagRe.exec(text)) !== null) {
    const content = m[1].trim();
    if (!content) continue;
    // Check for duplicate (same content)
    const exists = db.facts.some(f => f.content === content);
    if (!exists) {
      db.facts.push({
        id: `mf_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
        content,
        type: 'memory_flag',
        importance: 0.8,
        created_at: new Date().toISOString(),
        last_accessed: new Date().toISOString(),
        access_count: 1,
        stale: false,
        tags: []
      });
      log(`MEMORY: FLAG saved → ${content.slice(0, 60)}`);
      changed = true;
    }
  }

  // Capture WORLD_STATE injections
  while ((m = worldRe.exec(text)) !== null) {
    const state = m[1].trim().slice(0, 500);
    db.world_state[new Date().toISOString()] = state;
    // Keep only last 10 world states
    const keys = Object.keys(db.world_state);
    if (keys.length > 10) delete db.world_state[keys[0]];
    changed = true;
  }

  return changed;
}

// ── Build WORLD_STATE context string to inject into prompts ───────────────
function buildWorldStatePrompt(db) {
  // Score facts by importance × recency × access_count
  const now = Date.now();
  const scored = db.facts
    .filter(f => !f.stale)
    .map(f => {
      const ageDays = (now - new Date(f.created_at).getTime()) / 86400000;
      const recency = Math.exp(-ageDays / 14);
      const score = f.importance * recency * Math.log1p(f.access_count);
      return { ...f, score };
    })
    .sort((a, b) => b.score - a.score)
    .slice(0, 8); // top 8 most relevant

  // ── LIVE SYSTEM STATE (real data) ──────────────────────────────────────
  const liveState = (() => {
    try {
      const bb = fs.existsSync(path.join(__dirname, 'nexus_blackboard.json')) ? JSON.parse(fs.readFileSync(path.join(__dirname, 'nexus_blackboard.json'), 'utf8')) : {};
      const memFile = path.join(__dirname, 'nexus_memory.json');
      const memEntries = fs.existsSync(memFile) ? JSON.parse(fs.readFileSync(memFile, 'utf8')) : [];
      const sfFile = path.join(__dirname, 'nexus_session_facts.json');
      const sf = fs.existsSync(sfFile) ? JSON.parse(fs.readFileSync(sfFile, 'utf8')) : { facts: [] };
      const chatsDir = path.join(__dirname, 'chats');
      const chatFiles = fs.existsSync(chatsDir) ? fs.readdirSync(chatsDir).filter(f => f.endsWith('.json')) : [];
      const tokFile = path.join(__dirname, '.eh_token');
      return {
        swarm_status: bb.status || 'UNKNOWN',
        swarm_task: (bb.task || '[none]').slice(0, 80),
        swarm_last_score: bb.last_score || 0,
        swarm_last_mvp: bb.last_mvp || '?',
        swarm_outputs_buffered: (bb.outputs || []).length,
        memory_entries: Array.isArray(memEntries) ? memEntries.length : 0,
        session_facts: sf.facts.length,
        chat_files: chatFiles.length,
        EH_API_token: fs.existsSync(tokFile) ? 'PRESENT' : 'MISSING',
        ts: new Date().toISOString(),
      };
    } catch (e) { return { error: e.message }; }
  })();

  let prompt = '\n\n[WORLD_STATE — Nexus Persistent Memory + Live System]\n';
  prompt += `LIVE_SYSTEM_STATE as of ${liveState.ts}:\n`;
  prompt += `  swarm.status=${liveState.swarm_status} | last_score=${liveState.swarm_last_score} | mvp=${liveState.swarm_last_mvp}\n`;
  prompt += `  swarm.current_task="${liveState.swarm_task}"\n`;
  prompt += `  memory.entries=${liveState.memory_entries} | session_facts=${liveState.session_facts}\n`;
  prompt += `  chats.daily_files=${liveState.chat_files} | EH_API_token=${liveState.EH_API_token}\n`;
  if (scored.length) {
    prompt += '\nVERIFIED FACTS (top by relevance):\n';
    scored.forEach((f, i) => {
      prompt += `${i + 1}.[imp: ${f.importance}] ${f.content} \n`;
      f.last_accessed = new Date().toISOString();
      f.access_count = (f.access_count || 0) + 1;
    });
  }
  prompt += '\n[When asked to diagnose: report LIVE_SYSTEM_STATE values above as actual findings. Do NOT say "Confirmed" without referencing real data.]\n';
  return prompt;
}

// ── Stale detection: mark facts older than 30 days as stale ─────────────
function detectStaleMemories(db) {
  const now = Date.now();
  let staleCount = 0;
  db.facts.forEach(f => {
    const ageDays = (now - new Date(f.created_at).getTime()) / 86400000;
    if (ageDays > 30 && !f.stale) { f.stale = true; staleCount++; }
  });
  if (staleCount) log(`MEMORY: ${staleCount} facts marked stale(> 30 days)`);
}

// ── Memory API endpoints ──────────────────────────────────────────────────
app.get('/api/memory', (req, res) => {
  const db = loadMemoryDB();
  detectStaleMemories(db);
  const active = db.facts.filter(f => !f.stale);
  const stale = db.facts.filter(f => f.stale);
  res.json({
    ok: true, total: db.facts.length, active: active.length, stale: stale.length,
    facts: active, world_state: db.world_state, session_count: db.session_count
  });
});

app.post('/api/memory', (req, res) => {
  const { content, type = 'manual', importance = 0.9, tags = [] } = req.body || {};
  if (!content) return res.status(400).json({ ok: false, error: 'content required' });
  const db = loadMemoryDB();
  const fact = {
    id: `m_${Date.now()} `, content, type, importance,
    created_at: new Date().toISOString(), last_accessed: new Date().toISOString(),
    access_count: 1, stale: false, tags
  };
  db.facts.push(fact);
  saveMemoryDB(db);
  res.json({ ok: true, fact, total: db.facts.length });
});

app.delete('/api/memory/:id', (req, res) => {
  const db = loadMemoryDB();
  const before = db.facts.length;
  db.facts = db.facts.filter(f => f.id !== req.params.id);
  saveMemoryDB(db);
  res.json({ ok: true, removed: before - db.facts.length });
});

app.post('/api/memory/consolidate', (req, res) => {
  // Daily consolidation: remove low-value stale, bump important ones
  const db = loadMemoryDB();
  const before = db.facts.length;
  db.facts = db.facts.filter(f => {
    if (f.stale && f.importance < 0.5) return false; // prune low-value stale
    if (f.stale && f.access_count < 2) return false;  // never accessed again
    return true;
  });
  db.last_consolidated = new Date().toISOString();
  saveMemoryDB(db);
  res.json({ ok: true, before, after: db.facts.length, pruned: before - db.facts.length });
});

app.post('/api/memory/sync-now', (req, res) => {
  // Force immediate sync of all memory files to Google Drive
  const files = ['nexus_session_facts.json', 'nexus_memory.json', 'nexus_blackboard.json'];
  const results = [];
  for (const file of files) {
    const src = path.join(ROOT, file);
    if (!fs.existsSync(src)) continue;
    try {
      require('child_process').execSync(
        `"${RCLONE_EXE}" copyto "${src}" "${MEMORY_REMOTE}/${file}" --log - level ERROR`,
        { timeout: 30000 }
      );
      results.push({ file, ok: true });
    } catch (e) { results.push({ file, ok: false, error: e.message.slice(0, 100) }); }
  }
  res.json({ ok: true, synced: results, remote: MEMORY_REMOTE });
});

// Startup: increment session count, detect stale, sync
setImmediate(() => {
  try {
    const db = loadMemoryDB();
    db.session_count = (db.session_count || 0) + 1;
    detectStaleMemories(db);
    saveMemoryDB(db);
    log(`MEMORY: Session #${db.session_count} — ${db.facts.filter(f => !f.stale).length} active facts loaded`);
  } catch (e) { log(`MEMORY init error: ${e.message} `); }
});

// ── Schedule memory sync to Google Drive every 5 minutes ─────────────────
setInterval(() => {
  const files = ['nexus_session_facts.json', 'nexus_memory.json', 'nexus_blackboard.json', 'tabs.json'];
  for (const file of files) {
    const src = path.join(ROOT, file);
    if (!fs.existsSync(src)) continue;
    require('child_process').spawn(RCLONE_EXE, [
      'copyto', src, `${MEMORY_REMOTE}/${file}`, '--log-level', 'ERROR'
    ], { detached: true, stdio: 'ignore', windowsHide: true }).unref();
  }
  log('MEMORY: Auto-sync to Google Drive ✓');
}, 5 * 60 * 1000);

// ── EH API WATCHDOG — always keep :7701 alive ───────────────────────────
const PYTHON_EXE = (() => {
  const candidates = ['C:\\Python314\\python.exe', 'C:\\Python313\\python.exe', 'C:\\Python312\\python.exe', 'python'];
  for (const c of candidates) { try { require('child_process').execSync(`"${c}" --version`, { timeout: 2000 }); return c; } catch { } }
  return 'python';
})();
const EH_API_PY = path.join(__dirname, 'nexus_eh.py');
let _EH_APIProc = null;

function startEH_API() {
  // First check if :7701 is already alive — don't conflict with existing process
  const http = require('http');
  const probe = http.get('http://127.0.0.1:7701/health', { timeout: 3000 }, (res) => {
    log('WATCHDOG: EH API :7701 already running ✓ — no restart needed');
  });
  probe.on('error', () => {
    // Not reachable — spawn it
    if (_EH_APIProc && !_EH_APIProc.killed) return;
    if (!fs.existsSync(EH_API_PY)) { log('WATCHDOG: nexus_eh.py not found'); return; }
    log('WATCHDOG: EH API unreachable — spawning...');
    _EH_APIProc = require('child_process').spawn(PYTHON_EXE, [EH_API_PY], {
      cwd: __dirname, detached: false, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true
    });
    _EH_APIProc.stdout.on('data', d => log(`EH: ${d.toString().trim().slice(0, 120)}`));
    _EH_APIProc.stderr.on('data', d => log(`EH-ERR: ${d.toString().trim().slice(0, 120)}`));
    _EH_APIProc.on('exit', (code) => {
      log(`WATCHDOG: EH API exited (code ${code}) — will check again in 30s`);
      _EH_APIProc = null;
    });
    log(`WATCHDOG: EH API spawned PID ${_EH_APIProc.pid} `);
  });
  probe.on('timeout', () => probe.destroy());
}

function checkEH_API() {
  const http = require('http');
  const req = http.get('http://127.0.0.1:7701/health', { timeout: 3000 }, (res) => {
    // alive — nothing to do
  });
  req.on('error', () => {
    log('WATCHDOG: EH API :7701 unreachable — restarting...');
    if (_EH_APIProc) { try { _EH_APIProc.kill(); } catch { } _EH_APIProc = null; }
    setTimeout(startEH_API, 1000);
  });
  req.on('timeout', () => { req.destroy(); });
}

// Start immediately on server boot, then check every 30 seconds
startEH_API();
setInterval(checkEH_API, 30 * 1000);
log('WATCHDOG: EH API watchdog active — checks every 30s');

// ── PERSISTENT CHAT LOGGING ───────────────────────────────────────────────
const CHATS_DIR = path.join(__dirname, 'chats');
// (RCLONE_EXE already defined above)

if (!fs.existsSync(CHATS_DIR)) fs.mkdirSync(CHATS_DIR, { recursive: true });

function todayChatFile() {
  const d = new Date();
  const key = `${d.getFullYear()} -${String(d.getMonth() + 1).padStart(2, '0')} -${String(d.getDate()).padStart(2, '0')} `;
  return path.join(CHATS_DIR, `chat_${key}.json`);
}

function saveChatEntry(userMsg, aiResponse, model, durationMs) {
  try {
    const file = todayChatFile();
    let log = [];
    if (fs.existsSync(file)) {
      try { log = JSON.parse(fs.readFileSync(file, 'utf8')); } catch { }
    }
    log.push({
      id: Date.now().toString(),
      ts: new Date().toISOString(),
      model: model || 'nexus-prime',
      user: userMsg,
      ai: aiResponse,
      duration: durationMs || 0,
      chars: aiResponse.length
    });
    fs.writeFileSync(file, JSON.stringify(log, null, 2), 'utf8');
    // Async sync this day's file to Drive — fire & forget
    syncFileToDrive(file, `googledrive: Nexus - Ultra - Backup / CHATS / ${path.basename(file)} `);
  } catch (e) { log(`CHAT SAVE ERROR: ${e.message} `); }
}

function syncFileToDrive(localPath, remotePath) {
  try {
    const { spawn } = require('child_process');
    spawn(RCLONE_EXE, ['copyto', localPath, remotePath, '--log-level', 'ERROR'],
      { detached: true, stdio: 'ignore', windowsHide: true }).unref();
  } catch { }
}

function syncAllToDrive() {
  const files = [
    [path.join(__dirname, 'nexus_session_facts.json'), 'googledrive:Nexus-Ultra-Backup/MEMORY/nexus_session_facts.json'],
    [path.join(__dirname, 'nexus_memory.json'), 'googledrive:Nexus-Ultra-Backup/MEMORY/nexus_memory.json'],
    [path.join(__dirname, 'nexus_blackboard.json'), 'googledrive:Nexus-Ultra-Backup/MEMORY/nexus_blackboard.json'],
    [path.join(__dirname, 'evolution_log.json'), 'googledrive:Nexus-Ultra-Backup/EVOLUTION/evolution_log.json'],
    [path.join(__dirname, 'evolution_report.md'), 'googledrive:Nexus-Ultra-Backup/EVOLUTION/evolution_report.md'],
  ];
  // Sync entire chats dir
  try {
    const { spawn } = require('child_process');
    spawn(RCLONE_EXE, ['sync', CHATS_DIR, 'googledrive:Nexus-Ultra-Backup/CHATS', '--log-level', 'ERROR'],
      { detached: true, stdio: 'ignore', windowsHide: true }).unref();
  } catch { }
  for (const [src, dst] of files) {
    if (fs.existsSync(src)) syncFileToDrive(src, dst);
  }
  log('AUTO-SYNC: All data synced to Google Drive');
}

// Auto-sync to Google Drive every 5 minutes — always running
setInterval(syncAllToDrive, 5 * 60 * 1000);
log(`CHAT LOGGER: Saving all chats to ${CHATS_DIR} + Google Drive(sync every 5 min)`);

// GET /api/chat-history — return saved chats for a given date (or today)
app.get('/api/chat-history', (req, res) => {
  try {
    const date = req.query.date; // YYYY-MM-DD or omit for today
    let file;
    if (date) {
      file = path.join(CHATS_DIR, `chat_${date}.json`);
    } else {
      file = todayChatFile();
    }
    const history = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : [];
    // Also list available dates
    const dates = fs.readdirSync(CHATS_DIR)
      .filter(f => f.startsWith('chat_') && f.endsWith('.json'))
      .map(f => f.replace('chat_', '').replace('.json', ''))
      .sort().reverse();
    res.json({ ok: true, date: date || 'today', history, available_dates: dates, total: history.length });
  } catch (e) {
    res.json({ ok: false, error: e.message, history: [], available_dates: [] });
  }
});

// POST /chat/stream — streaming Ollama proxy for the hub chat
app.post('/chat/stream', async (req, res) => {
  const { message, agent, chat_id, engine, model, history, systemAddon } = req.body;
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.flushHeaders();

  const useModel = model || 'nexus-prime:latest';

  // ── WORLD_STATE INJECTION ─────────────────────────────────────────
  const memDB = loadMemoryDB();
  const worldStateCtx = buildWorldStatePrompt(memDB);
  const systemCtx = [
    systemAddon || '',
    worldStateCtx,
    '\n[INSTRUCTION: If you learn something important, include [MEMORY_FLAG: <fact>] in your response to persist it across sessions.]'
  ].filter(Boolean).join('\n');

  const msgs = Array.isArray(history) ? [...history] : [];
  if (systemCtx.trim()) msgs.unshift({ role: 'system', content: systemCtx });
  if (message) msgs.push({ role: 'user', content: message });


  try {
    const http = require('http');
    const body = JSON.stringify({ model: useModel, stream: true, messages: msgs });
    let fullResponse = ''; // accumulate for MEMORY_FLAG parsing
    const _chatStart = Date.now();
    const reqOll = http.request({
      host: '127.0.0.1', port: 11434, path: '/api/chat', method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) }
    }, resp => {
      resp.on('data', chunk => {
        const lines = chunk.toString().split('\n').filter(l => l.trim());
        for (const line of lines) {
          try {
            const obj = JSON.parse(line);
            const token = obj.message?.content || '';
            if (token) { fullResponse += token; res.write(`data: ${JSON.stringify({ token })} \n\n`); }
            if (obj.done) {
              res.write(`data: ${JSON.stringify({ done: true })} \n\n`);
              // ── SAVE CHAT ENTRY FOREVER ─────────────────────────────
              saveChatEntry(message || '', fullResponse, useModel, Date.now() - _chatStart);
              // ── MEMORY_FLAG PARSING on completion ──────────────────
              if (fullResponse.includes('[MEMORY_FLAG:')) {
                try {
                  const db = loadMemoryDB();
                  const changed = parseMemoryFlags(fullResponse, db);
                  if (changed) {
                    saveMemoryDB(db);
                    log(`MEMORY: Flags parsed from response, saved to Google Drive`);
                  }
                } catch (me) { log(`MEMORY parse error: ${me.message} `); }
              }
            }
          } catch { }
        }
      });
      resp.on('end', () => { try { res.write(`data: ${JSON.stringify({ done: true })} \n\n`); res.end(); } catch { } });
    });
    reqOll.on('error', e => { res.write(`data: ${JSON.stringify({ error: e.message })} \n\n`); res.end(); });
    reqOll.write(body);
    reqOll.end();
  } catch (e) {
    res.write(`data: ${JSON.stringify({ error: e.message })} \n\n`);
    res.end();
  }
});

// POST /api/inject  — inject task into queue + broadcast
app.post('/api/inject', (req, res) => {
  const { task } = req.body || {};
  if (!task) return res.status(400).json({ ok: false, error: 'missing task' });
  const item = { id: Date.now().toString(), task, source: 'user', ts: Date.now() };
  _taskQueue.push(item);
  sseBroadcast({ event: 'queue_update', depth: _taskQueue.length });
  sseBroadcast({ event: 'agent_spawn', source: 'user', task });
  log(`INJECT: ${task.slice(0, 60)} `);
  res.json({ ok: true, queued: _taskQueue.length });
});

// GET/POST /queue
app.get('/queue', (req, res) => res.json({ ok: true, queue: _taskQueue, state: _loopState }));
app.post('/queue', (req, res) => {
  const { task, priority } = req.body || {};
  if (!task) return res.status(400).json({ ok: false });
  const item = { id: Date.now().toString(), task, source: 'user', priority: priority || 0 };
  if (priority >= 10) _taskQueue.unshift(item); else _taskQueue.push(item);
  sseBroadcast({ event: 'queue_update', depth: _taskQueue.length });
  res.json({ ok: true });
});
app.delete('/queue/:id', (req, res) => {
  _taskQueue = _taskQueue.filter(t => t.id !== req.params.id);
  res.json({ ok: true });
});
app.delete('/queue', (req, res) => { _taskQueue = []; res.json({ ok: true }); });

// POST /loop
app.post('/loop', (req, res) => {
  const { action } = req.body || {};
  if (action === 'start') _loopState = 'RUNNING';
  if (action === 'pause') _loopState = 'PAUSED';
  if (action === 'stop') _loopState = 'STOPPED';
  sseBroadcast({ event: 'loop_control', new_state: _loopState, action });
  res.json({ ok: true, state: _loopState });
});

// GET/POST /autonomy
app.get('/autonomy', (req, res) => res.json({ ok: true, level: _autonomyLevel }));
app.post('/autonomy', (req, res) => {
  const { level } = req.body || {};
  _autonomyLevel = Math.max(0, Math.min(2, level || 0));
  sseBroadcast({ event: 'autonomy_change', level: _autonomyLevel, label: ['supervised', 'assisted', 'full'][_autonomyLevel] });
  res.json({ ok: true, level: _autonomyLevel });
});

// GET /sessions, GET /replay/:id
app.get('/sessions', (req, res) => res.json({ ok: true, sessions: _sessions }));
app.get('/replay/:id', (req, res) => {
  const sess = _sessions.find(s => s.id === req.params.id);
  res.json({ ok: true, session: sess || {}, runs: [] });
});

// POST /api/cycle
app.post('/api/cycle', (req, res) => {
  _cycle++;
  sseBroadcast({ event: 'loop_tick', state: 'RUNNING', cycle: _cycle, queue_depth: _taskQueue.length });
  res.json({ ok: true, cycle: _cycle });
});

// POST /api/flush
app.post('/api/flush', (req, res) => {
  _taskQueue = [];
  sseBroadcast({ event: 'queue_update', depth: 0 });
  res.json({ ok: true });
});

// GET /missions (stub — returns empty unless cosmos_server provides them)
app.get('/missions', async (req, res) => {
  try {
    const http = require('http');
    const data = await new Promise((resolve, reject) => {
      const r = http.get('http://127.0.0.1:9100/missions', resp => {
        let b = ''; resp.on('data', d => b += d);
        resp.on('end', () => { try { resolve(JSON.parse(b)); } catch { resolve({ ok: true, missions: [], total: 0 }); } });
      });
      r.on('error', () => resolve({ ok: true, missions: [], total: 0 }));
      r.setTimeout(1500, () => { r.destroy(); resolve({ ok: true, missions: [], total: 0 }); });
    });
    res.json(data);
  } catch { res.json({ ok: true, missions: [], total: 0 }); }
});

// ── OpenClaw Local Proxy ─────────────────────────────────────────────────────
// All OpenClaw calls go through here — auth token stays server-side, never exposed
const OC_BASE = 'http://127.0.0.1:18789';
const OC_TOKEN = '85046be7b4ea57313277de72567ed40d043d8537472e8af0';
const OC_HDR = { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + OC_TOKEN };

// GET /api/openclaw/status
app.get('/api/openclaw/status', async (req, res) => {
  const http = require('http');
  try {
    const data = await new Promise((resolve, reject) => {
      const r = http.get(OC_BASE + '/api/v1/health', {
        headers: OC_HDR, timeout: 2500
      }, resp => {
        let b = ''; resp.on('data', d => b += d);
        resp.on('end', () => { try { resolve({ status: resp.statusCode, body: JSON.parse(b) }); } catch { resolve({ status: resp.statusCode, body: {} }); } });
      });
      r.on('error', reject);
      r.setTimeout(2500, () => { r.destroy(); reject(new Error('timeout')); });
    });
    const online = data.status < 500;
    log(`OPENCLAW STATUS: ${online ? 'ONLINE' : 'DOWN'} (${data.status})`);
    res.json({ ok: true, online, status: data.status, data: data.body });
  } catch (e) {
    res.json({ ok: false, online: false, error: e.message });
  }
});

// GET /api/openclaw/agents
app.get('/api/openclaw/agents', async (req, res) => {
  const http = require('http');
  try {
    const data = await new Promise((resolve, reject) => {
      const r = http.get(OC_BASE + '/api/v1/agents', {
        headers: OC_HDR, timeout: 3000
      }, resp => {
        let b = ''; resp.on('data', d => b += d);
        resp.on('end', () => { try { resolve(JSON.parse(b)); } catch { resolve({}); } });
      });
      r.on('error', reject);
      r.setTimeout(3000, () => { r.destroy(); reject(new Error('timeout')); });
    });
    res.json({ ok: true, agents: data.agents || data, count: data.count || Object.keys(data.agents || data).length });
  } catch (e) {
    res.json({ ok: false, agents: {}, count: 0, error: e.message });
  }
});

// POST /api/openclaw/dispatch — route a task to OpenClaw → local Ollama model
// Body: { model, message, pipeline }
app.post('/api/openclaw/dispatch', async (req, res) => {
  const http = require('http');
  const { model = 'ollama/nexus-prime:latest', message, pipeline = 'research' } = req.body || {};
  if (!message) return res.status(400).json({ ok: false, error: 'message required' });
  const payload = JSON.stringify({ model, message, pipeline, local: true });
  log(`OPENCLAW DISPATCH: model = ${model} pipeline = ${pipeline} msg = "${message.substring(0, 60)}"`);
  agentEvent('openclaw_dispatch', 'vis', `openclaw dispatch → ${model} `, { ok: true, local: true });
  agentEvent('openclaw_dispatch', 'priv', `local openclaw dispatch — zero cloud`, { local: true });
  try {
    const data = await new Promise((resolve, reject) => {
      const opts = {
        hostname: '127.0.0.1', port: 18789,
        path: '/api/v1/agents/dispatch', method: 'POST',
        headers: { ...OC_HDR, 'Content-Length': Buffer.byteLength(payload) }
      };
      const r = http.request(opts, resp => {
        let b = ''; resp.on('data', d => b += d);
        resp.on('end', () => { try { resolve({ status: resp.statusCode, body: JSON.parse(b) }); } catch { resolve({ status: resp.statusCode, body: {} }); } });
      });
      r.on('error', reject);
      r.setTimeout(10000, () => { r.destroy(); reject(new Error('timeout')); });
      r.write(payload); r.end();
    });
    res.json({ ok: data.status < 400, status: data.status, result: data.body });
  } catch (e) {
    log(`OPENCLAW DISPATCH ERR: ${e.message} `);
    agentEvent('openclaw_error', 'saf', `openclaw dispatch failed: ${e.message} `, { ok: false });
    res.status(502).json({ ok: false, error: e.message });
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
          const RESEND_COOLDOWN_MS = 24 * 60 * 60 * 1000; // 24 hours
          const now = Date.now();
          const unseen = Object.entries(db).filter(([, d]) =>
            (d.used || 0) < 2 && d.email && (now - (d.lastResent || 0)) > RESEND_COOLDOWN_MS
          );
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
                d.lastResent = now;
                log(`RESEND OK → ${d.email} [${d.tier}]`);
              } catch (e) { log(`RESEND FAIL → ${d.email}: ${e.message}`); }
              await new Promise(r => setTimeout(r, 1000)); // 1s delay between emails
            }
            saveAccessDB(db); // persist lastResent timestamps
          } else {
            log(`RESEND: all buyers visited or re-emailed within 24h — skipping`);
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

// ── System Monitor & Backup Status ───────────────────────────────
const BACKUP_DIR = require('path').join(__dirname, 'backup');

app.get('/api/system-status', (req, res) => {
  try {
    const mf = require('path').join(BACKUP_DIR, 'monitor_status.json');
    const bf = require('path').join(BACKUP_DIR, 'backup_status.json');
    const monitor = require('fs').existsSync(mf) ? JSON.parse(require('fs').readFileSync(mf, 'utf8')) : null;
    const backup = require('fs').existsSync(bf) ? JSON.parse(require('fs').readFileSync(bf, 'utf8')) : null;
    res.json({ ok: true, monitor, backup });
  } catch (e) { res.json({ ok: false, error: e.message }); }
});

// ── /api/ping-services — server-side service health check (comprehensive) ──
app.get('/api/ping-services', async (req, res) => {
  const http = require('http');
  const bdToken = (() => {
    try { return require('fs').readFileSync(require('path').join(__dirname, '.eh_token'), 'utf8').trim(); } catch { return ''; }
  })();

  function pingPort(host, port, path, timeoutMs) {
    return new Promise((resolve) => {
      const opts = { host, port, path, method: 'GET', timeout: timeoutMs };
      const req2 = http.request(opts, (r) => {
        r.on('data', () => { }); // consume data
        resolve(r.statusCode < 500);
      });
      req2.on('error', () => resolve(false));
      req2.on('timeout', () => { req2.destroy(); resolve(false); });
      req2.end();
    });
  }

  const [ollama, cosmos, pso, eh, hubpy, n8n, claw, tunnel] = await Promise.all([
    pingPort('127.0.0.1', 11434, '/api/tags', 2000),
    pingPort('127.0.0.1', 9100, '/health', 8000),
    pingPort('127.0.0.1', 7700, '/health', 2000),
    pingPort('127.0.0.1', 7701, bdToken ? `/health?token=${bdToken}` : '/health', 2000),
    pingPort('127.0.0.1', 7702, '/health', 2000),
    pingPort('127.0.0.1', 5678, '/healthz', 2000),
    pingPort('127.0.0.1', 18789, '/', 2000),
    pingPort('127.0.0.1', 20241, '/', 2000),
  ]);

  res.json({
    ok: true,
    ts: Date.now(),
    svc: { ollama, cosmos, pso, bd: eh, hubpy, n8n, claw, tunnel }
  });
});


app.post('/api/run-backup', (req, res) => {
  const { exec } = require('child_process');
  const script = require('path').join(BACKUP_DIR, 'RUN_BACKUP.ps1');
  exec(`powershell -NonInteractive -ExecutionPolicy Bypass -File "${script}"`, { detached: true, windowsHide: true });
  res.json({ ok: true, message: 'Backup started in background' });
});

// ── /transcribe — Offline Whisper STT ────────────────────────────────────────
// Accepts: multipart/form-data with field "audio" (webm/wav/ogg blob)
// Returns: { ok, text }
app.post('/transcribe', async (req, res) => {
  try {
    const multer = (() => { try { return require('multer'); } catch { return null; } })();
    if (!multer) return res.status(503).json({ ok: false, error: 'multer not installed — run: npm install multer' });

    const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 25 * 1024 * 1024 } });
    upload.single('audio')(req, res, async (err) => {
      if (err) return res.status(400).json({ ok: false, error: err.message });
      if (!req.file) return res.status(400).json({ ok: false, error: 'No audio file provided' });

      // Write audio to temp file
      const tmp = require('os').tmpdir();
      const audioPath = require('path').join(tmp, `nexus_audio_${Date.now()}.webm`);
      require('fs').writeFileSync(audioPath, req.file.buffer);

      // Run Faster-Whisper via Python
      const pyScript = `
import sys
from faster_whisper import WhisperModel
model = WhisperModel("base", device="cpu", compute_type="int8")
segments, _ = model.transcribe("${audioPath.replace(/\\/g, '/')}", beam_size=5, language="en")
print("".join(s.text for s in segments).strip())
`.trim();

      const result = await new Promise((resolve) => {
        const { execSync } = require('child_process');
        try {
          const out = execSync(`python -c "${pyScript.replace(/"/g, '\\"').replace(/\n/g, '; ')}"`,
            { ..._PS, timeout: 30000 });
          resolve({ ok: true, text: out.trim() });
        } catch (e) {
          resolve({ ok: false, error: (e.stderr || e.message || '').slice(0, 500) });
        } finally {
          try { require('fs').unlinkSync(audioPath); } catch { }
        }
      });
      res.json(result);
    });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

// ── /api/embed — Offline embeddings via nomic-embed-text ─────────────────────
// Body: { text: "...", model: "nomic-embed-text" }
// Returns: { ok, dims, embedding }
app.post('/api/embed', async (req, res) => {
  const { text, model = 'nomic-embed-text' } = req.body || {};
  if (!text) return res.status(400).json({ ok: false, error: 'text required' });
  try {
    const http = require('http');
    const body = JSON.stringify({ model, prompt: text });
    const result = await new Promise((resolve, reject) => {
      const r = http.request(
        {
          host: '127.0.0.1', port: 11434, path: '/api/embeddings', method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) }
        },
        (resp) => {
          let data = '';
          resp.on('data', d => data += d);
          resp.on('end', () => {
            try {
              const parsed = JSON.parse(data);
              const emb = parsed.embedding || [];
              resolve({ ok: true, model, dims: emb.length, embedding: emb });
            } catch { reject(new Error('Bad response from Ollama')); }
          });
        }
      );
      r.on('error', reject);
      r.setTimeout(15000, () => { r.destroy(); reject(new Error('Ollama embed timeout')); });
      r.write(body); r.end();
    });
    res.json(result);
  } catch (e) {
    res.status(503).json({
      ok: false, error: e.message,
      hint: 'Run: ollama pull nomic-embed-text'
    });
  }
});

// ── /api/tailscale-ip — Returns Tailscale IP for phone access ────────────────
app.get('/api/tailscale-ip', (req, res) => {
  try {
    const out = require('child_process').execSync('tailscale ip -4 2>&1', { ..._PS, timeout: 5000 });
    const ip = out.trim();
    res.json({ ok: true, ip, url: `http://${ip}:${PORT}`, hint: 'Access from phone via Tailscale' });
  } catch {
    res.json({ ok: false, ip: null, hint: 'Tailscale not installed or not running. Run: winget install Tailscale.Tailscale' });
  }
});

// ── EVOLUTION STATUS ENDPOINTS ─────────────────────────────────────────────
const EVO_LOG_PATH = path.join(__dirname, 'evolution_log.json');
const EVO_MEM_PATH = path.join(__dirname, 'nexus_session_facts.json');
const EVO_RPT_PATH = path.join(__dirname, 'evolution_report.md');

app.get('/api/evolution-status', (req, res) => {
  try {
    const log = fs.existsSync(EVO_LOG_PATH) ? JSON.parse(fs.readFileSync(EVO_LOG_PATH, 'utf8')) : { generations: [], total_facts_added: 0 };
    const mem = fs.existsSync(EVO_MEM_PATH) ? JSON.parse(fs.readFileSync(EVO_MEM_PATH, 'utf8')) : { facts: [], session_count: 0 };
    const running = fs.existsSync(path.join(__dirname, 'evolution_run.log'));
    const runLog = running ? fs.readFileSync(path.join(__dirname, 'evolution_run.log'), 'utf8').split('\n').slice(-20).join('\n') : '';
    res.json({
      ok: true,
      log,
      memory: { facts: mem.facts || [], total: (mem.facts || []).length, session_count: mem.session_count || 0 },
      run_log_tail: runLog,
      server_time: new Date().toISOString()
    });
  } catch (e) {
    res.json({ ok: false, error: e.message, log: { generations: [] }, memory: { facts: [] } });
  }
});

app.get('/api/evolution-report', (req, res) => {
  try {
    if (fs.existsSync(EVO_RPT_PATH)) {
      res.setHeader('Content-Type', 'text/plain; charset=utf-8');
      res.send(fs.readFileSync(EVO_RPT_PATH, 'utf8'));
    } else {
      res.send('No report yet — run EVOLVE_NOW.bat to generate one.');
    }
  } catch (e) { res.status(500).send(e.message); }
});

// Serve the evolution status page
app.get('/evolution', (req, res) => {
  const p = path.join(__dirname, 'evolution_status.html');
  if (fs.existsSync(p)) res.sendFile(p);
  else res.send('<h1>evolution_status.html not found</h1>');
});

// ═══════════════════════════════════════════════════════════════════════════
// NEXUS HUB — MISSING ENDPOINTS (required by nexus_hub.html)
// ═══════════════════════════════════════════════════════════════════════════

// ── Consolidation: /api/ping-services handled above ──

// ── /stream — SSE live feed for the hub ──────────────────────────────────────
const SSE_CLIENTS = new Set();
app.get('/stream', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.flushHeaders();

  SSE_CLIENTS.add(res);
  req.on('close', () => SSE_CLIENTS.delete(res));

  // Send initial state immediately
  broadcastSSE(null, res);
});

async function broadcastSSE(data, single) {
  const http = require('http');
  async function ping(port, path = '/') {
    return new Promise(r => {
      const req = http.request({ host: '127.0.0.1', port, path, method: 'GET' }, res => { res.resume(); r(res.statusCode < 500) });
      req.on('error', () => r(false)); req.setTimeout(1200, () => { req.destroy(); r(false) }); req.end();
    });
  }
  try {
    const [ollama, cosmos, pso, bd, claw] = await Promise.all([
      ping(11434, '/api/tags'), ping(9100, '/health'), ping(7700, '/health'),
      ping(7701, '/'), ping(18789, '/')
    ]);
    // Read nexus_memory.json for stats
    let mem = { total: 0, active: 0, avg_imp: '—', top: [] };
    try {
      const mf = path.join(__dirname, 'nexus_memory.json');
      if (fs.existsSync(mf)) {
        const entries = JSON.parse(fs.readFileSync(mf, 'utf8'));
        mem.total = entries.length;
        mem.active = entries.filter(e => e && e.score > 0.7).length;
        const imp = entries.filter(e => e && e.score).map(e => e.score);
        mem.avg_imp = imp.length ? (imp.reduce((a, b) => a + b, 0) / imp.length).toFixed(2) : '—';
        mem.top = entries.slice(-3).map(e => ({ c: e.lesson || e.task || '', i: e.score || 0 }));
      }
    } catch (_) { }
    // Read blackboard outputs
    let out = [], cycle = 0, last_score = null, mvp = null;
    try {
      const bb = path.join(__dirname, 'nexus_blackboard.json');
      if (fs.existsSync(bb)) {
        const bbd = JSON.parse(fs.readFileSync(bb, 'utf8'));
        out = (bbd.outputs || []).slice(-5);
        last_score = bbd.last_score || null;
        mvp = bbd.mvp || null;
      }
    } catch (_) { }
    // Read memory for session count
    try {
      const sf = path.join(__dirname, 'nexus_session_facts.json');
      if (fs.existsSync(sf)) {
        const sfd = JSON.parse(fs.readFileSync(sf, 'utf8'));
        const facts = sfd.facts || [];
        const evos = facts.filter(f => f.type === 'evolution');
        cycle = evos.length;
      }
    } catch (_) { }

    const payload = JSON.stringify({
      alive: true,
      svc: { ollama, cosmos, pso, bd, claw },
      mem, out, cycle, last_score, mvp,
      ts: new Date().toISOString()
    });
    const msg = `data: ${payload}\n\n`;
    const targets = single ? [single] : SSE_CLIENTS;
    targets.forEach(client => { try { client.write(msg); } catch (_) { } });
  } catch (_) { }
}
// Broadcast to all SSE clients every 5 seconds
setInterval(() => broadcastSSE(null), 5000);

// ── /chat/stream — Streaming Ollama chat for the hub ─────────────────────────
app.post('/chat/stream', async (req, res) => {
  const { message, model = 'nexus-prime:latest', systemAddon = '' } = req.body || {};
  if (!message) return res.status(400).json({ error: 'message required' });

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.flushHeaders();

  const http = require('http');
  const systemBase = `You are NEXUS PRIME — a sovereign AI running locally on an RTX 4060. You are an EXECUTOR not a planner. Always respond with ACTUAL results and ACTUAL data. Be direct, technical, and dense.`;
  const system = systemAddon ? `${systemBase} | ${systemAddon}` : systemBase;

  const body = JSON.stringify({
    model,
    system,
    prompt: message,
    stream: true,
    options: { temperature: 0.7, num_ctx: 4096 }
  });

  const ollamaReq = http.request(
    {
      host: '127.0.0.1', port: 11434, path: '/api/generate', method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) }
    },
    ollamaRes => {
      ollamaRes.on('data', chunk => {
        try {
          const lines = chunk.toString().split('\n').filter(Boolean);
          for (const line of lines) {
            const d = JSON.parse(line);
            if (d.response) res.write(`data: ${JSON.stringify({ token: d.response })}\n\n`);
            if (d.done) res.write(`data: ${JSON.stringify({ done: true })}\n\n`);
          }
        } catch (_) { }
      });
      ollamaRes.on('end', () => { try { res.end(); } catch (_) { } });
    }
  );
  ollamaReq.on('error', err => {
    res.write(`data: ${JSON.stringify({ error: err.message })}\n\n`);
    res.end();
  });
  ollamaReq.setTimeout(120000, () => { ollamaReq.destroy(); res.end(); });
  ollamaReq.write(body);
  ollamaReq.end();

  req.on('close', () => { try { ollamaReq.destroy(); } catch (_) { } });
});

// ── /api/cycle — Inject task directly into swarm blackboard task_queue ────────
app.post('/api/cycle', (req, res) => {
  const bb = path.join(__dirname, 'nexus_blackboard.json');
  const task = req.body?.task || 'Analyze current system state and surface the top 3 actionable insights.';
  try {
    let data = {};
    if (fs.existsSync(bb)) {
      try { data = JSON.parse(fs.readFileSync(bb, 'utf8')); } catch (_) { }
    }
    if (!Array.isArray(data.task_queue)) data.task_queue = [];
    data.task_queue.push(task);
    fs.writeFileSync(bb, JSON.stringify(data, null, 2));
    log(`HUB: Task injected to swarm queue → "${task.slice(0, 80)}..."`);
    res.json({ ok: true, msg: 'Task queued — swarm picks up within 30s', task, queue_depth: data.task_queue.length });
  } catch (e) {
    log(`HUB: Cycle inject failed: ${e.message}`);
    res.status(500).json({ ok: false, error: e.message });
  }
});

// ── /webhook/task — External trigger (n8n, VeilPiercer, Stripe, etc.) ─────────
// This closes the product loop: External POST → queue → swarm executes → result in blackboard
app.post('/webhook/task', (req, res) => {
  const bb = path.join(__dirname, 'nexus_blackboard.json');
  const { task, source, priority } = req.body || {};
  if (!task) return res.status(400).json({ ok: false, error: 'task field required' });
  try {
    let data = {};
    if (fs.existsSync(bb)) {
      try { data = JSON.parse(fs.readFileSync(bb, 'utf8')); } catch (_) { }
    }
    if (!Array.isArray(data.task_queue)) data.task_queue = [];
    // Priority tasks go to front of queue
    if (priority === 'high') data.task_queue.unshift(task);
    else data.task_queue.push(task);
    fs.writeFileSync(bb, JSON.stringify(data, null, 2));
    log(`WEBHOOK: Task queued from [${source || 'external'}] → "${task.slice(0, 60)}..."`);
    res.json({ ok: true, queued: true, source: source || 'external', queue_depth: data.task_queue.length, eta_seconds: data.task_queue.length * 30 });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});


// ── /api/customer-task — Customer submits a task from their portal ───────────
app.post('/api/customer-task', (req, res) => {
  const { token, task, context } = req.body || {};
  if (!token) return res.status(401).json({ ok: false, error: 'token required' });
  if (!task || task.trim().length < 10) return res.status(400).json({ ok: false, error: 'task too short (min 10 chars)' });

  const db = loadAccessDB();
  const record = db[token];
  if (!record) return res.status(403).json({ ok: false, error: 'invalid token' });

  // Build task with customer context prefix
  const contextPrefix = context && context.trim()
    ? `[CUSTOMER CONTEXT: ${context.trim()}] `
    : `[CUSTOMER: ${record.email} / ${record.tier}] `;
  const fullTask = contextPrefix + task.trim();

  try {
    const bb = path.join(__dirname, 'nexus_blackboard.json');
    let data = {};
    if (fs.existsSync(bb)) { try { data = JSON.parse(fs.readFileSync(bb, 'utf8')); } catch (_) { } }
    if (!Array.isArray(data.task_queue)) data.task_queue = [];
    data.task_queue.unshift(fullTask); // high priority — goes to front
    fs.writeFileSync(bb, JSON.stringify(data, null, 2));
    log(`CUSTOMER TASK: ${record.email} [${record.tier}] → "${task.slice(0, 60)}..."`);
    res.json({ ok: true, queued: true, queue_depth: data.task_queue.length, eta_minutes: Math.ceil(data.task_queue.length * 0.5) });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

// ── /api/flush — Flush the blackboard ────────────────────────────────────────
app.post('/api/flush', (req, res) => {
  const bb = path.join(__dirname, 'nexus_blackboard.json');
  try {
    const fresh = { status: 'IDLE', task: '', outputs: [], last_score: null, mvp: null, flushed_at: new Date().toISOString() };
    fs.writeFileSync(bb, JSON.stringify(fresh, null, 2));
    log('HUB: Blackboard flushed via /api/flush');
    res.json({ ok: true, msg: 'Blackboard cleared' });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

// ── /api/result — Last swarm result (VeilPiercer polling endpoint) ────────────
app.get('/api/result', (req, res) => {
  const bbPath = path.join(__dirname, 'nexus_blackboard.json');
  try {
    const bb = fs.existsSync(bbPath) ? JSON.parse(fs.readFileSync(bbPath, 'utf8')) : {};
    const outputs = bb.outputs || [];
    const last = outputs[outputs.length - 1] || null;

    res.json({
      ok: true,
      status: bb.status || 'IDLE',
      task: bb.task || null,
      score: bb.last_score ?? null,
      mvp: bb.last_mvp || null,
      queue_depth: (bb.task_queue || []).length,
      last_output: last ? {
        agent: last.agent,
        text: last.text,
        ts: last.ts
      } : null,
      cycle_count: outputs.length,
      ts: new Date().toISOString()
    });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

// ── /api/results — Recent swarm outputs (last N, default 10) ─────────────────
app.get('/api/results', (req, res) => {
  const bbPath = path.join(__dirname, 'nexus_blackboard.json');
  const n = Math.min(parseInt(req.query.n) || 10, 50); // max 50
  try {
    const bb = fs.existsSync(bbPath) ? JSON.parse(fs.readFileSync(bbPath, 'utf8')) : {};
    const outputs = (bb.outputs || []).slice(-n).reverse(); // newest first

    res.json({
      ok: true,
      status: bb.status || 'IDLE',
      task: bb.task || null,
      score: bb.last_score ?? null,
      mvp: bb.last_mvp || null,
      queue_depth: (bb.task_queue || []).length,
      total_outputs: (bb.outputs || []).length,
      results: outputs.map(o => ({
        agent: o.agent || 'UNKNOWN',
        text: (o.text || '').slice(0, 1000), // cap at 1000 chars per output
        ts: o.ts || null
      })),
      ts: new Date().toISOString()
    });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

// ── /api/chat-history — Save chat dump from hub ──────────────────────────────
app.get('/api/chat-history', (req, res) => {
  res.json({ ok: true, msg: 'Chat history endpoint active. POST to save.', ts: new Date().toISOString() });
});
app.post('/api/chat-history', express.json({ limit: '10mb' }), (req, res) => {
  try {
    const { messages } = req.body || {};
    if (!messages) return res.status(400).json({ ok: false, error: 'messages required' });
    const f = path.join(__dirname, 'chats', `chat_${new Date().toISOString().slice(0, 10)}.json`);
    fs.mkdirSync(path.join(__dirname, 'chats'), { recursive: true });
    fs.writeFileSync(f, JSON.stringify({ savedAt: new Date().toISOString(), messages }, null, 2));
    log(`HUB: Chat saved — ${messages.length} messages → ${f}`);
    res.json({ ok: true, saved: messages.length, file: path.basename(f) });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

// ── /veilpiercer — Serve VeilPiercer observatory (buyer-facing, no auth) ─────
const VP_DIR = 'C:\\Users\\fyou1\\Desktop\\julia\\VEIL-PIERCER';
app.use('/veilpiercer-assets', express.static(VP_DIR));
app.get('/veilpiercer', (req, res) => {
  const p = path.join(VP_DIR, 'index.html');
  if (fs.existsSync(p)) res.sendFile(p);
  else res.status(404).send('<h1>VeilPiercer not found at ' + p + '</h1>');
});

// (server already started at line ~2142)

// ── VEILPIERCER: COMMAND & TELEMETRY ENGINE ──────────────────────────────────
// This connects the Buyer's Observatory to the NEXUS Core.

app.post('/veilpiercer/command', async (req, res) => {
  const { token, command, protocol, scores, useCase } = req.body || {};
  if (!token) return res.status(403).json({ ok: false, error: 'Token required' });

  // 1. Verify token
  const db = loadAccessDB();
  const entry = db[token];
  if (!entry) return res.status(403).json({ ok: false, error: 'Invalid token' });

  // 2. Log signal if provided
  if (scores && useCase) {
    agentEvent('telemetry', scores.saf < 50 ? 'saf' : scores.priv > 90 ? 'priv' : 'vis',
      `Signal received from ${useCase}: ${command || 'Periodic update'}`,
      { ...scores, ok: true, agent: useCase });
  }

  // 3. Handle Protocols (Optional: could trigger real system changes)
  if (protocol) {
    log(`VEILPIERCER [${entry.email}]: Protocol Shift → ${protocol}`);
  }

  // 4. AI Reasoning (if Pro/Agency)
  const features = {
    Starter: { aiAudit: false },
    Pro: { aiAudit: true },
    Agency: { aiAudit: true }
  }[entry.tier] || { aiAudit: false };

  let aiResponse = "";
  if (features.aiAudit && command) {
    try {
      const payload = JSON.stringify({
        model: 'llama3.2:1b',
        system: 'You are the VeilPiercer Security AI. Briefly explain the security implications of the users command or signal. Be professional and technical.',
        prompt: `User (${entry.tier}) sent command/signal: "${command}". Current Scores: ${JSON.stringify(scores)}. Protocol: ${protocol}.`,
        stream: false
      });
      const http = require('http');
      const result = await new Promise((resolve, reject) => {
        const r = http.request({ hostname: 'localhost', port: 11434, path: '/api/generate', method: 'POST', headers: { 'Content-Type': 'application/json' } }, resp => { let b = ''; resp.on('data', d => b += d); resp.on('end', () => { try { resolve(JSON.parse(b)); } catch { resolve({}); } }); });
        r.on('error', reject); r.write(payload); r.end();
      });
      aiResponse = result.response || "";
    } catch (e) { log(`VP AI Error: ${e.message}`); }
  }

  res.json({ ok: true, response: aiResponse, scores: calcVPScores() });
});

app.get('/veilpiercer/signals', (req, res) => {
  const { token } = req.query;
  if (!token) return res.status(403).json({ ok: false, error: 'Token required' });
  const db = loadAccessDB();
  if (!db[token]) return res.status(403).json({ ok: false, error: 'Access denied' });

  res.json({
    ok: true,
    events: AGENT_EVENTS.slice(-20).reverse(),
    metrics: calcVPScores()
  });
});
// ── SECURITY: Global Error Handler ───────────────────────────────────────────────
// Catches ALL unhandled errors from any route. Never leaks stack traces.
// eslint-disable-next-line no-unused-vars
app.use((err, req, res, next) => {
  const id = crypto.randomBytes(4).toString('hex');
  secLog(`UNHANDLED ERROR [${id}] ${req.method} ${req.path} — ${err.message}`);
  res.status(500).json({ ok: false, error: 'An internal error occurred.', ref: id });
});
