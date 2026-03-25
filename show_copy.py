"""
show_copy.py — shows the latest deployable copy from the swarm.
Run: python show_copy.py
"""
import json, sys
from pathlib import Path

f = Path(__file__).parent / "nexus_deployable_copy.json"
if not f.exists():
    print("No deployable copy yet — swarm needs a qualifying cycle (score >= 0.65 + EXECUTIONER READY)")
    sys.exit(0)

data = json.loads(f.read_text(encoding="utf-8"))
unposted = [x for x in data if not x.get("posted")]

print(f"\n{'='*65}")
print(f"  NEXUS DEPLOYABLE COPY — {len(unposted)} unposted / {len(data)} total")
print(f"{'='*65}\n")

for i, item in enumerate(unposted[-5:], 1):
    print(f"-- #{i} [{item['type']}] score={item['score']:.2f} | {item['ts'][:16]} --")
    print(f"Target: post in r/LocalLLaMA or r/selfhosted")
    print()
    print(item['body'])
    print()
    print(f"Scout context: {item.get('scout_ctx','')[:150]}")
    print()
    print("─"*65)
    print()

print("To mark as posted, edit nexus_deployable_copy.json → set posted:true")
