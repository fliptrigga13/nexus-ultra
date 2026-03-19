const nodemailer = require('nodemailer');
const fs = require('fs');
const path = require('path');

// ─── Load .env manually ────────────────────────────
try {
  const envPath = path.join(__dirname, '.env');
  if (fs.existsSync(envPath)) {
    fs.readFileSync(envPath, 'utf8').split('\n').filter(Boolean).forEach(line => {
      const [k, ...v] = line.split('=');
      if (k && !k.startsWith('#') && v.length) process.env[k.trim()] = v.join('=').trim();
    });
  }
} catch (_) { }

console.log('Loading env... DONE. User:', process.env.EMAIL_USER);

const transporter = nodemailer.createTransport({
  host: 'smtp.gmail.com',
  port: 465,
  secure: true,
  auth: { user: process.env.EMAIL_USER, pass: process.env.EMAIL_PASS }
});

console.log('Transporter initialized. Sending mail...');

const summaryBody = `
# 📅 Project VeilPiercer: 24-Hour Tactical Summary
**Timeline**: March 17, 2026
**Receiver**: Lauren Flipo (laurenflipo1388@gmail.com)

---

### ✅ Accomplishments (Last 24 Hours)

1. **Visual & Interactive Overhaul ("Mission Control" UI)**
- **Particle Deployer System**: Implemented a node-based, interactive neural net animation in the hero background.
- **Tactical HUD Aesthetics**: Added a dynamic grid and scanline overlay to all backgrounds.
- **Signal Wave Dividers**: Replaced flat dividers with animated multi-phase sinusoidal waves simulating live telemetry.
- **Glowing HUD Nodes**: Feature icons now use glowing circular nodes with rotating arcs.
- **Pulse Hover States**: Integrated glowing borders on story cards for better user interaction.

2. **Infrastructure & Stability**
- **Telemetry API**: Built the /veilpiercer/metrics endpoint for real-time hub diagnostics.
- **Email Relay Fix**: Pro Access delivery is 100% operational (fixed "Relay access denied").
- **API Verification**: Confirmed EH API (port 7701) status and swarm-to-hub communication pathways.

3. **Strategic Alignment (GTC 2026)**
- **NVIDIA Integration**: Updated sales copy to feature the NVIDIA Vera Rubin architecture and NemoClaw Agentic OS.

---

### 🚀 Agent Pitch Script (Ready to use tomorrow)

"I built VeilPiercer because I was tired of running my AI agents into a black box. I ran 53,000 operations on my own machine and had no idea what they were actually doing until the bill hit or something broke. Datadog wanted $400 a month for 'cloud visibility' that didn't even let me stop a rogue loop.

VeilPiercer is a real-time, mission-control dashboard that runs 100% locally. 
- See Every Move: Real-time observability live on your machine.
- Total Control: 4 instant protocols to freeze or ramp up your swarm.
- Zero Cloud, Zero Monthly: Privacy-first. $197 one-time and it's yours forever.
If your agents are doing things you didn't expect and you don't know why—this is how you fix that."

---

### 🕵️ Recruitment Status
- **LinkedIn**: 3 candidates have been covered and identified. They are ready to receive the script above for the morning briefing.

---

### 📝 Next 24-Hour Task List

- [ ] **Canvas Profiling**: Verify particle animation CPU/GPU usage on mobile devices.
- [ ] **Asset Minification**: Compress UI assets for <1.2s load times.
- [ ] **Success Page Refinement**: Update success.html to match the Mission Control aesthetic.
- [ ] **Stripe Webhook Test**: Live test the link-to-inbox delivery flow.
- [ ] **Swarm Stress Test**: Run 100k agent operation to verify metrics stability.
- [ ] **Memory Guard Update**: Set MEMORY_GUARD.ps1 to clear GPU caches if >4GB.

---
*Sent via NEXUS ULTRA Automated Briefing Engine*
`;

async function sendMail() {
  try {
    await transporter.sendMail({
      from: process.env.EMAIL_FROM || 'VeilPiercer <laurenflipo1388@gmail.com>',
      to: 'laurenflipo1388@gmail.com',
      subject: '🕵️ [ACTION REQ] VeilPiercer - 24-Hour Summary & Agent Script',
      text: summaryBody
    });
    console.log('EMAIL SENT SUCCESSFULY');
  } catch (err) {
    console.error('EMAIL FAILED:', err.message);
    process.exit(1);
  }
}

sendMail();
