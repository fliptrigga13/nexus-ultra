"""
nexus_veilpiercer_agent.py — Autonomous VeilPiercer Orchestrator
════════════════════════════════════════════════════════════════
One process that takes care of everything:

  • Scrapes 6 niche sources every 30 min → pushes to swarm Redis queue
  • Queries nexus_mind.db for latest EXECUTIONER + METACOG memories
  • Rebuilds nexus_niche_report.json with combined signals (scraped + swarm)
  • Logs a summary every cycle so you can see it working

Run alongside the swarm:
    python nexus_veilpiercer_agent.py

Flags:
    --once      Run one cycle and exit (for testing)
    --interval N  Override scrape interval in minutes (default 30)
"""

import json, time, logging, sqlite3, os, sys, argparse
from pathlib import Path
from datetime import datetime, UTC

log = logging.getLogger("VP-AGENT")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [VP-AGENT] %(message)s",
    datefmt="%H:%M:%S"
)

BASE   = Path(__file__).parent
DB     = BASE / "nexus_mind.db"
REPORT = BASE / "nexus_niche_report.json"
CONFIG = BASE / "nexus_niche_config.json"

# ── 1. Pull EXECUTIONER + METACOG memories from DB ───────────────────────────
def fetch_swarm_memories(top_n: int = 20) -> list[dict]:
    """Pull the freshest EXECUTIONER, METACOG, SENTINEL outputs from SQLite."""
    if not DB.exists():
        log.warning("nexus_mind.db not found — skipping memory pull")
        return []
    try:
        conn = sqlite3.connect(str(DB))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT content, agent, importance, tags, created_at
            FROM memories
            WHERE agent IN ('EXECUTIONER','METACOG','SENTINEL_MAGNITUDE')
              AND is_active = 1
            ORDER BY created_at DESC
            LIMIT ?
        """, (top_n,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        log.info(f"[DB] Pulled {len(rows)} swarm memories (EXECUTIONER/METACOG/SENTINEL)")
        return rows
    except Exception as e:
        log.warning(f"[DB] Memory pull failed: {e}")
        return []

# ── 2. Score agent type to signal type ───────────────────────────────────────
def agent_to_signal_type(agent: str, content: str) -> str:
    c = content.lower()
    if agent == "EXECUTIONER":
        return "action"
    if agent == "METACOG":
        return "insight"
    if agent == "SENTINEL_MAGNITUDE":
        if "competitor" in c or "alternative" in c:
            return "competitor"
        return "insight"
    if "pain" in c or "expensive" in c or "frustrat" in c:
        return "pain"
    if "buy" in c or "intent" in c or "pay" in c:
        return "intent"
    return "insight"

# ── 3. Run niche scraper ──────────────────────────────────────────────────────
def run_scraper() -> list[dict]:
    """Import and run the niche scraper, return scored posts."""
    try:
        from nexus_niche_scraper import run_once
        tasks = run_once(dry_run=False)
        log.info(f"[SCRAPER] Pushed {len(tasks)} niche tasks to Redis")

        # Read what was saved to report
        if REPORT.exists():
            with open(REPORT, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("top_signals", [])
        return []
    except Exception as e:
        log.warning(f"[SCRAPER] Failed: {e}")
        return []

# ── 4. Build combined signal report ──────────────────────────────────────────
def build_report(scraped: list[dict], swarm_mems: list[dict]) -> dict:
    """Merge scraper signals + swarm memories into unified report JSON."""
    signals = []

    # Scraper signals
    for s in scraped:
        signals.append({
            "title":     s.get("title", "")[:120],
            "body":      s.get("body", "")[:500],
            "type":      classify_scraped(s),
            "source":    s.get("url", "niche scraper"),
            "relevance": s.get("relevance", 0.5),
            "agent":     "NICHE INTAKE",
        })

    # Swarm memory signals
    for m in swarm_mems:
        content = m.get("content", "")
        agent   = m.get("agent", "EXECUTIONER")
        signals.append({
            "title":      f"{agent}: {content[:80]}",
            "body":       content[:500],
            "type":       agent_to_signal_type(agent, content),
            "source":     agent,
            "relevance":  min(1.0, m.get("importance", 8.5) / 10.0),
            "agent":      agent,
            "importance": m.get("importance", 8.5),
            "timestamp":  m.get("created_at", ""),
        })

    # Sort by relevance descending
    signals.sort(key=lambda s: s["relevance"], reverse=True)

    report = {
        "client":        "VeilPiercer",
        "generated_at":  datetime.now(UTC).isoformat(),
        "total_signals": len(signals),
        "swarm_memories": len(swarm_mems),
        "scraped_signals": len(scraped),
        "top_signals":   signals[:20],
        "signals":       signals,
        "summary": {
            "pain":       sum(1 for s in signals if s["type"] == "pain"),
            "intent":     sum(1 for s in signals if s["type"] == "intent"),
            "action":     sum(1 for s in signals if s["type"] == "action"),
            "insight":    sum(1 for s in signals if s["type"] == "insight"),
            "competitor": sum(1 for s in signals if s["type"] == "competitor"),
        }
    }
    return report

def classify_scraped(post: dict) -> str:
    text = (post.get("title","") + " " + post.get("body","")).lower()
    if any(w in text for w in ["pain","expensive","cost","frustrat","can't afford","too much","billing","api limit"]):
        return "pain"
    if any(w in text for w in ["looking for","willing to pay","need a solution","buy","switch","alternative"]):
        return "intent"
    if any(w in text for w in ["competitor","vs ","compared to","alternative to"]):
        return "competitor"
    return "insight"

# ── 5. Save report + log summary ─────────────────────────────────────────────
def save_and_log(report: dict):
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    s = report["summary"]
    log.info(
        f"[REPORT] {report['total_signals']} signals saved → "
        f"Pain:{s['pain']} Intent:{s['intent']} Action:{s['action']} "
        f"Insight:{s['insight']} Competitor:{s['competitor']}"
    )
    log.info(f"[REPORT] → {REPORT}")

# ── 6. Print executive summary ───────────────────────────────────────────────
def print_exec_summary(report: dict):
    top = [s for s in report["signals"] if s["type"] == "action"][:3]
    if not top:
        top = report["signals"][:3]
    log.info("═" * 60)
    log.info("  VEILPIERCER INTELLIGENCE BRIEF — TOP SIGNALS THIS CYCLE")
    log.info("═" * 60)
    for i, s in enumerate(top, 1):
        log.info(f"  [{i}] {s['type'].upper()} | {s['title'][:70]}")
        if s.get("body"):
            log.info(f"      {s['body'][:100]}…")
    log.info("═" * 60)

# ── 7. Main loop ──────────────────────────────────────────────────────────────
def run_cycle():
    log.info("━━━ VeilPiercer Agent Cycle Starting ━━━")
    scraped    = run_scraper()
    swarm_mems = fetch_swarm_memories(top_n=20)
    report     = build_report(scraped, swarm_mems)
    save_and_log(report)
    print_exec_summary(report)
    log.info("━━━ Cycle Complete ━━━\n")

def main():
    parser = argparse.ArgumentParser(description="VeilPiercer Autonomous Agent")
    parser.add_argument("--once",     action="store_true", help="Run one cycle and exit")
    parser.add_argument("--interval", type=int, default=30, help="Scrape interval in minutes")
    args = parser.parse_args()

    log.info("╔══════════════════════════════════════════╗")
    log.info("║  VEILPIERCER AUTONOMOUS AGENT — ONLINE   ║")
    log.info(f"║  Interval: {args.interval} min | DB: {'✓' if DB.exists() else '✗'}              ║")
    log.info("╚══════════════════════════════════════════╝")

    if args.once:
        run_cycle()
        return

    interval_sec = args.interval * 60
    while True:
        try:
            run_cycle()
        except Exception as e:
            log.error(f"Cycle failed (non-fatal): {e}")
        log.info(f"Sleeping {args.interval} min until next cycle…")
        time.sleep(interval_sec)

if __name__ == "__main__":
    main()
