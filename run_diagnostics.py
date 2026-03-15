import json, time
from pathlib import Path

base = Path(r'C:\Users\fyou1\Desktop\New folder\nexus-ultra')

print('='*60)
print('NEXUS REAL MEMORY DIAGNOSTICS - 2026-03-13 08:30')
print('='*60)

# 1. Session facts
sf = base / 'nexus_session_facts.json'
if sf.exists():
    d = json.loads(sf.read_text(encoding='utf-8'))
    facts = d.get('facts', [])
    sz = sf.stat().st_size
    mtime = time.ctime(sf.stat().st_mtime)
    print(f'[session_facts.json]  {len(facts)} entries  {sz} bytes  modified: {mtime}')
    # Show type distribution
    types = {}
    for f in facts:
        t = f.get('type', 'unknown') if isinstance(f, dict) else 'raw'
        types[t] = types.get(t, 0) + 1
    for t, cnt in types.items():
        print(f'  type={t}: {cnt} entries')
else:
    print('[session_facts.json]  MISSING')

# 2. nexus_memory.json
mf = base / 'nexus_memory.json'
if mf.exists():
    mem = json.loads(mf.read_text(encoding='utf-8'))
    sz = mf.stat().st_size
    mtime = time.ctime(mf.stat().st_mtime)
    print(f'[nexus_memory.json]   {len(mem)} entries  {sz} bytes  modified: {mtime}')
    if mem and isinstance(mem, list):
        last = mem[-1]
        sc = last.get('score', 0)
        mv = last.get('mvp', '?')
        cy = last.get('cycle', '?')
        ls = str(last.get('lesson', ''))[:100]
        print(f'  Last cycle: {cy}  score={sc:.2f}  mvp={mv}')
        print(f'  Last lesson: {ls}')
else:
    print('[nexus_memory.json]   MISSING')

# 3. blackboard
bb_path = base / 'nexus_blackboard.json'
if bb_path.exists():
    d = json.loads(bb_path.read_text(encoding='utf-8', errors='replace'))
    outputs = d.get('outputs', [])
    st = d.get('status', '?')
    sc = d.get('last_score', '?')
    task = str(d.get('task', ''))[:80]
    print(f'[nexus_blackboard.json] status={st}  outputs={len(outputs)}  score={sc}')
    print(f'  Last task: {task}')
else:
    print('[nexus_blackboard.json] MISSING')

# 4. chats
chats = base / 'chats'
if chats.exists():
    files = list(chats.glob('*.json'))
    total_msgs = 0
    for f in files:
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            total_msgs += len(data.get('messages', []))
        except Exception:
            pass
    print(f'[chats/]  {len(files)} daily files  {total_msgs} total messages stored')
else:
    print('[chats/]  MISSING - chat history not being saved')

# 5. evolution log
elog = base / 'evolution_log.json'
if elog.exists():
    try:
        d = json.loads(elog.read_text(encoding='utf-8'))
        if isinstance(d, dict):
            cycles = d.get('cycles', d.get('history', []))
        else:
            cycles = d if isinstance(d, list) else []
        sz = elog.stat().st_size
        print(f'[evolution_log.json]  {len(cycles)} evolution cycles  {sz} bytes')
    except Exception as e:
        print(f'[evolution_log.json]  ERROR reading: {e}')
else:
    print('[evolution_log.json]  MISSING')

# 6. token
tok = base / '.backdoor_token'
tok_exists = tok.exists()
tok_size = tok.stat().st_size if tok_exists else 0
print(f'[.backdoor_token]  {"EXISTS" if tok_exists else "MISSING"}  {tok_size} bytes')

# 7. modelfile hash
mfsig = base / '.modelfile_sha256'
if mfsig.exists():
    saved_hash = mfsig.read_text().strip()
    print(f'[.modelfile_sha256]  EXISTS  hash={saved_hash[:16]}...')
else:
    print('[.modelfile_sha256]  MISSING')

# 8. swarm log last entry
slog = base / 'swarm_loop.log'
if slog.exists():
    lines = slog.read_text(encoding='utf-8', errors='replace').splitlines()
    march13 = [l for l in lines if '2026-03-13' in l]
    print(f'[swarm_loop.log]  {len(lines)} total lines  {len(march13)} today')
    if march13:
        print(f'  Latest: {march13[-1][:100]}')
    elif lines:
        print(f'  Latest: {lines[-1][:100]}')
else:
    print('[swarm_loop.log]  MISSING')

print()
print('=== VERDICT ===')
issues = []
if not mf.exists(): issues.append('nexus_memory.json MISSING')
if not sf.exists(): issues.append('session_facts.json MISSING')
if not tok_exists: issues.append('.backdoor_token MISSING')
if not chats.exists(): issues.append('chats/ dir MISSING')

if issues:
    for i in issues:
        print(f'  ISSUE: {i}')
else:
    print('  ALL MEMORY SYSTEMS: HEALTHY')
    print('  DATA LOSS RISK: NONE')
    print('  CHAT PERSISTENCE: ACTIVE')
