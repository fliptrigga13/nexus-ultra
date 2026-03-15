"""
nexus_task_rotator.py
NEXUS ANTIGRAVITY COSMOS — Evolutionary Task Rotator
Feeds high-value self-improvement tasks into the swarm blackboard.
Runs independently alongside nexus_swarm_loop.py.
"""

import json
import time
import logging
from pathlib import Path
from datetime import datetime, UTC

# ── CONFIG ──────────────────────────────────────────────────────────────────
BLACKBOARD_PATH = Path(__file__).parent / "nexus_blackboard.json"
LOG_PATH        = Path(__file__).parent / "task_rotator.log"
CHECK_INTERVAL  = 60        # seconds between checks
MIN_QUEUE_SIZE  = 3         # refill when queue drops below this

# -- TASK POOL: grounded tasks with real, verifiable outputs ------------------
# Replaces meta-reflection loop - real tasks REWARD can score meaningfully
TASK_POOL = [
    # -- CODE --
    "Write a Python merge sort function with type hints, docstring, and 5 "
    "test cases showing correct output. Use [CODE:] blocks.",

    "Design a REST API spec for a subscription SaaS. Define endpoints, "
    "HTTP methods, request/response schemas, auth, and rate limits with curl examples.",

    "Write a Python script that reads JSON, validates required fields, and "
    "outputs clean CSV. Handle missing fields gracefully. Include [CODE:] block.",

    "Implement an in-memory LRU cache in Python with get/put/stats. "
    "Include [CODE:] block with 10 demonstration operations.",

    "Write a JavaScript fetch wrapper with retry (3 attempts, exponential "
    "backoff) and timeout support. Include [CODE:] block and usage example.",

    # -- MARKET RESEARCH --
    "Research AI agent tools market 2024-2025. Identify top 5 competitors, "
    "pricing and positioning. Use [FACT:] tags. Output a competitive matrix.",

    "Analyze AI research tools for solopreneurs. Top 3 buyer pain points, "
    "price points that convert, features that drive purchases. Use [FACT:] tags.",

    "Research pricing for AI SaaS products under $100/month. What price "
    "points convert best? Output a tiered pricing recommendation with rationale.",

    # -- PRODUCT: VeilPiercer --
    "Write 3 sales page headlines for VeilPiercer (AI swarm intelligence). "
    "One each for: developers, founders, researchers. Include a subheadline each.",

    "Define the ideal VeilPiercer buyer persona: demographics, job title, "
    "daily frustration, what they have tried, why they buy, one-line hook.",

    "Write a 3-email cold sequence for VeilPiercer targeting tech founders. "
    "Email 1: problem. Email 2: proof. Email 3: urgency. Each under 150 words.",

    # -- ANALYSIS --
    "Compare fine-tuning a small LLM vs prompt engineering a large one. "
    "Give a 5-criteria decision framework with concrete recommendations.",

    "Compare Redis vs SQLite vs in-memory dict for a 100 task/hour queue "
    "on one machine. Output a decision matrix: performance, complexity, reliability.",

    "Explain semantic search over 10,000 docs with local embeddings. "
    "Cover architecture, chunking strategy, and retrieval logic in detail.",

    "Identify the highest-leverage feature to add to VeilPiercer in 30 days "
    "to improve conversion. Support with user psychology and implementation estimate.",

    # -- SELF-LEARNING: ingest session logs --
    "Read the most recent chat log file in C:/Users/fyou1/Desktop/New folder/nexus-ultra/chats/ "
    "and extract: 1) all technical decisions made, 2) all bugs fixed and how, "
    "3) business model insights, 4) key lessons learned. "
    "Output as structured [MEMORIZE:] entries with importance scores.",

    "Review C:/Users/fyou1/Desktop/New folder/nexus-ultra/nexus_memory.json — "
    "identify the top 5 most valuable facts, the 5 most outdated/irrelevant facts, "
    "and 3 critical knowledge gaps the swarm should research next. "
    "Output actionable recommendations.",

    "Read C:/Users/fyou1/Desktop/New folder/nexus-ultra/evolution_log.json — "
    "analyze REWARD scores across all cycles, identify which agent types score highest, "
    "which task types get the best scores, and what patterns predict success. "
    "Output a performance report with recommendations.",
]

# ── LOGGING ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ROTATOR] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ],
)
log = logging.getLogger("task_rotator")


# ── BLACKBOARD HELPERS ───────────────────────────────────────────────────────
def load_blackboard() -> dict:
    if BLACKBOARD_PATH.exists():
        try:
            return json.loads(BLACKBOARD_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"Blackboard load failed: {e} — using empty")
    return {}


def save_blackboard(data: dict):
    BLACKBOARD_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ── CORE ROTATION LOGIC ──────────────────────────────────────────────────────
def refill_queue():
    bb = load_blackboard()

    queue = bb.get("task_queue", [])
    current_size = len(queue)

    if current_size >= MIN_QUEUE_SIZE:
        log.info(f"Queue has {current_size} tasks — no refill needed")
        return

    rotation_index = bb.get("task_rotation_index", 0)
    needed = MIN_QUEUE_SIZE - current_size
    added = []

    for i in range(needed):
        idx = (rotation_index + i) % len(TASK_POOL)
        task = TASK_POOL[idx]
        queue.append(task)
        added.append(task[:80] + "...")

    new_index = (rotation_index + needed) % len(TASK_POOL)

    bb["task_queue"] = queue
    bb["task_rotation_index"] = new_index
    bb["task_rotator_last_run"] = datetime.now(UTC).isoformat()

    save_blackboard(bb)

    log.info(f"Refilled {needed} tasks (index {rotation_index} → {new_index})")
    for t in added:
        log.info(f"  → {t}")


# ── MAIN LOOP ────────────────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("NEXUS TASK ROTATOR ONLINE")
    log.info(f"  Blackboard: {BLACKBOARD_PATH}")
    log.info(f"  Check interval: {CHECK_INTERVAL}s")
    log.info(f"  Min queue size: {MIN_QUEUE_SIZE}")
    log.info(f"  Task pool size: {len(TASK_POOL)}")
    log.info("=" * 60)

    while True:
        try:
            refill_queue()
        except Exception as e:
            log.error(f"Refill error: {e}")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
