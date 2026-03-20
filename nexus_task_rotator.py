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

# ── MISSION STATEMENT (injected into every task context) ────────────────────
MISSION = (
    "MISSION: You are an intelligence agent working exclusively for VeilPiercer "
    "(veil-piercer.com) — the definitive AI swarm control platform for 2026. "
    "VeilPiercer sells for $197 USD, one-time payment, no subscriptions. "
    "Your singular purpose is to help VeilPiercer achieve maximum sales at $197, "
    "product excellence, and market dominance. Every output must directly "
    "serve this mission. Use [FACT:] tags for verifiable claims. "
    "Be specific, actionable, and scored against real business outcomes."
)

# -- TASK POOL: 100% VeilPiercer mission-critical tasks -----------------------
TASK_POOL = [

    # ── CATEGORY 1: COMPETITIVE INTELLIGENCE ─────────────────────────────────
    MISSION + "\n\nTASK: Identify the top 5 competitors to VeilPiercer right now "
    "(AI agent monitoring, LLM observability, swarm control tools). "
    "For each: name, price, weak point, and how VeilPiercer beats them. "
    "Output a [COMPETITOR MATRIX] with actionable positioning language.",

    MISSION + "\n\nTASK: Search for products that monitor, control, or audit AI agents. "
    "What are they missing that VeilPiercer has? List 3 critical gaps in the market "
    "that VeilPiercer fills uniquely. Use [FACT:] tags. "
    "Output: market gap analysis with evidence.",

    MISSION + "\n\nTASK: Analyze what LangChain, AutoGPT, and CrewAI users complain about most "
    "on Reddit, HN, and Discord. What pain points do they share that VeilPiercer solves? "
    "Output 5 specific complaints with direct VeilPiercer solutions. "
    "Format: [PAIN:] [SOLUTION:] pairs.",

    MISSION + "\n\nTASK: Who is selling AI agent tooling at $197–$497 one-time price points? "
    "What is their conversion strategy? What social proof do they use? "
    "Identify 3 tactics VeilPiercer could adopt immediately. "
    "Output: [TACTIC:] blocks with implementation steps.",

    # ── CATEGORY 2: BUYER PSYCHOLOGY ─────────────────────────────────────────
    MISSION + "\n\nTASK: Define the EXACT moment a VeilPiercer buyer decides to purchase. "
    "What fear, pain, or ambition triggers the $197 decision? "
    "Build a 3-stage buyer journey: AWARE → CONSIDER → BUY. "
    "For each stage: what they think, what they need to see, what removes objection.",

    MISSION + "\n\nTASK: Write the internal monologue of someone who almost bought VeilPiercer "
    "but didn't. What stopped them? List 5 specific objections and the exact words "
    "that would have overcome each one. Output: [OBJECTION:] [OVERCOME:] pairs.",

    MISSION + "\n\nTASK: Identify the 3 buyer personas most likely to purchase VeilPiercer at $197. "
    "For each: job title, tech stack, biggest AI pain point, what success looks like to them, "
    "and the single sentence that makes them buy. "
    "Use [PERSONA:] blocks with purchase trigger.",

    MISSION + "\n\nTASK: What do AI builders, founders, and researchers search on Google "
    "when they have the problem VeilPiercer solves? "
    "List 10 high-intent search queries. For each: monthly estimated volume, "
    "content angle VeilPiercer should target, and CTA that converts. "
    "Output: [KEYWORD:] [INTENT:] [CONTENT:] blocks.",

    # ── CATEGORY 3: PRODUCT ENHANCEMENT ──────────────────────────────────────
    MISSION + "\n\nTASK: What is the single feature that would make VeilPiercer worth $497 "
    "instead of $197? Back your answer with user psychology and technical feasibility. "
    "Output: feature spec with user story, implementation outline, and pricing justification.",

    MISSION + "\n\nTASK: VeilPiercer currently provides AI swarm monitoring and control. "
    "Propose 3 new use cases that would unlock entirely new buyer segments. "
    "Each must be implementable within 30 days on the existing RTX 4060 + Ollama stack. "
    "Output: [USE CASE:] blocks with target buyer and revenue estimate.",

    MISSION + "\n\nTASK: Design a VeilPiercer onboarding sequence for a new buyer. "
    "From purchase confirmation to first 'aha moment' in under 10 minutes. "
    "What do they see, click, and experience? "
    "Output: step-by-step onboarding flow with success milestones.",

    MISSION + "\n\nTASK: What automated report could VeilPiercer generate daily for its users "
    "that would make the product feel indispensable? "
    "Design the report: what it contains, what insight it surfaces, how it's delivered. "
    "Output: [REPORT SPEC] with sample output format.",

    # ── CATEGORY 4: MARKETING & CONTENT ──────────────────────────────────────
    MISSION + "\n\nTASK: Write 5 Twitter/X thread hooks about VeilPiercer that would go viral "
    "in the AI builder community. Each hook must create immediate curiosity or FOMO. "
    "Include the full first thread (7 tweets) for the strongest hook. "
    "Output: [HOOK:] blocks + full thread.",

    MISSION + "\n\nTASK: Write a LinkedIn article (800 words) that positions VeilPiercer's creator "
    "as the definitive authority on AI swarm control. "
    "Topic: 'The Silent Failure Mode Killing Every Auto-GPT Deployment in 2026'. "
    "Output: full article with title, subheadings, and CTA to veil-piercer.com.",

    MISSION + "\n\nTASK: Design a 5-step cold outreach sequence targeting AI team leads "
    "at companies with 10-100 employees using LLM-based workflows. "
    "Each touchpoint: channel, message, hook, CTA. Sequence spans 10 days. "
    "Output: full sequence with copy for each step.",

    MISSION + "\n\nTASK: Create 3 Reddit posts (r/MachineLearning, r/artificial, r/LocalLLaMA) "
    "that provide genuine value while organically positioning VeilPiercer. "
    "Posts must not feel like ads — they should teach something. "
    "Output: [POST:] blocks with title, body (300 words each), and soft CTA.",

    # ── CATEGORY 5: MARKET POSITIONING & PRICING ─────────────────────────────
    MISSION + "\n\nTASK: Make the case for raising VeilPiercer's price to $297 or $497. "
    "What would need to change in the product, positioning, or proof to justify it? "
    "Output: [REQUIREMENT:] blocks for each price tier with evidence-backed reasoning.",

    MISSION + "\n\nTASK: Design a VeilPiercer affiliate/referral program. "
    "Commission structure, who the ideal affiliates are, how they promote it, "
    "what assets they need. Output: full program spec with payout model and launch plan.",

    MISSION + "\n\nTASK: What's the fastest path to VeilPiercer's first 10 paying customers? "
    "Map out exact channels, exact outreach messages, and exact sequence of actions "
    "for the next 7 days. Be brutally specific — no generic advice. "
    "Output: [DAY X:] action blocks with expected outcomes.",

    MISSION + "\n\nTASK: Identify 5 newsletters, podcasts, or communities where VeilPiercer "
    "would convert best if featured. For each: audience size, reach method, "
    "pitch angle, expected conversion. "
    "Output: [CHANNEL:] blocks with outreach copy.",

    # ── CATEGORY 6: REAL-WORLD VALIDATION & ITERATION ────────────────────────
    MISSION + "\n\nTASK: Analyze the VeilPiercer sales page at veil-piercer.com. "
    "Identify the 3 biggest conversion killers — elements that create doubt, "
    "confusion, or lost urgency. For each: what's wrong, what to replace it with, "
    "expected conversion lift. Output: [CRO FIX:] blocks.",

    MISSION + "\n\nTASK: Write 10 testimonial frameworks VeilPiercer beta users could fill in. "
    "Each testimonial template must be specific, credible, and highlight a different "
    "benefit. Output: [TESTIMONIAL TEMPLATE:] blocks with fill-in-the-blank format.",

    MISSION + "\n\nTASK: Design a 30-day content calendar for VeilPiercer across "
    "Twitter/X, LinkedIn, and Reddit. "
    "One post per day — alternating between: value/education, social proof, "
    "urgency, and product showcase. "
    "Output: 30-day calendar with post type and topic for each day.",

    MISSION + "\n\nTASK: What does VeilPiercer need to prove to a skeptical AI engineer "
    "in the first 90 seconds on the sales page? "
    "Design the above-the-fold experience: headline, subheadline, visual, "
    "first CTA, and trust signal. "
    "Output: wireframe description + copy for each element.",

    MISSION + "\n\nTASK: If VeilPiercer had $0 in marketing budget, what are the top 3 "
    "zero-cost growth strategies with the highest ROI in the next 30 days? "
    "Output: full execution plan for each strategy with exact steps and expected results.",

    MISSION + "\n\nTASK: Write the VeilPiercer founding story (400 words). "
    "Why was it built? What problem pushed the founder to create it? "
    "What would have been lost without it? "
    "Make it authentic, specific, and emotionally resonant. "
    "Output: full story formatted for the 'About' section.",

    MISSION + "\n\nTASK: Design a VeilPiercer case study template for early adopters. "
    "Structure: problem → attempted solutions → discovery → implementation → results. "
    "Write a complete fictional example case study using the template. "
    "Output: template + full example case study (500 words).",

    MISSION + "\n\nTASK: What are the 5 most powerful proof elements VeilPiercer could show "
    "on its sales page right now (e.g. live cycle counter, memory score, real logs)? "
    "For each: what it proves, how to implement it on the page, expected trust lift. "
    "Output: [PROOF ELEMENT:] blocks with implementation spec.",

    MISSION + "\n\nTASK: Analyze the NEXUS swarm's last 10 cycle outputs. "
    "Which ones produced the most valuable VeilPiercer intelligence? "
    "What task types should be run MORE? What should be eliminated? "
    "Output: performance analysis with task priority recommendations.",

    MISSION + "\n\nTASK: Write the VeilPiercer product roadmap for Q2 2026. "
    "3 major features, each with: user benefit, technical approach, "
    "marketing angle, and how it justifies a price increase. "
    "Output: [ROADMAP ITEM:] blocks formatted for a public announcement.",
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
        added.append(str(task)[:80] + "...")

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
