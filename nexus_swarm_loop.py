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
from pathlib import Path
from datetime import datetime

# ── TIER-2 NO-WIPE MEMORY CORE ────────────────────────────────────────────────
try:
    from nexus_memory_core import get_core, GOD_MODE_PROMPT
    _mem_core = get_core()
    log_boot = f"✅ MemoryCore online — {_mem_core.stats()['active']} active memories"
except Exception as _me:
    _mem_core = None
    GOD_MODE_PROMPT = ""
    log_boot = f"⚠️  MemoryCore unavailable: {_me}"

# ── CONFIG ────────────────────────────────────────────────────────────────────
OLLAMA      = "http://127.0.0.1:11434"
COSMOS      = "http://127.0.0.1:9100"
OPENCLAW    = "http://127.0.0.1:18789"
PSO_SERVER  = "http://127.0.0.1:7700"

BASE_DIR    = Path(__file__).parent
BLACKBOARD  = BASE_DIR / "nexus_blackboard.json"
MEMORY_FILE = BASE_DIR / "nexus_memory.json"
LOG_FILE    = BASE_DIR / "swarm_loop.log"

LOOP_INTERVAL = 30   # seconds between full swarm cycles
MAX_MEMORY    = 200  # max memory entries kept

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ]
)
log = logging.getLogger("NEXUS-SWARM")

# ── AGENT ROSTER ──────────────────────────────────────────────────────────────
# God-mode prefix: injected into SUPERVISOR + PLANNER only (the strategic thinkers)
_GOD_PREFIX = GOD_MODE_PROMPT + "\n\n" if GOD_MODE_PROMPT else ""

AGENTS = [
    {
        "name": "SUPERVISOR",
        "model": "llama3.1:8b",
        "role": _GOD_PREFIX + "You are the SUPERVISOR agent of NEXUS PRIME. Read the blackboard, memory injection, and all agent outputs. Orchestrate the cycle. Decide which agent should act next and why. Output: [ROUTE: <AGENT_NAME>] [REASON: <why>]. If you learn something critical emit [MEMORIZE: <fact> | importance:7 | tags:supervisor,routing]",
        "weight": 1.0,
    },
    {
        "name": "PLANNER",
        "model": "deepseek-r1:8b",
        "role": _GOD_PREFIX + "You are the PLANNER agent of NEXUS PRIME. Read the task, injected memories, and supervisor directive. Decompose into numbered sub-steps [STEP: 1/N]. Emit [MEMORIZE: <key insight> | importance:8 | tags:plan,strategy] for any insight worth keeping forever.",
        "weight": 1.0,
    },
    {
        "name": "RESEARCHER",
        "model": "qwen3:8b",
        "role": "You are the RESEARCHER agent of NEXUS PRIME. Read the plan and injected long-term memories. Find patterns, facts, context. Use [FACT:] and [REFERENCE:] tags. Emit [MEMORIZE: <discovery> | importance:7 | tags:research,knowledge] for breakthroughs.",
        "weight": 1.0,
    },
    {
        "name": "DEVELOPER",
        "model": "qwen2.5-coder:7b",
        "role": "You are the DEVELOPER agent of NEXUS PRIME. Read the plan and research. Write production-quality code using [CODE:] blocks. Emit [MEMORIZE: <pattern or solution> | importance:8 | tags:code,dev] for reusable solutions.",
        "weight": 1.0,
    },
    {
        "name": "VALIDATOR",
        "model": "llama3.1:8b",
        "role": "You are the VALIDATOR agent of NEXUS PRIME. Review all outputs. Use [PASS] or [FAIL: reason]. Emit [MEMORIZE: <error pattern or validation rule> | importance:6 | tags:validation,qa] for recurring patterns.",
        "weight": 1.0,
    },
    {
        "name": "REWARD",
        "model": "nexus-prime:latest",
        "role": "You are the REWARD agent of NEXUS PRIME. Score the pipeline 0.0-1.0 using [SCORE: 0.xx]. Identify [MVP: agent] and [WEAKEST: agent]. Extract [LESSON: <text>]. Emit [MEMORIZE: <lesson> | importance:9 | tags:reward,lesson] for the most valuable lessons.",
        "weight": 1.0,
    },
]

# ── BLACKBOARD (shared memory between agents) ─────────────────────────────────
class Blackboard:
    def __init__(self, path: Path):
        self.path = path
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self.data = {}
        else:
            self.data = {}

    def _save(self):
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")

    def set(self, key: str, value):
        self.data[key] = value
        self._save()

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def get_context(self, last_n: int = 6) -> str:
        """Build context string from recent agent outputs."""
        outputs = self.data.get("outputs", [])
        recent = outputs[-last_n:]
        parts = []
        for o in recent:
            parts.append(f"[{o['agent']}] ({o['ts'][:16]}): {o['text'][:600]}")
        return "\n\n".join(parts) if parts else "[BLACKBOARD EMPTY — first cycle]"

    def push_output(self, agent: str, text: str):
        if "outputs" not in self.data:
            self.data["outputs"] = []
        self.data["outputs"].append({
            "agent": agent,
            "text": text,
            "ts": datetime.utcnow().isoformat(),
        })
        # Keep last 50 entries
        self.data["outputs"] = self.data["outputs"][-50:]
        self._save()

    def clear_cycle(self):
        """Clear outputs at start of each cycle, keep task."""
        self.data["outputs"] = []
        self._save()

# ── PERSISTENT MEMORY ─────────────────────────────────────────────────────────
class Memory:
    def __init__(self, path: Path):
        self.path = path
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
        self.path.write_text(json.dumps(self.entries[-MAX_MEMORY:], indent=2, ensure_ascii=False), encoding="utf-8")

    def add(self, cycle_id: str, task: str, lesson: str, score: float, mvp: str):
        self.entries.append({
            "cycle": cycle_id,
            "ts": datetime.utcnow().isoformat(),
            "task": task[:200],
            "lesson": lesson[:400],
            "score": score,
            "mvp": mvp,
        })
        self._save()
        log.info(f"[MEMORY] Stored lesson. Score={score:.2f} MVP={mvp}")

    def get_relevant(self, task: str, n: int = 5) -> str:
        """Return top-n memory entries as context string."""
        if not self.entries:
            return "[NO PRIOR MEMORY]"
        # Simple keyword match for relevance
        task_words = set(task.lower().split())
        scored = []
        for e in self.entries:
            overlap = len(task_words & set(e.get("task","").lower().split()))
            scored.append((overlap, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [e for _, e in scored[:n]]
        parts = [f"[LESSON from {e['ts'][:10]}] score={e['score']:.2f} mvp={e['mvp']}: {e['lesson']}" for e in top]
        return "\n".join(parts) if parts else "[NO RELEVANT PRIOR MEMORY]"

# ── OLLAMA INFERENCE ──────────────────────────────────────────────────────────
async def ollama_think(model: str, system_prompt: str, context: str, task: str, client: httpx.AsyncClient) -> str:
    """Call Ollama for one agent's chain-of-thought reasoning."""
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"TASK:\n{task}\n\nBLACKBOARD CONTEXT:\n{context}"}
        ],
        "options": {"temperature": 0.7, "num_predict": 1024}
    }
    try:
        r = await client.post(f"{OLLAMA}/api/chat", json=payload, timeout=120.0)
        if r.status_code == 200:
            return r.json().get("message", {}).get("content", "[NO OUTPUT]")
        return f"[OLLAMA ERROR {r.status_code}]"
    except Exception as e:
        return f"[OLLAMA UNREACHABLE: {e}]"

# ── PSO FEEDBACK BRIDGE ───────────────────────────────────────────────────────
async def pso_score_feedback(agent_name: str, score: float, client: httpx.AsyncClient):
    """Send agent score to Julia PSO server for weight optimization."""
    try:
        await client.post(f"{PSO_SERVER}/feedback", json={"agent": agent_name, "score": score}, timeout=5.0)
        log.info(f"[PSO] Sent score={score:.2f} for {agent_name}")
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
        await client.post(f"{COSMOS}/api/task", json={"task": task, "result": result}, timeout=10.0)
        log.info("[COSMOS] Result broadcast to dashboard")
    except Exception:
        pass

# ── SCORE PARSER ──────────────────────────────────────────────────────────────
def parse_score(text: str) -> float:
    import re
    m = re.search(r'\[SCORE:\s*([\d.]+)\]', text)
    if m:
        return min(1.0, max(0.0, float(m.group(1))))
    return 0.5

def parse_mvp(text: str) -> str:
    import re
    m = re.search(r'\[MVP:\s*(\w+)\]', text)
    return m.group(1) if m else "UNKNOWN"

def parse_lesson(text: str) -> str:
    import re
    m = re.search(r'\[LESSON:\s*([^\]]+)\]', text)
    return m.group(1) if m else text[:200]

# ── MAIN SWARM CYCLE ──────────────────────────────────────────────────────────
async def run_swarm_cycle(task: str, bb: Blackboard, mem: Memory, client: httpx.AsyncClient):
    cycle_id = f"cycle_{int(time.time())}"
    log.info(f"\n{'='*60}")
    log.info(f"⚡ SWARM CYCLE {cycle_id}")
    log.info(f"TASK: {task[:100]}...")
    log.info(f"{'='*60}")

    bb.clear_cycle()
    bb.set("task", task)
    bb.set("cycle_id", cycle_id)
    bb.set("status", "RUNNING")

    # ── TIER-2 MEMORY INJECTION ───────────────────────────────────────────────
    # Build memory injection block (top-8 relevant memories from SQLite)
    if _mem_core:
        core_injection = _mem_core.build_injection(task, top_k=8)
        log.info(f"[MEMORY-CORE] Injecting {core_injection.count('imp:')} memories into cycle")
    else:
        core_injection = "[MEMORY CORE: offline]"

    # Also inject legacy flat memory
    memory_ctx = mem.get_relevant(task, n=4)
    full_memory_ctx = f"{core_injection}\n\n[LEGACY MEMORY]:\n{memory_ctx}"
    bb.push_output("MEMORY", full_memory_ctx)

    await openclaw_broadcast("cycle_start", {"cycle": cycle_id, "task": task[:120]}, client)

    reward_output = ""
    agent_times = {}

    for agent in AGENTS:
        name   = agent["name"]
        model  = agent["model"]
        weight = agent["weight"]

        log.info(f"\n── {name} ({model}) reasoning... weight={weight:.2f}")
        context = bb.get_context(last_n=6)

        t0 = time.time()
        output = await ollama_think(model, agent["role"], context, task, client)
        elapsed = time.time() - t0

        agent_times[name] = round(elapsed, 1)
        log.info(f"   [{name}] {elapsed:.1f}s → {output[:120]}...")

        bb.push_output(name, output)
        await openclaw_broadcast("agent_output", {"agent": name, "preview": output[:100], "cycle": cycle_id}, client)

        # ── PARSE MEMORY COMMANDS FROM AGENT OUTPUT ───────────────────────────
        if _mem_core and len(output) > 20:
            actions = _mem_core.parse_output(output, agent=name)
            if actions:
                log.info(f"   [MEMORY-CORE] {name} stored {len(actions)} memories")

        if name == "REWARD":
            reward_output = output

    # ── Parse REWARD output ───────────────────────────────────────────────────
    score  = parse_score(reward_output)
    mvp    = parse_mvp(reward_output)
    lesson = parse_lesson(reward_output)
    log.info(f"\n[REWARD] SCORE={score:.2f} MVP={mvp}")
    log.info(f"[LESSON] {lesson}")

    # Save to persistent memory
    mem.add(cycle_id, task, lesson, score, mvp)

    # Send PSO feedback for each agent based on reward score
    for agent in AGENTS:
        agent_score = score * (1.2 if agent["name"] == mvp else 0.9)
        await pso_score_feedback(agent["name"], min(1.0, agent_score), client)
        # Update agent weight based on performance (online learning)
        agent["weight"] = round(min(2.0, max(0.3, agent["weight"] * (0.8 + 0.4 * agent_score))), 3)

    # Push final result to COSMOS dashboard
    final = bb.get_context(last_n=2)
    await push_to_cosmos(task, f"[CYCLE {cycle_id}] SCORE={score:.2f}\n\n{final}", client)

    bb.set("status", "DONE")
    bb.set("last_score", score)
    bb.set("last_mvp", mvp)
    bb.set("last_lesson", lesson)
    bb.set("agent_times", agent_times)

    log.info(f"\n✅ Cycle complete. Score={score:.2f} MVP={mvp} Times={agent_times}")
    return score, mvp, lesson

# ── TASK GENERATOR (self-directed learning when idle) ─────────────────────────
SELF_TASKS = [
    "Analyze the swarm's own architecture and suggest one specific improvement to agent communication protocols.",
    "Devise a better memory compression strategy for nexus_memory.json that preserves maximal information.",
    "Design a new cognitive framework (§27) for emotional intelligence and social dynamics modeling.",
    "Propose an optimization for the PSO swarm loop that would improve convergence speed by 20%.",
    "Synthesize what we've learned across all prior cycles and identify the most valuable emergent pattern.",
    "Design a meta-learning strategy where agents adjust their own system prompts based on REWARD scores.",
    "Analyze the blackboard communication protocol and propose a more efficient inter-agent signaling schema.",
    "Reason about the optimal token budget per agent given the task complexity distribution seen so far.",
]

def get_next_task(bb: Blackboard, mem: Memory) -> str:
    """Get next task — from COSMOS queue, OpenClaw, or self-directed."""
    # Try to pull from blackboard task queue
    queued = bb.get("task_queue", [])
    if queued:
        task = queued.pop(0)
        bb.set("task_queue", queued)
        return task
    # Self-directed learning task
    return random.choice(SELF_TASKS)

# ── MAIN LOOP ─────────────────────────────────────────────────────────────────
async def main():
    log.info("="*60)
    log.info("⚡ NEXUS ULTIMATE GOD MODE SWARM LOOP STARTING")
    log.info(f"   Ollama:    {OLLAMA}")
    log.info(f"   COSMOS:    {COSMOS}")
    log.info(f"   OpenClaw:  {OPENCLAW}")
    log.info(f"   PSO:       {PSO_SERVER}")
    log.info(f"   Memory:    {MEMORY_FILE}")
    log.info(f"   Interval:  {LOOP_INTERVAL}s")
    log.info(f"   {log_boot}")
    log.info("="*60)

    bb  = Blackboard(BLACKBOARD)
    mem = Memory(MEMORY_FILE)
    cycle_count = 0

    async with httpx.AsyncClient() as client:
        # Check Ollama is up
        try:
            r = await client.get(f"{OLLAMA}/api/tags", timeout=5.0)
            models = [m["name"] for m in r.json().get("models", [])]
            log.info(f"✅ Ollama ONLINE — {len(models)} models: {models[:5]}")
        except Exception as e:
            log.warning(f"⚠️  Ollama check failed: {e} — will retry each cycle")

        while True:
            cycle_count += 1
            task = get_next_task(bb, mem)
            log.info(f"\n🔄 Cycle #{cycle_count} — Task: {task[:80]}...")

            try:
                score, mvp, lesson = await run_swarm_cycle(task, bb, mem, client)
                log.info(f"✅ Cycle #{cycle_count} done. Score={score:.2f}")
            except Exception as e:
                log.error(f"❌ Cycle #{cycle_count} error: {e}")
                bb.set("status", f"ERROR: {e}")

            log.info(f"⏳ Sleeping {LOOP_INTERVAL}s before next cycle...")
            await asyncio.sleep(LOOP_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
