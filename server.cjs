// ╔══════════════════════════════════════════╗
// ║      NEXUS ULTRA v2 // SERVER CORE       ║
// ╚══════════════════════════════════════════╝
const path = require('path');
const fs = require('fs');
const express = require('express');
const cors = require('cors');
const { exec } = require('child_process');
const cron = require('node-cron');

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
const PUBLIC_URL = process.env.PUBLIC_URL || `http://127.0.0.1:${PORT}`;
const N8N_URL = "http://localhost:5678";


// ─── Paths ────────────────────────────────
const ROOT = __dirname;
const LOG_FILE = path.join(ROOT, 'nexus.log');
const DROP_DIR = path.join(ROOT, 'drop-zone');
const CAPTURE_DIR = path.join(ROOT, 'captures');
const TABS_FILE = path.join(ROOT, 'tabs.json');

// ─── Bootstrap dirs ───────────────────────
for (const d of [DROP_DIR, CAPTURE_DIR]) {
  if (!fs.existsSync(d)) fs.mkdirSync(d, { recursive: true });
}

// ─── Logging ──────────────────────────────
function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}`;
  console.log(line);
  try { fs.appendFileSync(LOG_FILE, line + '\n'); } catch (_) { }
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
  });
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
      success_url: `http://${HOST}:${PORT}/success.html?session_id={CHECKOUT_SESSION_ID}&tier=${tier}`,
      cancel_url: `http://${HOST}:${PORT}/veilpiercer-pitch.html#pricing`,
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
      // TODO: provision access, send welcome email, etc.
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

// ── Boot ─────────────────────────────────
app.listen(PORT, HOST, () => {
  log('╔══════════════════════════════════════════╗');
  log('║      NEXUS ULTRA v2 // ONLINE            ║');
  log('╚══════════════════════════════════════════╝');
  log(`Dashboard   → http://${HOST}:${PORT}`);
  log(`Pitch page  → http://${HOST}:${PORT}/veilpiercer-pitch.html`);
  log(`Command     → http://${HOST}:${PORT}/veilpiercer-command.html`);
  log(`Stripe cfg  → ${STRIPE_PK ? 'pk loaded (' + (STRIPE_PK.startsWith('pk_live') ? 'LIVE' : 'TEST') + ')' : 'NOT SET'}`);
  log(`Stripe sk   → ${stripe ? 'ACTIVE' : 'NOT SET — add sk_live_... to .env'}`);
  log(`Drop Zone   → ${DROP_DIR}`);
  log(`Scheduled   → ${Object.keys(jobs).length} job(s) active`);
});
