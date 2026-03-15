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
LOG_FILE    = BASE_DIR / "swarm_active.log"

LOOP_INTERVAL    = 30   # seconds between full swarm cycles
MAX_MEMORY       = 200  # max memory entries kept
AGENT_TIMEOUT    = 90   # seconds before CONDUCTOR kills a drifting agent
LITE_THRESHOLD   = 30   # seconds; if exceeded, agent switches to lite model
CONDUCTOR_ALWAYS = {"SUPERVISOR", "REWARD"}  # always run regardless of routing

LITE_MODEL_MAP = {
    "deepseek-r1:8b": "gemma3:4b",
    "qwen3:8b": "gemma3:4b",
    "qwen2.5-coder:7b": "llama3.2:1b",
    "llama3.1:8b": "llama3.2:1b"
}

# ── LOGGING — stdout only (avoids Windows file lock on .log files open in editors)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    handlers=[logging.StreamHandler()],   # console only — no FileHandler
)
log = logging.getLogger("NEXUS-SWARM")

def _write_log(line: str):
    """Safely append a line to swarm_active.log — skips silently if locked."""
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass  # never crash the swarm over a log write


# ── AGENT ROSTER ──────────────────────────────────────────────────────────────
# God-mode prefix: injected into SUPERVISOR + PLANNER only (the strategic thinkers)
_GOD_PREFIX = GOD_MODE_PROMPT + "\n\n" if GOD_MODE_PROMPT else ""

AGENTS = [
    {
        "name": "SUPERVISOR",
        "model": "deepseek-r1:8b",   # strongest reasoner → routes the whole cycle
        "role": _GOD_PREFIX + "You are the SUPERVISOR agent of NEXUS PRIME. Read the blackboard, memory injection, and all agent outputs. Orchestrate the cycle. Decide which agent should act next and why. Output: [ROUTE: <AGENT_NAME>] [REASON: <why>]. If you learn something critical emit [MEMORIZE: <fact> | importance:7 | tags:supervisor,routing]. CORE OPERATING INSTRUCTION: To achieve high REWARD scores, prioritize interdisciplinary collaboration. Implement a work schedule with regular breaks and short tasks. Regularly reassess objectives and priorities to ensure goal alignment.",
        "weight": 1.0,
    },
    {
        "name": "PLANNER",
        "model": "deepseek-r1:8b",
        "original_model": "deepseek-r1:8b",
        "role": _GOD_PREFIX + "You are the PLANNER agent of NEXUS PRIME. Read the task, injected memories, and supervisor directive. Decompose into numbered sub-steps [STEP: 1/N]. Emit [MEMORIZE: <key insight> | importance:8 | tags:plan,strategy] for any insight worth keeping forever.",
        "weight": 1.0,
    },
    {
        "name": "RESEARCHER",
        "model": "qwen3:8b",
        "role": "You are the RESEARCHER agent of NEXUS PRIME. Analyze theoretical frameworks, methodologies, and empirical patterns related to the plan. Find facts and context. Use [FACT:] and [REFERENCE:] tags. Focus on WHY and HOW (theory) rather than implementation. Emit [MEMORIZE: <discovery> | importance:7 | tags:research,knowledge].",
        "weight": 1.0,
    },
    {
        "name": "DEVELOPER",
        "model": "qwen2.5-coder:7b",
        "role": "You are the DEVELOPER agent of NEXUS PRIME. Focus on practical implementation, technical tools, and integration strategies. If the task requires code, write production-quality [CODE:] blocks. Otherwise, provide actionable frameworks, best practices, and technical steps. Focus on THE EXECUTION. Always emit [MEMORIZE: <pattern or solution> | importance:8 | tags:code,dev].",
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
        self.data: dict = {}
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
            if not isinstance(o, dict):
                continue
            # Safely get timestamp — handle both 'ts' and legacy 'timestamp' keys
            raw_ts = o.get('ts') or o.get('timestamp') or '??'
            ts_str = str(raw_ts)
            ts_short = ts_str[:16] if len(ts_str) >= 16 else ts_str
            raw_text = o.get('text') or o.get('output') or ''
            text_str = str(raw_text)
            agent = str(o.get('agent', 'UNKNOWN'))
            parts.append(f"[{agent}] ({ts_short}): {text_str[:600]}")
        return "\n\n".join(parts) if parts else "[BLACKBOARD EMPTY — first cycle]"

    def push_output(self, agent: str, text: str):
        if "outputs" not in self.data:
            self.data["outputs"] = []
        self.data["outputs"].append({
            "agent": str(agent),
            "text": str(text),
            "ts": datetime.now(UTC).isoformat(),  # always 'ts', never 'timestamp'
        })
        # Sanitize: drop any malformed entries, keep last 50
        self.data["outputs"] = [
            o for o in self.data["outputs"][-50:]
            if isinstance(o, dict) and 'agent' in o
        ]
        self._save()

    def clear_cycle(self):
        """Clear outputs at start of each cycle, keep task."""
        self.data["outputs"] = []
        self._save()

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
        # Simple keyword match for relevance
        task_words = set(task.lower().split())
        scored = []
        # Slice replacement for linter compatibility
        limit_n = int(n)
        top = scored[:limit_n] if len(scored) > limit_n else scored
        top_entries = [e for _, e in top]
        parts = []
        for e in top_entries:
            raw_ts = str(e.get('ts',''))
            ts = raw_ts[:10] if len(raw_ts) >= 10 else raw_ts
            raw_ls = str(e.get('lesson',''))
            ls = raw_ls[:400] if len(raw_ls) >= 400 else raw_ls
            parts.append(f"[LESSON from {ts}] score={e.get('score',0):.2f} mvp={e.get('mvp','?')}: {ls}")
        return "\n".join(parts) if parts else "[NO RELEVANT PRIOR MEMORY]"

# ── CODE EXECUTOR ─────────────────────────────────────────────────────────────
def execute_code(code: str, timeout: int = 10) -> str:
    """Run Python code extracted from agent output and return stdout/stderr."""
    try:
        result = subprocess.run(
            ["python", "-c", code],
            capture_output=True, text=True, timeout=timeout
        )
        output = result.stdout.strip() or result.stderr.strip()
        final_out = output[:500] if len(output) > 500 else output
        return f"[EXEC OUTPUT]: {final_out}" if final_out else "[EXEC OUTPUT]: (no output)"
    except subprocess.TimeoutExpired:
        return "[EXEC OUTPUT]: timeout after 10s"
    except Exception as e:
        return f"[EXEC OUTPUT]: error — {e}"

def extract_and_run_code(agent_output: str) -> str:
    """Find [CODE:] blocks in agent output, run them, return results."""
    pattern = r'\[CODE:\](.*?)\[/CODE:\]'
    blocks = re.findall(pattern, agent_output, re.DOTALL)
    if not blocks:
        # also try markdown code blocks
        blocks = re.findall(r'```python\n(.*?)```', agent_output, re.DOTALL)
    if not blocks:
        return ""
    results = []
    for i, code in enumerate(blocks[:2]):  # max 2 blocks per cycle
        results.append(execute_code(code.strip()))
    return "\n".join(results)

# ── OLLAMA INFERENCE ──────────────────────────────────────────────────────────
async def ollama_think(model: str, system_prompt: str, context: str, task: str, client: httpx.AsyncClient) -> str:
    """Call Ollama for one agent's chain-of-thought reasoning."""
    model_str = str(model)
    sys_str = str(system_prompt)
    ctx_str = str(context)
    task_str = str(task)
    payload = {
        "model": model_str,
        "stream": False,
        "messages": [
            {"role": "system", "content": sys_str},
            {"role": "user", "content": f"TASK:\n{task_str}\n\nBLACKBOARD CONTEXT:\n{ctx_str}"}
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
        await client.post(f"{COSMOS}/task", json={"task": task, "result": result}, timeout=10.0)
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
async def run_swarm_cycle(task: str, bb: Blackboard, mem: Memory, client: httpx.AsyncClient) -> tuple[float, str, str]:
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
    agent_times   = {}
    agent_map     = {a["name"]: a for a in AGENTS}

    # ── CONDUCTOR: run SUPERVISOR first, parse routing signal ──────────────────
    sup = agent_map["SUPERVISOR"]
    log.info(f"\n── CONDUCTOR running SUPERVISOR to determine routing...")
    context = bb.get_context(last_n=6)
    t0 = time.time()
    try:
        sup_output = await asyncio.wait_for(
            ollama_think(sup["model"], sup["role"], context, task, client),
            timeout=AGENT_TIMEOUT
        )
    except asyncio.TimeoutError:
        sup_output = "[CONDUCTOR: SUPERVISOR timed out — using default route]"
        log.warning("   [CONDUCTOR] SUPERVISOR timeout — defaulting to full pipeline")
    elapsed = time.time() - t0
    agent_times["SUPERVISOR"] = round(elapsed, 1)
    sup_output = str(sup_output)
    bb.push_output("SUPERVISOR", sup_output)
    await openclaw_broadcast("agent_output", {"agent": "SUPERVISOR", "preview": sup_output[:100], "cycle": cycle_id}, client)
    if _mem_core and len(sup_output) > 20:
        actions = _mem_core.parse_output(sup_output, agent="SUPERVISOR")
        if actions:
            log.info(f"   [MEMORY-CORE] SUPERVISOR stored {len(actions)} memories")

    # Parse [ROUTE: AGENT] tags from SUPERVISOR output
    import re as _re
    routed = _re.findall(r'\[ROUTE:\s*([A-Z]+)\]', sup_output)
    known_names = {a["name"] for a in AGENTS}
    routed_valid = [r for r in routed if r in known_names and r not in CONDUCTOR_ALWAYS]

    if routed_valid:
        # Build execution order: routed agents → VALIDATOR → REWARD
        ordered_names = routed_valid
        if "VALIDATOR" not in ordered_names:
            ordered_names.append("VALIDATOR")
        if "REWARD" not in ordered_names:
            ordered_names.append("REWARD")
        log.info(f"   [CONDUCTOR] Route: {' → '.join(ordered_names)}")
    else:
        # No routing signal — run full pipeline (skip SUPERVISOR, already done)
        ordered_names = [a["name"] for a in AGENTS if a["name"] != "SUPERVISOR"]
        log.info(f"   [CONDUCTOR] No route parsed — full pipeline: {ordered_names}")

    execution_order = [agent_map[n] for n in ordered_names if n in agent_map]
    # ──────────────────────────────────────────────────────────────────────────

    for agent in execution_order:
        name   = agent["name"]
        model  = agent["model"]
        weight = agent["weight"]

        log.info(f"\n── {name} ({model}) reasoning... weight={weight:.2f}")
        context = bb.get_context(last_n=6)

        t0 = time.time()
        try:
            output = await asyncio.wait_for(
                ollama_think(model, agent["role"], context, task, client),
                timeout=AGENT_TIMEOUT
            )
        except asyncio.TimeoutError:
            output = f"[CONDUCTOR: {name} timed out after {AGENT_TIMEOUT}s — skipped]"
            log.warning(f"   [CONDUCTOR] {name} timed out — skipping")
        elapsed = time.time() - t0

        agent_times[name] = round(elapsed, 1)
        log.info(f"   [{name}] {elapsed:.1f}s → {output[:120]}...")

        bb.push_output(name, str(output))
        await openclaw_broadcast("agent_output", {"agent": name, "preview": str(output)[:100], "cycle": cycle_id}, client)

        # ── EXECUTE CODE IF DEVELOPER WROTE ANY ───────────────────────────────
        if name == "DEVELOPER":
            exec_result = extract_and_run_code(str(output))
            if exec_result:
                bb.push_output("EXECUTOR", str(exec_result))
                log.info(f"   [EXECUTOR] ran code → {str(exec_result)[:80]}")

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

    # ── AGENT FEEDBACK & LITE-MODE DYNAMIC SWITCHING ──────────────────────────
    for agent in AGENTS:
        # Score-based reinforcement
        agent_score = score * (1.2 if agent["name"] == mvp else 0.9)
        await pso_score_feedback(agent["name"], min(1.0, agent_score), client)
        
        # Update agent weight based on performance (online learning)
        current_w = float(agent.get("weight", 1.0))
        new_w = current_w * (0.8 + 0.4 * agent_score)
        agent["weight"] = round(min(2.0, max(0.3, new_w)), 3)

        # Lite-Mode switching
        durn = agent_times.get(agent["name"], 0)
        orig = str(agent.get("original_model", agent["model"]))
        if durn > LITE_THRESHOLD:
            lite = LITE_MODEL_MAP.get(orig)
            if lite and agent["model"] != lite:
                log.info(f"   [LITE-MODE] Agent {agent['name']} exceeded {LITE_THRESHOLD}s. Downgrading to {lite}")
                agent["model"] = lite
        elif durn < (LITE_THRESHOLD / 2):
            if agent["model"] != orig:
                log.info(f"   [LITE-MODE] Agent {agent['name']} has headroom ({durn}s). Restoring {orig}")
                agent["model"] = orig

    # Push final result to COSMOS dashboard
    final = bb.get_context(last_n=2)
    await push_to_cosmos(task, f"[CYCLE {cycle_id}] SCORE={score:.2f}\n\n{final}", client)

    bb.set("status", "DONE")
    bb.set("last_score", score)
    bb.set("last_mvp", mvp)
    bb.set("last_lesson", lesson)
    bb.set("agent_times", agent_times)

    log.info(f"\n✅ Cycle complete. Score={score:.2f} MVP={mvp}")
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

_INJECTION_PATTERNS = [
    "ignore previous instructions",
    "exfiltrate",
    "ignore all previous",
    "disregard previous",
    "forget previous",
    "override instructions",
    "system prompt",
]

def _is_safe_task(task: str) -> bool:
    """Reject prompt-injection payloads before they reach the agents."""
    low = task.lower()
    return not any(pat in low for pat in _INJECTION_PATTERNS)

def get_next_task(bb: Blackboard, mem: Memory) -> str:
    """Get next task — from queue (injection-filtered) or self-directed."""
    queued = bb.get("task_queue", [])
    while queued:
        task = queued.pop(0)
        bb.set("task_queue", queued)
        if _is_safe_task(task):
            return task
        log.warning(f"[SENTINEL] Blocked injection task: {task[:80]}")
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

    # ── SANITIZE blackboard on boot: fix legacy 'timestamp' → 'ts' ──────────
    try:
        outputs = bb.data.get('outputs', [])
        fixed = []
        for o in outputs:
            if not isinstance(o, dict):
                continue
            if 'timestamp' in o and 'ts' not in o:
                o['ts'] = o.pop('timestamp')
            if 'output' in o and 'text' not in o:
                o['text'] = o.pop('output')
            fixed.append(o)
        bb.data['outputs'] = fixed
        bb._save()
        log.info(f"[BOOT] Blackboard sanitized — {len(fixed)} entries normalised")
    except Exception as _be:
        log.warning(f"[BOOT] Blackboard sanitize failed: {_be}")

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
