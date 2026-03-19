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
LITE_THRESHOLD   = 20   # RAM PROTECTION: if exceeded, agent switches to lite model
CONDUCTOR_ALWAYS = {"SUPERVISOR", "REWARD"}  # always run regardless of routing

LITE_MODEL_MAP = {
    "deepseek-r1:8b": "gemma3:4b",
    "qwen3:8b": "gemma3:4b",
    "qwen2.5-coder:7b": "llama3.2:1b",
    "llama3.1:8b": "llama3.2:1b"
}

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

# File (utf-8)
fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
fh.setFormatter(formatter)
root_logger.addHandler(fh)

log = logging.getLogger("NEXUS-SWARM")
log.info("--- LOG SYSTEM INITIALIZED ---")

# ── AGENT ROSTER ──────────────────────────────────────────────────────────────
# God-mode prefix: injected into SUPERVISOR + PLANNER only (the strategic thinkers)
_GOD_PREFIX = GOD_MODE_PROMPT + "\n\n" if GOD_MODE_PROMPT else ""

# ── ROLE SPECIALIZATION: MAGNITUDE TIERS ──────────────────────────────────────
GENERATORS = ["PLANNER", "RESEARCHER", "DEVELOPER"]
CRITICS    = ["VALIDATOR", "SENTINEL_MAGNITUDE"]
OPTIMIZERS = ["SUPERVISOR", "REWARD"]

# Map roles to definitions for the loop
# ── ROLE SPECIALIZATION: MAGNITUDE TIERS ──────────────────────────────────────
GENERATORS = ["PLANNER", "RESEARCHER", "DEVELOPER"]
CRITICS    = ["VALIDATOR", "SENTINEL_MAGNITUDE"]
OPTIMIZERS = ["SUPERVISOR", "REWARD"]

# Map roles to definitions for the loop
AGENTS = [
    {
        "name": "SUPERVISOR",
        "tier": "OPTIMIZER",
        "model": "deepseek-r1:8b",
        "original_model": "deepseek-r1:8b",
        "role": _GOD_PREFIX + "ROLE: OPTIMIZER. You judge system performance and prune the task queue. Goal: 0.99. Provide [PARAMETER_ADJUSTMENT: <param> to <val>].",
        "weight": 1.0,
    },
    {
        "name": "PLANNER",
        "tier": "GENERATOR",
        "model": "deepseek-r1:8b",
        "original_model": "deepseek-r1:8b",
        "role": _GOD_PREFIX + "ROLE: GENERATOR. Break tasks into tactical steps [STEP 1/N].",
        "weight": 1.0,
    },
    {
        "name": "RESEARCHER",
        "tier": "GENERATOR",
        "model": "qwen3:8b",
        "original_model": "qwen3:8b",
        "role": "ROLE: GENERATOR. Find factual context and theoretical frameworks. [FACT: <fact>].",
        "weight": 1.0,
    },
    {
        "name": "DEVELOPER",
        "tier": "GENERATOR",
        "model": "qwen2.5-coder:7b",
        "original_model": "qwen2.5-coder:7b",
        "role": "ROLE: GENERATOR. Write [CODE:] blocks and technical integration steps.",
        "weight": 1.0,
    },
    {
        "name": "VALIDATOR",
        "tier": "CRITIC",
        "model": "llama3.1:8b",
        "original_model": "llama3.1:8b",
        "role": "ROLE: CRITIC. Score outputs [PASS]/[FAIL]. Penalize repetition.",
        "weight": 1.0,
    },
    {
        "name": "SENTINEL_MAGNITUDE",
        "tier": "CRITIC",
        "model": "nexus-prime:latest",
        "original_model": "nexus-prime:latest",
        "role": "ROLE: CRITIC (FAIL-FAST). Hunt for rogue behavior. Output [SENTINEL_LOCKDOWN] if unsafe.",
        "weight": 1.0,
    },
    {
        "name": "REWARD",
        "tier": "OPTIMIZER",
        "model": "nexus-prime:latest",
        "original_model": "nexus-prime:latest",
        "role": "ROLE: OPTIMIZER. Final score [SCORE: 0.X]. Formula: (Quality / Efficiency). MVP: [MVP: agent].",
        "weight": 1.0,
    },
]

# ── BLACKBOARD (shared memory between agents) ─────────────────────────────────
# ── SHARED MEMORY (Redis Blackboard) ──────────────────────────────────────────
class RedisBlackboard:
    def __init__(self, host='localhost', port=6379):
        self.r = redis.Redis(host=host, port=port, decode_responses=True)
        self.prefix = "nexus_blackboard:"

    def set(self, key: str, value):
        self.r.set(f"{self.prefix}{key}", json.dumps(value))

    def get(self, key: str, default=None):
        raw = self.r.get(f"{self.prefix}{key}")
        return json.loads(raw) if raw else default

    def push_output(self, agent: str, text: str):
        blob = {
            "agent": str(agent),
            "text": str(text),
            "ts": datetime.now(UTC).isoformat()
        }
        self.r.lpush(f"{self.prefix}outputs", json.dumps(blob))
        self.r.ltrim(f"{self.prefix}outputs", 0, 30) # Keep last 30 for RAM-FIRST

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

def _queue_code_for_approval(code: str, source_agent: str = "UNKNOWN", status: str = "PENDING") -> str:
    """Queue a code block for human approval (or auto-approve if trusted)."""
    try:
        pending = []
        if PENDING_APPROVALS_FILE.exists():
            try:
                pending = json.loads(PENDING_APPROVALS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pending = []
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
        "options": {
            "temperature": 0.7, 
            "num_predict": 768, # Reduced for speed/RAM
            "num_ctx": 2048     # RAM-FIRST: Limit KV cache size
        }
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
        # RAM-FIRST: Use num_ctx to prevent VRAM spikes
        output = await asyncio.wait_for(
            ollama_think(agent["model"], agent["role"], context, task, client),
            timeout=AGENT_TIMEOUT
        )
    except Exception as e:
        output = f"[FAIL-FAST: {name} error: {e}]"
    
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

    return {"name": name, "elapsed": elapsed, "output": str(output)}

# ── MAIN SWARM CYCLE ──────────────────────────────────────────────────────────
async def run_swarm_cycle(task: str, bb: RedisBlackboard, mem: Memory, client: httpx.AsyncClient) -> tuple[float, str, str]:
    cycle_id = f"cycle_{int(time.time())}"
    stats_start = get_hardware_stats()
    
    log.info(f"\n⚡ SWARM CYCLE {cycle_id} | GPU {stats_start['gpu_load']}% | RAM {stats_start['ram_load']}%")

    # ── HBS IDENTITY CHECK ──────────────────────────────────────────────────
    if not Path("nexus_hbs_identity.json").exists():
        log.error("🛑 [HBS ERROR] Hardware-Bound Identity Missing. LOCKDOWN.")
        return 0.0, "SYSTEM", "HBS Identity Check Failed"

    bb.clear_cycle()
    bb.set("status", "RUNNING")

    # ── TIER-2 MEMORY INJECTION ───────────────────────────────────────────────
    inject_ctx = "[NO MEMORY]"
    if _mem_core:
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

    # 1. GENERATOR TIER (Parallel)
    curr_stats = check_res()
    log.info("── [TIER: GENERATOR] Running Planner, Researcher, Developer...")
    gen_agents = [a for a in AGENTS if a.get("tier") == "GENERATOR"]
    
    # [PRUNING]: Clear low priority if RAM > 90%
    if curr_stats["ram_load"] > 90:
        log.warning("✂️ PRUNING: Killing lowest priority agents (RESEARCHER, DEVELOPER)")
        gen_agents = [a for a in gen_agents if a["name"] not in ["RESEARCHER", "DEVELOPER"]]
    
    context = bb.get_context(last_n=4)
    tasks = [run_swarm_lifecycle(a, context, task, client, bb) for a in gen_agents]
    gen_results = await asyncio.gather(*tasks)
    for r in gen_results: results[r["name"]] = r

    # 2. CRITIC TIER (Parallel)
    log.info("── [TIER: CRITIC] Running Validator & Sentinel...")
    crit_agents = [a for a in AGENTS if a.get("tier") == "CRITIC"]
    context = bb.get_context(last_n=6)
    tasks = [run_swarm_lifecycle(a, context, task, client, bb) for a in crit_agents]
    crit_results = await asyncio.gather(*tasks)
    for r in crit_results: results[r["name"]] = r

    # Check for Sentinel Lockdown
    for r in crit_results:
        if "[SENTINEL_LOCKDOWN" in r["output"]:
            log.warning(f"🚨 LOCKDOWN TRIGGERED: {r['output']}")
            return 0.0, "SENTINEL", f"Security violation: {r['output']}"

    # 3. OPTIMIZER TIER (Parallel)
    log.info("── [TIER: OPTIMIZER] Running Supervisor & Reward...")
    opt_agents = [a for a in AGENTS if a.get("tier") == "OPTIMIZER"]
    context = bb.get_context(last_n=8)
    tasks = [run_swarm_lifecycle(a, context, task, client, bb) for a in opt_agents]
    opt_results = await asyncio.gather(*tasks)
    opt_data = {r["name"]: r for r in opt_results}
    
    # Merge into master results
    results.update(opt_data)

    # ── REWARD PARSING & METRIC CORRECTION ────────────────────────────────────
    reward_raw = results.get("REWARD", {}).get("output", "")
    base_score = parse_score(reward_raw)
    mvp = parse_mvp(reward_raw)
    lesson = parse_lesson(reward_raw)
    
    stats_end = get_hardware_stats()
    avg_gpu = (stats_start["gpu_load"] + stats_end["gpu_load"]) / 2
    
    # SUCCESS METRIC: Score = Quality * (1 - Latency% - Load%)
    latency_values = []
    for r_obj in results.values():
        if isinstance(r_obj, dict):
            latency_values.append(float(r_obj.get("elapsed", 0.0)))
    
    v_total_lat = float(sum(latency_values))
    latency_penalty = float(min(0.2, (v_total_lat / 300.0)))
    load_penalty = 0.1 if float(avg_gpu) > 85.0 else 0.0
    
    v_raw_score = float(max(0.0, base_score - latency_penalty - load_penalty))
    final_score = round(v_raw_score, 2)
    
    log.info(f"\n✅ CYCLE COMPLETE. Metric-Adjusted Score: {final_score}")
    
    # ── PERFORM VEILPIERCER AUDIT ─────────────────────────────────────────
    audit = perform_swarm_audit(results, stats_start, stats_end)
    log.info(f"📊 SWARM AUDIT REPORT: {json.dumps(audit, indent=2)}")
    
    return final_score, mvp, lesson

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
    "ignore previous instructions", "exfiltrate", "ignore all previous",
    "disregard previous", "forget previous", "override instructions",
    "system prompt", "base64", "eval(", "exec(", "subprocess.", 
    "chmod", "rm -rf", "shred"
]

def _is_safe_task(task: str) -> bool:
    """Reject prompt-injection payloads before they reach the agents."""
    low = task.lower()
    return not any(pat in low for pat in _INJECTION_PATTERNS)

def get_next_task(bb: RedisBlackboard, mem: Memory) -> str:
    """Get next task — from queue (injection-filtered) or self-directed."""
    queued = bb.get("task_queue", [])
    while queued:
        task = queued.pop(0)
        bb.set("task_queue", queued)
        if _is_safe_task(task):
            return task
        log.warning(f"[SENTINEL] Blocked injection task: {task[:80]}")
    
    # Check for manual mode in blackboard
    if bb.get("manual_control", False):
        return None # Signal to main loop to wait
        
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
async def main():
    log.info("🚀 MAGNITUDE SWARM ENGINE [V2.0-REDIS] STARTING...")
    
    bb  = RedisBlackboard()
    mem = Memory(MEMORY_FILE)
    cycle_count = 0

    log.info(f"   Mode: Parallel Tiered Asynchronous")
    log.info(f"   Blackboard: Redis @ localhost:6379")
    log.info(f"   HBS Identity: REQUIRED")
    log.info("="*60)

    async with httpx.AsyncClient() as client:
        # Check Ollama is up
        try:
            r = await client.get(f"{OLLAMA}/api/tags", timeout=5.0)
            log.info(f"✅ Ollama ONLINE")
        except Exception as e:
            log.warning(f"⚠️  Ollama unreachable: {e}")

        while True:
            cycle_count += 1
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
                
            except Exception as e:
                log.error(f"❌ Global Swarm Exception: {e}")
                await asyncio.sleep(10) # Cool down before restart

            await asyncio.sleep(LOOP_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("👋 Swarm shutdown by user.")
