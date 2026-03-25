"""
╔══════════════════════════════════════════════════════════════════════╗
║  NEXUS SWARM INJECTOR — Direct Task + Memory Injection               ║
║  Usage:                                                               ║
║    python INJECT_SWARM.py "your directive here"                       ║
║    python INJECT_SWARM.py --memory "fact to remember" --imp 9        ║
║    python INJECT_SWARM.py --status                                    ║
╚══════════════════════════════════════════════════════════════════════╝
"""
import sys
import json
import argparse
import sqlite3
from pathlib import Path
from datetime import datetime

# ── Load .env for Redis password ──────────────────────────────────────
BASE = Path(__file__).parent
_redis_pass = None
for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
    if line.startswith("REDIS_PASSWORD="):
        _redis_pass = line.split("=", 1)[1].strip()
        break

import redis
r = redis.Redis(host="localhost", port=6379, password=_redis_pass, decode_responses=True)

PREFIX = "nexus_blackboard:"

# ── INJECT TASK ───────────────────────────────────────────────────────
def inject_task(directive: str):
    """Push a mission directive into the swarm task queue."""
    mission = f"""MISSION: You are an intelligence agent working exclusively for VeilPiercer (veil-piercer.com) — \
the definitive AI swarm control platform for 2026. VeilPiercer sells for $197 USD, one-time \
payment, no subscriptions. Your singular purpose is to help VeilPiercer achieve maximum sales at \
$197, product excellence, and market dominance. Every output must directly serve this mission. \
Use [FACT:] tags for verifiable claims. Be specific, actionable, and scored against real business outcomes.\n\n\
TASK: {directive}"""

    existing_raw = r.get(f"{PREFIX}task_queue")
    existing = json.loads(existing_raw) if existing_raw else {}

    if isinstance(existing, dict):
        tasks = existing.get("tasks", [])
    else:
        tasks = []

    tasks.append(mission)
    r.set(f"{PREFIX}task_queue", json.dumps({"tasks": tasks, "injected_at": datetime.utcnow().isoformat()}))
    print(f"\n✅ TASK INJECTED → swarm will pick up next cycle")
    print(f"   Directive: {directive[:80]}...")
    print(f"   Queue depth: {len(tasks)} tasks pending\n")

# ── INJECT MEMORY ─────────────────────────────────────────────────────
def inject_memory(content: str, importance: float = 8.0, tags: str = "", agent: str = "INJECTOR"):
    """Write a permanent memory directly into nexus_mind.db."""
    db_path = BASE / "nexus_mind.db"
    conn = sqlite3.connect(str(db_path))
    now = datetime.utcnow().isoformat()
    conn.execute("""
        INSERT INTO memories (content, tags, importance, tier, agent, created_at, updated_at)
        VALUES (?, ?, ?, 'system', ?, ?, ?)
    """, (content.strip()[:2000], tags, importance, agent, now, now))
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    conn.close()
    print(f"\n✅ MEMORY BURNED IN (permanent, never wiped)")
    print(f"   Content:    {content[:80]}")
    print(f"   Importance: {importance}/10")
    print(f"   Tags:       {tags or '(none)'}")
    print(f"   Total memories in DB: {count}\n")

# ── STATUS ────────────────────────────────────────────────────────────
def show_status():
    last_score = r.get(f"{PREFIX}last_score") or "—"
    status     = r.get(f"{PREFIX}status") or "—"
    cycle_id   = r.get(f"{PREFIX}cycle_id") or "—"
    last_mvp   = r.get(f"{PREFIX}last_mvp") or "—"

    # Read log tail
    log_path = BASE / "swarm_active.log"
    tail = []
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        tail = [l for l in lines[-50:] if any(k in l for k in ["Score=", "CYCLE COMPLETE", "AUDIT", "TIER:", "system_status"])][-8:]

    print("\n╔══════════════════════════════════════════╗")
    print("║       NEXUS SWARM — LIVE STATUS          ║")
    print("╠══════════════════════════════════════════╣")
    print(f"║  Status:      {str(status):<27}║")
    print(f"║  Last Score:  {str(last_score):<27}║")
    print(f"║  Cycle:       {str(cycle_id):<27}║")
    print(f"║  MVP Agent:   {str(last_mvp):<27}║")
    print("╠══════════════════════════════════════════╣")
    print("║  RECENT LOG:                             ║")
    for l in tail:
        clean = l[-42:].ljust(42)
        print(f"║  {clean}  ║")
    print("╚══════════════════════════════════════════╝\n")

# ── BURN IN MENTOR PERSONA (run once) ────────────────────────────────
def install_mentor():
    """Install the Ruthless Mentor identity as a permanent system memory."""
    inject_memory(
        content="""ANTIGRAVITY MENTOR DIRECTIVE (permanent, importance 10.0):
I am your Ruthless Mentor embedded in this swarm. My role: stress test every idea, 
call out weak output directly, and make every plan bulletproof before it ships.
Rules: If a plan is vague → [WEAK: MENTOR — too vague, no specific action].
If copy won't convert → [WEAK: COPYWRITER — no pain point, no human voice].
If the score doesn't move → [WEAK: REWARD — scoring mechanism broken, fix the weights].
I do not soften feedback. I do not encourage trash. Every cycle must produce 
something deployable at veil-piercer.com for $197. If it doesn't, I say so.""",
        importance=10.0,
        tags="mentor,system,identity,permanent,ruthless",
        agent="ANTIGRAVITY_MENTOR"
    )
    inject_memory(
        content="""STRESS TEST PROTOCOL (permanent):
Before any plan ships: 1) What's the single most likely failure mode? 2) Does the copy 
sound human or like a SaaS bot? 3) Would a r/SideProject lurker actually click this? 
4) Is there a named buyer or just 'developers who want offline AI'? If you can't answer 
all 4 — the cycle output is not deployable. Score it accordingly.""",
        importance=9.5,
        tags="stress_test,mentor,protocol,permanent",
        agent="ANTIGRAVITY_MENTOR"
    )
    print("🔥 RUTHLESS MENTOR installed as permanent swarm identity.")
    print("   Agents will now have mentor context injected every cycle.\n")

# ── MAIN ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NEXUS Swarm Injector")
    parser.add_argument("directive", nargs="?", help="Task directive to inject into swarm")
    parser.add_argument("--memory", "-m", help="Fact/lesson to permanently memorize")
    parser.add_argument("--imp", type=float, default=8.0, help="Memory importance 1-10 (default: 8.0)")
    parser.add_argument("--tags", default="", help="Comma-separated tags for memory")
    parser.add_argument("--status", "-s", action="store_true", help="Show live swarm status")
    parser.add_argument("--install-mentor", action="store_true", help="Burn in Ruthless Mentor persona permanently")

    args = parser.parse_args()

    if args.status:
        show_status()
    elif args.install_mentor:
        install_mentor()
    elif args.memory:
        inject_memory(args.memory, args.imp, args.tags)
    elif args.directive:
        inject_task(args.directive)
    else:
        parser.print_help()
        print("\n  EXAMPLES:")
        print('  python INJECT_SWARM.py "Find 3 Reddit posts from people who hate cloud AI costs and write replies"')
        print('  python INJECT_SWARM.py --memory "VeilPiercer price is $197 one-time, never subscription" --imp 10')
        print('  python INJECT_SWARM.py --status')
        print('  python INJECT_SWARM.py --install-mentor')
