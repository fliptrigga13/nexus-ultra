"""
nexus_notion_reporter.py
══════════════════════════════════════════════════════════════
NEXUS Swarm → Notion MCP Bridge
Reads nexus_deployable_copy.json + Redis cycle stats and logs
every new swarm cycle to the Notion "Swarm Cycle Log" database.

Run as a side-car (loops every 60s) — does NOT touch the swarm:
    python nexus_notion_reporter.py

Or run once to sync current data:
    python nexus_notion_reporter.py --once
══════════════════════════════════════════════════════════════
"""

import json
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone

import requests

# ── Config ────────────────────────────────────────────────────────────────────

BASE = Path(__file__).parent

# Load .env
_notion_token = None
_redis_pass = None
for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
    if line.startswith("NOTION_TOKEN="):
        _notion_token = line.split("=", 1)[1].strip()
    if line.startswith("REDIS_PASSWORD="):
        _redis_pass = line.split("=", 1)[1].strip()

NOTION_TOKEN    = _notion_token or ""
DATABASE_ID     = "32ff17fe54c68086be8dda4f1816a0bb"
COPY_FILE       = BASE / "nexus_deployable_copy.json"
STATE_FILE      = BASE / "nexus_notion_state.json"  # tracks which cycles we've logged
POLL_INTERVAL   = 60  # seconds

log = logging.getLogger("NOTION_REPORTER")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

# ── State tracking ─────────────────────────────────────────────────────────────

def load_state() -> set:
    """Return set of cycle IDs already logged to Notion."""
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return set(data.get("logged_cycles", []))
        except Exception:
            pass
    return set()

def save_state(logged: set):
    STATE_FILE.write_text(
        json.dumps({"logged_cycles": sorted(logged)}, indent=2),
        encoding="utf-8"
    )

# ── Notion API ─────────────────────────────────────────────────────────────────

def create_page(cycle: dict) -> bool:
    """Create a Notion database row for one swarm cycle entry."""
    ts_raw = cycle.get("ts", datetime.now(timezone.utc).isoformat())
    # Normalize timestamp to ISO 8601 with Z suffix for Notion
    try:
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    except Exception:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    cycle_id  = cycle.get("cycle", "unknown")
    score     = cycle.get("score", 0.0)
    mvp       = cycle.get("mvp", "—")
    copy_type = cycle.get("type", "UNKNOWN")
    body      = (cycle.get("body") or "")[:2000]
    scout_ctx = (cycle.get("scout_ctx") or "")[:500]
    posted    = cycle.get("posted", False)

    # Title: "cycle_XXXXXXXXXX | score=0.77 | REDDIT_REPLY"
    title = f"{cycle_id} | score={score:.2f} | {copy_type}"

    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "Name": {
                "title": [{"text": {"content": title}}]
            },
            "Cycle ID": {
                "rich_text": [{"text": {"content": cycle_id}}]
            },
            "Score": {
                "number": round(score, 3)
            },
            "MVP Agent": {
                "select": {"name": mvp}
            },
            "Type": {
                "select": {"name": copy_type}
            },
            "Posted": {
                "checkbox": posted
            },
            "Timestamp": {
                "date": {"start": ts}
            },
            "Scout Context": {
                "rich_text": [{"text": {"content": scout_ctx}}]
            },
        },
        "children": [
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"text": {"content": "Outreach Copy"}}]
                }
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": body or "(no copy generated)"}}]
                }
            }
        ]
    }

    resp = requests.post(
        "https://api.notion.com/v1/pages",
        headers=HEADERS,
        json=payload,
        timeout=15,
    )

    if resp.status_code == 200:
        log.info(f"[NOTION] ✅ Logged: {title}")
        return True
    else:
        log.error(f"[NOTION] ❌ Failed {resp.status_code}: {resp.text[:200]}")
        return False

# ── Setup: ensure DB has required properties ───────────────────────────────────

def setup_database():
    """Add missing properties to the Notion database if not present."""
    resp = requests.get(
        f"https://api.notion.com/v1/databases/{DATABASE_ID}",
        headers=HEADERS,
        timeout=10,
    )
    if resp.status_code != 200:
        log.error(f"[NOTION] Cannot fetch DB: {resp.status_code} {resp.text[:200]}")
        return False

    existing = set(resp.json().get("properties", {}).keys())

    desired = {
        "Cycle ID":      {"rich_text": {}},
        "Score":         {"number": {"format": "number"}},
        "MVP Agent":     {"select": {}},
        "Type":          {"select": {}},
        "Posted":        {"checkbox": {}},
        "Timestamp":     {"date": {}},
        "Scout Context": {"rich_text": {}},
    }

    to_add = {k: v for k, v in desired.items() if k not in existing}
    if not to_add:
        log.info("[NOTION] DB schema already up to date.")
        return True

    patch = requests.patch(
        f"https://api.notion.com/v1/databases/{DATABASE_ID}",
        headers=HEADERS,
        json={"properties": to_add},
        timeout=10,
    )
    if patch.status_code == 200:
        log.info(f"[NOTION] ✅ Added {len(to_add)} properties: {list(to_add.keys())}")
        return True
    else:
        log.error(f"[NOTION] ❌ Schema patch failed: {patch.status_code} {patch.text[:200]}")
        return False

# ── Main sync loop ─────────────────────────────────────────────────────────────

def sync_once():
    """Read deployable copy and log any new cycles to Notion."""
    if not COPY_FILE.exists():
        log.info("[NOTION] No deployable copy file yet — waiting for swarm cycles.")
        return 0

    try:
        cycles = json.loads(COPY_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"[NOTION] Could not read copy file: {e}")
        return 0

    logged = load_state()
    new_count = 0

    for cycle in cycles:
        cycle_id = cycle.get("cycle")
        if not cycle_id or cycle_id in logged:
            continue

        # Only log cycles with a score and non-empty body
        if not cycle.get("body") and not cycle.get("score"):
            continue

        if create_page(cycle):
            logged.add(cycle_id)
            new_count += 1
            time.sleep(0.35)  # Notion rate limit: ~3 req/sec

    save_state(logged)
    if new_count:
        log.info(f"[NOTION] Synced {new_count} new cycle(s). Total logged: {len(logged)}")
    return new_count

def main():
    parser = argparse.ArgumentParser(description="NEXUS Swarm → Notion Reporter")
    parser.add_argument("--once", action="store_true", help="Sync once and exit")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("  NEXUS NOTION REPORTER — Swarm Cycle Log Bridge")
    log.info(f"  Database: {DATABASE_ID}")
    log.info(f"  Token: {NOTION_TOKEN[:16]}..." if NOTION_TOKEN else "  ⚠️  NO TOKEN — set NOTION_TOKEN in .env")
    log.info("=" * 60)

    if not NOTION_TOKEN:
        log.error("NOTION_TOKEN not set in .env — aborting.")
        return

    log.info("[NOTION] Setting up database schema...")
    if not setup_database():
        log.error("DB setup failed. Check token and database ID.")
        return

    if args.once:
        synced = sync_once()
        log.info(f"[NOTION] Done. {synced} new entries logged.")
        return

    log.info(f"[NOTION] Polling every {POLL_INTERVAL}s — Ctrl+C to stop.")
    while True:
        try:
            sync_once()
        except KeyboardInterrupt:
            log.info("[NOTION] Stopped.")
            break
        except Exception as e:
            log.error(f"[NOTION] Unexpected error: {e}")
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
