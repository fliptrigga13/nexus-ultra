import sqlite3
conn = sqlite3.connect('nexus_mind.db')
cur = conn.cursor()
cur.execute("SELECT agent, importance, substr(content,1,180) FROM memories WHERE archived=0 AND agent IN ('PLANNER','SUPERVISOR') AND importance=10.0 LIMIT 8")
rows = cur.fetchall()
for r in rows:
    print(f"[{r[0]}] imp={r[1]}")
    print(f"  {r[2]}")
    print()
conn.close()
