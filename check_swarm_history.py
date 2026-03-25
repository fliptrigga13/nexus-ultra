import re, json
from pathlib import Path

log = open('swarm_loop.log', encoding='utf-8', errors='ignore').read()
lines = log.splitlines()
print('=== SWARM LOG ===')
print('First line:', lines[0] if lines else 'empty')
scores = [float(m) for m in re.findall(r'Cycle #\d+ COMPLETE. Score=([\d.]+)', log)]
starts = re.findall(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*MAGNITUDE SWARM ENGINE.*STARTING', log)
print(f'Total cycles: {len(scores)}')
print(f'Restart count: {len(starts)}')
if starts:
    print(f'First start: {starts[0]}')
    print(f'Last start:  {starts[-1]}')
if scores:
    nz = [s for s in scores if s > 0]
    print(f'Avg: {sum(scores)/len(scores):.3f} | Peak: {max(scores):.2f} | Zero%: {scores.count(0.0)/len(scores)*100:.0f}%')

mem_path = Path('nexus_memory.json')
if mem_path.exists():
    mem = json.loads(mem_path.read_text(encoding='utf-8', errors='ignore'))
    print(f'\n=== EPISODIC MEMORY ===')
    print(f'Entries: {len(mem)}')
    if mem:
        oldest = mem[0]
        newest = mem[-1]
        best = max(mem, key=lambda x: x.get('score', 0))
        print(f'Oldest ts: {oldest.get("ts","?")} score={oldest.get("score")}')
        print(f'Newest ts: {newest.get("ts","?")} score={newest.get("score")}')
        print(f'Best:      score={best.get("score")} ts={best.get("ts")}')
        print(f'Best lesson: {str(best.get("lesson",""))[:150]}')

db_path = Path('nexus_mind.db')
if db_path.exists():
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM memories")
    count = cur.fetchone()[0]
    cur.execute("SELECT MIN(created_at), MAX(created_at) FROM memories")
    mn, mx = cur.fetchone()
    print(f'\n=== TIER-2 MIND DB ===')
    print(f'Total memories: {count}')
    print(f'Oldest: {mn}')
    print(f'Newest: {mx}')
    conn.close()
