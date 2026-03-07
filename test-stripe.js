const http = require('http');

const SECRET = 'Burton';
const PORT = 3000;

function hitAccessCreate() {
    const payload = JSON.stringify({
        email: 'testbuyer@example.com',
        tier: 'Pro',
        amount: 9700,
        sessionId: 'cs_test_12345',
        sendEmail: true
    });

    const options = {
        hostname: '127.0.0.1',
        port: PORT,
        path: '/access/create',
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(payload),
            'x-api-key': SECRET
        }
    };

    const req = http.request(options, (res) => {
        let data = '';
        res.on('data', (chunk) => { data += chunk; });
        res.on('end', () => {
            console.log('--- Stripe Access Pipeline Result ---');
            console.log('Status:', res.statusCode);
            try {
                const parsed = JSON.parse(data);
                console.log(JSON.stringify(parsed, null, 2));

                if (parsed.token) {
                    console.log('\n--- Fetching Token Info ---');
                    verifyToken(parsed.token);
                }
            } catch (e) {
                console.log('Raw response:', data);
            }
        });
    });

    req.on('error', (e) => {
        console.error(`Problem with request: ${e.message}`);
    });

    req.write(payload);
    req.end();
}

function verifyToken(token) {
    const options = {
        hostname: '127.0.0.1',
        port: PORT,
        path: `/access/verify?token=${token}`,
        method: 'GET'
    };

    const req = http.request(options, (res) => {
        let data = '';
        res.on('data', (chunk) => { data += chunk; });
        res.on('end', () => {
            console.log('Status:', res.statusCode);
            try {
                console.log(JSON.stringify(JSON.parse(data), null, 2));
            } catch (e) {
                console.log('Raw response:', data);
            }
        });
    });

    req.on('error', (e) => {
        console.error(`Problem verifying token: ${e.message}`);
    });

    req.end();
}

console.log('Triggering Stripe Access Pipeline test...');
hitAccessCreate();
