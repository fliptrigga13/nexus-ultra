const http = require('http');

const SECRET = process.env.NEXUS_API_SECRET;
const PORT = 3000;
const EVENTS = 100;
const DELAY = 50; // ms between events

const PILLARS = ['vis', 'saf', 'priv'];
const TYPES = ['drift_warning', 'latency_spike', 'null_reference', 'pii_leak_attempt', 'database_timeout'];
const MESSAGES = [
    'Node 3 failed to respond in time.',
    'Unexpected PII found in payload.',
    'Memory leak detected in worker thread.',
    'Output drift: schema mismatch.',
    'API rate limit exceeded during chain.',
    'Connection reset during inference.',
    'Unauthorized field access attempt blocked.',
    'Model degraded by 8.5% over last 100 inferences.'
];

console.log(`Starting Heavy Load Test: Firing ${EVENTS} anomalous events...`);

let i = 0;
const interval = setInterval(() => {
    if (i >= EVENTS) {
        clearInterval(interval);
        console.log('Finished firing events. Check the VeilPiercer Command dashboard!');
        return;
    }

    const p = PILLARS[Math.floor(Math.random() * PILLARS.length)];
    const t = TYPES[Math.floor(Math.random() * TYPES.length)];
    const m = MESSAGES[Math.floor(Math.random() * MESSAGES.length)];

    const payload = JSON.stringify({
        type: t,
        pillar: p,
        msg: m,
        data: { simulated: true, iteration: i }
    });

    const options = {
        hostname: '127.0.0.1',
        port: PORT,
        path: '/veilpiercer/event',
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(payload),
            'x-api-key': SECRET
        }
    };

    const req = http.request(options, (res) => {
        // silently consume response
        res.on('data', () => { });
    });

    req.on('error', (e) => {
        console.error(`Request error on event ${i}: ${e.message}`);
    });

    req.write(payload);
    req.end();

    i++;
    if (i % 20 === 0) {
        console.log(`Fired ${i} events...`);
    }
}, DELAY);

