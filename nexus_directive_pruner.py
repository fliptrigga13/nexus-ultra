"""
nexus_directive_pruner.py — REFLECT Directive Pruning Engine
============================================================
Reads all [REFLECT INSIGHT] directives from nexus_mind.db,
detects contradictions and redundancies, merges the best,
deletes the rest. Run manually or wire into SELF_EVOLUTION_LOOP.

Usage:
    python nexus_directive_pruner.py [--dry-run]
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from datetime import datetime

import httpx
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
DB_PATH     = BASE_DIR / "nexus_mind.db"
OLLAMA      = "http://127.0.0.1:11434"
JUDGE_MODEL = "deepseek-r1:14b"   # use the model already in VRAM (swarm uses it too)
PRUNE_MODEL = "deepseek-r1:14b"   # reasoning model — merges directives
MIN_KEEP    = 3                # never prune below this many directives

# ── Ollama helper ─────────────────────────────────────────────────────────────

async def llm(model: str, system: str, user: str, max_tokens: int = 300) -> str:
    """LLM call: Groq first (avoids Ollama conflict with running swarm), then Ollama fallback."""
    import os
    groq_key = os.environ.get("GROQ_API_KEY", "")

    # Try Groq first — doesn't conflict with the swarm's Ollama calls
    if groq_key:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                    json={
                        "model": "llama-3.1-8b-instant",
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user",   "content": user},
                        ],
                        "max_tokens": max_tokens,
                        "temperature": 0.3,
                    }
                )
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"].strip()
                else:
                    print(f"[LLM] Groq error {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            print(f"[LLM] Groq failed: {e} — falling back to Ollama")

    # Ollama fallback
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                f"{OLLAMA}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user},
                    ],
                    "stream": False,
                    "options": {"num_predict": max_tokens, "temperature": 0.3},
                }
            )
            if resp.status_code == 200:
                return resp.json().get("message", {}).get("content", "").strip()
            else:
                print(f"[LLM] Ollama error {resp.status_code}: {resp.text[:80]}")
    except Exception as e:
        print(f"[LLM] Ollama failed: {e}")
    return ""


# ── Load directives from SQLite ───────────────────────────────────────────────

def load_reflect_directives() -> list[dict]:
    """Load all REFLECT INSIGHT memories from nexus_mind.db."""
    try:
        import sqlite3
        conn = sqlite3.connect(str(DB_PATH))
        cur  = conn.cursor()
        # Try standard memory table structure
        cur.execute("""
            SELECT id, content, importance, created_at
            FROM memories
            WHERE (tags LIKE '%reflect%' OR content LIKE '%[REFLECT%')
              AND tier IN ('long_term', 'long-term')
            ORDER BY created_at ASC
        """)
        rows = cur.fetchall()
        conn.close()
        return [
            {"id": r[0], "content": r[1], "importance": r[2], "created_at": r[3]}
            for r in rows
        ]
    except Exception as e:
        print(f"[DB] Load error: {e}")
        return []


def delete_directive(directive_id: int, dry_run: bool):
    """Delete a directive from nexus_mind.db by ID."""
    if dry_run:
        print(f"  [DRY RUN] Would delete ID={directive_id}")
        return
    try:
        import sqlite3
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("DELETE FROM memories WHERE id = ?", (directive_id,))
        conn.commit()
        conn.close()
        print(f"  [PRUNED] Deleted ID={directive_id}")
    except Exception as e:
        print(f"  [DB] Delete error: {e}")


def insert_directive(content: str, dry_run: bool):
    """Insert a merged directive into nexus_mind.db."""
    if dry_run:
        print(f"  [DRY RUN] Would insert: {content[:80]}")
        return
    try:
        import sqlite3
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""
            INSERT INTO memories (content, importance, tags, agent, tier, created_at, updated_at)
            VALUES (?, 9.0, 'reflect,pruned,merged,auto', 'PRUNER', 'long_term', ?, ?)
        """, (content, datetime.utcnow().isoformat(), datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        print(f"  [MERGED] Inserted: {content[:80]}")
    except Exception as e:
        print(f"  [DB] Insert error: {e}")


# ── Grouping and dedup ────────────────────────────────────────────────────────

def _keyword_group(directives: list[dict]) -> list[list[dict]]:
    """
    Group directives by shared keywords — lightweight clustering without embeddings.
    Returns list of groups (each group = related directives).
    """
    THEME_KEYWORDS = {
        "opener":    ["opener", "open with", "start with", "first sentence"],
        "length":    ["sentence", "length", "short", "too long", "2-4"],
        "grounding": ["ground", "thread", "specific", "pain", "context"],
        "veilpiercer": ["veilpiercer", "vp", "tracing", "per-step"],
        "style":     ["em-dash", "question", "cringe", "ai tell", "marketer"],
        "platform":  ["reddit", "discord", "hn", "dev.to", "platform"],
    }
    buckets: dict[str, list[dict]] = {k: [] for k in THEME_KEYWORDS}
    buckets["other"] = []

    for d in directives:
        text = d["content"].lower()
        matched = False
        for theme, kws in THEME_KEYWORDS.items():
            if any(kw in text for kw in kws):
                buckets[theme].append(d)
                matched = True
                break
        if not matched:
            buckets["other"].append(d)

    return [g for g in buckets.values() if g]


# ── Contradiction detection ───────────────────────────────────────────────────

async def detect_and_merge(group: list[dict], dry_run: bool) -> int:
    """
    Given a group of related directives, ask LLM to detect contradictions
    and redundancies, then merge into 1-2 canonical directives.
    Returns number of net directives removed.
    """
    if len(group) < 2:
        return 0  # nothing to prune in a singleton group

    bullets = "\n".join(f"- [ID={d['id']}] {d['content']}" for d in group)

    system = """You are a directive consolidation engine for an AI swarm.
You will receive a list of behavioral directives. Your job:
1. Identify any that directly CONTRADICT each other (e.g., "always start with X" vs "never start with X")
2. Identify any that are REDUNDANT (same meaning, different words)
3. For contradictions and redundancies, produce ONE merged canonical directive that captures the best intent.
4. Keep directives that are unique and non-redundant.

Output format — respond with valid JSON only:
{
  "keep_ids": [list of IDs to keep unchanged],
  "delete_ids": [list of IDs to delete],
  "merged": "The new merged directive text if merging, else empty string"
}"""

    user = f"""Directives to analyze:
{bullets}

Respond with JSON:"""

    raw = await llm(JUDGE_MODEL, system, user, max_tokens=200)

    try:
        data = json.loads(raw)
    except Exception:
        # Try to extract JSON block
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group())
            except Exception:
                print(f"  [PRUNER] Could not parse LLM response — skipping group")
                return 0
        else:
            return 0

    delete_ids = data.get("delete_ids", [])
    merged     = data.get("merged", "").strip()
    kept       = data.get("keep_ids", [])

    if not delete_ids:
        return 0

    # Safety: never delete everything — must keep at least 1 per group
    ids_in_group = {d["id"] for d in group}
    safe_deletes = [i for i in delete_ids if i in ids_in_group]
    remaining    = ids_in_group - set(safe_deletes)

    if not remaining and not merged:
        # Don't delete all without a replacement
        safe_deletes = safe_deletes[1:]

    for did in safe_deletes:
        d_content = next((d["content"][:60] for d in group if d["id"] == did), "?")
        print(f"  Deleting [{did}]: {d_content}...")
        delete_directive(did, dry_run)

    if merged and len(merged) > 20:
        print(f"  Merging into: {merged[:80]}")
        insert_directive(merged, dry_run)

    return len(safe_deletes)


# ── Main prune loop ───────────────────────────────────────────────────────────

async def run_pruner(dry_run: bool = False):
    print(f"\n{'='*60}")
    print(f"[PRUNER] NEXUS DIRECTIVE PRUNER {'(DRY RUN)' if dry_run else '(LIVE)'}")
    print(f"{'='*60}")

    directives = load_reflect_directives()
    print(f"\n[PRUNER] Loaded {len(directives)} REFLECT directives from nexus_mind.db")

    if len(directives) <= MIN_KEEP:
        print(f"[PRUNER] Only {len(directives)} directives — below MIN_KEEP={MIN_KEEP}. Nothing to prune.")
        return

    # Group by theme
    groups = _keyword_group(directives)
    print(f"[PRUNER] Grouped into {len(groups)} theme clusters")

    total_pruned = 0
    for i, group in enumerate(groups):
        if len(group) < 2:
            continue
        print(f"\n[GROUP {i+1}] {len(group)} directives:")
        for d in group:
            print(f"  [{d['id']}] {d['content'][:70]}...")
        pruned = await detect_and_merge(group, dry_run)
        total_pruned += pruned

    print(f"\n{'='*60}")
    print(f"[PRUNER] ✅ Done. Net directives pruned: {total_pruned}")
    if dry_run:
        print("[PRUNER] Dry run — no changes written to database.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NEXUS Directive Pruner")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be pruned without writing to database")
    args = parser.parse_args()
    asyncio.run(run_pruner(dry_run=args.dry_run))
