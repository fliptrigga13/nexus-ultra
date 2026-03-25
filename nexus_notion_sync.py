"""
nexus_notion_sync.py
NEXUS Ultra → Notion Live Intelligence Feed
Notion MCP Challenge Entry — veil-piercer.com

Pipes live swarm cycle data into 3 Notion databases every 35 seconds:
  - Cycle Reports: score, MVP agent, task, latency, status
  - Agent Leaderboard: per-agent scores, MVP count, trend
  - Buyer Intelligence: signals, hooks, urgency from SCOUT outputs

Usage:
  pip install requests
  Set NOTION_TOKEN in .env (secret_xxx from notion.so/profile/integrations)
  Run: python nexus_notion_sync.py
"""

import os, json, sqlite3, time, logging, re
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

try:
    import redis as redis_lib
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# ── CONFIG ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
ENV_PATH = BASE_DIR / ".env"

def load_env():
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    env.update(os.environ)
    return env

ENV = load_env()

NOTION_TOKEN        = ENV.get("NOTION_TOKEN", "")
NOTION_CYCLES_DB    = ENV.get("NOTION_CYCLES_DB", "")
NOTION_AGENTS_DB    = ENV.get("NOTION_AGENTS_DB", "")
NOTION_BUYERS_DB    = ENV.get("NOTION_BUYERS_DB", "")
NEXUS_DB_PATH       = BASE_DIR / "nexus_mind.db"
SWARM_LOG           = BASE_DIR / "swarm_active.log"
SYNC_INTERVAL       = 35   # match swarm cycle interval

NOTION_API          = "https://api.notion.com/v1"
NOTION_VERSION      = "2022-06-28"

# ── LOGGING ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [NOTION-SYNC] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BASE_DIR / "notion_sync.log", encoding="utf-8"),
    ]
)
log = logging.getLogger("notion_sync")

# ── NOTION API HELPERS ───────────────────────────────────────────────────────
def notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }

def create_page(database_id: str, properties: dict, children: list = None) -> dict:
    """Create a new page (row) in a Notion database."""
    payload = {"parent": {"database_id": database_id}, "properties": properties}
    if children:
        payload["children"] = children
    r = requests.post(f"{NOTION_API}/pages", headers=notion_headers(), json=payload, timeout=15)
    if not r.ok:
        log.error(f"Notion API error {r.status_code}: {r.text[:200]}")
    return r.json() if r.ok else {}

def create_database(parent_page_id: str, title: str, properties: dict) -> str:
    """Create a Notion database and return its ID."""
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"type": "text", "text": {"content": title}}],
        "properties": properties,
    }
    r = requests.post(f"{NOTION_API}/databases", headers=notion_headers(), json=payload, timeout=15)
    if r.ok:
        db_id = r.json().get("id", "")
        log.info(f"Created database '{title}': {db_id}")
        return db_id
    log.error(f"Failed to create DB '{title}': {r.status_code} {r.text[:200]}")
    return ""

def create_root_page(title: str) -> str:
    """Create a root page in the workspace to host databases."""
    payload = {
        "parent": {"type": "workspace", "workspace": True},
        "properties": {"title": {"title": [{"type": "text", "text": {"content": title}}]}}
    }
    r = requests.post(f"{NOTION_API}/pages", headers=notion_headers(), json=payload, timeout=15)
    if r.ok:
        pid = r.json().get("id", "")
        log.info(f"Created root page '{title}': {pid}")
        return pid
    log.error(f"Failed root page: {r.status_code} {r.text[:200]}")
    return ""

# ── DATABASE SETUP ───────────────────────────────────────────────────────────
def setup_databases() -> dict:
    """Create the 3 NEXUS databases in Notion if IDs not already in .env."""
    ids = {
        "cycles": NOTION_CYCLES_DB,
        "agents": NOTION_AGENTS_DB,
        "buyers": NOTION_BUYERS_DB,
    }
    if all(ids.values()):
        log.info("All database IDs already configured.")
        return ids

    log.info("Setting up NEXUS databases in Notion...")
    root_id = create_root_page("NEXUS Ultra — Live Command Center")
    if not root_id:
        return ids

    # Cycle Reports DB
    if not ids["cycles"]:
        ids["cycles"] = create_database(root_id, "🔄 Cycle Reports", {
            "Cycle ID":    {"title": {}},
            "Score":       {"number": {"format": "percent"}},
            "MVP Agent":   {"select": {"options": [
                {"name": a, "color": c} for a, c in [
                    ("SCOUT","blue"),("COPYWRITER","green"),("COMMANDER","orange"),
                    ("CONVERSION_ANALYST","red"),("VALIDATOR","gray"),
                    ("EXECUTIONER","pink"),("OFFER_OPTIMIZER","purple"),("CLOSER","yellow"),
                ]]}},
            "Task":        {"rich_text": {}},
            "Score Reason": {"rich_text": {}},
            "Latency (s)": {"number": {"format": "number"}},
            "Status":      {"select": {"options": [
                {"name":"STABLE","color":"green"},{"name":"UNSTABLE","color":"red"},{"name":"RUNNING","color":"yellow"}
            ]}},
            "Timestamp":   {"date": {}},
        })

    # Agent Leaderboard DB
    if not ids["agents"]:
        ids["agents"] = create_database(root_id, "🏆 Agent Leaderboard", {
            "Agent":       {"title": {}},
            "Avg Score":   {"number": {"format": "percent"}},
            "Last Score":  {"number": {"format": "percent"}},
            "Model":       {"rich_text": {}},
            "MVP Count":   {"number": {"format": "number"}},
            "Trend":       {"select": {"options": [
                {"name":"↑ Rising","color":"green"},{"name":"→ Stable","color":"yellow"},{"name":"↓ Dropping","color":"red"}
            ]}},
            "Last Updated":{"date": {}},
        })

    # Buyer Intelligence DB
    if not ids["buyers"]:
        ids["buyers"] = create_database(root_id, "🎯 Buyer Intelligence", {
            "Signal":       {"title": {}},
            "Hook":         {"rich_text": {}},
            "Urgency":      {"select": {"options": [
                {"name":"HIGH","color":"red"},{"name":"MED","color":"yellow"},{"name":"LOW","color":"gray"}
            ]}},
            "Source":       {"rich_text": {}},
            "Action":       {"rich_text": {}},
            "Cycle":        {"rich_text": {}},
            "Date":         {"date": {}},
        })

    # Save IDs back to .env
    _save_notion_ids_to_env(ids)
    return ids

def _save_notion_ids_to_env(ids: dict):
    env_text = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
    updates = {
        "NOTION_CYCLES_DB": ids["cycles"],
        "NOTION_AGENTS_DB": ids["agents"],
        "NOTION_BUYERS_DB": ids["buyers"],
    }
    for key, val in updates.items():
        if not val:
            continue
        if key in env_text:
            env_text = re.sub(rf"^{key}=.*$", f"{key}={val}", env_text, flags=re.MULTILINE)
        else:
            env_text += f"\n{key}={val}"
    ENV_PATH.write_text(env_text, encoding="utf-8")
    log.info("Saved Notion DB IDs to .env")

# ── DATA READERS ─────────────────────────────────────────────────────────────
TAIL_BYTES = 51_200  # Read only last 50 KB — avoids full-file parse on huge logs

def read_latest_cycle_from_log() -> dict:
    """Parse the last completed cycle from swarm_active.log (tail only)."""
    if not SWARM_LOG.exists():
        return {}
    try:
        with open(SWARM_LOG, "rb") as f:
            f.seek(0, 2)  # seek to end
            size = f.tell()
            f.seek(max(0, size - TAIL_BYTES))
            raw = f.read()
        lines = raw.decode("utf-8", errors="ignore").splitlines()

    cycle_data = {
        "cycle_id": "", "score": 0.0, "mvp": "", "task": "",
        "latency": 0.0, "status": "STABLE", "fail_rate": 0.0,
        "agent_scores": {}, "timestamp": datetime.now(timezone.utc).isoformat()
    }

    for line in reversed(lines):
        if "SCORE_NORM" in line and not cycle_data["agent_scores"]:
            m = re.search(r"normed=(\{[^}]+\})", line)
            if m:
                try:
                    raw = m.group(1).replace("'", '"')
                    cycle_data["agent_scores"] = json.loads(raw)
                except Exception:
                    pass
            mvp_m = re.search(r"MVP=(\w+)", line)
            if mvp_m:
                cycle_data["mvp"] = mvp_m.group(1)

        if "SWARM CYCLE cycle_" in line and not cycle_data["cycle_id"]:
            m = re.search(r"cycle_(\d+)", line)
            if m:
                cycle_data["cycle_id"] = f"cycle_{m.group(1)}"

        if "TASK-BIAS" in line and not cycle_data["task"]:
            m = re.search(r"task selection: (.+)$", line)
            if m:
                cycle_data["task"] = m.group(1)[:120]

        if "avg_latency" in line and not cycle_data["latency"]:
            m = re.search(r'"avg_latency":\s*([\d.]+)', line)
            if m:
                cycle_data["latency"] = float(m.group(1))

        if "Cycle #" in line and "COMPLETE" in line and not cycle_data["score"]:
            m = re.search(r"Score=([\d.]+)", line)
            if m:
                cycle_data["score"] = float(m.group(1))

        if "system_status" in line:
            if "UNSTABLE" in line:
                cycle_data["status"] = "UNSTABLE"
            elif "STABLE" in line:
                cycle_data["status"] = "STABLE"

        if all([cycle_data["cycle_id"], cycle_data["score"], cycle_data["agent_scores"]]):
            break

    # Extract score reason from REWARD agent output in DB
    score_reason = ""
    if NEXUS_DB_PATH.exists():
        try:
            conn = sqlite3.connect(NEXUS_DB_PATH)
            row = conn.execute("""
                SELECT content FROM memories
                WHERE agent IN ('REWARD', 'SUPERVISOR')
                ORDER BY created_at DESC LIMIT 1
            """).fetchone()
            conn.close()
            if row:
                score_reason = row[0][:300].strip()
        except Exception:
            pass

    cycle_data["score_reason"] = score_reason
    return cycle_data

def read_buyer_signals_from_db() -> list:
    """Read recent SCOUT outputs tagged with buyer signals from SQLite."""
    if not NEXUS_DB_PATH.exists():
        return []
    try:
        conn = sqlite3.connect(NEXUS_DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT agent, content, importance, tags, created_at
            FROM memories
            WHERE (agent='SCOUT' OR tags LIKE '%buyer%' OR content LIKE '%BUYER:%' OR content LIKE '%veil-piercer%')
            AND created_at > datetime('now', '-1 hour')
            ORDER BY importance DESC, created_at DESC
            LIMIT 5
        """)
        rows = c.fetchall()
        conn.close()
        return [{"agent": r[0], "content": r[1], "importance": r[2], "tags": r[3], "created_at": r[4]} for r in rows]
    except Exception as e:
        log.warning(f"DB read error: {e}")
        return []

# ── NOTION WRITERS ───────────────────────────────────────────────────────────
_synced_cycles = set()
_agent_scores_history: dict[str, list] = {}

def push_cycle_report(db_ids: dict, cycle: dict):
    if not cycle.get("cycle_id") or cycle["cycle_id"] in _synced_cycles:
        return
    if not db_ids.get("cycles"):
        return

    score_pct = min(cycle["score"], 1.0)
    score_reason = cycle.get("score_reason", "")[:300]
    props = {
        "Cycle ID":     {"title": [{"text": {"content": cycle["cycle_id"]}}]},
        "Score":        {"number": round(score_pct, 3)},
        "MVP Agent":    {"select": {"name": cycle["mvp"] or "N/A"}},
        "Task":         {"rich_text": [{"text": {"content": cycle["task"] or "self-directed"}}]},
        "Score Reason": {"rich_text": [{"text": {"content": score_reason or "Pending REWARD evaluation"}}]},
        "Latency (s)":  {"number": round(cycle["latency"], 1)},
        "Status":      {"select": {"name": cycle["status"]}},
        "Timestamp":   {"date": {"start": cycle["timestamp"]}},
    }
    result = create_page(db_ids["cycles"], props)
    if result.get("id"):
        _synced_cycles.add(cycle["cycle_id"])
        log.info(f"✅ Pushed cycle {cycle['cycle_id']} score={score_pct:.2f} MVP={cycle['mvp']}")

def push_agent_leaderboard(db_ids: dict, cycle: dict):
    if not db_ids.get("agents") or not cycle.get("agent_scores"):
        return

    AGENT_MODELS = {
        "COMMANDER": "phi4:14b", "SCOUT": "qwen2.5:14b", "COPYWRITER": "qwen2.5:14b",
        "SUPERVISOR": "phi4:14b", "REWARD": "phi4:14b",
        "VALIDATOR": "gemma3:12b", "SENTINEL_MAGNITUDE": "gemma3:12b",
        "METACOG": "gemma3:12b", "EXECUTIONER": "mistral:7b",
        "CONVERSION_ANALYST": "mistral:7b", "OFFER_OPTIMIZER": "mistral:7b",
        "CLOSER": "mistral:7b",
    }

    now = datetime.now(timezone.utc).isoformat()
    for agent, score in cycle["agent_scores"].items():
        history = _agent_scores_history.setdefault(agent, [])
        history.append(score)
        if len(history) > 5:
            history.pop(0)

        trend = "Stable"
        if len(history) >= 2:
            if history[-1] > history[-2] + 0.05:
                trend = "Rising"
            elif history[-1] < history[-2] - 0.05:
                trend = "Dropping"

        props = {
            "Agent":        {"title": [{"text": {"content": agent + (" MVP" if agent == cycle.get("mvp") else "")}}]},
            "Last Score":   {"number": round(score, 3)},
            "Model":        {"rich_text": [{"text": {"content": AGENT_MODELS.get(agent, "unknown")}}]},
            "Trend":        {"select": {"name": trend}},
            "Last Updated": {"date": {"start": now}},
        }
        create_page(db_ids["agents"], props)

    log.info(f"✅ Pushed leaderboard for {len(cycle['agent_scores'])} agents")

def push_buyer_signals(db_ids: dict):
    if not db_ids.get("buyers"):
        return
    signals = read_buyer_signals_from_db()
    if not signals:
        return

    now = datetime.now(timezone.utc).isoformat()
    for sig in signals:
        content = sig["content"]
        # Extract BUYER: blocks if present
        buyer_match = re.search(r"BUYER:\s*(.+?)(?:\n|$)", content, re.IGNORECASE)
        signal_text = buyer_match.group(1)[:100] if buyer_match else content[:100]

        urgency = "HIGH" if sig["importance"] >= 9 else "MED" if sig["importance"] >= 7 else "LOW"

        props = {
            "Signal":   {"title": [{"text": {"content": signal_text}}]},
            "Hook":     {"rich_text": [{"text": {"content": content[:500]}}]},
            "Urgency":  {"select": {"name": urgency}},
            "Source":   {"rich_text": [{"text": {"content": sig["agent"]}}]},
            "Date":     {"date": {"start": now}},
        }
        create_page(db_ids["buyers"], props)

    if signals:
        log.info(f"✅ Pushed {len(signals)} buyer signals")

# ── MAIN LOOP ────────────────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("NEXUS → NOTION SYNC ONLINE")
    log.info(f"  Token: {'SET ✅' if NOTION_TOKEN else 'MISSING ❌ — set NOTION_TOKEN in .env'}")
    log.info(f"  Sync interval: {SYNC_INTERVAL}s")
    log.info("=" * 60)

    if not NOTION_TOKEN:
        log.error("NOTION_TOKEN not set. Add it to .env and restart.")
        return

    db_ids = setup_databases()
    log.info(f"Databases: cycles={db_ids['cycles'][:8]}... agents={db_ids['agents'][:8]}... buyers={db_ids['buyers'][:8]}...")

    cycle_count = 0
    while True:
        try:
            cycle = read_latest_cycle_from_log()
            if cycle.get("cycle_id"):
                push_cycle_report(db_ids, cycle)
                push_agent_leaderboard(db_ids, cycle)
            push_buyer_signals(db_ids)
            cycle_count += 1
            log.info(f"Sync #{cycle_count} complete. Sleeping {SYNC_INTERVAL}s...")
        except KeyboardInterrupt:
            log.info("Stopped by user.")
            break
        except Exception as e:
            log.error(f"Sync error: {e}")
        time.sleep(SYNC_INTERVAL)

if __name__ == "__main__":
    main()
