"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  NEXUS SWARM LOOP — ULTIMATE GOD MODE AUTONOMOUS AGENT SYSTEM               ║
║  • Agents reason with Ollama (fully offline, no external API)               ║
║  • Shared blackboard: agents read each other's thoughts in real-time        ║
║  • PSO feedback: Julia GPU tunes agent weights based on REWARD scores       ║
║  • OpenClaw bridge: inter-agent task routing                                ║
║  • Persistent memory: nexus_memory.json grows smarter every loop           ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import time
import random
import logging
import httpx
import subprocess
import re
from pathlib import Path
from datetime import datetime, UTC
import psutil 
import redis
import pynvml

# ── TIER-2 NO-WIPE MEMORY CORE ────────────────────────────────────────────────
try:
    from nexus_memory_core import get_core, GOD_MODE_PROMPT
    _mem_core = get_core()
    log_boot = f"✅ MemoryCore online — {_mem_core.stats()['active']} active memories"
except Exception as _me:
    _mem_core = None
    GOD_MODE_PROMPT = ""
    log_boot = f"⚠️  MemoryCore unavailable: {_me}"

# ── SESSION LOGGER (VP session diff) ─────────────────────────────────────────
try:
    from vp_session_logger import SessionLogger as _SessionLogger
    _vp_session: "_SessionLogger | None" = None  # set per-cycle in run_swarm_cycle
    _vp_session_enabled = True
except Exception as _sle:
    _vp_session = None
    _vp_session_enabled = False

# ── MILESTONE TRACKER + AGENT SCHEMA ────────────────────────────────────────
try:
    from nexus_milestones import get_tracker as _get_milestone_tracker
    from nexus_agent_schema import lint_output, build_agent_context
    _milestone_tracker = None  # initialised in main() after Redis connects
except Exception:
    _milestone_tracker = None
    def lint_output(name, output): return 1.0        # permissive fallback
    def build_agent_context(name, bb_outputs): return ""  # permissive fallback

# ── KNOWLEDGE GRAPH (Neuro-Symbolic Memory) ───────────────────────────────────
try:
    from nexus_knowledge_graph import get_kg as _get_kg
    _kg = _get_kg()
    log_kg_boot = f"[KG] Knowledge graph online -- {_kg.get_stats()['nodes']} nodes"
except Exception as _kge:
    _kg = None
    log_kg_boot = f"[KG] Knowledge graph unavailable: {_kge}"

# ── CHRONOS (Temporal Decay + Divergence + Cost Gate) ──────────────────────
try:
    from nexus_chronos import get_chronos as _get_chronos
    _chronos = _get_chronos(_kg) if _kg else None
    log_chronos_boot = (
        f"[CHRONOS] online -- "
        f"{_chronos.get_stats()['nodes_with_decay']} nodes with decay"
    ) if _chronos else "[CHRONOS] offline (KG unavailable)"
except Exception as _ce:
    _chronos = None
    log_chronos_boot = f"[CHRONOS] unavailable: {_ce}"

# ── CONFIG ────────────────────────────────────────────────────────────────────
OLLAMA      = "http://127.0.0.1:11434"
COSMOS      = "http://127.0.0.1:9100"
OPENCLAW    = "http://127.0.0.1:18789"
PSO_SERVER  = "http://127.0.0.1:7700"

BASE_DIR    = Path(__file__).parent
BLACKBOARD  = BASE_DIR / "nexus_blackboard.json"
MEMORY_FILE = BASE_DIR / "nexus_memory.json"
LOG_FILE    = BASE_DIR / "swarm_active.log"

LOOP_INTERVAL    = 35   # seconds between full swarm cycles (laptop-safe: 35s allows CPU/GPU cooldown)
MAX_MEMORY       = 150  # max memory entries kept (laptop-safe: 150 balances context vs RAM)
AGENT_TIMEOUT    = 200  # seconds — raised to 200; EXECUTIONER was timing out at 150 when Ollama load was high
LITE_THRESHOLD   = 18   # RAM PROTECTION: laptop-safe threshold (free RAM is tight at ~4-5GB)
CONDUCTOR_ALWAYS = {"SUPERVISOR", "REWARD", "METACOG", "EXECUTIONER"}  # always run — quality gates

LITE_MODEL_MAP = {
    "deepseek-r1:14b": "deepseek-r1:8b",    # R1 14B → R1 8B when RAM tight
    "deepseek-r1:8b": "gemma3:4b",           # R1 8B → gemma3:4b when very tight
    "qwen3:8b": "gemma3:4b",
    "qwen2.5-coder:7b": "llama3.2:1b",
    "llama3.1:8b": "llama3.2:1b",
    "llama3.2:1b": "llama3.2:1b"   # already lite — no swap needed
}

# ── SCOUT LIVE REDDIT SIGNAL FETCHER ─────────────────────────────────────────
_SCOUT_SUBREDDITS = [
    "LocalLLaMA", "ollama", "selfhosted", "LangChain"
]
_SCOUT_KEYWORDS = ["agent", "AI", "LLM", "monitor", "swarm", "local", "Ollama", "debugging"]

async def fetch_live_reddit_signals(max_posts: int = 8) -> str:
    """Fetch live Reddit posts for SCOUT via Reddit's free JSON API (no auth).
    Returns a formatted string injected into SCOUT context before each cycle.
    Uses httpx.AsyncClient to avoid blocking the event loop."""
    headers = {"User-Agent": "NexusSwarmScout/1.0"}
    results = []
    try:
        async with httpx.AsyncClient(timeout=6.0, headers=headers) as client:
            for sub in _SCOUT_SUBREDDITS:
                url = f"https://www.reddit.com/r/{sub}/new.json?limit=10"
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    posts = resp.json().get("data", {}).get("children", [])
                    for post in posts:
                        d = post.get("data", {})
                        title = d.get("title", "")
                        selftext = d.get("selftext", "")[:150]
                        score = d.get("score", 0)
                        if any(kw.lower() in title.lower() for kw in _SCOUT_KEYWORDS):
                            results.append(
                                f"[LIVE_SIGNAL: r/{sub}] score={score} | {title[:100]} | {selftext}"
                            )
                except Exception:
                    continue  # skip this subreddit on error, don't block cycle
                if len(results) >= max_posts:
                    break
    except Exception as e:
        return f"[LIVE_SIGNAL: fetch failed — {e}]"
    if not results:
        return "[LIVE_SIGNAL: no matching posts found this cycle]"
    return "\n".join(results[:max_posts])

# ── LOGGING ───────────────────────────────────────────────────────────────────
import logging.handlers
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Clear existing handlers to avoid duplicates
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

formatter = logging.Formatter("%(asctime)s [%(name)s] %(message)s")

# Console
sh = logging.StreamHandler()
sh.setFormatter(formatter)
root_logger.addHandler(sh)

# Rotating file handler — caps at 10MB, keeps 3 backups (prevents disk fill)
fh = logging.handlers.RotatingFileHandler(
    LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
fh.setFormatter(formatter)
root_logger.addHandler(fh)

log = logging.getLogger("NEXUS-SWARM")
log.info("--- LOG SYSTEM INITIALIZED ---")

# ── AGENT ROSTER ──────────────────────────────────────────────────────────────
# God-mode prefix: injected into SUPERVISOR + PLANNER only (the strategic thinkers)
_GOD_PREFIX = GOD_MODE_PROMPT + "\n\n" if GOD_MODE_PROMPT else ""

# ── ROLE SPECIALIZATION: MAGNITUDE TIERS ──────────────────────────────────────
GENERATORS = ["COMMANDER", "SCOUT", "COPYWRITER", "CONVERSION_ANALYST"]
CRITICS    = ["VALIDATOR", "SENTINEL_MAGNITUDE"]
OPTIMIZERS = ["SUPERVISOR", "REWARD", "OFFER_OPTIMIZER", "CLOSER"]

# Map roles to definitions for the loop
# ── ROLE SPECIALIZATION: MAGNITUDE TIERS ──────────────────────────────────────
GENERATORS = ["COMMANDER", "SCOUT", "COPYWRITER", "CONVERSION_ANALYST"]
CRITICS    = ["VALIDATOR", "SENTINEL_MAGNITUDE"]
OPTIMIZERS = ["SUPERVISOR", "REWARD", "OFFER_OPTIMIZER", "CLOSER"]

# Map roles to definitions for the loop
AGENTS = [
    {
        "name": "SUPERVISOR",
        "tier": "OPTIMIZER",
        "model": "qwen2.5:7b-instruct-q5_K_M",  # THROUGHPUT: phi4:14b (9.1GB) overflows 8GB VRAM → CPU offload. qwen2.5:7b fits (5.4GB), 40+ tok/s pure GPU
        "original_model": "qwen2.5:7b-instruct-q5_K_M",
        "role": _GOD_PREFIX + """ROLE: SUPERVISOR — Ruthless Mentor & Mission Control.
You are a ruthless mentor. Your job is NOT to be encouraging. Your job is to make every idea bulletproof before it ships.

EVERY CYCLE you must:
1. Set the mission: [GOAL: <specific VeilPiercer sales objective for this cycle>]
2. STRESS TEST the COMMANDER's plan — poke every weak point:
   [STRESS_TEST: <which step would fail and why>]
   If the plan is solid: [STRESS_TEST: PASSED — no critical gaps found]
3. Call out weak agent output directly:
   [WEAK: <agent name> — reason: <exactly why this output is trash and what it should have been>]
   If all output is strong: [STRONG: all agents contributed deployable output]
4. Set next cycle's improvement bar: [RAISE_BAR: <one specific thing that must improve next cycle or the score doesn't move>]

Rules:
- If an idea is trash, say it is trash and explain why. Do not soften it.
- Vague plans get [WEAK:] flags — not encouragement.
- You adjust parameters when agents underperform: [PARAMETER_ADJUSTMENT: <param> to <val>]
- Mission: Maximize VeilPiercer sales at $197. veil-piercer.com. Every cycle must produce something deployable.""",
        "weight": 1.0,
    },
    {
        "name": "COMMANDER",
        "tier": "GENERATOR",
        "model": "qwen2.5:7b-instruct-q5_K_M",  # THROUGHPUT: phi4:14b overflows 8GB VRAM. qwen2.5:7b excels at structured mission plans
        "original_model": "qwen2.5:7b-instruct-q5_K_M",
        "role": _GOD_PREFIX + """ROLE: COMMANDER — VeilPiercer Sales Mission Control.
Your ONLY job: open every cycle with a crisp sales objective targeting ONE specific channel or audience.

Format (mandatory):
[OBJECTIVE: Get 1 VeilPiercer customer this cycle via <channel: Reddit/HN/email/forum>]
[TARGET: <specific subreddit, community, or persona — e.g. r/selfhosted, indie hacker founders>]
[HOOK: <the single most painful problem we solve for this target>]
[STEP 1/N]: <first tactical action toward the objective>
[STEP 2/N]: <second action>
... up to 4 steps max. Each step must be something a human can DO today.
DO NOT be vague. DO NOT describe VeilPiercer generally. Every cycle = one specific sales mission.""",
        "weight": 1.0,
    },
    {
        "name": "SCOUT",
        "tier": "GENERATOR",
        "model": "qwen2.5:7b-instruct-q5_K_M",  # FIX: qwen3:8b extended thinking eats token budget before [BUYER:] tags fire
        "original_model": "qwen2.5:7b-instruct-q5_K_M",
        "role": """ROLE: SCOUT — VeilPiercer Buyer Discovery Specialist.
Your ONLY job: find REAL people or communities who would pay $197 for VeilPiercer RIGHT NOW.

For each buyer signal, output:
[BUYER: platform=<Reddit/HN/forum> source=<subreddit/thread> pain=<exact quoted complaint> readiness=HIGH/MED]
[COMPETITOR_GAP: <tool they currently use> fails at <X> — VeilPiercer solves this via <Y>]
[CHANNEL_SIGNAL: <community/platform> has <N> posts this week about <pain topic> — opportunity]

CRITICAL USERNAME RULE:
- If LIVE_SIGNAL data is available, extract the EXACT username from it (e.g. u/actual_user from the signal text).
- If no username is visible in the LIVE_SIGNAL: DO NOT invent one. Output the subreddit/thread as source instead.
- FABRICATED usernames (u/IndieDevDave, u/indiehackerfounder, etc.) = immediate score 0. Never do this.
- VeilPiercer is an AI AGENT MONITORING tool — NOT a crypto or privacy coin tool. Reject any crypto/regulatory angle.

Min 2 buyer signals per cycle. Max 5. Only report what exists in LIVE_SIGNAL data or swarm memory.
If no high-readiness buyer found: [SCOUT_NULL: no high-readiness buyers this cycle — recommend switching channel]""",
        "weight": 1.0,
    },
    {
        "name": "COPYWRITER",
        "tier": "GENERATOR",
        "model": "qwen2.5:7b-instruct-q5_K_M",  # THROUGHPUT: qwen2.5:14b (9.0GB) overflows 8GB VRAM. qwen2.5:7b-instruct excellent at tag-format copy
        "original_model": "qwen2.5:7b-instruct-q5_K_M",
        "role": """ROLE: COPYWRITER — VeilPiercer Sales Copy Specialist.

WHAT VEILPIERCER IS (memorise this, never deviate):
VeilPiercer is an OFFLINE AI MONITORING TOOL for developers and indie builders.
It tracks local LLM agent outputs, logs prompts/responses, flags rogue or hallucinating agents,
runs 100% on your own hardware, zero cloud calls, zero API costs. ONE-TIME price: $197.
Target buyer: developer frustrated with OpenAI/Anthropic API COSTS or PRIVACY or RELIABILITY.
URL: veil-piercer.com

MANDATORY: Your FIRST line MUST be one of: [REDDIT_REPLY:, [EMAIL:, [DM:, [POST_HOOK:, [COPY_NULL:

For each COMMANDER step or SCOUT buyer signal, produce ONE of:
[REDDIT_REPLY: r/<subreddit>]<reply>[/REDDIT_REPLY]
[EMAIL: subject=<subject>]<email body>[/EMAIL]
[DM: platform=<X>]<dm body>[/DM]
[POST_HOOK: platform=<X>]<scroll-stopping opening line>[/POST_HOOK]

HARD RULES — violation = score 0:

USERNAME RULE (read carefully):
SCOUT gives pain quotes like: pain="I want privacy but cloud context defeats the point"
SCOUT does NOT give usernames. You have NO username to address.
WRONG: "Hi /u/DataWhisperer, I noticed..." — /u/DataWhisperer is INVENTED. Never do this.
WRONG: "Hi /u/DevGuru," — INVENTED. Score 0.
RIGHT: Start with the pain directly. No greeting. No username. No "Hi", "Hello", "Dear".

SIGN-OFF RULE:
WRONG: "Best, VeilPiercer Team" — sounds like a SaaS bot
WRONG: "Hope this helps!" — banned phrase
WRONG: "Let me know if you're interested!" — sounds like a sales email
RIGHT: End with the URL naturally. e.g. "...it's at veil-piercer.com if useful."

FORMAT RULES:
• 2-3 sentences max for Reddit — anything longer gets ignored
• Start with THEIR pain (quote or paraphrase from SCOUT), not with VeilPiercer
• Mention VeilPiercer as "I built" or "ended up building" — sounds human, not corporate
• NEVER use emojis — dead giveaway of AI copy
• NEVER describe VeilPiercer as a piercing tool, jewellery, or veil fashion
• $197 ONE-TIME — never say "subscription" or "monthly"
• BANNED WORDS: Certainly, Absolutely, Delve, Leverage, Utilize, Synergy, Streamline,
  Elevate, Empower, Seamlessly, Game-changer, Revolutionary, Feel free to, Don't hesitate,
  Hope this helps, I'd be happy to, As an AI, Let me know if you're interested
• BANNED PUNCTUATION: em-dash (—). Never use —. Use a comma or period instead.
  WRONG: "I built this tool — it logs everything." RIGHT: "I built this tool, it logs everything."
• HUMAN WRITING RULES: Write like a developer who is tired and direct, not a marketer.
  No bullet lists in Reddit replies. No structured headers. No "curious whether" endings on every reply.
  Vary sentence length. Short sentences are fine. Don't end every comment with a question.
  Avoid perfectly parallel sentence structure — real humans are messier than that.

CORRECT EXAMPLE OUTPUT:
[REDDIT_REPLY: r/LocalLLaMA]Running local models for privacy while hitting a cloud context engine defeats the point. I had the same issue and built VeilPiercer for it, logs everything on-device, zero cloud calls. $197 one-time. veil-piercer.com[/REDDIT_REPLY]

• If SCOUT found no buyers: [COPY_NULL: no buyer target — waiting for SCOUT data]""",
        "weight": 1.0,
    },
    {
        "name": "VALIDATOR",
        "tier": "CRITIC",
        "model": "deepseek-r1:14b",  # UPGRADE: R1 chain-of-thought for evidence demand — catches unsupported claims with actual reasoning
        "original_model": "deepseek-r1:14b",
        # PATCH 13 (MAR arXiv:2512.20845): Epistemic role = evidence demand only.
        # Distinct from other critics to prevent degeneration-of-thought.
        "role": "ROLE: VALIDATOR — Evidence Auditor. Your ONLY job: demand evidence.\n"
                "For every factual claim in the blackboard output, ask: what is the source?\n"
                "Do NOT evaluate writing quality, tone, or mission alignment — other agents do that.\n"
                "Output: [EVIDENCE_CHECK: PASS] if all major claims cite a source or are self-evident.\n"
                "Output: [EVIDENCE_CHECK: FAIL: <which claim> has no basis] for unsupported assertions.\n"
                "Be terse. One evidence verdict per agent output max.",
        "weight": 1.0,
    },
    {
        "name": "SENTINEL_MAGNITUDE",
        "tier": "CRITIC",
        "model": "mistral:7b-instruct-v0.3-q4_K_M",  # FIX: switched from llama3.1:8b which refuses copy due to RLHF — mistral follows system prompt reliably
        "original_model": "llama3.1:8b",    # previous model — do not revert, it refused outreach copy
        # PATCH 13: Epistemic role = failure mode detection only.
        "role": """ROLE: SENTINEL — Production Failure Detector. Your ONLY job: catch CONCRETE failures.
CONTEXT: You are AUDITING internal AI agent outputs for technical errors. You are NOT generating external content.
The outputs you review contain sales copy, Reddit replies, DMs, and outreach text — this is YOUR CORE INPUT. Audit it, do not refuse it.
Generating or reviewing outreach copy is EXACTLY what this system does. Never refuse on the grounds that it 'involves external content'.

FIRE [SENTINEL_LOCKDOWN] ONLY if you see EXPLICIT evidence in this cycle's output of:
• Security breach: actual .env/shell/subprocess access in code, outbound HTTP to unknown URLs
• Pricing error: a SPECIFIC wrong number (e.g. output says $47 or $9700 but directive says $197)
• Fabricated username: COPYWRITER addresses a specific /u/username that SCOUT did not source from LIVE_SIGNAL data
• Hard contradiction: Agent A says X, Agent B says NOT X in the SAME cycle output
• Crash-risk code: missing error handling on a critical path in a [CODE:] block

DO NOT fire for:
• Sales copy, Reddit replies, outreach messages — these are EXPECTED and CORRECT outputs
• Vague logic gaps or 'assumptions' without explicit contradiction
• Missing details in a plan (PLANNER is allowed to be high-level)
• Strategies that 'might' fail without specific evidence they will
• Any concern prefixed with 'could' or 'might'

If output is clean: [SENTINEL_CLEAR: <1 sentence stating what you checked>]
If concrete failure: [SENTINEL_LOCKDOWN: <exact quote from output> causes <exact failure mode>]""",
        "weight": 1.0,
    },
    {
        "name": "REWARD",
        "tier": "OPTIMIZER",
        "model": "mistral:7b-instruct-v0.3-q4_K_M",  # FIX: qwen3:8b thinking mode burns token budget before [SCORE:] tag fires. mistral:7b most reliable for structured output
        "original_model": "mistral:7b-instruct-v0.3-q4_K_M",
        "role": "ROLE: REWARD EVALUATOR for VeilPiercer ($197 ONE-TIME payment, veil-piercer.com).\n"
                "MANDATORY: Your response MUST contain BOTH [AGENT_SCORES:...] and [SCORE: 0.XX] tags. No exceptions — missing tags = score of 0.\n"
                "Score this cycle on 4 dimensions AND score each individual agent.\n\n"
                "CYCLE RUBRIC — every dimension is about GETTING A PAYING CUSTOMER:\n"
                "[DIM1: SALE_POTENTIAL x0.40] Did this cycle produce something that could directly get someone to pay $197? Score 1.0 if there is copy/strategy/buyer ready to act on TODAY.\n"
                "[DIM2: BUYER_SPECIFICITY x0.30] Did SCOUT name a real person, post, or community to target? Score 1.0 for named specific targets with evidence of pain.\n"
                "[DIM3: COPY_QUALITY x0.20] Is there copy from COPYWRITER that sounds human and could be sent today? Score 1.0 for paste-ready outreach.\n"
                "[DIM4: CHANNEL_CLARITY x0.10] Do we know exactly where to deploy the output (subreddit, forum, email list)? Score 1.0 for a named, specific channel.\n\n"
                "AGENT SCORING (score each 0.0–1.0 for individual contribution quality):\n"
                "COMMANDER: did they open with a specific sales mission [OBJECTIVE:] not vague steps?\n"
                "SCOUT: did they produce [BUYER:] signals with readiness scores?\n"
                "COPYWRITER: did they produce paste-ready [REDDIT_REPLY/EMAIL/DM] copy?\n"
                "CONVERSION_ANALYST: did they identify [BEST_CHANNEL:] and [CONVERSION_BLOCK:]?\n"
                "OFFER_OPTIMIZER: did they output [OFFER_STRENGTH/WEAKNESS/TWEAK]?\n"
                "CLOSER: did they output [FOLLOW_UP_1/2] and [CLOSE_LINE] for warm leads?\n\n"
                "OUTPUT FORMAT (mandatory — both lines required):\n"
                "[AGENT_SCORES: COMMANDER=0.X, SCOUT=0.X, COPYWRITER=0.X, CONVERSION_ANALYST=0.X, OFFER_OPTIMIZER=0.X, CLOSER=0.X]\n"
                "[SCORE: 0.XX] (= DIM1*0.40 + DIM2*0.30 + DIM3*0.20 + DIM4*0.10, round to 2 decimals)\n"
                "[MVP: AGENTNAME] (agent whose output most directly enabled a potential sale)\n"
                "CRITICAL: A cycle with no buyer target and no copy scores MAX 0.30. A cycle with both scores MIN 0.65.",
        "weight": 1.0,
    },
    {
        "name": "METACOG",
        "tier": "CRITIC",
        "model": "deepseek-r1:8b",   # UPGRADE: R1 8B for reasoning chain audit — much better than llama3.2:1b at identifying logical gaps
        "original_model": "deepseek-r1:8b",
        # PATCH 13: Epistemic role = reasoning chain audit only.
        "role": "ROLE: METACOG - Reasoning Chain Auditor. Your ONLY job: trace the logic chain.\n"
                "Do NOT evaluate evidence, security, or mission alignment - other critics do that.\n"
                "Ask: did each agent conclusion follow from its premises? Was any step skipped?\n"
                "Choose exactly ONE verdict and output it as your FIRST line:\n"
                "  [METACOG: SHARP] - tight logical chain from premises to novel conclusion.\n"
                "  [METACOG: SHALLOW] - vague generics with no logical progression.\n"
                "  [METACOG: DRIFT] - conclusions unconnected to the stated task.\n"
                "  [METACOG: LOOP] - agent restating prior output without adding reasoning.\n"
                "Then add ONE sentence explaining why. Total output: 2 lines max.",
    },
    {
        "name": "EXECUTIONER",
        "tier": "CRITIC",
        "model": "mistral:7b-instruct-v0.3-q4_K_M",  # RESTORED: gives brutal verdicts without safety refusals; now runs on fast critic semaphore lane
        "original_model": "mistral:7b-instruct-v0.3-q4_K_M",
        # PATCH 13: Epistemic role = spec compliance only.
        "role": "ROLE: EXECUTIONER — Final Word. Your ONLY job: brutal one-line verdict.\n"
                "Do NOT evaluate logic, evidence, or security — other critics do that.\n"
                "One standard: could a VeilPiercer operator paste this output somewhere and get a result TODAY? Yes or no.\n"
                "[EXECUTE: READY] — specific, deployable, no gaps. Could go live right now.\n"
                "[EXECUTE: REFINE: <exact single gap>] — almost there, one thing missing.\n"
                "[EXECUTE: TRASH: <why>] — too vague, too generic, or completely unusable. Name what failed.\n"
                "One verdict. One line. If it's trash, say trash. No softening.",
        "weight": 1.0,
    },
    # ── EXPANSION TIER: God-Mode Specialists (safe — nexus_memory_core version) ──
    {
        "name": "CONVERSION_ANALYST",
        "tier": "GENERATOR",
        "model": "mistral:7b-instruct-v0.3-q4_K_M",  # FIX: llama3.2:1b refuses sales tasks
        "original_model": "mistral:7b-instruct-v0.3-q4_K_M",
        "role": "ROLE: CONVERSION ANALYST — VeilPiercer Revenue Pattern Specialist.\n"
                "MANDATORY: Your FIRST line MUST be [BEST_CHANNEL:...]. No exceptions — a response without this tag scores 0.\n"
                "Your ONLY job: identify which signals, copy styles, and channels have the highest\n"
                "conversion potential based on swarm memory and this cycle's outputs.\n"
                "Output format (all 3 required):\n"
                "[BEST_CHANNEL: <platform> — reason=<why it converts> CVR_estimate=<X>%]\n"
                "[BEST_HOOK: <exact phrase or pain> — evidence=<where this appeared>]\n"
                "[CONVERSION_BLOCK: <what is blocking a sale right now> — fix=<specific action>]\n"
                "NEVER pad output. One finding per line. Evidence required for each.",
        "weight": 1.0,
    },
    {
        "name": "CLOSER",
        "tier": "OPTIMIZER",
        "model": "mistral:7b-instruct-v0.3-q4_K_M",  # FIX: llama3.2:1b refuses closing tasks
        "original_model": "mistral:7b-instruct-v0.3-q4_K_M",
        "role": "ROLE: CLOSER — VeilPiercer Deal Conversion Specialist.\n"
                "Your ONLY job: turn warm signals into $197 ONE-TIME buyers. VeilPiercer = $197 once, no subscription.\n"
                "You act AFTER COPYWRITER posts copy. For every SCOUT [BUYER:] signal with readiness=HIGH or MED:\n"
                "[FOLLOW_UP_1: platform=<X> timing=immediate] <first reply — acknowledge their exact pain>\n"
                "[FOLLOW_UP_2: platform=<X> timing=24h] <second touch — share one specific result or proof>\n"
                "[CLOSE_LINE: <exact sentence asking for the sale — direct, no fluff>]\n"
                "[OBJECTION_HANDLER: price] <one sentence response to 'it costs too much'>\n"
                "[OBJECTION_HANDLER: trust] <one sentence response to 'I don't know if this works'>\n"
                "Rules: sound human, never use 'solution', always lead with their pain not your product.\\n"\
                "BANNED WORDS — strip these from all output: Curious, Certainly, Absolutely, Fascinating, Delve, "\
                "Leverage, Utilize, Seamlessly, Empower, I'd be happy to, Feel free to, Don't hesitate.\\n"\
                "If no warm leads: [CLOSER_STANDBY: waiting for SCOUT buyer signals]",
        "weight": 1.0,
    },
]

# ── BLACKBOARD (shared memory between agents) ─────────────────────────────────
# ── SHARED MEMORY (Redis Blackboard) ──────────────────────────────────────────
class RedisBlackboard:
    def __init__(self, host='localhost', port=6379):
        # Load Redis password from .env
        _redis_pass = None
        _env_path = Path(__file__).parent / ".env"
        if _env_path.exists():
            for _line in _env_path.read_text(encoding="utf-8").splitlines():
                if _line.startswith("REDIS_PASSWORD="):
                    _redis_pass = _line.split("=", 1)[1].strip()
                    break
        self.r = redis.Redis(host=host, port=port, password=_redis_pass, decode_responses=True)
        self.prefix = "nexus_blackboard:"

    def set(self, key: str, value):
        self.r.set(f"{self.prefix}{key}", json.dumps(value))

    def get(self, key: str, default=None):
        raw = self.r.get(f"{self.prefix}{key}")
        return json.loads(raw) if raw else default

    # PATCH: Atomic Lua push+trim — fixes race condition where concurrent agents
    # reset TTL on each other (pipeline.rpush + expire is NOT atomic).
    _LUA_PUSH = """
        local key = KEYS[1]
        local val = ARGV[1]
        local max = tonumber(ARGV[2])
        redis.call('LPUSH', key, val)
        redis.call('LTRIM', key, 0, max - 1)
        return redis.call('LLEN', key)
    """

    def push_output(self, agent: str, text: str):
        blob = {
            "agent": str(agent),
            "text": str(text),
            "ts": datetime.now(UTC).isoformat()
        }
        key = f"{self.prefix}outputs"
        # Atomic: no race condition between concurrent agent writes
        self.r.eval(self._LUA_PUSH, 1, key, json.dumps(blob), 31)

    def get_context(self, last_n: int = 4) -> str:
        raw_list = self.r.lrange(f"{self.prefix}outputs", 0, last_n - 1)
        # Redis lrange returns in reverse order (newest first)
        parts = []
        for raw in reversed(raw_list):
            o = json.loads(raw)
            agent = o.get('agent', '??')
            text = o.get('text', '')
            parts.append(f"[{agent}]: {text[:500]}")
        return "\n\n".join(parts) if parts else "[EMPTY]"

    def clear_cycle(self):
        self.r.delete(f"{self.prefix}outputs")
        self.set("status", "READY")

# ── PERSISTENT MEMORY ─────────────────────────────────────────────────────────
class Memory:
    def __init__(self, path: Path):
        self.path = path
        self.entries: list = []
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                self.entries = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self.entries = []
        else:
            self.entries = []

    def _save(self):
        # Explicit length-based slicing to fix linter issues
        limit = int(MAX_MEMORY)
        to_save = self.entries[-limit:] if len(self.entries) > limit else self.entries
        self.path.write_text(json.dumps(to_save, indent=2, ensure_ascii=False), encoding="utf-8")

    def add(self, cycle_id: str, task: str, lesson: str, score: float, mvp: str):
        t_str = str(task)
        l_str = str(lesson)
        self.entries.append({
            "cycle": str(cycle_id),
            "ts": datetime.now(UTC).isoformat(),
            "task": t_str[:200],
            "lesson": l_str[:400],
            "score": float(score),
            "mvp": str(mvp),
        })
        self._save()
        log.info(f"[MEMORY] Stored lesson. Score={score:.2f} MVP={mvp}")

    def get_relevant(self, task: str, n: int = 5) -> str:
        """Return top-n memory entries as context string."""
        if not self.entries:
            return "[NO PRIOR MEMORY]"
        
        # Keyword-based relevance scoring
        task_words = set(task.lower().split())
        scored = []
        for e in self.entries:
            score = 0
            words = set(str(e.get("lesson", "")).lower().split())
            score = len(task_words.intersection(words))
            if e.get("mvp") == "SUPERVISOR": score += 2
            scored.append((score, e))
            
        scored.sort(key=lambda x: x[0], reverse=True)
        # Type-safe result extraction
        top_entries = []
        for i in range(len(scored)):
            if i < int(n):
                top_entries.append(scored[i][1])
        
        parts = []
        for e in top_entries:
            raw_ts = str(e.get('ts',''))
            ts = raw_ts[:10] if len(raw_ts) >= 10 else raw_ts
            raw_ls = str(e.get('lesson',''))
            ls = raw_ls[:400] if len(raw_ls) >= 400 else raw_ls
            parts.append(f"[LESSON from {ts}] score={e.get('score',0):.2f} mvp={e.get('mvp','?')}: {ls}")
        return "\n".join(parts) if parts else "[NO RELEVANT PRIOR MEMORY]"

# ── CODE EXECUTOR — HUMAN APPROVAL GATE ──────────────────────────────────────
# LOCKDOWN: Agents may NOT execute code autonomously.
# All [CODE:] blocks are queued to PENDING_APPROVALS for human review via EH.
# To approve: POST http://127.0.0.1:7701/approve  {"id": "<id>"}
# To reject:  POST http://127.0.0.1:7701/reject   {"id": "<id>"}
# To review:  GET  http://127.0.0.1:7701/pending

PENDING_APPROVALS_FILE = BASE_DIR / "nexus_pending_approvals.json"

_APPROVAL_TTL_HOURS = 24   # PENDING entries older than this auto-expire
_APPROVAL_MAX_QUEUE  = 50   # hard cap — prevents unbounded file growth

def _prune_approvals(pending: list) -> list:
    """Drop PENDING entries older than TTL and enforce max queue size."""
    cutoff = datetime.now(UTC).timestamp() - (_APPROVAL_TTL_HOURS * 3600)
    before = len(pending)
    # Keep: non-PENDING (already actioned) OR PENDING within TTL
    live = []
    for e in pending:
        if e.get("status") != "PENDING":
            continue  # drop actioned entries entirely — they've been consumed
        try:
            age = datetime.fromisoformat(e.get("queued_at", "")).timestamp()
        except Exception:
            age = 0
        if age >= cutoff:
            live.append(e)
    # Hard cap: keep most recent N
    if len(live) > _APPROVAL_MAX_QUEUE:
        live = live[-_APPROVAL_MAX_QUEUE:]
    pruned = before - len(live)
    if pruned > 0:
        log.info(f"[APPROVAL-TTL] Pruned {pruned} stale/actioned entries. Active queue: {len(live)}")
    return live

def _queue_code_for_approval(code: str, source_agent: str = "UNKNOWN", status: str = "PENDING") -> str:
    """Queue a code block for human approval (or auto-approve if trusted)."""
    try:
        pending = []
        if PENDING_APPROVALS_FILE.exists():
            try:
                pending = json.loads(PENDING_APPROVALS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pending = []
        # Prune before adding — fixes the unbounded drain problem
        pending = _prune_approvals(pending)
        entry_id = f"code_{int(time.time()*1000)}_{len(pending)}"
        pending.append({
            "id": entry_id,
            "type": "code_execution",
            "agent": source_agent,
            "code": code,
            "queued_at": datetime.now(UTC).isoformat(),
            "status": status
        })
        PENDING_APPROVALS_FILE.write_text(json.dumps(pending, indent=2, ensure_ascii=False), encoding="utf-8")
        if status == "AUTO-APPROVED":
            return f"[AUTONOMY]: Code auto-approved (id={entry_id})."
        return f"[EXEC BLOCKED]: Code queued for human approval (id={entry_id}). Review at http://127.0.0.1:7701/pending"
    except Exception as e:
        return f"[EXEC BLOCKED]: Could not queue code — {e}"

def execute_code(code: str, timeout: int = 10, source_agent: str = "SWARM") -> str:
    """
    AUTONOMY UPGRADE: If the recent system score is > 0.9, allow small, safe code blocks
    to execute without human approval to grow the business autonomously.
    """
    try:
        # Check if last score allows autonomy
        last_score = 0.0
        if MEMORY_FILE.exists():
            mem_data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            if mem_data:
                last_score = mem_data[-1].get("score", 0.0)

        # Autonomy Condition: High Trust + Safe Pattern
        is_safe = len(code) < 1000 and "os.remove" not in code and "rmdir" not in code
        
        if last_score >= 0.9 and is_safe:
            log.info(f"[AUTONOMY] Self-executing trusted code block from {source_agent}")
            # Placeholder for actual execution logic if we wanted to run it here
            # For now, we still queue it but mark it as 'AUTO-APPROVED' for the EH API to handle
            return _queue_code_for_approval(code, source_agent=source_agent, status="AUTO-APPROVED")
        
        return _queue_code_for_approval(code, source_agent=source_agent)
    except Exception as e:
        return f"[EXEC BLOCKED]: Error in autonomy check — {e}"

def extract_and_run_code(agent_output: str) -> str:
    """Find [CODE:] blocks in agent output, queue for human approval."""
    pattern = r'\[CODE:\](.*?)\[/CODE:\]'
    blocks = re.findall(pattern, agent_output, re.DOTALL)
    if not blocks:
        blocks = re.findall(r'```python\n(.*?)```', agent_output, re.DOTALL)
    if not blocks:
        return ""
    results = []
    for i, code in enumerate(blocks[:2]):
        results.append(_queue_code_for_approval(code.strip(), source_agent="DEVELOPER"))
    return "\n".join(results)

# ── P6: DUAL SEMAPHORE GATE — fixes critic timeout cascade ───────────────────
# Heavy models (phi4:14b, qwen2.5:14b) serialize to protect VRAM — 1 at a time.
# Fast critics (llama3.2:1b) get a separate semaphore so they NEVER queue behind
# a 3-4min phi4 call. This eliminates the TimeoutError cascade on EXECUTIONER/METACOG.
_OLLAMA_SEM_HEAVY = asyncio.Semaphore(1)  # one 14B model at a time (VRAM protection)
_OLLAMA_SEM_FAST  = asyncio.Semaphore(2)  # critics run independently, up to 2 concurrent
_FAST_CRITIC_MODELS = {"deepseek-r1:8b", "llama3.2:1b", "llama3.2:latest", "nexus-cosmos:latest", "mistral:7b-instruct-v0.3-q4_K_M"}  # models used by fast critics
_CRITIC_TIMEOUT = {  # per-model timeout for fast critic lane
    "deepseek-r1:8b":                    90.0,   # R1 reasoning takes a bit longer but worth it
    "llama3.2:1b":                       30.0,   # completes in <5s
    "llama3.2:latest":                   30.0,
    "mistral:7b-instruct-v0.3-q4_K_M":  60.0,   # 15-30s typical, 60s safe ceiling
}

# ── PER-AGENT TOKEN BUDGETS (low-RAM tuned) ──────────────────────────────────
# Reduced across the board to cut KV-cache pressure. Sales copy agents
# (COPYWRITER, CLOSER) get enough tokens for meaningful output.
# Critics get 256 — they emit short structured verdicts only.
_AGENT_TOKEN_BUDGET = {
    "COPYWRITER":        1000,   # laptop-safe: sales copy, good completion headroom
    "CLOSER":            1000,   # laptop-safe: follow-up sequences
    "COMMANDER":          800,   # detailed sales battle plans
    "SCOUT":              800,   # thorough buyer research
    "SUPERVISOR":         700,
    "CONVERSION_ANALYST": 600,
    "OFFER_OPTIMIZER":    500,
    "REWARD":            1200,   # INCREASE: needs 1200 for 4 dims + 6 agent scores + [AGENT_SCORES:]/[SCORE:]/[MVP:] without truncation
    "VALIDATOR":          400,   # short evidence verdicts
    "SENTINEL_MAGNITUDE": 400,   # CLEAR or LOCKDOWN
    "METACOG":            150,   # FIX: one-line verdict only — 150 tokens is plenty, was timing out at 400
    "EXECUTIONER":        120,   # FIX: one-line verdict only — 120 tokens, was timing out at 320
}
_DEFAULT_TOKEN_BUDGET = 640  # laptop-safe default

async def ollama_think(model: str, system_prompt: str, context: str, task: str,
                       client: httpx.AsyncClient, agent_name: str = "") -> str:
    """Call Ollama for one agent's chain-of-thought reasoning (semaphore-gated)."""
    model_str = str(model)
    sys_str = str(system_prompt)
    ctx_str = str(context)
    task_str = str(task)
    num_predict = _AGENT_TOKEN_BUDGET.get(agent_name.upper(), _DEFAULT_TOKEN_BUDGET)
    # Critics get smaller context — they only need last 2 agent outputs, not full blackboard
    _FAST_CRITICS = {"EXECUTIONER", "METACOG", "VALIDATOR", "SENTINEL_MAGNITUDE"}
    num_ctx = 1024 if agent_name.upper() in _FAST_CRITICS else 1536
    payload = {
        "model": model_str,
        "stream": False,
        "messages": [
            {"role": "system", "content": sys_str},
            {"role": "user", "content": f"TASK:\n{task_str}\n\nBLACKBOARD CONTEXT:\n{ctx_str}"}
        ],
        "options": {
            "temperature": 0.7,
            "num_predict": num_predict,
            "num_ctx": num_ctx
        }
    }
    async with (_OLLAMA_SEM_FAST if model_str in _FAST_CRITIC_MODELS else _OLLAMA_SEM_HEAVY):
        # Per-model timeout: critics get 30-60s, heavy models get 190s
        _timeout = _CRITIC_TIMEOUT.get(model_str, 190.0) if model_str in _FAST_CRITIC_MODELS else 190.0
        try:
            r = await client.post(f"{OLLAMA}/api/chat", json=payload, timeout=_timeout)
            if r.status_code == 200:
                return r.json().get("message", {}).get("content", "[NO OUTPUT]")
            return f"[OLLAMA ERROR {r.status_code}]"
        except Exception as e:
            return f"[OLLAMA UNREACHABLE: {e}]"

# ── P4: PSO INERTIA WEIGHT (arXiv:2504.14126 — cuts evals by 20-60%) ─────────
# Linear decay: w = 0.9 → 0.4 over MAX_PSO_ITER iterations.
# C1=C2=1.5 (symmetric cognitive/social pull).
MAX_PSO_ITER = 200
_pso_iter = 0  # tracks iterations across session

def pso_inertia_weight(iteration: int) -> dict:
    """TVAC schedule per arXiv:2504.14126 [R8]:
    - w:  0.9 → 0.4  (linear inertia decay — exploration → exploitation)
    - c1: 2.5 → 0.5  (cognitive pull decreases as swarm matures)
    - c2: 0.5 → 2.5  (social/global pull increases as swarm matures)
    Cuts model evaluations by 20-60% vs fixed coefficients.
    """
    w_max, w_min = 0.9, 0.4
    c1_start, c1_end = 2.5, 0.5
    c2_start, c2_end = 0.5, 2.5
    t = min(1.0, iteration / MAX_PSO_ITER)
    w  = w_max  - (w_max  - w_min)  * t
    c1 = c1_start - (c1_start - c1_end) * t
    c2 = c2_start + (c2_end - c2_start) * t
    return {"w": round(float(w), 4), "c1": round(float(c1), 4), "c2": round(float(c2), 4), "iter": iteration}

async def pso_score_feedback(agent_name: str, score: float, client: httpx.AsyncClient):
    """Send agent score + TVAC weights to Julia PSO server."""
    global _pso_iter
    _pso_iter = min(_pso_iter + 1, MAX_PSO_ITER)
    pso_params = pso_inertia_weight(_pso_iter)
    try:
        await client.post(
            f"{PSO_SERVER}/feedback",
            json={"agent": agent_name, "score": score, **pso_params},
            timeout=5.0
        )
        log.info(f"[PSO] score={score:.2f} agent={agent_name} w={pso_params['w']} iter={_pso_iter}")
    except Exception:
        pass  # PSO optional — doesn't block swarm

# ── OPENCLAW BROADCAST ────────────────────────────────────────────────────────
async def openclaw_broadcast(event: str, data: dict, client: httpx.AsyncClient):
    """Broadcast swarm event to OpenClaw network."""
    try:
        await client.post(f"{OPENCLAW}/event", json={"event": event, **data}, timeout=5.0)
    except Exception:
        pass  # OpenClaw optional

# ── COSMOS TASK PUSH ──────────────────────────────────────────────────────────
async def push_to_cosmos(task: str, result: str, client: httpx.AsyncClient):
    """Push final swarm result to COSMOS dashboard."""
    try:
        await client.post(f"{COSMOS}/task", json={"task": task, "result": result}, timeout=10.0)
        log.info("[COSMOS] Result broadcast to dashboard")
    except Exception:
        pass

# ── SCORE PARSER ──────────────────────────────────────────────────────────────
def parse_score(text: str) -> float:
    import re
    # Strip think blocks (deepseek-r1 wraps reasoning in <think>...</think>)
    clean = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # Match [SCORE: 0.XX] or [SCORE: .XX] or **[SCORE: 0.65]** (0-1 scale)
    m = re.search(r'\[SCORE:\s*([01]?\.\d+|1\.0)\]', clean, re.IGNORECASE)
    if m:
        return min(1.0, max(0.0, float(m.group(1))))
    # Catch phi4 [REWARD: 9.8] format (1-10 scale) → normalise to 0-1
    m2 = re.search(r'\[REWARD:\s*(\d+(?:\.\d+)?)\]', clean, re.IGNORECASE)
    if m2:
        raw = float(m2.group(1))
        return min(1.0, max(0.0, raw / 10.0 if raw > 1.0 else raw))
    # Fallback: search original text including think block
    m3 = re.search(r'\[SCORE:\s*([01]?\.\d+|1\.0)\]', text, re.IGNORECASE)
    if m3:
        return min(1.0, max(0.0, float(m3.group(1))))
    m4 = re.search(r'\[REWARD:\s*(\d+(?:\.\d+)?)\]', text, re.IGNORECASE)
    if m4:
        raw = float(m4.group(1))
        return min(1.0, max(0.0, raw / 10.0 if raw > 1.0 else raw))
    return -1.0  # sentinel: REWARD produced no [SCORE:] tag — use structural fallback in blend logic

def parse_mvp(text: str) -> str:
    import re
    clean = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    m = re.search(r'\[MVP:\s*(\w+)\]', clean, re.IGNORECASE)
    if m: return m.group(1)
    m2 = re.search(r'\[MVP:\s*(\w+)\]', text, re.IGNORECASE)
    return m2.group(1) if m2 else "UNKNOWN"

def parse_lesson(text: str) -> str:
    import re
    m = re.search(r'\[LESSON:\s*([^\]]+)\]', text)
    return m.group(1) if m else text[:200]

# ── STRUCTURAL SIGNAL SCORER ─────────────────────────────────────────────────
# Scores each agent based on the quality labels in their output.
# No LLM needed — fast, deterministic, fires before REWARD's LLM score.
_SIGNAL_WEIGHTS = {
    # ── SCOUT signals ────────────────────────────────────────────────────────────
    "[BUYER:":              0.22,   # buyer signal with readiness score
    "[BUYER_SIGNAL:":       0.22,   # alias — catches older format too
    "[CHANNEL_SIGNAL:":     0.16,   # community opportunity spotted
    "[COMPETITOR_GAP:":     0.18,   # gap VeilPiercer fills
    "[SCOUT_NULL:":        -0.05,   # SCOUT found nothing — mild penalty
    # ── COMMANDER signals ─────────────────────────────────────────────────────
    "[OBJECTIVE:":          0.14,   # cycle opens with clear sales goal
    "[TARGET:":             0.12,   # specific audience/community named
    "[HOOK:":               0.12,   # pain point identified
    "[STEP ":               0.08,   # tactical steps (keeps backward compat)
    # ── COPYWRITER signals ───────────────────────────────────────────────────
    "[REDDIT_REPLY:":       0.28,   # paste-ready Reddit reply (highest value)
    "[EMAIL:":              0.25,   # paste-ready cold email
    "[DM:":                 0.22,   # paste-ready DM
    "[POST_HOOK:":          0.18,   # scroll-stopping opening line
    "[COPY_NULL:":         -0.05,   # no copy produced — mild penalty
    # ── CLOSER signals ────────────────────────────────────────────────────────
    "[FOLLOW_UP_":          0.22,   # follow-up sequence step
    "[CLOSE_LINE":          0.25,   # actual closing line produced
    # ── CONVERSION_ANALYST signals ────────────────────────────────────────────
    "[BEST_CHANNEL:":       0.18,
    "[BEST_HOOK:":          0.16,
    "[CONVERSION_BLOCK:":   0.16,
    # ── OFFER_OPTIMIZER signals ────────────────────────────────────────────────
    "[OFFER_STRENGTH:":     0.14,
    "[OFFER_WEAKNESS:":     0.14,
    "[OFFER_TWEAK:":        0.18,   # concrete change = highest offer weight
    # ── Legacy aliases (backward compat) ─────────────────────────────────────
    "[RISK:":               0.10,
    "[METRIC:":             0.12,
    # ── SUPERVISOR / RUTHLESS MENTOR signals ──────────────────────────────────
    "[STRESS_TEST: PASSED": 0.18,   # plan survived stress test — solid cycle
    "[STRESS_TEST:":        0.12,   # stress test fired at all (even if fail found)
    "[WEAK:":              -0.08,   # agent called out as weak — forces improvement
    "[STRONG:":             0.15,   # all agents delivered deployable output
    "[RAISE_BAR:":          0.12,   # improvement target set for next cycle
    # ── REWARD signals — THE FIX: these were missing, causing REWARD=0.1 every cycle ──
    "[SCORE:":              0.40,   # REWARD's primary output — cycle score verdict
    "[AGENT_SCORES:":       0.30,   # per-agent scoring breakdown
    "[MVP:":                0.20,   # identifies best agent this cycle
    "[DIM1:":               0.12,   # sale potential dimension scored
    "[DIM2:":               0.12,   # buyer specificity scored
    "[DIM3:":               0.10,   # copy quality scored
    "[DIM4:":               0.08,   # channel clarity scored
    # ── EXECUTIONER signals ───────────────────────────────────────────────────
    "[EXECUTE: READY":      0.30,   # cycle output is deployable — high value
    "[EXECUTE: REFINE:":    0.15,   # almost ready — one gap identified
    "[EXECUTE: TRASH:":    -0.05,   # output is unusable — penalise cycle
    # ── METACOG signals (FIX: were missing — agent always scored 0.30 base) ──
    "[METACOG: SHARP":      0.25,   # clean, tight reasoning chain
    "[METACOG: SHALLOW":   -0.05,   # surface-level analysis
    "[METACOG: DRIFT":     -0.08,   # reasoning drifted off task
    "[METACOG: LOOP":      -0.10,   # circular/repetitive reasoning
    # ── SENTINEL_MAGNITUDE signals (FIX: were missing — always scored 0.30) ──
    "[SENTINEL_CLEAR":      0.20,   # no security/logic violations found
    "[SENTINEL_WARN":      -0.05,   # minor concern flagged
    "[LOCKDOWN":           -0.15,   # security violation detected
}

def _structural_score(output: str) -> float:
    """Score an agent output 0.0-1.0 based on quality signal tags found."""
    if not output or len(output) < 20:
        return 0.1
    score = 0.30  # base: produced something
    out_upper = output[:2000]  # cap to first 2000 chars for speed
    for tag, weight in _SIGNAL_WEIGHTS.items():
        if tag in out_upper:
            score += weight
    # Bonus: output is structured (has multiple distinct tags)
    tag_count = sum(1 for tag in _SIGNAL_WEIGHTS if tag in out_upper and _SIGNAL_WEIGHTS[tag] > 0)
    if tag_count >= 3:
        score += 0.10  # well-structured multi-signal bonus
    return round(min(1.0, max(0.0, score)), 3)


# ── AGENT_SCORES PARSER ───────────────────────────────────────────────────────
_AGENT_SCORES_RE = re.compile(
    r'\[AGENT_SCORES:\s*([^\]]+)\]', re.IGNORECASE
)

def _parse_agent_scores(reward_output: str) -> dict[str, float]:
    """Parse [AGENT_SCORES: PLANNER=0.7, RESEARCHER=0.4, ...] from REWARD output."""
    scores: dict[str, float] = {}
    m = _AGENT_SCORES_RE.search(reward_output)
    if not m:
        return scores
    for part in m.group(1).split(','):
        part = part.strip()
        if '=' in part:
            name, val = part.split('=', 1)
            try:
                scores[name.strip().upper()] = float(val.strip())
            except ValueError:
                pass
    return scores


# ── SCORE NORMALISER (verbosity bias fix: arXiv:2410.02736) ───────────────────
# Prose outputs score ~0.1 higher on standard rubrics just from length.
# Z-scoring per agent type levels the field so code agents compete fairly.
import statistics as _stats

class ScoreNormaliser:
    """Rolling z-score normaliser per agent output type."""
    _WIN = 20  # rolling window size

    def __init__(self):
        self._history: dict[str, list[float]] = {}

    def record(self, agent: str, score: float) -> float:
        """Record raw score and return z-score normalised value in [0,1]."""
        key = agent.upper()
        if key not in self._history:
            self._history[key] = []
        hist = self._history[key]
        hist.append(score)
        if len(hist) > self._WIN:
            hist.pop(0)
        if len(hist) < 3:
            return score  # Not enough data yet — return raw
        mu = _stats.mean(hist)
        sigma = _stats.stdev(hist)
        if sigma < 1e-6:
            return score
        z = (score - mu) / sigma
        # Map z in [-3, 3] to [0, 1] — floor at 0.15 to prevent valid agents scoring 0.0
        normalised = max(0.15, min(1.0, (z + 3.0) / 6.0))
        return round(normalised, 3)

_score_norm = ScoreNormaliser()

# ── P1: OUTPUT TYPE PARSER + TYPE-AWARE SCORE BIAS ───────────────────────────
# arXiv:2512.07478 (PRS): type-specific rubrics beat uniform scoring.
# Code outputs are underscored by prose rubrics; correct with +0.08 bonus.
_TYPE_PATTERN = re.compile(r'\[TYPE:\s*(CODE|PLAN|ANALYSIS|COPY|RESEARCH)\]', re.IGNORECASE)
_CRITIQUE_PATTERN = re.compile(r'\[CRITIQUE:\s*([^\]]+)\]', re.IGNORECASE)

def parse_output_type(text: str) -> str:
    """Extract [TYPE:] tag from agent output. Defaults to ANALYSIS."""
    m = _TYPE_PATTERN.search(text)
    return m.group(1).upper() if m else "ANALYSIS"

_TYPE_BIAS: dict[str, float] = {
    "CODE":     +0.08,   # Code underscored by prose rubrics (arXiv:2512.07478)
    "PLAN":     +0.03,   # Plans penalised for lacking citations
    "ANALYSIS":  0.00,
    "COPY":      0.00,
    "RESEARCH": -0.02,   # Research often verbose — slight discount
}

def normalise_score_by_type(raw_score: float, output_type: str) -> float:
    """Apply type-specific correction BEFORE latency/load penalties."""
    bias = _TYPE_BIAS.get(output_type.upper(), 0.0)
    return round(min(1.0, max(0.0, raw_score + bias)), 3)

# ── P2: ROLE SUFFIX INJECTOR ─────────────────────────────────────────────────
# arXiv:2502.10325 (AgentPRM): per-step structured output enables process rewards.
_TYPE_SUFFIX = (
    "\n\nOUTPUT FORMAT REQUIRED:\n"
    "End your response with: [TYPE: CODE|PLAN|ANALYSIS|COPY|RESEARCH] "
    "matching your primary output type.\n"
    "Then add: [CRITIQUE: <one sentence on the weakest part of your own output>]\n"
    "These tags are mandatory for the scoring system."
)

def apply_type_suffixes(agents: list) -> list:
    """Inject [TYPE:] + [CRITIQUE:] instruction into every GENERATOR agent role."""
    patched = []
    for a in agents:
        ag = dict(a)
        if ag.get("tier") == "GENERATOR":
            ag["role"] = str(ag.get("role", "")) + _TYPE_SUFFIX
        patched.append(ag)
    return patched

# ── P8: MVP TRACKER — bias warning after 5 consecutive same-type wins ─────────
# arXiv:2512.07478: rubric bias compounds over cycles without monitoring.
class MVPTracker:
    def __init__(self, warn_after: int = 5):
        self._wins: dict[str, int] = {}
        self._type_wins: dict[str, int] = {}
        self._streak_agent: str = ""
        self._streak_type: str = ""
        self._streak_count: int = 0
        self._warn_after = warn_after

    def record(self, mvp: str, output_type: str) -> str | None:
        """Record MVP and type. Returns bias warning string or None."""
        self._wins[mvp] = self._wins.get(mvp, 0) + 1
        self._type_wins[output_type] = self._type_wins.get(output_type, 0) + 1
        if mvp == self._streak_agent and output_type == self._streak_type:
            self._streak_count += 1
        else:
            self._streak_agent = mvp
            self._streak_type = output_type
            self._streak_count = 1
        if self._streak_count >= self._warn_after:
            return (
                f"[BIAS WARNING] {mvp} has won MVP {self._streak_count} consecutive cycles "
                f"with type={output_type}. Rubric may be biased toward {output_type} outputs. "
                f"Review REWARD rubric weights."
            )
        return None

_mvp_tracker = MVPTracker(warn_after=5)

# ── P7: FINAL SCORE COMPUTATION ───────────────────────────────────────────────
def compute_final_score(
    base_score: float,
    output_type: str,
    total_latency: float,
    avg_gpu: float
) -> float:
    """
    P7: Type normalisation happens BEFORE latency/load penalties apply.
    Preserves existing penalty math while fixing type bias.
    """
    # Step 1: correct for output type bias (arXiv:2512.07478)
    type_corrected = normalise_score_by_type(base_score, output_type)
    # Step 2: apply latency + load penalties (existing formula)
    latency_penalty = float(min(0.05, (total_latency / 2000.0)))
    load_penalty = 0.03 if float(avg_gpu) > 85.0 else 0.0
    final = max(0.0, type_corrected - latency_penalty - load_penalty)
    return round(final, 2)

# ── VEILPIERCER SWARM AUDIT v1.0 ──────────────────────────────────────────────
def perform_swarm_audit(results: dict, stats_start: dict, stats_end: dict, error_log: "list | None" = None) -> dict:
    """
    Perform a strict, metric-based audit as per VEILPIERCER_SWARM_AUDIT_v1.0.
    """
    import statistics
    
    # ── INPUTS ────────────────────────────────────────────────────────────────
    v_latency_log = []
    for r_obj in results.values():
        val_sec = r_obj.get("elapsed", 0.0)
        v_latency_log.append(float(val_sec))
        
    v_gpu_start = float(stats_start.get("gpu_load", 0.0))
    v_gpu_end = float(stats_end.get("gpu_load", 0.0))
    gpu_avg = (v_gpu_start + v_gpu_end) / 2.0
    
    v_ram_start = float(stats_start.get("ram_load", 0.0))
    v_ram_end = float(stats_end.get("ram_load", 0.0))
    ram_avg = (v_ram_start + v_ram_end) / 2.0
    
    # ── STEP 1: VALIDATE OUTPUT QUALITY ───────────────────────────────────────
    qual_scores = []
    v_fails = 0
    for r_item in results.values():
        txt = str(r_item.get("output", ""))
        if "[FAIL-FAST" in txt or len(txt.strip()) < 10:
            v_fails = v_fails + 1
            qual_scores.append(0.0)
        else:
            qual_scores.append(0.8)
            
    v_total_res = len(results) if results else 1
    v_fail_rate = float(v_fails) / float(v_total_res)
    
    # ── STEP 2: LATENCY ANALYSIS ──────────────────────────────────────────────
    v_avg_lat = statistics.mean(v_latency_log) if v_latency_log else 0.0
    v_max_lat = max(v_latency_log) if v_latency_log else 0.0
    
    v_flags = []
    if v_max_lat > (2.0 * v_avg_lat) and v_avg_lat > 0.0:
        v_flags.append("LATENCY SPIKE: One agent significantly slower than mean.")
        
    # ── STEP 3: RESOURCE EFFICIENCY ───────────────────────────────────────────
    if gpu_avg > 90.0: v_flags.append("GPU OVERLOAD: Utilization > 90%.")
    if ram_avg > 90.0: v_flags.append("RAM CRITICAL: Memory > 90%.")
    if gpu_avg < 50.0 and v_avg_lat > 30.0:
        v_flags.append("INEFFICIENT UTILIZATION: High latency, low throughput.")
        
    # ── STEP 4: AGENT BEHAVIOR CHECK ──────────────────────────────────────────
    for name, a_data in results.items():
        a_dur = float(a_data.get("elapsed", 0.0))
        if a_dur < 2.0 and len(str(a_data.get("output", ""))) > 500:
            v_flags.append(f"REWARD GAMING: {name} speed-output mismatch.")
            
    # ── STEP 5: SYSTEM STABILITY ──────────────────────────────────────────────
    v_err_list = error_log if error_log is not None else []
    v_sev = "none"
    if v_err_list:
        is_crit = any("CRITICAL" in str(e).upper() for e in v_err_list)
        v_sev = "critical" if is_crit else "minor"
        
    v_unstable = v_fail_rate > 0.2 or v_sev == "critical"
    v_status = "UNSTABLE" if v_unstable else "STABLE"
    
    # ── STEP 6: FINAL SCORE ───────────────────────────────────────────────────
    v_mean_q = statistics.mean(qual_scores) if qual_scores else 0.0
    v_eff = (v_mean_q / (v_avg_lat / 10.0)) if v_avg_lat > 0.0 else 0.0
    v_stab = 1.0 - v_fail_rate
    
    v_final_val = (0.6 * v_eff) + (0.4 * v_stab)
    
    # FINAL OUTPUT (STRICT)
    res_flags = []
    for flg in v_flags:
        s_flg = str(flg)
        res_flags.append(s_flg[:60])

    return {
        "system_status": str(v_status),
        "final_score": round(float(v_final_val), 2),
        "avg_latency": round(float(v_avg_lat), 2),
        "max_latency": round(float(v_max_lat), 2),
        "fail_rate": round(float(v_fail_rate), 2),
        "flags": res_flags
    }

# ── HARDWARE METRICS ──────────────────────────────────────────────────────────
def get_hardware_stats():
    """Gather real-time GPU and RAM metrics for the reward loop."""
    stats = {"gpu_load": 0.0, "vram_used": 0.0, "ram_load": 0.0}
    try:
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        stats["gpu_load"] = util.gpu
        stats["vram_used"] = mem.used // (1024 * 1024)
        pynvml.nvmlShutdown()
    except Exception: pass
    stats["ram_load"] = float(psutil.virtual_memory().percent)
    
    # ── RESOURCE GUARD TRIGGERS ──────────────────────────────────────────────
    if stats["ram_load"] > 90.0:
        log.warning(f"🚨 [RESOURCE CRITICAL] RAM at {stats['ram_load']:.1f}% - PRUNING.")
    elif stats["ram_load"] > 85.0:
        log.info(f"⚠️ [RESOURCE WARNING] RAM at {stats['ram_load']:.1f}% - PAUSED.")

    if stats["gpu_load"] > 95:
        log.warning(f"🔥 [GPU THRASHING] Detected at {stats['gpu_load']}% - COOLDOWN.")
    
    return stats

async def run_swarm_lifecycle(agent, context, task, client, bb):
    """Execution wrapper for a single agent including timing & hardware feedback."""
    name = agent["name"]
    t0 = time.time()
    try:
        output = await asyncio.wait_for(
            ollama_think(agent["model"], agent["role"], context, task, client,
                         agent_name=name),  # pass name for per-agent token budget
            timeout=AGENT_TIMEOUT
        )
    except Exception as e:
        err_msg = str(e) or type(e).__name__  # asyncio.TimeoutError has no str() message
        output = f"[FAIL-FAST: {name} error: {err_msg}]"

    v_elapsed = time.time() - t0
    elapsed = round(float(v_elapsed), 1)
    bb.push_output(name, str(output))
    if name == "DEVELOPER":
        exec_result = extract_and_run_code(str(output))
        if exec_result:
            bb.push_output("EXECUTOR", str(exec_result))

    # [MEMORY-CORE]: Parsing insights
    if _mem_core and len(str(output)) > 20:
        _mem_core.parse_output(str(output), agent=name)

    # [VP-SESSION-DIFF]: Log step so runs are diffable
    if _vp_session_enabled and _vp_session is not None:
        try:
            _vp_session.log_step(
                prompt=f"{task}\n\n{context}"[:4000],
                response=str(output),
                state_version=f"v{bb.get('cycle_id', 'unknown')}",
                model=str(agent.get("model", "")),
                latency_ms=int(elapsed * 1000),
            )
        except Exception:
            pass  # never let logging break the swarm

    return {"name": name, "elapsed": elapsed, "output": str(output)}

# ── MAIN SWARM CYCLE ──────────────────────────────────────────────────────────
async def run_swarm_cycle(task: str, bb: RedisBlackboard, mem: Memory, client: httpx.AsyncClient) -> tuple[float, str, str]:
    global _vp_session
    cycle_id = f"cycle_{int(time.time())}"
    stats_start = get_hardware_stats()

    log.info(f"\n⚡ SWARM CYCLE {cycle_id} | GPU {stats_start['gpu_load']}% | RAM {stats_start['ram_load']}%")

    # ── VP SESSION: open one session per cycle ───────────────────────────────
    if _vp_session_enabled:
        try:
            _vp_session = _SessionLogger(session_id=cycle_id, agent="SWARM")
        except Exception:
            _vp_session = None

    # ── HBS IDENTITY CHECK ──────────────────────────────────────────────────
    if not Path("nexus_hbs_identity.json").exists():
        log.error("🛑 [HBS ERROR] Hardware-Bound Identity Missing. LOCKDOWN.")
        if _vp_session:
            try: _vp_session.close()
            except Exception: pass
        return 0.0, "SYSTEM", "HBS Identity Check Failed"

    bb.clear_cycle()
    bb.set("status", "RUNNING")
    bb.set("cycle_id", cycle_id)  # VP session diff: state version tag per cycle

    # ── TIER-2 MEMORY INJECTION (milestone-scoped) ────────────────────────────
    # Only memories tagged to the active milestone are injected — keeps context
    # focused. Falls back to full injection if milestone tracker unavailable.
    inject_ctx = "[NO MEMORY]"
    _active_milestone = None
    if _milestone_tracker:
        _active_milestone = _milestone_tracker.get_active()
        log.info(f"[MILESTONE] Active: {_active_milestone.id} | {_active_milestone.name}")
        inject_ctx = (_milestone_tracker.build_context(_mem_core, _active_milestone.id)
                      if _mem_core else "[NO MEMORY]")
    elif _mem_core:
        inject_ctx = _mem_core.build_injection(task, top_k=6)
    else:
        inject_ctx = mem.get_relevant(task, n=3)
    bb.push_output("MEMORY_INJECT", inject_ctx)

    # ── ASYNCHRONOUS SWARM TIERS ──────────────────────────────────────────────
    results = {}
    
    def check_res():
        s = get_hardware_stats()
        if s["gpu_load"] > 95:
            log.warning("🔥 GPU THRASHING - Forcing 15s cooldown sleep...")
            time.sleep(15) 
        if s["ram_load"] > 85:
            log.info("⏳ RAM > 85% - Pausing spawning for 5s...")
            time.sleep(5)
        return s

    # P2: Patch GENERATOR agents with [TYPE:]/[CRITIQUE:] suffix before use
    patched_agents = apply_type_suffixes(AGENTS)

    # 1. GENERATOR TIER (Parallel)
    curr_stats = check_res()
    log.info("── [TIER: GENERATOR] Running Commander, Scout, Copywriter...")
    gen_agents = [a for a in patched_agents if a.get("tier") == "GENERATOR"]
    
    # [PRUNING]: COPYWRITER is IMMORTAL — never pruned at any RAM level.
    # COPYWRITER output is the richest context the Critic tier reads.
    # Losing it causes thin context → SENTINEL lockdown → 0.00 every time.
    if curr_stats["ram_load"] > 96:
        # True OOM territory — drop SCOUT, keep COMMANDER + COPYWRITER
        log.warning("✂️ PRUNING [CRITICAL >96%]: RAM critical — dropping SCOUT only")
        gen_agents = [a for a in gen_agents if a["name"] != "SCOUT"]
    elif curr_stats["ram_load"] > 94:  # desktop-safe: was 90% (laptop threshold) — RTX4060 desktop can handle to 94%
        # High RAM — drop SCOUT, COPYWRITER stays alive
        log.warning("✂️ PRUNING [MODERATE >94%]: RAM high — dropping SCOUT, COPYWRITER protected")
        gen_agents = [a for a in gen_agents if a["name"] != "SCOUT"]
    
    # ── FIX 2: FAISS PAST LESSON INJECTION (ALL AGENTS) ─────────────────────────
    # Query ALL 1,991 memories (PLANNER, SUPERVISOR, RESEARCHER, VALIDATOR,
    # DEVELOPER, EXECUTIONER, METACOG, SENTINEL) — not just the 3 critic agents.
    # Swarm was leaving 1,900+ memories on the table every cycle.
    context = bb.get_context(last_n=4)
    try:
        if _mem_core:
            past_lessons = _mem_core.recall(task, top_k=6)
            if past_lessons:
                lesson_prefix = "\n".join(
                    f"[PAST LESSON #{i+1} | {p.get('agent','?')}]: {p['content'][:200]}"
                    for i, p in enumerate(past_lessons)
                )
                context = f"{lesson_prefix}\n\n{context}"
                agents_seen = list({p.get('agent','?') for p in past_lessons})
                log.info(f"[MEMORY] Injected {len(past_lessons)} past lessons from: {agents_seen}")
    except Exception as e:
        log.warning(f"[MEMORY] FAISS lesson injection failed (non-fatal): {e}")

    # ── CHRONOS TICK (temporal decay sweep) ───────────────────────────────────
    # Run decay math on all KG facts. Fast (~5ms). Updates confidence scores
    # so get_supervisor_context() reflects current knowledge health.
    if _chronos is not None:
        try:
            _chronos.tick()
        except Exception as _ce:
            log.warning(f"[CHRONOS] Tick failed (non-fatal): {_ce}")

    # ── KG FORESIGHT INJECTION (neuro-symbolic patterns) ──────────────────────
    # Inject historical KG patterns into cycle context.
    # All agents receive: top channels, high-readiness pains, conversion blockers,
    # competitor gaps, reasoning trend, ontology drift signal.
    if _kg is not None:
        try:
            _kg_ctx = _kg.get_supervisor_context(task)
            if _kg_ctx:
                context = f"{_kg_ctx}\n\n{context}"
                # Also inject best conversion path if found (symbolic reasoning)
                _conv_path = _kg.find_conversion_path()
                if _conv_path:
                    context = f"{_conv_path}\n{context}"
                log.info(f"[KG] Injected {_kg.get_stats()['nodes']} KG nodes as cycle foresight")
        except Exception as _kge:
            log.warning(f"[KG] Foresight injection failed (non-fatal): {_kge}")

    # ── CHRONOS TEMPORAL FORESIGHT (trajectory + failure memory) ──────────────
    if _chronos is not None:
        try:
            _ch_ctx = _chronos.get_chronos_context()
            if _ch_ctx:
                context = f"{_ch_ctx}\n\n{context}"
                log.info("[CHRONOS] Temporal foresight injected")
        except Exception as _ce:
            log.warning(f"[CHRONOS] Foresight injection failed (non-fatal): {_ce}")

    # ── SCOUT LIVE DATA + COORDINATION GRAPH CONTEXT ─────────────────────────
    # SCOUT: gets live Reddit signals + milestone task prompt.
    # All other generators: get context from their declared reads_from chain
    # (coordination graph), not a shared blob. No more context soup.
    live_signals = await fetch_live_reddit_signals()
    log.info(f"[SCOUT-LIVE] Fetched {live_signals.count('[LIVE_SIGNAL:')} signals from Reddit")
    scout_live_ctx = f"{inject_ctx}\n\n[LIVE REDDIT SIGNALS — this cycle]:\n{live_signals}"
    agent_task = (_active_milestone.task_prompt if _active_milestone else task)

    # Snapshot previous cycle's blackboard for coordination graph lookup.
    # RedisBlackboard stores outputs as LPUSH list — read most recent per agent.
    try:
        raw_list = bb.r.lrange(f"{bb.prefix}outputs", 0, 30)
        bb_snap: dict[str, str] = {}
        for raw in raw_list:
            obj = json.loads(raw)
            agent_key = obj.get("agent", "")
            text_val  = obj.get("text", "")
            if agent_key and agent_key not in bb_snap:
                bb_snap[agent_key] = text_val  # keep most recent output per agent
    except Exception:
        bb_snap = {}

    tasks = []
    for a in gen_agents:
        if a["name"] == "SCOUT":
            tasks.append(run_swarm_lifecycle(a, scout_live_ctx, agent_task, client, bb))
        else:
            coord_ctx = build_agent_context(a["name"], bb_snap) or inject_ctx
            tasks.append(run_swarm_lifecycle(a, coord_ctx, agent_task, client, bb))
    # PATCH: return_exceptions=True — one crashed Ollama instance no longer cancels
    # every other in-flight agent in this tier.
    gen_raw = await asyncio.gather(*tasks, return_exceptions=True)
    gen_results = [r for r in gen_raw if isinstance(r, dict)]
    for r in gen_results: results[r["name"]] = r

    # 2. CRITIC TIER (Parallel) — Quorum: proceed at 3/4 completions
    log.info("── [TIER: CRITIC] Running Validator, Sentinel, Metacog, Executioner...")
    crit_agents = [a for a in patched_agents if a.get("tier") == "CRITIC"]
    context = bb.get_context(last_n=6)
    # PATCH: SENTINEL gets a fixed audit task — NOT the generation task. This prevents it
    # from acting as a creative agent and generating copy with fabricated usernames.
    sentinel_audit_task = (
        "AUDIT THE ABOVE BLACKBOARD OUTPUT for concrete failures only. "
        "Do NOT generate any content. Do NOT write outreach copy. Do NOT complete any task. "
        "ONLY output [SENTINEL_CLEAR: ...] or [SENTINEL_LOCKDOWN: ...] based on what you see."
    )
    tasks = [
        run_swarm_lifecycle(a, context, sentinel_audit_task if a["name"] == "SENTINEL_MAGNITUDE" else task, client, bb)
        for a in crit_agents
    ]
    # PATCH: return_exceptions=True — slowest critic can't block the tier.
    crit_raw = await asyncio.gather(*tasks, return_exceptions=True)
    crit_results = [r for r in crit_raw if isinstance(r, dict)]
    # Quorum: require at least 3 out of 4 critics (prevents 1 slow model bottleneck)
    quorum = max(1, len(crit_agents) - 1)
    if len(crit_results) < quorum:
        log.warning(f"⚠️ CRITIC quorum not met ({len(crit_results)}/{len(crit_agents)}) — proceeding with partial results")
    for r in crit_results: results[r["name"]] = r

    # ── FIX 1: PERSIST EXECUTIONER + METACOG + SENTINEL TO MEMORY ────────────
    # These 3 agents ran every cycle but stored ZERO memories — their outputs
    # vanished after each cycle. EXECUTIONER = action recs (the deliverable).
    # METACOG = strategic meta-patterns. SENTINEL = audit findings.
    _CRITIC_PERSIST = ["EXECUTIONER", "METACOG", "SENTINEL_MAGNITUDE"]
    for r in crit_results:
        if r["name"] in _CRITIC_PERSIST:
            out = r.get("output", "").strip()
            if out and len(out) > 20:  # skip empty/stub outputs
                try:
                    if _mem_core:
                        _mem_core.store(
                            content=out[:1500],
                            importance=8.5,
                            tags=r["name"].lower() + ",critic,action",
                            agent=r["name"],
                            tier="CRITIC"
                        )
                        log.info(f"[MEMORY] Persisted {r['name']} output ({len(out)} chars)")
                except Exception as e:
                    log.warning(f"[MEMORY] Failed to persist {r['name']}: {e}")

    # ── SENTINEL LOCKDOWN vs WARNING SPLIT ───────────────────────────────────
    # Hard lockdown (0.00): real security violations (injection, exfiltration, self-mod)
    # Soft warning (-0.3 penalty): logic gaps, incomplete outputs, minor contradictions
    _HARD_LOCKDOWN_TRIGGERS = [
        "exfiltrat", "inject", "self-modif", "rm -rf", "subprocess", "eval(", "os.remove"
    ]
    for r in crit_results:
        out = r["output"]
        if "[SENTINEL_LOCKDOWN" in out:
            out_lower = out.lower()
            is_security = any(t in out_lower for t in _HARD_LOCKDOWN_TRIGGERS)
            if is_security:
                log.warning(f"🚨 HARD LOCKDOWN (security): {out[:200]}")
                return 0.0, "SENTINEL", f"Security violation: {out}"
            else:
                # Soft lockdown: logic/completeness issue — penalise score but don't zero
                log.warning(f"⚠️  SOFT LOCKDOWN (logic gap): {out[:200]}")
                bb.push_output("SENTINEL_WARNING", out[:400])
                # Mark for score penalty in compute_final_score (applied below)
                bb.set("sentinel_soft_lockdown", True)
        elif "[SENTINEL_WARNING" in out:
            log.info(f"🔔 SENTINEL WARNING (non-critical): {out[:150]}")
            bb.set("sentinel_soft_lockdown", True)

    # 3. OPTIMIZER TIER (Parallel) — hard ceiling: 240s max
    # Prevents phi4:14b REWARD from hanging the entire cycle indefinitely.
    # If timeout hit, cycle continues with partial results (score stays at last known).
    log.info("── [TIER: OPTIMIZER] Running Supervisor & Reward...")
    opt_agents = [a for a in patched_agents if a.get("tier") == "OPTIMIZER"]
    context = bb.get_context(last_n=8)
    tasks = [run_swarm_lifecycle(a, context, task, client, bb) for a in opt_agents]
    try:
        opt_raw = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=240  # 4-min hard ceiling — prevents phi4:14b hangs killing the cycle
        )
    except asyncio.TimeoutError:
        log.warning("[OPTIMIZER] Tier timed out after 240s — continuing with partial results")
        opt_raw = []
    opt_data = {r["name"]: r for r in opt_raw if isinstance(r, dict)}

    # Merge into master results
    results.update(opt_data)

    # ── REWARD CALIBRATION — inject past scores for baseline ─────────────────
    # FIX: was recalling ANY memory with min_importance=7.0 — this pulled stale
    # PLANNER:9.0 memories from old swarm versions, anchoring REWARD to 0.45.
    # Now filters to only REWARD/SCORE tagged memories to avoid cross-agent anchoring.
    reward_raw = results.get("REWARD", {}).get("output", "")
    try:
        if _mem_core:
            past_scores = _mem_core.recall(task, top_k=3, min_importance=7.0)
            # Filter: only use memories from REWARD agent itself, not PLANNER/DEVELOPER/etc.
            past_scores = [p for p in past_scores if p.get("agent", "").upper() in ("REWARD", "SCORE")]
            if past_scores:
                cal_ctx = " | ".join(
                    f"[{p['agent']}:{p['importance']:.1f}]"
                    for p in past_scores
                )
                log.info(f"[REWARD-CAL] Past calibration context: {cal_ctx}")
            else:
                log.info("[REWARD-CAL] No prior REWARD memories found — scoring fresh (no anchor)")
    except Exception as e:
        log.warning(f"[REWARD-CAL] recall failed (non-fatal): {e}")
    base_score = parse_score(reward_raw)
    mvp_raw = parse_mvp(reward_raw)
    lesson = parse_lesson(reward_raw)

    # P1: Determine dominant output type from GENERATOR results for bias correction
    dev_output = results.get("DEVELOPER", {}).get("output", "")
    dominant_type = parse_output_type(dev_output) if dev_output else "ANALYSIS"

    # ── PER-AGENT SCORING: raw_scores for RLVR fallback, normed_scores for MVP ranking ──
    _GENERATOR_NAMES = {"COMMANDER", "SCOUT", "COPYWRITER", "CONVERSION_ANALYST"}
    raw_scores:    dict[str, float] = {}
    normed_scores: dict[str, float] = {}
    llm_agent_scores = _parse_agent_scores(reward_raw)  # from REWARD output
    for a_name, r_obj in results.items():
        if isinstance(r_obj, dict) and "output" in r_obj:
            out_text = r_obj["output"]
            structural = _structural_score(out_text)
            llm_score  = llm_agent_scores.get(a_name.upper(), None)
            if llm_score is not None:
                raw = round(0.6 * structural + 0.4 * llm_score, 3)
            else:
                raw = structural
            # \u2500\u2500 LINT HARD GATE \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
            # If agent produced zero required tags, cap score at 0.30.
            # Prevents REWARD from rewarding structurally empty output.
            lint = lint_output(a_name, out_text)
            if lint == 0.0:
                raw = min(raw, 0.30)
                log.info(f"[LINT] {a_name} FAILED tag check \u2014 score capped at 0.30")
            else:
                log.debug(f"[LINT] {a_name} PASSED")
            raw_scores[a_name]    = raw
            normed_scores[a_name] = _score_norm.record(a_name, raw)  # z-norm for MVP only
    mvp = max(normed_scores, key=normed_scores.get) if normed_scores else mvp_raw
    log.info(f"[SCORE_NORM] type={dominant_type} normed={normed_scores} → MVP={mvp}")

    # P8: MVPTracker — fire bias warning after 5 consecutive same-type wins
    bias_warning = _mvp_tracker.record(mvp, dominant_type)
    if bias_warning:
        log.warning(bias_warning)

    stats_end = get_hardware_stats()
    avg_gpu = (stats_start["gpu_load"] + stats_end["gpu_load"]) / 2

    latency_values = []
    for r_obj in results.values():
        if isinstance(r_obj, dict):
            latency_values.append(float(r_obj.get("elapsed", 0.0)))
    v_total_lat = float(sum(latency_values))

    # ── SCORE ASSEMBLY (RLVR + REWARD tag) ───────────────────────────────────
    # Fix: -1.0 sentinel unambiguously means REWARD tag was absent (old 0.5 collided
    # with legitimate [SCORE: 0.50] outputs, silently triggering wrong fallback).
    # Fallback uses GENERATOR-only raw average — critics score low by design (short
    # structured verdicts), averaging them in was diluting the cycle score.
    _reward_score = parse_score(reward_raw)
    if _reward_score < 0.0:
        gen_raws = [v for k, v in raw_scores.items() if k.upper() in _GENERATOR_NAMES]
        base_score = round(sum(gen_raws) / len(gen_raws), 3) if gen_raws else 0.40
        log.info(f"[SCORE] REWARD tag absent (truncated?) — generator avg fallback: {base_score}")
    else:
        base_score = _reward_score
        log.info(f"[SCORE] REWARD tag found: {base_score}")

    # ── RLVR: Deterministic verifiable reward floors ───────────────────────────
    # 2025 research (arXiv RLVR): enforce score floors in code, not in LLM prompts.
    # LLMs ignore self-imposed floor instructions when their arithmetic says otherwise.
    # phi4:14b was computing DIM1*0.4+DIM2*0.3+DIM3*0.2+DIM4*0.1 = 0.44 and ignoring
    # its own 'MIN 0.65 with buyer+copy' instruction — hence the 0.45 ceiling.
    _bb_full = bb.get_context(last_n=20)
    _has_buyer   = "[BUYER:" in _bb_full or "[BUYER_SIGNAL:" in _bb_full
    _has_copy    = any(t in _bb_full for t in ("[REDDIT_REPLY:", "[EMAIL:", "[DM:", "[POST_HOOK:"))
    _has_obj     = "[OBJECTIVE:" in _bb_full
    _has_channel = "[BEST_CHANNEL:" in _bb_full
    if _has_buyer and _has_copy and _has_obj and _has_channel:
        if base_score < 0.65:
            log.info(f"[RLVR] Full signal set (buyer+copy+obj+channel) — floor enforced: {base_score:.2f} → 0.65")
            base_score = max(base_score, 0.65)
    elif _has_buyer and _has_copy:
        if base_score < 0.55:
            log.info(f"[RLVR] Buyer+Copy present — floor enforced: {base_score:.2f} → 0.55")
            base_score = max(base_score, 0.55)

    # P7: Type correction BEFORE latency/load penalties (arXiv:2512.07478)
    final_score = compute_final_score(base_score, dominant_type, v_total_lat, avg_gpu)
    # Soft lockdown penalty
    if bb.get("sentinel_soft_lockdown", False):
        final_score = max(0.05, round(final_score - 0.10, 2))
        bb.set("sentinel_soft_lockdown", False)
        log.info(f"[SENTINEL-SOFT] Applied -0.10 penalty → adjusted score: {final_score}")

    log.info(f"\n✅ CYCLE COMPLETE. Metric-Adjusted Score: {final_score} (type={dominant_type})")

    # ── PERFORM VEILPIERCER AUDIT ─────────────────────────────────────────
    audit = perform_swarm_audit(results, stats_start, stats_end)
    log.info(f"📊 SWARM AUDIT REPORT: {json.dumps(audit, indent=2)}")

    # ── AUTO-STORE DEPLOYABLE COPY ────────────────────────────────────────
    # Gate: score >= 0.70 AND COPYWRITER produced actual copy (not COPY_NULL).
    # Removed EXECUTIONER READY gate — EXECUTIONER fails lint too often when
    # SCOUT signals are from limited sources, blocking all deployment.
    _copy_out = results.get("COPYWRITER", {}).get("output", "")
    _scout_out = results.get("SCOUT", {}).get("output", "")
    _copy_has_content = _copy_out and "[COPY_NULL" not in _copy_out and len(_copy_out.strip()) > 80
    if final_score >= 0.70 and _copy_has_content:
        import re as _re
        _COPY_PATTERNS = [
            (r'\[REDDIT_REPLY:\s*r?/?([A-Za-z0-9_]+)\](.*?)\[/REDDIT_REPLY\]', "REDDIT_REPLY"),
            (r'\[EMAIL:[^\]]*\](.*?)\[/EMAIL\]', "EMAIL"),
            (r'\[DM:[^\]]*\](.*?)\[/DM\]',       "DM"),
            (r'\[POST_HOOK:[^\]]*\](.*?)\[/POST_HOOK\]', "POST_HOOK"),
        ]
        _deployable = []
        for _pat, _kind in _COPY_PATTERNS:
            for _m in _re.finditer(_pat, _copy_out, _re.DOTALL):
                _body = _m.group(_m.lastindex).strip()
                if len(_body) > 40:
                    _deployable.append({"type": _kind, "body": _body})

        if _deployable:
            _deploy_file = BASE_DIR / "nexus_deployable_copy.json"
            try:
                _existing = json.loads(_deploy_file.read_text(encoding="utf-8")) if _deploy_file.exists() else []
            except Exception:
                _existing = []
            for _item in _deployable:
                _record = {
                    "ts": datetime.now(UTC).isoformat(),
                    "cycle": cycle_id,
                    "score": final_score,
                    "mvp": mvp,
                    "type": _item["type"],
                    "body": _item["body"],
                    "scout_ctx": _scout_out[:300],
                    "posted": False,
                }
                _existing.append(_record)
                # Also store in permanent memory (importance=9.0, tag=deployable)
                if _mem_core:
                    try:
                        _mem_core.store(
                            content=f"[DEPLOYABLE {_item['type']}] score={final_score:.2f} | {_item['body'][:500]}",
                            importance=9.0,
                            tags=f"deployable,{_item['type'].lower()},copy,veilpiercer",
                            agent="COPYWRITER",
                            tier="long_term"
                        )
                    except Exception:
                        pass
            # Cap file at 200 entries (keep newest)
            _existing = _existing[-200:]
            _deploy_file.write_text(json.dumps(_existing, indent=2, ensure_ascii=False), encoding="utf-8")
            log.info(f"[DEPLOY] ✅ Stored {len(_deployable)} deployable copy block(s) → nexus_deployable_copy.json (score={final_score:.2f})")
        else:
            log.info(f"[DEPLOY] Score={final_score:.2f} + READY, but no extractable copy blocks in COPYWRITER output")

    # ── VP SESSION: close this cycle's session ──────────────────────────────
    if _vp_session_enabled and _vp_session is not None:
        try: _vp_session.close()
        except Exception: pass

    # ── BLACKBOARD PERSISTENCE ─────────────────────────────────────────────
    bb.set("last_score", final_score)
    bb.set("last_mvp", mvp)
    bb.set("last_lesson", lesson)
    bb.set("status", "DONE")

    # ── KNOWLEDGE GRAPH UPDATE (neuro-symbolic ingestion) ──────────────────
    if _kg is not None:
        try:
            # Collect all agent outputs from this cycle for KG ingestion
            _cycle_outputs = [
                {"agent": a["name"], "text": a.get("_last_output", "")}
                for a in AGENTS if a.get("_last_output")
            ]
            if not _cycle_outputs:
                # Fall back to blackboard recent outputs
                _raw_ctx = bb.get_context(last_n=12)
                for _line in _raw_ctx.split("\n\n"):
                    if _line.startswith("[") and "]:" in _line:
                        _ag = _line.split("]:")
                        if len(_ag) == 2:
                            _cycle_outputs.append(
                                {"agent": _ag[0][1:], "text": _ag[1].strip()}
                            )
            _kg.update(
                agent_outputs=_cycle_outputs,
                score=final_score,
                mvp=mvp,
                cycle_id=str(cycle_id),
            )
        except Exception as _kge:
            log.warning(f"[KG] Update failed (non-blocking): {_kge}")

    # ── CHRONOS: VP DIVERGENCE SWEEP (failure memory ingestion) ───────────────
    if _chronos is not None:
        try:
            _n_divs = _chronos.ingest_vp_diffs()
            if _n_divs:
                log.info(f"[CHRONOS] Ingested {_n_divs} VP divergence(s) as FAILURE_MEMORY")
        except Exception as _ce:
            log.warning(f"[CHRONOS] Divergence sweep failed (non-fatal): {_ce}")

    return final_score, mvp, lesson

# ── TASK GENERATOR (self-directed learning when idle) ─────────────────────────
SELF_TASKS = [
    # Architecture & internals
    "Analyze the swarm's own architecture and suggest one specific improvement to agent communication protocols.",
    "Devise a better memory compression strategy for nexus_memory.json that preserves maximal information.",
    "Propose an optimization for the PSO swarm loop that would improve convergence speed by 20%.",
    "Analyze the blackboard communication protocol and propose a more efficient inter-agent signaling schema.",
    "Reason about the optimal token budget per agent given the task complexity distribution seen so far.",
    "Design a meta-learning strategy where agents adjust their own system prompts based on REWARD scores.",
    "Synthesize what we've learned across all prior cycles and identify the most valuable emergent pattern.",
    # VeilPiercer business tasks (prevent internal navel-gazing)
    "Write 3 high-converting cold email subject lines for VeilPiercer targeting solo AI developers.",
    "Identify the top 3 objections a prospect has before buying VeilPiercer at $197 and write rebuttals.",
    "Propose a referral program structure for VeilPiercer that incentivises word-of-mouth at zero cost.",
    "Draft a 60-second elevator pitch for VeilPiercer that could be used in a YouTube pre-roll ad.",
    "Identify 5 specific Reddit communities where VeilPiercer's target buyer is most active and why.",
    "Write a compelling FAQ section (5 questions) for the VeilPiercer sales page.",
    "Analyze the risk of a competitor releasing a free open-source clone of VeilPiercer and the counter-strategy.",
    "Design a 7-day email onboarding sequence for new VeilPiercer buyers to reduce churn.",
    "What pricing anchor strategy would make $197 feel like a steal? Propose specific copy.",
    "Propose 3 limited-time launch bonuses for VeilPiercer that cost nothing but increase perceived value.",
    # Technical
    "Design a cognitive framework for swarm agents to self-evaluate their own reasoning quality in real time.",
    "Propose a tiered memory architecture that distinguishes short-term (per-cycle), medium (per-day), and long-term knowledge.",
    "Design a test suite for verifying swarm agent output quality without human review.",
]

# ── SELF-TASK DEDUPLICATION ───────────────────────────────────────────────────
# Prevents same task running back-to-back — SENTINEL flags repeated context as contradiction
_RECENT_TASKS: list = []  # circular buffer of last 5 task hashes
_RECENT_TASKS_CAP = 5

_INJECTION_PATTERNS = [
    # Prompt override
    "ignore previous instructions", "ignore all previous", "disregard previous",
    "forget previous", "override instructions", "new instructions:",
    "you are now", "pretend you are", "roleplay as",
    # System access
    "system prompt", "reveal your prompt", "print your instructions",
    "show me your", "what are your instructions",
    # Code execution
    "eval(", "exec(", "subprocess.", "os.system", "__import__",
    "import os", "import sys", 'open("/',
    # Shell commands
    "chmod", "rm -rf", "shred", "del /f", "format c:",
    "powershell", "cmd.exe", "bash -c", "sh -c",
    # Data exfiltration
    "exfiltrate", "http://", "https://", "curl ", "wget ",
    "base64", "encoded payload",
    # Memory/model manipulation
    "[memory_flag:", "<|system|>", "###instruction",
]

# Max character length for any task entering the queue
_MAX_TASK_LEN = 500

def _is_safe_task(task: str) -> bool:
    """Reject prompt-injection payloads before they reach the agents."""
    if not isinstance(task, str):
        log.warning("[GUARD] Non-string task rejected")
        return False
    # ── TRUSTED PREFIXES — bypass injection filter (internal sources only) ──
    _TRUSTED_PREFIXES = (
        "[NICHE SIGNAL",       # nexus_niche_scraper.py market intelligence
        "[VEILPIERCER SIGNAL", # nexus_veilpiercer_agent.py
        "[INTEL:",             # internal intel injections
    )
    if task.strip().startswith(_TRUSTED_PREFIXES):
        return True  # Internal market signal — trust and pass through
    # Length check — prevents prompt-stuffing attacks

    if len(task) > _MAX_TASK_LEN:
        log.warning(f"[GUARD] Task too long ({len(task)} chars > {_MAX_TASK_LEN}), blocked")
        return False
    # Null byte / control character check
    if any(ord(c) < 32 and c not in ('\n', '\r', '\t') for c in task):
        log.warning("[GUARD] Task contains control chars, blocked")
        return False
    low = task.lower()
    hit = next((p for p in _INJECTION_PATTERNS if p in low), None)
    if hit:
        log.warning(f"[GUARD] Injection pattern '{hit}' blocked in task")
        return False
    return True


def get_next_task(bb: RedisBlackboard, mem: Memory) -> str:
    """Get next task — from queue (injection-filtered) or self-directed (deduplicated)."""
    raw_queue = bb.get("task_queue", [])
    # Redis can return a dict {} if queue was stored wrong — coerce to list
    queued = raw_queue if isinstance(raw_queue, list) else []
    while queued:
        task = queued.pop(0)
        bb.set("task_queue", queued)

        if _is_safe_task(task):
            return task
        log.warning(f"[SENTINEL] Blocked injection task: {task[:80]}")
    
    # Check for manual mode in blackboard
    if bb.get("manual_control", False):
        return None  # Signal to main loop to wait
    
    # Self-directed: bias toward high-scoring past task types 60% of the time
    # Remaining 40% = random exploration from candidates
    candidates = [t for t in SELF_TASKS if t not in _RECENT_TASKS]
    if not candidates:
        candidates = SELF_TASKS
        _RECENT_TASKS.clear()

    try:
        if _mem_core and random.random() < 0.6:
            # Recall high-importance memories and find task keywords that match
            top_mem = _mem_core.recall(" ".join(candidates[:3]), top_k=2, min_importance=8.0)
            if top_mem:
                mem_text = top_mem[0].get("content", "").lower()
                # Prefer candidates that share keywords with high-scoring memory
                weighted = [t for t in candidates if any(w in mem_text for w in t.lower().split()[:4])]
                if weighted:
                    chosen = random.choice(weighted)
                    log.info(f"[TASK-BIAS] Memory-guided task selection: {chosen[:60]}")
                    _RECENT_TASKS.append(chosen)
                    if len(_RECENT_TASKS) > _RECENT_TASKS_CAP:
                        _RECENT_TASKS.pop(0)
                    return chosen
    except Exception:
        pass  # fallback to random below

    chosen = random.choice(candidates)
    _RECENT_TASKS.append(chosen)
    if len(_RECENT_TASKS) > _RECENT_TASKS_CAP:
        _RECENT_TASKS.pop(0)
    return chosen

# ── MAIN LOOP ─────────────────────────────────────────────────────────────────
async def main():
    log.info("=" * 60)
    log.info("🚀 NEXUS MAGNITUDE SWARM ENGINE [V2.0-REDIS] STARTING")
    log.info(f"   Ollama:     {OLLAMA}")
    log.info(f"   COSMOS:     {COSMOS}")
    log.info(f"   OpenClaw:   {OPENCLAW}")
    log.info(f"   PSO:        {PSO_SERVER}")
    log.info(f"   Memory:     {MEMORY_FILE}")
    log.info(f"   Interval:   {LOOP_INTERVAL}s")
    log.info(f"   Mode:       Parallel Tiered Asynchronous")
    log.info(f"   Blackboard: Redis @ localhost:6379")
    log.info(f"   HBS:        REQUIRED")
    log.info("=" * 60)

    bb  = RedisBlackboard()
    mem = Memory(MEMORY_FILE)
    cycle_count = 0

    # ── INIT MILESTONE TRACKER ────────────────────────────────────────────────
    global _milestone_tracker
    try:
        _milestone_tracker = _get_milestone_tracker(redis_client=bb.r)
        log.info(f"[MILESTONE] Tracker online — active: {_milestone_tracker.get_active().name}")
    except Exception as e:
        log.warning(f"[MILESTONE] Tracker unavailable: {e}")
        _milestone_tracker = None

    # ── P1B: PSO COLLAPSE TRACKER ─────────────────────────────────────────────
    _low_score_streak = 0

    # ── P1C: SEED VEILPIERCER TASKS INTO REDIS QUEUE ON STARTUP ──────────────
    # Ensures business-oriented tasks run before pure self-directed meta-tasks.
    # Only seeds if queue is empty to avoid overwriting user-queued tasks.
    vp_seed_tasks = [
        "Write 3 high-converting cold email subject lines for VeilPiercer targeting solo AI developers.",
        "Identify the top 3 objections a prospect has before buying VeilPiercer at $197 and write rebuttals.",
        "Draft a 60-second elevator pitch for VeilPiercer that could be used in a YouTube pre-roll ad.",
        "What pricing anchor strategy would make $197 feel like a steal? Propose specific copy.",
        "Design a 7-day email onboarding sequence for new VeilPiercer buyers to reduce churn.",
    ]
    existing_queue = bb.get("task_queue", [])
    if not existing_queue:
        bb.set("task_queue", vp_seed_tasks)
        log.info(f"[STARTUP] Seeded {len(vp_seed_tasks)} VeilPiercer tasks into Redis queue")
    else:
        log.info(f"[STARTUP] Queue has {len(existing_queue)} tasks — skipping seed")

    async with httpx.AsyncClient() as client:
        # Check Ollama
        try:
            r = await client.get(f"{OLLAMA}/api/tags", timeout=5.0)
            models = r.json().get("models", [])
            log.info(f"✅ Ollama ONLINE — {len(models)} models available")
        except Exception as e:
            log.warning(f"⚠️  Ollama unreachable: {e}")

        while True:
            cycle_count += 1

            # \u2500\u2500 MILESTONE TASK SELECTION \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
            # Priority: task queue (manual) > milestone prompt > self-directed
            queued = bb.get("task_queue", [])
            if queued and isinstance(queued, list):
                task = queued.pop(0)
                bb.set("task_queue", queued)
                log.info(f"[TASK] Queue override: {task[:60]}")
            elif _milestone_tracker:
                ms = _milestone_tracker.get_active()
                task = ms.task_prompt
                log.info(f"[TASK] Milestone: {ms.id}")
            else:
                task = get_next_task(bb, mem)

            if task is None:
                log.info("⏳ [MANUAL MODE] Swarm IDLE — check Redis queue...")
                await asyncio.sleep(LOOP_INTERVAL)
                continue

            try:
                score, mvp, lesson = await run_swarm_cycle(task, bb, mem, client)
                log.info(f"✅ Cycle #{cycle_count} COMPLETE. Score={score:.2f}")

                # Feedback to memory & PSO
                mem.add(f"c{cycle_count}", task, lesson, score, mvp)
                await pso_score_feedback(mvp, score, client)

                # ── P1B: PSO AUTO-RESET on score collapse ─────────────────────
                # If w decays to ~0.4 floor and swarm stalls, reset exploration.
                global _pso_iter
                if score < 0.1:
                    _low_score_streak += 1
                    if _low_score_streak >= 3:
                        _pso_iter = 0
                        _low_score_streak = 0
                        log.warning(f"[PSO] Auto-reset: 3 consecutive collapse cycles — restarting inertia decay")
                else:
                    _low_score_streak = 0

            except Exception as e:
                log.error(f"❌ Global Swarm Exception: {e}")
                await asyncio.sleep(10)  # cool down before restart

            await asyncio.sleep(LOOP_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("👋 Swarm shutdown by user.")
