"""
nexus_sales_agent.py — Autonomous VeilPiercer Sales Outreach Agent
══════════════════════════════════════════════════════════════════
Reads pain/intent signals from nexus_niche_report.json, uses local
Ollama to craft personalized outreach messages, queues them for
human approval before sending. Zero spam — you approve every send.

Flow:
  1. Read top PAIN + INTENT signals from niche report
  2. For each new signal — draft a helpful reply (not a pitch)
  3. Save to nexus_outreach_queue.json for your review
  4. On your approval via /api/approve-outreach → sends via email

Run: python nexus_sales_agent.py
"""

import json, time, logging, asyncio, httpx
from pathlib import Path
from datetime import datetime, UTC

log = logging.getLogger("SALES-AGENT")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [SALES] %(message)s", datefmt="%H:%M:%S")

BASE          = Path(__file__).parent
REPORT        = BASE / "nexus_niche_report.json"
QUEUE         = BASE / "nexus_outreach_queue.json"
SEEN          = BASE / "nexus_outreach_seen.json"
OLLAMA_URL    = "http://localhost:11434"
OLLAMA_MODEL  = "llama3.1:8b"   # good balance: persuasive writing quality


def load_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default
    except Exception:
        return default


def save_json(p: Path, data):
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_new_pain_signals():
    """Return PAIN + INTENT signals not yet drafted."""
    report = load_json(REPORT, {})
    seen   = set(load_json(SEEN, []))
    signals = report.get("signals", [])
    new = [
        s for s in signals
        if s.get("type") in ("pain", "intent")
        and s.get("source", "") not in seen
        and len(s.get("body", "")) > 30
    ]
    return new[:5]   # max 5 per cycle — quality over quantity


async def draft_outreach(signal: dict) -> str:
    """Use Ollama to draft a helpful, non-spammy response to a pain signal."""
    prompt = f"""You are a helpful AI tool advisor. Someone online posted this:

TITLE: {signal.get('title', '')}
POST: {signal.get('body', '')[:400]}

Write a SHORT, genuinely helpful reply (3-4 sentences max) that:
1. Acknowledges their specific pain point
2. Mentions that VeilPiercer (a local AI swarm at $197/mo) might help — but only if relevant
3. Ends with a soft CTA: "Happy to share more if useful"
4. Sounds human, NOT like marketing copy

Reply only with the message text, no quotes or labels."""

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{OLLAMA_URL}/api/generate", json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False
            })
            return r.json().get("response", "").strip()
    except Exception as e:
        log.warning(f"Ollama draft failed: {e}")
        return ""


async def run_cycle():
    log.info("=== Sales Agent Cycle ===")
    signals = get_new_pain_signals()
    if not signals:
        log.info("No new pain signals to draft for.")
        return

    queue = load_json(QUEUE, [])
    seen  = load_json(SEEN, [])

    for s in signals:
        source = s.get("source", "")
        title  = s.get("title", "")[:80]
        log.info(f"Drafting outreach for: {title}")

        draft = await draft_outreach(s)
        if not draft:
            continue

        entry = {
            "id":          f"outreach_{int(time.time())}",
            "signal_type": s.get("type"),
            "title":       title,
            "source":      source,
            "body":        s.get("body", "")[:300],
            "draft":       draft,
            "status":      "pending",   # pending → approved → sent
            "created_at":  datetime.now(UTC).isoformat(),
        }
        queue.append(entry)
        seen.append(source)
        log.info(f"  Draft queued: {draft[:80]}...")

    save_json(QUEUE, queue)
    save_json(SEEN, seen)
    log.info(f"Queue now has {len(queue)} items pending review.")
    log.info(f"Review at: http://localhost:3000/hub-login -> /intelligence/summary")


def main():
    log.info("VeilPiercer Sales Agent ONLINE")
    log.info(f"Monitoring: {REPORT}")
    log.info(f"Queue file: {QUEUE}")
    log.info("--- APPROVAL REQUIRED before any outreach is sent ---")

    interval = 30 * 60   # 30 minutes

    while True:
        try:
            asyncio.run(run_cycle())
        except Exception as e:
            log.error(f"Cycle error (non-fatal): {e}")
        log.info(f"Sleeping 30 min...")
        time.sleep(interval)


if __name__ == "__main__":
    main()
