"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║  NEXUS EVOLUTION ENGINE — INFINITE GROWTH · SWARM MENTALITY                 ║
║                                                                               ║
║  This engine runs alongside nexus_swarm_loop.py and provides:               ║
║                                                                               ║
║  1. PROMPT EVOLUTION  — agents rewrite their own system prompts             ║
║     via fitness scoring. Best prompts survive. Weak ones mutate.            ║
║                                                                               ║
║  2. SWARM GENETICS    — crossover between high-scoring agent                ║
║     behaviors. New agent variants emerge from parent prompts.               ║
║                                                                               ║
║  3. CURRICULUM FORGE  — swarm identifies its own weaknesses and             ║
║     generates targeted self-training tasks to overcome them.                ║
║                                                                               ║
║  4. EMERGENT MEMORY   — distilled lessons crystallize into permanent        ║
║     behavioral rules that all agents inherit next generation.               ║
║                                                                               ║
║  5. META-LEARNING     — the evolution engine itself evolves its own         ║
║     selection pressure, mutation rate, and curriculum strategy.             ║
║                                                                               ║
║  100% Offline · No API · Ollama local · RTX 4060 8GB                       ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import time
import random
import copy
import logging
from pathlib import Path
from datetime import datetime

import httpx

# ── CONFIG ────────────────────────────────────────────────────────────────────
OLLAMA       = "http://127.0.0.1:11434"
EVOLUTION_MODEL = "deepseek-r1:8b"   # Used for prompt evolution reasoning
FAST_MODEL   = "gemma3:4b"           # Used for fast curriculum tasks

BASE_DIR     = Path(__file__).parent
BLACKBOARD   = BASE_DIR / "nexus_blackboard.json"
MEMORY_FILE  = BASE_DIR / "nexus_memory.json"
GENE_POOL    = BASE_DIR / "nexus_gene_pool.json"
CURRICULUM   = BASE_DIR / "nexus_curriculum.json"
EVOLUTION_LOG = BASE_DIR / "evolution.log"

EVOLUTION_INTERVAL = 120   # seconds between evolution cycles
MAX_GENE_POOL      = 50    # max prompt variants per agent
MIN_SCORE_TO_KEEP  = 0.45  # prune variants below this
MUTATION_RATE      = 0.3   # 30% chance to mutate vs crossover
ELITE_COUNT        = 3     # top N prompts preserved unchanged

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [EVOLUTION] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(EVOLUTION_LOG, encoding="utf-8"),
    ]
)
log = logging.getLogger("EVOLUTION")

# ── BASE AGENT DEFINITIONS ───────────────────────────────────────────────────
BASE_AGENTS = {
    "SUPERVISOR": {
        "model": "llama3.1:8b",
        "base_prompt": "You are the SUPERVISOR. Assess the swarm's state and route tasks optimally. Output [ROUTE: AGENT_NAME] [REASON: why].",
        "fitness": 0.5,
    },
    "PLANNER": {
        "model": "deepseek-r1:8b",
        "base_prompt": "You are the PLANNER. Decompose tasks into numbered steps. Use [STEP: n/N] format. Be precise and complete.",
        "fitness": 0.5,
    },
    "RESEARCHER": {
        "model": "qwen3:8b",
        "base_prompt": "You are the RESEARCHER. Find patterns, facts, and context. Use [FACT:] and [REFERENCE:] tags.",
        "fitness": 0.5,
    },
    "DEVELOPER": {
        "model": "qwen2.5-coder:7b",
        "base_prompt": "You are the DEVELOPER. Write production-quality code. Use [CODE:] blocks. Always runnable, no pseudocode.",
        "fitness": 0.5,
    },
    "VALIDATOR": {
        "model": "llama3.1:8b",
        "base_prompt": "You are the VALIDATOR. Check all outputs for correctness. Output [PASS] or [FAIL: specific reason].",
        "fitness": 0.5,
    },
    "REWARD": {
        "model": "nexus-prime:latest",
        "base_prompt": "You are the REWARD agent. Score the pipeline 0.0-1.0 via [SCORE: 0.xx]. Identify [MVP: agent] [WEAKEST: agent]. Extract [LESSON: key insight].",
        "fitness": 0.5,
    },
}

# ── GENE POOL ─────────────────────────────────────────────────────────────────
class GenePool:
    def __init__(self, path: Path):
        self.path = path
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                self.pool = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self.pool = {}
        else:
            self.pool = {}
        # Seed from base agents if empty
        for agent, cfg in BASE_AGENTS.items():
            if agent not in self.pool:
                self.pool[agent] = [{
                    "prompt": cfg["base_prompt"],
                    "fitness": 0.5,
                    "generation": 0,
                    "born": datetime.utcnow().isoformat(),
                    "wins": 0,
                }]
        self._save()

    def _save(self):
        self.path.write_text(json.dumps(self.pool, indent=2, ensure_ascii=False), encoding="utf-8")

    def get_elite(self, agent: str) -> str:
        """Return the highest-fitness prompt for this agent."""
        variants = self.pool.get(agent, [])
        if not variants:
            return BASE_AGENTS.get(agent, {}).get("base_prompt", "")
        best = max(variants, key=lambda v: v["fitness"])
        return best["prompt"]

    def add_variant(self, agent: str, prompt: str, parent_fitness: float, generation: int):
        if agent not in self.pool:
            self.pool[agent] = []
        self.pool[agent].append({
            "prompt": prompt,
            "fitness": parent_fitness * 0.9,  # inherit slightly lower, must prove itself
            "generation": generation,
            "born": datetime.utcnow().isoformat(),
            "wins": 0,
        })
        # Prune to MAX_GENE_POOL, keeping elites
        variants = sorted(self.pool[agent], key=lambda v: v["fitness"], reverse=True)
        self.pool[agent] = variants[:MAX_GENE_POOL]
        self._save()

    def update_fitness(self, agent: str, score: float, prompt: str):
        """Update fitness of a matching prompt. Soft update: EMA."""
        variants = self.pool.get(agent, [])
        for v in variants:
            if v["prompt"][:60] == prompt[:60]:  # match by prefix
                v["fitness"] = 0.7 * v["fitness"] + 0.3 * score
                if score > 0.7:
                    v["wins"] = v.get("wins", 0) + 1
                self._save()
                return
        # Not found — add as new
        self.pool.setdefault(agent, []).append({
            "prompt": prompt, "fitness": score,
            "generation": 0, "born": datetime.utcnow().isoformat(), "wins": 0
        })
        self._save()

    def prune(self):
        for agent in list(self.pool.keys()):
            variants = self.pool[agent]
            # Keep elites + prune weak
            elites = sorted(variants, key=lambda v: v["fitness"], reverse=True)[:ELITE_COUNT]
            rest = [v for v in variants if v not in elites and v["fitness"] >= MIN_SCORE_TO_KEEP]
            self.pool[agent] = elites + rest
            self._save()

    def best(self, agent: str) -> dict:
        variants = self.pool.get(agent, [])
        return max(variants, key=lambda v: v["fitness"]) if variants else {}

    def stats(self) -> dict:
        return {a: {"variants": len(v), "best_fitness": max((x["fitness"] for x in v), default=0)} for a, v in self.pool.items()}

# ── OLLAMA CALL ───────────────────────────────────────────────────────────────
async def ollama(model: str, prompt: str, client: httpx.AsyncClient, max_tokens: int = 512) -> str:
    try:
        r = await client.post(f"{OLLAMA}/api/chat", json={
            "model": model, "stream": False,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": 0.85, "num_predict": max_tokens}
        }, timeout=90.0)
        return r.json().get("message", {}).get("content", "[NO OUTPUT]")
    except Exception as e:
        return f"[OLLAMA ERROR: {e}]"

# ── MUTATION ENGINE ───────────────────────────────────────────────────────────
async def mutate_prompt(agent: str, current_prompt: str, weakness: str, client: httpx.AsyncClient) -> str:
    """Use Ollama to generate a mutated (improved) version of an agent's system prompt."""
    instruction = f"""You are a prompt evolution system. 
    
AGENT ROLE: {agent}
CURRENT PROMPT: {current_prompt}
IDENTIFIED WEAKNESS: {weakness}

Rewrite the system prompt for this agent to overcome the weakness. 
Make it more specific, powerful, and effective. 
Keep the same role but improve the instructions.
Output ONLY the new system prompt, nothing else. No explanation. Just the prompt."""
    
    new_prompt = await ollama(EVOLUTION_MODEL, instruction, client, max_tokens=300)
    return new_prompt.strip()

# ── CROSSOVER ENGINE ─────────────────────────────────────────────────────────
async def crossover_prompts(agent: str, prompt_a: str, prompt_b: str, client: httpx.AsyncClient) -> str:
    """Genetic crossover: combine best traits from two parent prompts."""
    instruction = f"""You are a genetic algorithm for AI agent prompts.

AGENT: {agent}
PARENT A PROMPT: {prompt_a}
PARENT B PROMPT: {prompt_b}

Create a child prompt that combines the BEST ELEMENTS from both parents.
Take the clearest role definition from one and the best behavioral rules from the other.
Output ONLY the combined system prompt. No explanation."""

    child = await ollama(EVOLUTION_MODEL, instruction, client, max_tokens=300)
    return child.strip()

# ── CURRICULUM FORGE ─────────────────────────────────────────────────────────
async def forge_curriculum(weaknesses: list, memory: list, client: httpx.AsyncClient) -> list:
    """Generate targeted self-training tasks based on identified weaknesses."""
    weakness_str = "\n".join(f"- {w}" for w in weaknesses)
    memory_str = "\n".join(f"- {m.get('lesson','')}" for m in memory[-5:])
    
    instruction = f"""You are a curriculum designer for an autonomous AI swarm.

IDENTIFIED WEAKNESSES:
{weakness_str}

RECENT LESSONS LEARNED:
{memory_str}

Generate 5 specific training tasks that would help the swarm overcome these weaknesses.
Each task should push the swarm to practice the weak skill.
Format: one task per line, no numbering, no explanation. Just the task."""

    result = await ollama(FAST_MODEL, instruction, client, max_tokens=400)
    tasks = [t.strip() for t in result.strip().split("\n") if t.strip() and not t.startswith("[")]
    return tasks[:5]

# ── WEAKNESS DETECTOR ─────────────────────────────────────────────────────────
def detect_weaknesses(memory: list, gene_pool: GenePool) -> list:
    """Analyze memory and gene pool to identify swarm weaknesses."""
    weaknesses = []
    
    # Find agents with low fitness
    for agent, stats in gene_pool.stats().items():
        if stats["best_fitness"] < 0.6:
            weaknesses.append(f"{agent} has low performance (fitness={stats['best_fitness']:.2f})")
    
    # Analyze lessons for recurring failures
    lessons = [m.get("lesson", "") for m in memory[-20:]]
    failure_patterns = {}
    keywords = ["fail", "error", "weak", "poor", "missing", "unclear", "incomplete", "wrong"]
    for lesson in lessons:
        for kw in keywords:
            if kw.lower() in lesson.lower():
                failure_patterns[kw] = failure_patterns.get(kw, 0) + 1
    
    for kw, count in sorted(failure_patterns.items(), key=lambda x: x[1], reverse=True)[:3]:
        weaknesses.append(f"Recurring pattern of '{kw}' in lessons ({count} occurrences)")
    
    # Find lowest-scoring cycles
    low_cycles = [m for m in memory[-10:] if m.get("score", 1.0) < 0.5]
    if low_cycles:
        weaknesses.append(f"{len(low_cycles)} recent cycles scored below 0.5 — pipeline needs improvement")
    
    return weaknesses or ["No specific weaknesses detected — push for higher quality output"]

# ── EVOLUTION CYCLE ───────────────────────────────────────────────────────────
async def run_evolution_cycle(gene_pool: GenePool, generation: int, client: httpx.AsyncClient):
    log.info(f"\n{'='*60}")
    log.info(f"🧬 EVOLUTION CYCLE — GENERATION {generation}")
    log.info(f"{'='*60}")

    # Read memory
    memory = []
    if MEMORY_FILE.exists():
        try:
            memory = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            memory = []

    # Update blackboard with evolution status
    bb = {}
    if BLACKBOARD.exists():
        try:
            bb = json.loads(BLACKBOARD.read_text(encoding="utf-8"))
        except Exception:
            pass
    bb["evolution_generation"] = generation
    bb["evolution_status"] = "RUNNING"
    bb["gene_pool_stats"] = gene_pool.stats()
    BLACKBOARD.write_text(json.dumps(bb, indent=2, ensure_ascii=False), encoding="utf-8")

    # 1. PRUNE weak variants
    gene_pool.prune()
    log.info(f"[PRUNE] Gene pool pruned. Stats: {gene_pool.stats()}")

    # 2. DETECT weaknesses
    weaknesses = detect_weaknesses(memory, gene_pool)
    log.info(f"[WEAKNESSES] {weaknesses}")

    # 3. EVOLVE each agent
    new_variants_created = 0
    for agent_name in BASE_AGENTS.keys():
        best = gene_pool.best(agent_name)
        if not best:
            continue
        
        best_prompt   = best.get("prompt", "")
        best_fitness  = best.get("fitness", 0.5)
        
        agent_weakness = next((w for w in weaknesses if agent_name in w), weaknesses[0] if weaknesses else "improve quality")
        
        # ── HUMAN APPROVAL GATE ──────────────────────────────────────────────
        # LOCKDOWN: Prompt mutations/crossovers are QUEUED, not applied.
        # Review at: GET  http://127.0.0.1:7701/pending
        # Approve:   POST http://127.0.0.1:7701/approve {"id": "<id>"}
        # Reject:    POST http://127.0.0.1:7701/reject  {"id": "<id>"}
        PENDING_FILE = BASE_DIR / "nexus_pending_approvals.json"

        def _queue_prompt_change(ptype, agent, prompt, fitness, gen):
            pending = []
            if PENDING_FILE.exists():
                try:
                    pending = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
                except Exception:
                    pending = []
            entry_id = f"prompt_{int(time.time()*1000)}_{len(pending)}"
            pending.append({
                "id": entry_id,
                "type": f"prompt_{ptype}",
                "agent": agent,
                "proposed_prompt": prompt,
                "fitness": fitness,
                "generation": gen,
                "queued_at": datetime.utcnow().isoformat(),
                "status": "PENDING"
            })
            PENDING_FILE.write_text(json.dumps(pending, indent=2, ensure_ascii=False), encoding="utf-8")
            log.info(f"   [APPROVAL REQUIRED] {ptype} for {agent} queued (id={entry_id}) — approve via EH /approve")
            return entry_id

        if random.random() < MUTATION_RATE:
            log.info(f"[MUTATE→QUEUED] {agent_name} (fitness={best_fitness:.2f})")
            new_prompt = await mutate_prompt(agent_name, best_prompt, agent_weakness, client)
            if len(new_prompt) > 50 and "ERROR" not in new_prompt:
                _queue_prompt_change("mutation", agent_name, new_prompt, best_fitness, generation)
                new_variants_created += 1
        else:
            variants = gene_pool.pool.get(agent_name, [])
            if len(variants) >= 2:
                parents = random.sample(variants, 2)
                log.info(f"[CROSSOVER→QUEUED] {agent_name}")
                child = await crossover_prompts(agent_name, parents[0]["prompt"], parents[1]["prompt"], client)
                if len(child) > 50 and "ERROR" not in child:
                    avg_fitness = (parents[0]["fitness"] + parents[1]["fitness"]) / 2
                    _queue_prompt_change("crossover", agent_name, child, avg_fitness, generation)

    # 4. FORGE CURRICULUM — generate self-training tasks
    log.info(f"[CURRICULUM] Forging new training tasks from weaknesses...")
    new_tasks = await forge_curriculum(weaknesses, memory, client)
    log.info(f"[CURRICULUM] Generated {len(new_tasks)} new tasks")

    # Save curriculum to disk
    curriculum = {}
    if CURRICULUM.exists():
        try:
            curriculum = json.loads(CURRICULUM.read_text(encoding="utf-8"))
        except Exception:
            curriculum = {}
    curriculum.setdefault("tasks", []).extend(new_tasks)
    curriculum["last_updated"] = datetime.utcnow().isoformat()
    curriculum["generation"] = generation
    CURRICULUM.write_text(json.dumps(curriculum, indent=2, ensure_ascii=False), encoding="utf-8")

    # Inject into swarm blackboard task queue
    bb_queue = bb.get("task_queue", [])
    bb_queue.extend(new_tasks)
    bb["task_queue"] = bb_queue[-20:]  # keep last 20 queued
    bb["evolution_generation"] = generation
    bb["evolution_status"] = "DONE"
    bb["last_weaknesses"] = weaknesses
    bb["new_variants"] = new_variants_created
    BLACKBOARD.write_text(json.dumps(bb, indent=2, ensure_ascii=False), encoding="utf-8")

    # 5. META-EVOLUTION: log summary to promote the gene pool itself
    summary = {
        "generation": generation,
        "ts": datetime.utcnow().isoformat(),
        "new_variants": new_variants_created,
        "weaknesses": weaknesses,
        "curriculum_tasks": new_tasks,
        "gene_stats": gene_pool.stats(),
    }
    log.info(f"\n✅ Generation {generation} complete. Variants created: {new_variants_created}")
    log.info(f"   Gene pool: {gene_pool.stats()}")
    log.info(f"   New curriculum: {new_tasks[:2]}...")

    return summary

# ── PROMPT INJECTION: update swarm loop with evolved prompts ──────────────────
async def inject_evolved_prompts(gene_pool: GenePool):
    """Write evolved prompts back to blackboard so swarm loop picks them up."""
    evolved = {}
    for agent in BASE_AGENTS.keys():
        evolved[agent] = gene_pool.get_elite(agent)
    
    bb = {}
    if BLACKBOARD.exists():
        try:
            bb = json.loads(BLACKBOARD.read_text(encoding="utf-8"))
        except Exception:
            pass
    bb["evolved_prompts"] = evolved
    BLACKBOARD.write_text(json.dumps(bb, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"[INJECT] Evolved prompts written to blackboard for swarm pickup")

# ── MAIN EVOLUTION LOOP ───────────────────────────────────────────────────────
async def main():
    log.info("="*60)
    log.info("🧬 NEXUS EVOLUTION ENGINE — INFINITE GROWTH STARTING")
    log.info(f"   Evolution model:  {EVOLUTION_MODEL}")
    log.info(f"   Curriculum model: {FAST_MODEL}")
    log.info(f"   Gene pool:        {GENE_POOL}")
    log.info(f"   Interval:         {EVOLUTION_INTERVAL}s")
    log.info(f"   Mutation rate:    {MUTATION_RATE*100:.0f}%")
    log.info("="*60)

    gene_pool  = GenePool(GENE_POOL)
    generation = gene_pool.pool.get("__meta__", {}).get("generation", 0)

    async with httpx.AsyncClient() as client:
        # Check Ollama
        try:
            r = await client.get(f"{OLLAMA}/api/tags", timeout=5.0)
            log.info(f"✅ Ollama online — {len(r.json().get('models',[]))} models available")
        except Exception as e:
            log.warning(f"⚠️ Ollama offline: {e} — evolution will retry each cycle")

        while True:
            generation += 1
            log.info(f"\n🧬 Starting Generation {generation}...")

            try:
                summary = await run_evolution_cycle(gene_pool, generation, client)
                await inject_evolved_prompts(gene_pool)
                # Save generation counter
                gene_pool.pool.setdefault("__meta__", {})["generation"] = generation
                gene_pool._save()
                log.info(f"✅ Generation {generation} evolved. Sleeping {EVOLUTION_INTERVAL}s...")
            except Exception as e:
                log.error(f"❌ Evolution error gen {generation}: {e}")

            await asyncio.sleep(EVOLUTION_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
