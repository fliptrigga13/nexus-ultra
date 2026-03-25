"""Fix corrupt $100 pricing cap memory that causes SENTINEL_LOCKDOWN every cycle."""
import sqlite3
from datetime import datetime

conn = sqlite3.connect("nexus_mind.db")

# Find the bad memories
rows = conn.execute(
    "SELECT id, content, importance FROM memories "
    "WHERE archived=0 AND ("
    "  content LIKE '%100%month%' OR content LIKE '%price%100%' "
    "  OR content LIKE '%pricing%above%' OR content LIKE '%SaaS%100%'"
    "  OR content LIKE '%above 100%' OR content LIKE '%cap%100%'"
    ") LIMIT 20"
).fetchall()

print(f"Found {len(rows)} problematic memories:")
for r in rows:
    print(f"  ID {r[0]} [imp:{r[2]:.1f}]: {r[1][:100]}")

if rows:
    ids = tuple(r[0] for r in rows)
    if len(ids) == 1:
        conn.execute("UPDATE memories SET archived=1 WHERE id=?", (ids[0],))
    else:
        conn.execute(f"UPDATE memories SET archived=1 WHERE id IN {ids}")
    conn.commit()
    print(f"✅ Archived {len(rows)} conflicting memories.")
else:
    print("No exact matches — searching broadly...")
    rows2 = conn.execute(
        "SELECT id, content FROM memories WHERE archived=0 AND content LIKE '%100%' LIMIT 10"
    ).fetchall()
    for r in rows2:
        print(f"  ID {r[0]}: {r[1][:100]}")

conn.close()
print("Done.")
