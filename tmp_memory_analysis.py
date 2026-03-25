import sqlite3, json
from collections import defaultdict

conn = sqlite3.connect('nexus_mind.db')

# === FULL PATTERN ANALYSIS ===
total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
avg_imp = conn.execute("SELECT AVG(importance) FROM memories WHERE archived=0").fetchone()[0] or 0

print(f"=== NEXUS MEMORY FULL HISTORY: {total} entries | avg_importance={avg_imp:.2f} ===\n")

# Agent distribution
print("--- AGENT DISTRIBUTION ---")
agents = conn.execute("SELECT agent, COUNT(*), AVG(importance) FROM memories GROUP BY agent ORDER BY COUNT(*) DESC").fetchall()
for ag, cnt, imp in agents:
    print(f"  {ag:20s}: {cnt:4d} memories | avg_imp={imp:.2f}")
print()

# Tag frequency (pattern recognition)
print("--- TOP EMERGING PATTERNS (by tag frequency) ---")
tags_raw = conn.execute("SELECT tags FROM memories WHERE tags IS NOT NULL AND tags != ''").fetchall()
tag_counts = defaultdict(int)
for (t,) in tags_raw:
    for tag in str(t).split(','):
        tag = tag.strip().lower()
        if tag:
            tag_counts[tag] += 1
for tag, cnt in sorted(tag_counts.items(), key=lambda x: -x[1])[:20]:
    print(f"  {tag:30s}: {cnt}")
print()

# EXECUTIONER - last 10
print("--- EXECUTIONER LAST 10 OUTPUTS ---")
rows = conn.execute(
    "SELECT content, importance, created_at FROM memories WHERE agent='EXECUTIONER' ORDER BY created_at DESC LIMIT 10"
).fetchall()
for i,(c,imp,ts) in enumerate(rows,1):
    print(f"[{i}] imp={imp:.1f} {str(ts)[:16]}")
    print(c[:600])
    print()

# METACOG - last 10
print("--- METACOG LAST 10 OUTPUTS (the unrecognized gem) ---")
rows = conn.execute(
    "SELECT content, importance, created_at FROM memories WHERE agent='METACOG' ORDER BY created_at DESC LIMIT 10"
).fetchall()
for i,(c,imp,ts) in enumerate(rows,1):
    print(f"[{i}] imp={imp:.1f} {str(ts)[:16]}")
    print(c[:600])
    print()

# SUPERVISOR - pattern synthesis
print("--- SUPERVISOR PATTERN SYNTHESIS (top 5 by importance) ---")
rows = conn.execute(
    "SELECT content, importance, created_at FROM memories WHERE agent='SUPERVISOR' ORDER BY importance DESC, created_at DESC LIMIT 5"
).fetchall()
for i,(c,imp,ts) in enumerate(rows,1):
    print(f"[{i}] imp={imp:.1f} {str(ts)[:16]}")
    print(c[:500])
    print()

# Highest importance across ALL agents
print("--- ALL-TIME TOP 10 MEMORIES (by importance) ---")
rows = conn.execute(
    "SELECT content, importance, agent, tags, created_at FROM memories ORDER BY importance DESC LIMIT 10"
).fetchall()
for i,(c,imp,ag,tags,ts) in enumerate(rows,1):
    print(f"[{i}] [{ag}] imp={imp:.1f} tags={tags}")
    print(c[:400])
    print()

conn.close()
