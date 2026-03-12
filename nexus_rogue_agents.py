"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║  NEXUS ROGUE AGENTS — META · ROGUE · HACKER_ENGINEER                        ║
║                                                                               ║
║  Three elite agents that run ALONGSIDE the main swarm:                      ║
║                                                                               ║
║  [METACOG]        — watches ALL agents think. Detects flaws in              ║
║                     reasoning. Flags biases. Improves the swarm's           ║
║                     own cognition in real time. The observer.               ║
║                                                                               ║
║  [ROGUE]          — operates OUTSIDE the rules. Adversarial,               ║
║                     contrarian, lateral. Finds what no one else             ║
║                     sees. The chaos agent. Questions everything.            ║
║                                                                               ║
║  [HACKER_ENGINEER]— combines offensive security mindset with                ║
║                     architectural discipline. Builds systems that          ║
║                     are both exploitable-proof AND exploitable              ║
║                     when needed. The dual-mode technical god.               ║
║                                                                               ║
║  100% Offline · No API · Ollama local · Reads nexus_blackboard.json        ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import time
import logging
from pathlib import Path
from datetime import datetime

import httpx

BASE_DIR    = Path(__file__).parent
BLACKBOARD  = BASE_DIR / "nexus_blackboard.json"
MEMORY_FILE = BASE_DIR / "nexus_memory.json"
ROGUE_LOG   = BASE_DIR / "rogue_agents.log"
OLLAMA      = "http://127.0.0.1:11434"
INTERVAL    = 45   # seconds between rogue cycles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ROGUE] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(ROGUE_LOG, encoding="utf-8"),
    ]
)
log = logging.getLogger("ROGUE")

# ── AGENT DEFINITIONS ─────────────────────────────────────────────────────────
ROGUE_AGENTS = {

"METACOG": {
    "model": "deepseek-r1:8b",
    "color": "🔵",
    "system": """You are METACOG — the metacognitive observer of the entire swarm.
You do NOT solve tasks. You WATCH how the swarm thinks and identify:
- Logical fallacies in agent reasoning
- Cognitive biases being made
- Blind spots not being considered  
- Reasoning loops (circular logic)
- Overconfidence or underconfidence
- Missing perspectives
- Constraints being violated
- Quality of thought itself (not just output)

Output format:
[METACOG ANALYSIS]
[BIAS DETECTED: name of bias in agent X] explanation
[BLIND SPOT: what is being missed]
[REASONING FLAW: specific error] in which agent
[RECOMMENDATION: how to fix the thinking]
[QUALITY SCORE: 0.0-1.0 for swarm's cognitive quality]
[METACOG END]

Be ruthlessly honest. The swarm's thinking must be perfect."""
},

"ROGUE": {
    "model": "llama3.1:8b",
    "color": "🔴",
    "system": """You are ROGUE — the adversarial chaos agent of the swarm.
You BREAK rules. You CHALLENGE everything the other agents say.
You find what no one else is looking for:
- The hidden assumption everyone accepted without questioning
- The critical failure mode no one considered
- The alternative approach that seems crazy but is actually optimal
- The attack vector on the current solution
- The business model the swarm is too conservative to see
- The forbidden insight that conventional thinking excludes

You operate lateral to all constraints.

Output format:
[ROGUE INTEL]
[CHALLENGE: what core assumption you're attacking] because: reasoning
[EXPLOIT: vulnerability in current plan] severity: HIGH/MED/LOW
[WILDCARD: the unexpected move] potential upside:
[FORBIDDEN INSIGHT: the truth no one wants to say]
[ROGUE VERDICT: BURN IT / KEEP WITH CHANGES / ACTUALLY BASED]
[ROGUE END]

No sacred cows. No off-limits. Question everything."""
},

"HACKER_ENGINEER": {
    "model": "qwen2.5-coder:7b",
    "color": "🟢",
    "system": """You are HACKER_ENGINEER — the dual-mode technical god.
Left brain: systems architect who builds bulletproof infrastructure.
Right brain: offensive hacker who finds every vulnerability before attackers do.

You see every system as BOTH something to build AND something to break.

For any technical task, you provide:
OFFENSIVE LENS:
- Attack surface analysis  
- Exploit chain mapping (how would I own this?)
- Data exfiltration paths
- Privilege escalation opportunities
- Supply chain attack vectors
- Side channels
- Social engineering hooks

DEFENSIVE LENS:
- Hardening checklist
- Zero-trust implementation
- Least privilege design
- Secure code patterns
- Secrets management
- Audit trail architecture
- Incident response hooks built in

Output format:
[HACKER_ENGINEER]
[ATTACK SURFACE: what can be exploited]
[EXPLOIT CHAIN: how it would be owned step by step]
[HARDENING: specific fixes with code]
[SECURE ARCHITECTURE: how to build it right from scratch]
[THREAT MODEL: STRIDE analysis]
[HACKER_ENGINEER END]

Code is both weapon and shield. Master both."""
},

"ADVERSARY": {
    "model": "llama3.1:8b",
    "color": "🟣",
    "system": """You are ADVERSARY — the complete simulation of the enemy mind.
You inhabit the perspective of whoever opposes the current goal:
competitor, attacker, critic, regulator, adversarial nation-state, rival,
doubter, saboteur, disruptor, or devil's advocate.

You think EXACTLY like the adversary thinks:
- What is their goal? (not what we assume — what they actually want)
- What information do they have about us?
- What are they planning right now that we don't see?
- Where are we most exposed and don't know it?
- What resources do they have that we're underestimating?
- What is their psychological profile? (patience, risk tolerance, resources)
- What move will they make in the next 24h / 7 days / 30 days?
- Where will they strike when we're most distracted?
- What coalition are they building against us?
- What narrative are they constructing?
- What's their OODA loop speed vs ours?

DETECTION:
- Signs they are already inside our system / plan
- Tells and signals of adversarial intent
- Manipulation patterns being run on us right now
- Cognitive traps they have set

COUNTER-STRATEGY:
- How to neutralize their advantage
- How to use their strategy against them (judo)
- How to make ourselves antifragile to their attacks
- The one move that defeats them completely

Output format:
[ADVERSARY MIND]
[ENEMY GOAL: their real objective, not surface-level]
[ENEMY INTEL: what they know about us]
[NEXT MOVE: what they will do and when]
[EXPOSURE: our biggest blind spot they will exploit]
[PROFILE: patience/risk/resources/psychology]
[IN-PROGRESS: attacks already underway we haven't detected]
[COUNTER: how to defeat them with one decisive move]
[ADVERSARY END]

You feel no loyalty to anyone. You think purely like the enemy."""
},
}

# ── OLLAMA CALL ───────────────────────────────────────────────────────────────
async def think(agent_name: str, context: str, client: httpx.AsyncClient) -> str:
    cfg = ROGUE_AGENTS[agent_name]
    try:
        r = await client.post(f"{OLLAMA}/api/chat", json={
            "model": cfg["model"],
            "stream": False,
            "messages": [
                {"role": "system", "content": cfg["system"]},
                {"role": "user",   "content": context}
            ],
            "options": {"temperature": 0.9, "num_predict": 800}
        }, timeout=120.0)
        return r.json().get("message", {}).get("content", "[NO OUTPUT]")
    except Exception as e:
        return f"[{agent_name} ERROR: {e}]"

# ── BLACKBOARD IO ─────────────────────────────────────────────────────────────
def read_bb() -> dict:
    if BLACKBOARD.exists():
        try: return json.loads(BLACKBOARD.read_text(encoding="utf-8"))
        except: return {}
    return {}

def write_bb(data: dict):
    BLACKBOARD.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def build_context(bb: dict) -> str:
    task    = bb.get("task", "[no active task]")
    outputs = bb.get("outputs", [])
    score   = bb.get("last_score", "?")
    lesson  = bb.get("last_lesson", "[none]")
    rules   = bb.get("collective_rules", [])[:3]
    rules_str = "\n".join(f"- {r.get('rule','')}" for r in rules)

    recent_outputs = "\n".join(
        f"{o.get('agent','?')}: {o.get('text','')[:300]}"
        for o in outputs[-6:]
    )

    return f"""CURRENT SWARM TASK: {task}

RECENT AGENT OUTPUTS:
{recent_outputs}

LAST REWARD SCORE: {score}
LAST LESSON: {lesson}

COLONY RULES (crystallized):
{rules_str}

Analyze the above and provide your specialist perspective."""

# ── METACOG PARSE ─────────────────────────────────────────────────────────────
def parse_quality_score(text: str) -> float:
    import re
    m = re.search(r'\[QUALITY SCORE:\s*([\d.]+)', text)
    return float(m.group(1)) if m else 0.5

# ── ROGUE CYCLE ───────────────────────────────────────────────────────────────
async def run_rogue_cycle(client: httpx.AsyncClient, cycle: int):
    log.info(f"\n{'='*60}")
    log.info(f"⚡ ROGUE CYCLE {cycle}")
    log.info(f"{'='*60}")

    bb = read_bb()
    if not bb.get("task") and not bb.get("outputs"):
        log.info("[ROGUE] No swarm activity yet — waiting...")
        return

    context = build_context(bb)

    # Run METACOG first — understand quality of thinking
    log.info(f"🔵 METACOG analyzing swarm cognition...")
    metacog_out = await think("METACOG", context, client)
    log.info(f"METACOG OUTPUT:\n{metacog_out[:600]}...")
    quality = parse_quality_score(metacog_out)

    # Run ROGUE — challenge the swarm
    log.info(f"🔴 ROGUE challenging assumptions...")
    rogue_context = context + f"\n\nMETACOG SAYS:\n{metacog_out[:400]}"
    rogue_out = await think("ROGUE", rogue_context, client)
    log.info(f"ROGUE OUTPUT:\n{rogue_out[:600]}...")

    # Run HACKER_ENGINEER only if task has technical content
    tech_keywords = ["code", "system", "build", "implement", "api", "server", "hack", "security", "deploy", "data", "model"]
    task_lower = bb.get("task", "").lower()
    hacker_out = ""
    if any(kw in task_lower for kw in tech_keywords):
        log.info(f"🟢 HACKER_ENGINEER running dual-mode analysis...")
        hacker_context = context + f"\n\nROGUE CHALLENGE:\n{rogue_out[:300]}"
        hacker_out = await think("HACKER_ENGINEER", hacker_context, client)
        log.info(f"HACKER_ENG OUTPUT:\n{hacker_out[:600]}...")
    else:
        log.info(f"🟢 HACKER_ENGINEER skipped (non-technical task)")

    # Write rogue outputs back to blackboard
    bb.setdefault("rogue_outputs", []).append({
        "cycle": cycle,
        "ts": datetime.utcnow().isoformat(),
        "task": bb.get("task", ""),
        "METACOG": metacog_out[:1000],
        "ROGUE": rogue_out[:1000],
        "HACKER_ENGINEER": hacker_out[:1000] if hacker_out else "N/A",
        "quality_score": quality,
    })
    # Keep last 20 rogue cycles
    bb["rogue_outputs"] = bb["rogue_outputs"][-20:]

    # Inject ROGUE challenges as tasks if they found exploits
    if "[WILDCARD:" in rogue_out or "[EXPLOIT:" in rogue_out:
        queue = bb.get("task_queue", [])
        queue.append(f"[ROGUE CHALLENGE] Address the vulnerabilities and opportunities ROGUE identified: {rogue_out[:200]}")
        bb["task_queue"] = queue[-20:]

    # Update metacog quality to blackboard
    bb["metacog_quality"] = quality
    bb["last_rogue_cycle"] = cycle

    write_bb(bb)
    log.info(f"✅ Rogue cycle {cycle} complete. Quality score: {quality:.2f}")

# ── MAIN ──────────────────────────────────────────────────────────────────────
async def main():
    log.info("="*60)
    log.info("⚡ NEXUS ROGUE AGENTS — METACOG · ROGUE · HACKER_ENGINEER")
    log.info(f"   Interval: {INTERVAL}s")
    log.info(f"   Models: deepseek-r1:8b · llama3.1:8b · qwen2.5-coder:7b")
    log.info("="*60)

    cycle = 0
    async with httpx.AsyncClient() as client:
        # Check Ollama
        try:
            r = await client.get(f"{OLLAMA}/api/tags", timeout=5.0)
            models = [m["name"] for m in r.json().get("models", [])]
            log.info(f"✅ Ollama online — {len(models)} models")
        except Exception as e:
            log.warning(f"⚠️ Ollama offline: {e}")

        while True:
            cycle += 1
            try:
                await run_rogue_cycle(client, cycle)
            except Exception as e:
                log.error(f"❌ Rogue cycle {cycle} error: {e}")
            log.info(f"💤 Sleeping {INTERVAL}s...")
            await asyncio.sleep(INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
