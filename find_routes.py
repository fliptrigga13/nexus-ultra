lines = open('server.cjs', encoding='utf-8', errors='ignore').readlines()
terms = ['feedback', '/api/signal', 'webhook/task', '/chat', 'req.body']
for i, l in enumerate(lines, 1):
    low = l.lower()
    if any(t in low for t in ['feedback', 'webhook/task', 'app.post', 'app.get(\'/api']):
        safe = l.rstrip()[:130].encode('ascii', errors='replace').decode('ascii')
        print(f"{i}: {safe}")
