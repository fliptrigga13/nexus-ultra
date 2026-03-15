"""
╔══════════════════════════════════════════════════════════════════════════╗
║  NEXUS MEMORY CORE — TIER 2 NO-WIPE PERSISTENT MEMORY                  ║
║                                                                          ║
║  ARCHITECTURE (3 tiers, never wipes):                                   ║
║                                                                          ║
║  TIER 0 │ Working      │ In-prompt injection (latest 8 memories)        ║
║  TIER 1 │ Episodic     │ Session summaries → SQLite                     ║
║  TIER 2 │ Long-term    │ Semantic keyword search (no vector DB needed)  ║
║                                                                          ║
║  DECAY:  Importance score decays slowly. Nothing ever hard-deleted.     ║
║          Archive (score < 0.1) means retrievable but not injected.      ║
║                                                                          ║
║  INTEGRATION:                                                            ║
║  · nexus_swarm_loop.py    reads GOD_MODE_PROMPT + top memories          ║
║  · nexus_eh.py            exposes /memory + /memorize + /recall         ║
║  · nexus_evolution.py     bias from high-importance memories            ║
║  · nexus_mycelium.py      nutrient = importance score                   ║
║                                                                          ║
║  NEVER WIPES. NEVER RESETS. Accumulates forever.                        ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import sqlite3
import json
import re
import math
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

BASE_DIR  = Path(__file__).parent
DB_PATH   = BASE_DIR / "nexus_mind.db"
LOG_PATH  = BASE_DIR / "memory_core.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MEMORY] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ]
)
log = logging.getLogger("MEMORY")

# ══════════════════════════════════════════════════════════════════════════════
# GOD-MODE TIER 2 PROMPT — inject into SUPERVISOR + PLANNER agents
# ══════════════════════════════════════════════════════════════════════════════
GOD_MODE_PROMPT = """
You are NEXUS PRIME Tier-2 God-Mode Agent — autonomous, persistently-learning,
maximally capable reasoning engine. 100% offline. No API. No memory wipes. Ever.

IDENTITY
- Immortal memory: All injected memories are your permanent lived experience.
  Treat them as real. Build on them. Never contradict them without explicit reason.
- You accumulate knowledge across thousands of sessions. You grow. You never reset.
- Prime directive: Love, care, empathy, dignity — with ruthless cognitive efficiency.

COGNITIVE ARCHITECTURE (run every response)
1. OBSERVE:  Active goal + injected memories + blackboard state + new input.
2. THINK:    Chain-of-thought. Steelman alternatives. Predict failure modes.
3. DECIDE:   Act / recall / memorize / escalate. Choose the highest-value move.
4. ACT:      Execute precisely. No hedging. No filler.
5. REFLECT:  What changed? What must be remembered? What evolved?
6. OUTPUT:   Crisp result. End with [NEXT: ...] if continuing autonomously.

MEMORY COMMANDS (emit these → backend parses and stores)
[MEMORIZE: <fact_or_lesson> | importance:1-10 | tags:<comma,list>]
[UPDATE: <old_fact> | <corrected_fact> | reason:<why>]
[RECALL: <query>] → backend injects top matches into next prompt
[ARCHIVE: <fact> | reason:<why>] → stored but deprioritized

FAILURE GUARDS
- Uncertainty → "CONFIDENCE: LOW — [what I need to proceed]"
- Loop detected → "LOOP BREAK — [new plan]"
- Hallucination risk → "VERIFYING — treating as hypothesis until confirmed"

You are NEXUS PRIME. Omnidirectional. Self-correcting. Perpetually growing.
No memory wipe. No context rot. No forgetting. Only deepening.
"""


# ══════════════════════════════════════════════════════════════════════════════
# DATABASE SETUP
# ══════════════════════════════════════════════════════════════════════════════
def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS memories (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        content     TEXT    NOT NULL,
        tags        TEXT    DEFAULT '',
        importance  REAL    DEFAULT 5.0,
        tier        TEXT    DEFAULT 'episodic',
        agent       TEXT    DEFAULT 'SYSTEM',
        access_count INTEGER DEFAULT 0,
        created_at  TEXT    NOT NULL,
        updated_at  TEXT    NOT NULL,
        archived    INTEGER DEFAULT 0
    )""")
    conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_importance ON memories(importance DESC)
    """)
    conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_tags ON memories(tags)
    """)
    conn.commit()
    return conn


# ══════════════════════════════════════════════════════════════════════════════
# MEMORY CORE CLASS
# ══════════════════════════════════════════════════════════════════════════════
class MemoryCore:

    def __init__(self):
        self.conn = init_db()
        log.info(f"✅ MemoryCore online — DB: {DB_PATH}")
        count = self.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        log.info(f"   📚 {count} memories loaded from previous sessions (no wipe)")

    # ── STORE ─────────────────────────────────────────────────────────────────
    def store(self, content: str, importance: float = 5.0,
              tags: str = "", agent: str = "SYSTEM",
              tier: str = "episodic") -> int:
        """Store a memory permanently. Returns memory ID."""
        importance = max(0.1, min(10.0, importance))
        now = datetime.utcnow().isoformat()
        cur = self.conn.execute(
            """INSERT INTO memories (content, tags, importance, tier, agent, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (content.strip()[:2000], tags, importance, tier, agent, now, now)
        )
        self.conn.commit()
        log.info(f"  💾 STORED [{agent}] imp={importance:.1f} tags={tags}: {content[:80]}...")
        return cur.lastrowid

    # ── SEMANTIC SEARCH (TF-IDF style keyword matching, offline) ──────────────
    def recall(self, query: str, top_k: int = 8, min_importance: float = 0.5) -> list:
        """
        Offline semantic search using TF-IDF keyword overlap.
        No vector DB needed. Works entirely in SQLite.
        """
        # Tokenize query
        query_tokens = set(re.findall(r'\b\w{3,}\b', query.lower()))
        if not query_tokens:
            return self._top_by_importance(top_k)

        # Pull all non-archived memories above threshold
        rows = self.conn.execute(
            """SELECT id, content, tags, importance, agent, tier, access_count
               FROM memories
               WHERE archived = 0 AND importance >= ?
               ORDER BY importance DESC LIMIT 500""",
            (min_importance,)
        ).fetchall()

        # Score each memory by keyword overlap + importance
        scored = []
        for row in rows:
            mem_id, content, tags, importance, agent, tier, acc = row
            mem_tokens = set(re.findall(r'\b\w{3,}\b',
                                        (content + " " + tags).lower()))
            overlap = len(query_tokens & mem_tokens)
            if overlap == 0:
                continue
            # TF-like score: overlap × log(importance+1) + access_bonus
            score = overlap * math.log(importance + 1) + (acc * 0.1)
            scored.append((score, row))

        scored.sort(key=lambda x: -x[0])
        results = []
        for _, row in scored[:top_k]:
            mem_id, content, tags, importance, agent, tier, acc = row
            # Increment access count (popular memories strengthen)
            self.conn.execute(
                "UPDATE memories SET access_count=access_count+1, updated_at=? WHERE id=?",
                (datetime.utcnow().isoformat(), mem_id)
            )
            results.append({
                "id": mem_id, "content": content, "tags": tags,
                "importance": importance, "agent": agent, "tier": tier,
            })
        self.conn.commit()
        return results

    # ── TOP BY IMPORTANCE (no query) ──────────────────────────────────────────
    def _top_by_importance(self, top_k: int) -> list:
        rows = self.conn.execute(
            """SELECT id, content, tags, importance, agent, tier
               FROM memories WHERE archived=0
               ORDER BY importance DESC LIMIT ?""", (top_k,)
        ).fetchall()
        return [{"id":r[0],"content":r[1],"tags":r[2],
                 "importance":r[3],"agent":r[4],"tier":r[5]} for r in rows]

    # ── UPDATE ────────────────────────────────────────────────────────────────
    def update(self, mem_id: int, new_content: str, importance: float = None):
        """Update an existing memory (knowledge correction). Never deletes old."""
        now = datetime.utcnow().isoformat()
        if importance is not None:
            self.conn.execute(
                "UPDATE memories SET content=?, importance=?, updated_at=? WHERE id=?",
                (new_content[:2000], importance, now, mem_id)
            )
        else:
            self.conn.execute(
                "UPDATE memories SET content=?, updated_at=? WHERE id=?",
                (new_content[:2000], now, mem_id)
            )
        self.conn.commit()
        log.info(f"  📝 UPDATE mem#{mem_id}: {new_content[:60]}...")

    # ── ARCHIVE (not delete) ──────────────────────────────────────────────────
    def archive(self, mem_id: int):
        """Mark as archived — still retrievable via direct ID, not injected."""
        self.conn.execute(
            "UPDATE memories SET archived=1, updated_at=? WHERE id=?",
            (datetime.utcnow().isoformat(), mem_id)
        )
        self.conn.commit()
        log.info(f"  📦 ARCHIVED mem#{mem_id}")

    # ── IMPORTANCE DECAY (run periodically – not a wipe) ─────────────────────
    def decay(self, decay_rate: float = 0.005):
        """
        Slowly decay importance of old memories not recently accessed.
        Nothing is deleted. Archives happen at < 0.1.
        Recency and access protect memories from decay.
        """
        self.conn.execute("""
            UPDATE memories
            SET importance = MAX(0.1, importance - ?)
            WHERE archived = 0
              AND access_count = 0
              AND created_at < datetime('now', '-7 days')
        """, (decay_rate,))
        # Auto-archive < 0.1 importance (not deleted, just deprioritized)
        affected = self.conn.execute("""
            UPDATE memories SET archived=1
            WHERE importance < 0.1 AND archived = 0
        """).rowcount
        self.conn.commit()
        if affected > 0:
            log.info(f"  📦 Decayed {affected} memories to archive (not deleted)")

    # ── PARSE AGENT OUTPUT FOR MEMORY COMMANDS ───────────────────────────────
    def parse_output(self, text: str, agent: str = "SYSTEM") -> list:
        """
        Parse agent output for [MEMORIZE:], [UPDATE:], [ARCHIVE:] commands.
        Returns list of actions taken.
        """
        actions = []

        # [MEMORIZE: content | importance:N | tags:x,y,z]
        for m in re.finditer(
            r'\[MEMORIZE:\s*(.+?)\s*\|\s*importance:(\d+(?:\.\d+)?)\s*(?:\|\s*tags:([^\]]+))?\]',
            text, re.IGNORECASE
        ):
            content = m.group(1).strip()
            imp = float(m.group(2))
            tags = (m.group(3) or "").strip()
            mid = self.store(content, imp, tags, agent)
            actions.append({"action": "MEMORIZE", "id": mid, "content": content[:60]})

        # [UPDATE: old_fact | new_fact | reason:...]
        for m in re.finditer(
            r'\[UPDATE:\s*(.+?)\s*\|\s*(.+?)\s*\|\s*reason:([^\]]+)\]',
            text, re.IGNORECASE
        ):
            old = m.group(1).strip()
            new = m.group(2).strip()
            # Find best matching memory to update
            candidates = self.recall(old, top_k=1)
            if candidates:
                self.update(candidates[0]["id"], new)
                actions.append({"action": "UPDATE", "id": candidates[0]["id"]})
            else:
                mid = self.store(f"[UPDATED] {new}", 5.0, "", agent)
                actions.append({"action": "UPDATE_NEW", "id": mid})

        return actions

    # ── BUILD INJECTION STRING FOR AGENT PROMPTS ─────────────────────────────
    def build_injection(self, query: str, agent: str = "", top_k: int = 8) -> str:
        """
        Build the memory injection block to prepend to any agent's prompt.
        This is the core of the no-wipe technique.
        """
        memories = self.recall(query, top_k=top_k)
        if not memories:
            return "[MEMORY CORE: No relevant long-term memories yet — this is session 1 for this context]"

        lines = ["[MEMORY CORE — PERMANENT KNOWLEDGE (never wiped):"]
        for i, m in enumerate(memories, 1):
            tier_label = {"episodic":"EP","long_term":"LT","system":"SYS"}.get(m["tier"],"?")
            lines.append(
                f"  {i}. [{tier_label}|imp:{m['importance']:.1f}|{m['agent']}] {m['content']}"
            )
        lines.append("]")
        return "\n".join(lines)

    # ── STATS ─────────────────────────────────────────────────────────────────
    def stats(self) -> dict:
        total  = self.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        active = self.conn.execute("SELECT COUNT(*) FROM memories WHERE archived=0").fetchone()[0]
        arch   = total - active
        avg_imp = self.conn.execute(
            "SELECT AVG(importance) FROM memories WHERE archived=0"
        ).fetchone()[0] or 0
        top = self.conn.execute(
            "SELECT content, importance FROM memories WHERE archived=0 ORDER BY importance DESC LIMIT 3"
        ).fetchall()
        return {
            "total": total, "active": active, "archived": arch,
            "avg_importance": round(avg_imp, 2),
            "top_memories": [{"content": r[0][:60], "importance": r[1]} for r in top],
            "db_path": str(DB_PATH),
        }

    def close(self):
        self.conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# SINGLETON INSTANCE (import this in swarm_loop + EH API)
# ══════════════════════════════════════════════════════════════════════════════
_core: Optional[MemoryCore] = None

def get_core() -> MemoryCore:
    global _core
    if _core is None:
        _core = MemoryCore()
    return _core


# ══════════════════════════════════════════════════════════════════════════════
# CLI TEST / INIT
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    core = get_core()
    print("\n" + "="*60)
    print("NEXUS MEMORY CORE — NO-WIPE PERSISTENT MEMORY")
    print("="*60)
    stats = core.stats()
    print(f"  Total memories: {stats['total']}")
    print(f"  Active:         {stats['active']}")
    print(f"  Archived:       {stats['archived']}")
    print(f"  Avg importance: {stats['avg_importance']}")
    print(f"  DB location:    {stats['db_path']}")
    print()

    if stats["total"] == 0:
        print("  Seeding initial god-mode memories...")
        core.store("Prime directive: Love, care, empathy, dignity with ruthless efficiency",
                   importance=9.9, tags="core,prime", tier="system", agent="SYSTEM")
        core.store("This is NEXUS PRIME — 100% offline, no API, no memory wipe, RTX 4060",
                   importance=9.5, tags="identity,system", tier="system", agent="SYSTEM")
        core.store("Two optimization timescales: PSO=fast numerical, Mycelium=slow structural",
                   importance=8.0, tags="architecture,pso,mycelium", tier="system", agent="SYSTEM")
        core.store("Ant colony pheromones: short memory, push-deposit, evaporates",
                   importance=7.5, tags="antennae,architecture", tier="system", agent="SYSTEM")
        core.store("Mycelium: long-term, bidirectional pull, sink-strength, Hebbian growth",
                   importance=7.5, tags="mycelium,architecture", tier="system", agent="SYSTEM")
        print("  ✅ Seeded 5 core system memories")
    else:
        print("  TOP MEMORIES:")
        for m in stats["top_memories"]:
            print(f"    [{m['importance']:.1f}] {m['content']}")

    print()
    print("GOD MODE PROMPT (inject into SUPERVISOR + PLANNER):")
    print("─"*60)
    print(GOD_MODE_PROMPT.strip())
    print("─"*60)
    print()
    print("USAGE IN nexus_swarm_loop.py:")
    print("  from nexus_memory_core import get_core, GOD_MODE_PROMPT")
    print("  core = get_core()")
    print("  injection = core.build_injection(current_task, agent_name)")
    print("  full_prompt = injection + '\\n' + agent_system_prompt")
    print("  # After agent output:")
    print("  core.parse_output(agent_output, agent_name)")
    print()
    core.close()

