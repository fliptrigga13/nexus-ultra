"""
cosmos/auto_learner.py  ──  Autonomous Agent Self-Learning Loop
================================================================
Agents learn from their own work — no API credits, no manual curation.

How it works:
  1. Every swarm task result is automatically logged to swarm_memory.jsonl
  2. A local Ollama model (judge) scores each output 0-10 every few minutes
  3. High-scoring outputs (>= threshold) are added to the training pool
  4. On a configurable schedule (default: nightly), DoRA fine-tuning runs
  5. Improved model is pushed to Ollama and the swarm uses it next run
  6. Loop repeats forever — agents get smarter every day on your own GPU

Zero external API calls. Zero credit usage. Pure local compute loop.

Usage (add to cosmos_kernel.py startup):
  from cosmos.auto_learner import AutoLearner
  learner = AutoLearner()
  asyncio.create_task(learner.run_forever())
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

log = logging.getLogger("cosmos.auto_learner")

OLLAMA_URL    = "http://127.0.0.1:11434"
JUDGE_MODEL   = "llama3.2:1b"     # local judge — scores outputs without API credits
SCORE_THRESHOLD = 6.5             # min score to add to training pool (0-10)
MIN_POOL_SIZE   = 20              # don't train until we have this many examples
SCORE_INTERVAL  = 300             # score new outputs every 5 minutes
TRAIN_INTERVAL  = 86400          # fine-tune every 24 hours (change to 3600 for hourly)


# ─────────────────────────────────────────────────────────────────────────────
#  DATA PATHS
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).parent.parent
SWARM_LOG      = BASE_DIR / "swarm_task_log.jsonl"      # raw swarm outputs go here
SCORED_LOG     = BASE_DIR / "swarm_scored.jsonl"         # outputs after scoring
TRAINING_POOL  = BASE_DIR / "training_pool.jsonl"        # curated high-quality examples
ADAPTER_DIR    = BASE_DIR / "cosmos_adapters"
LAST_TRAIN_FILE = BASE_DIR / ".last_train_time"


# ─────────────────────────────────────────────────────────────────────────────
#  TASK LOGGER  (call this from swarm callbacks to capture outputs)
# ─────────────────────────────────────────────────────────────────────────────
def log_swarm_result(
    agent_role: str,
    task: str,
    output: str,
    session_id: str = "",
    metadata: Optional[dict] = None,
) -> None:
    """
    Call this after every swarm agent completes a task.
    Appends the result to swarm_task_log.jsonl for later scoring.

    Add this to cosmos_kernel.py's on_agent_end callback:
        from cosmos.auto_learner import log_swarm_result
        log_swarm_result(result.agent, task_text, result.output, session_id)
    """
    record = {
        "ts":         time.time(),
        "session_id": session_id,
        "agent_role": agent_role,
        "task":       task[:2000],       # cap at 2k chars
        "output":     output[:4000],     # cap at 4k chars
        "scored":     False,
        "score":      None,
        "metadata":   metadata or {},
    }
    with open(SWARM_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


# ─────────────────────────────────────────────────────────────────────────────
#  LOCAL JUDGE  (scores outputs using local Ollama — zero API credits)
# ─────────────────────────────────────────────────────────────────────────────
async def judge_output(agent_role: str, task: str, output: str) -> float:
    """
    Uses a local Ollama model to score an agent output from 0-10.
    No API calls. No credits. Runs on your GPU.

    Scoring criteria:
      - Accuracy / correctness for the task
      - Completeness — did it fully address the request?
      - Clarity — is it well-structured and easy to understand?
      - Role fidelity — did it behave like the expected agent type?
    """
    import httpx

    prompt = (
        f"You are an expert evaluator of AI agent outputs.\n"
        f"Agent role: {agent_role}\n"
        f"Task given to the agent:\n{task}\n\n"
        f"Agent output:\n{output}\n\n"
        f"Score this output from 0 to 10 based on:\n"
        f"- Accuracy and correctness (does it answer the task well?)\n"
        f"- Completeness (fully addresses the request?)\n"
        f"- Clarity (well structured, clear writing?)\n"
        f"- Role fidelity (behaves like a {agent_role} agent should?)\n\n"
        f"Respond with ONLY a single number from 0 to 10 (decimals allowed). "
        f"No explanation. Just the number."
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": JUDGE_MODEL, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "0").strip()
            # Extract first float from response
            import re
            match = re.search(r"\d+\.?\d*", raw)
            score = float(match.group()) if match else 0.0
            return min(10.0, max(0.0, score))
    except Exception as e:
        log.warning(f"[Judge] Scoring failed: {e} — defaulting to 0")
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
#  SYNTHETIC DATA GENERATOR
#  (when pool is small, generates training examples using local model)
# ─────────────────────────────────────────────────────────────────────────────
async def generate_synthetic_examples(agent_role: str, count: int = 10) -> list[dict]:
    """
    Bootstraps the training pool when there isn't enough real swarm data yet.
    Uses the local Ollama model to generate high-quality instruction-response pairs
    for a given agent role.

    These are self-generated WITHOUT any external API — pure local inference.
    """
    import httpx

    role_topics = {
        "researcher": [
            "Compare transformer vs mamba architectures",
            "Explain RAG vs fine-tuning tradeoffs",
            "Research local LLM deployment options for 8GB VRAM",
            "What are the latest advances in multi-agent coordination?",
            "Compare RLHF vs DPO vs Constitutional AI",
        ],
        "coder": [
            "Write a Python async WebSocket server with rate limiting",
            "Implement a priority queue with async support",
            "Code a streaming LLM response handler",
            "Build a file-based persistent task queue",
            "Write a GPU memory monitor class",
        ],
        "planner": [
            "Plan a 5-stage ML pipeline for a small team",
            "Break down 'build a RAG system' into swarm tasks",
            "Create a sprint plan for deploying a local AI assistant",
            "Plan agent roles for a complex research task",
            "Organize parallel vs sequential tasks for swarm efficiency",
        ],
        "validator": [
            "Review this code for correctness and edge cases",
            "Validate a research summary for accuracy",
            "Check a technical plan for logical gaps",
            "Audit an AI system design for failure modes",
            "Review this output for the task it was given",
        ],
        "summarizer": [
            "Summarize a complex technical paper on attention mechanisms",
            "Distill 5 research papers into key findings",
            "Create an executive summary of a multi-agent task run",
            "Summarize the tradeoffs between different fine-tuning methods",
            "Compress a long conversation into key action items",
        ],
    }

    topics = role_topics.get(agent_role, role_topics["researcher"])
    examples = []

    from cosmos.local_trainer import AGENT_PERSONAS
    system = AGENT_PERSONAS.get(agent_role, "You are a helpful COSMOS agent.")

    async with httpx.AsyncClient(timeout=60.0) as client:
        for i in range(count):
            topic = topics[i % len(topics)]
            prompt = (
                f"{system}\n\n"
                f"Task: {topic}\n\n"
                f"Provide a thorough, high-quality response as a {agent_role} agent."
            )
            try:
                resp = await client.post(
                    f"{OLLAMA_URL}/api/generate",
                    json={"model": JUDGE_MODEL, "prompt": prompt, "stream": False},
                )
                resp.raise_for_status()
                output = resp.json().get("response", "").strip()
                if len(output) > 100:
                    examples.append({
                        "instruction": topic,
                        "response": output,
                        "agent_role": agent_role,
                        "source": "synthetic",
                        "ts": time.time(),
                    })
                    log.info(f"[Synthetic] Generated example {i+1}/{count} for {agent_role}")
            except Exception as e:
                log.warning(f"[Synthetic] Failed example {i}: {e}")
                await asyncio.sleep(1)

    return examples


# ─────────────────────────────────────────────────────────────────────────────
#  AUTO LEARNER  (the main autonomous loop)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class AutoLearnerConfig:
    judge_model: str       = JUDGE_MODEL
    score_threshold: float = SCORE_THRESHOLD
    min_pool_size: int     = MIN_POOL_SIZE
    score_interval: int    = SCORE_INTERVAL         # seconds between scoring runs
    train_interval: int    = TRAIN_INTERVAL         # seconds between training runs
    agent_roles: list      = field(default_factory=lambda: [
        "researcher", "coder", "planner", "validator", "summarizer"
    ])
    base_model: str        = "meta-llama/Llama-3.2-1B"  # smaller = faster training
    # Use Llama-3.1-8B for better quality if you have time to wait


class AutoLearner:
    """
    Autonomous self-improvement loop for COSMOS swarm agents.

    Runs two background tasks:
      1. _score_loop   — every N minutes, scores new swarm outputs with local judge
      2. _train_loop   — every N hours, runs DoRA fine-tuning on accumulated data

    Neither task requires internet or API credits after initial model download.
    """

    def __init__(self, config: Optional[AutoLearnerConfig] = None):
        self.cfg = config or AutoLearnerConfig()
        self._training_active = False
        self._total_scored = 0
        self._total_trained = 0
        self._last_score_time = 0.0
        self._last_train_time = self._load_last_train_time()

    def _load_last_train_time(self) -> float:
        try:
            return float(LAST_TRAIN_FILE.read_text().strip())
        except Exception:
            return 0.0

    def _save_last_train_time(self):
        LAST_TRAIN_FILE.write_text(str(time.time()))

    def status(self) -> dict:
        """Return current learner status — exposed via /learn/status endpoint."""
        pool_size = self._count_pool()
        next_score = max(0, self.cfg.score_interval - (time.time() - self._last_score_time))
        next_train = max(0, self.cfg.train_interval - (time.time() - self._last_train_time))
        return {
            "training_active":  self._training_active,
            "total_scored":     self._total_scored,
            "total_trained":    self._total_trained,
            "pool_size":        pool_size,
            "min_pool_needed":  self.cfg.min_pool_size,
            "pool_ready":       pool_size >= self.cfg.min_pool_size,
            "score_threshold":  self.cfg.score_threshold,
            "next_score_in_s":  round(next_score),
            "next_train_in_s":  round(next_train),
            "judge_model":      self.cfg.judge_model,
            "adapters_dir":     str(ADAPTER_DIR),
        }

    def _count_pool(self) -> int:
        try:
            return sum(1 for _ in open(TRAINING_POOL, encoding="utf-8"))
        except FileNotFoundError:
            return 0

    # ── SCORING LOOP ──────────────────────────────────────────────────────────
    async def _score_loop(self):
        """
        Continuously scores unscored swarm outputs using the local judge model.
        Runs every score_interval seconds. Adds good ones to training_pool.
        """
        log.info("[AutoLearner] Score loop started")
        while True:
            await asyncio.sleep(self.cfg.score_interval)
            self._last_score_time = time.time()
            await self._score_pending()

    async def _score_pending(self):
        """Read swarm log, score unscored entries, write to training pool if good."""
        if not SWARM_LOG.exists():
            return

        records = []
        try:
            with open(SWARM_LOG, encoding="utf-8") as f:
                records = [json.loads(l) for l in f if l.strip()]
        except Exception as e:
            log.warning(f"[Scorer] Failed reading swarm log: {e}")
            return

        unscored = [r for r in records if not r.get("scored")]
        if not unscored:
            return

        log.info(f"[Scorer] Scoring {len(unscored)} new outputs...")
        added = 0

        for r in unscored:
            score = await judge_output(
                r.get("agent_role", "researcher"),
                r.get("task", ""),
                r.get("output", ""),
            )
            r["score"] = score
            r["scored"] = True
            self._total_scored += 1

            if score >= self.cfg.score_threshold:
                # Add to training pool
                training_example = {
                    "instruction": r["task"],
                    "response":    r["output"],
                    "agent_role":  r.get("agent_role", "researcher"),
                    "score":       score,
                    "source":      "swarm_history",
                    "ts":          r.get("ts", time.time()),
                }
                with open(TRAINING_POOL, "a", encoding="utf-8") as pf:
                    pf.write(json.dumps(training_example) + "\n")
                added += 1

            await asyncio.sleep(0.5)  # small pause between judge calls

        # Rewrite swarm log with scored flags
        with open(SWARM_LOG, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        log.info(f"[Scorer] Done. {added} new examples added to training pool "
                 f"(pool size: {self._count_pool()})")

    # ── BOOTSTRAP POOL ────────────────────────────────────────────────────────
    async def _bootstrap_pool_if_empty(self):
        """
        If the training pool is too small, auto-generate synthetic examples
        using the local Ollama model. No internet, no credits.
        """
        pool_size = self._count_pool()
        if pool_size >= self.cfg.min_pool_size:
            return

        needed = self.cfg.min_pool_size - pool_size
        per_role = max(4, needed // len(self.cfg.agent_roles))
        log.info(f"[Bootstrap] Pool has {pool_size} examples, need {self.cfg.min_pool_size}. "
                 f"Generating {per_role} synthetic examples per role...")

        for role in self.cfg.agent_roles:
            examples = await generate_synthetic_examples(role, per_role)
            with open(TRAINING_POOL, "a", encoding="utf-8") as f:
                for ex in examples:
                    f.write(json.dumps(ex) + "\n")
            log.info(f"[Bootstrap] Added {len(examples)} examples for '{role}'")

        log.info(f"[Bootstrap] Pool now has {self._count_pool()} examples")

    # ── TRAINING LOOP ─────────────────────────────────────────────────────────
    async def _train_loop(self):
        """
        Runs DoRA fine-tuning on a schedule using accumulated training pool.
        Pushes improved model to Ollama automatically.
        """
        log.info("[AutoLearner] Train loop started")
        while True:
            # Wait until next training window
            elapsed = time.time() - self._last_train_time
            wait = max(0, self.cfg.train_interval - elapsed)
            log.info(f"[AutoLearner] Next training run in {wait/3600:.1f}h")
            await asyncio.sleep(wait)

            if self._training_active:
                log.warning("[AutoLearner] Training already active — skipping this cycle")
                await asyncio.sleep(60)
                continue

            pool_size = self._count_pool()
            if pool_size < self.cfg.min_pool_size:
                log.info(f"[AutoLearner] Pool too small ({pool_size} < {self.cfg.min_pool_size}) "
                         f"— bootstrapping with synthetic data first...")
                await self._bootstrap_pool_if_empty()

            await self._run_training()

    async def _run_training(self):
        """Run one full DoRA training cycle + export to Ollama."""
        self._training_active = True
        run_start = time.time()
        log.info("[AutoLearner] ═══ Starting autonomous training cycle ═══")

        try:
            from cosmos.local_trainer import SwarmTrainer, SwarmTrainerConfig

            for role in self.cfg.agent_roles:
                # Filter training pool to this role
                role_examples = self._filter_pool_for_role(role)
                if len(role_examples) < 5:
                    log.info(f"[AutoLearner] Not enough examples for {role} ({len(role_examples)}) — skipping")
                    continue

                # Write temp training file
                tmp_path = BASE_DIR / f"_tmp_train_{role}.jsonl"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    for ex in role_examples:
                        f.write(json.dumps(ex) + "\n")

                log.info(f"[AutoLearner] Training {role} on {len(role_examples)} examples...")

                cfg = SwarmTrainerConfig(
                    base_model=self.cfg.base_model,
                    agent_role=role,
                    epochs=2,           # fast cycle — quality over quantity
                    batch_size=2,
                    grad_accum_steps=8,
                    use_dora=True,
                )
                trainer = SwarmTrainer(cfg)

                try:
                    adapter_path = await trainer.fine_tune(str(tmp_path))
                    model_name = f"cosmos-{role}-v{int(time.time())}"
                    await trainer.export_to_ollama(model_name)
                    log.info(f"[AutoLearner] ✓ {role} → {model_name} deployed to Ollama")
                    self._total_trained += 1
                except Exception as e:
                    log.error(f"[AutoLearner] Training {role} failed: {e}")
                finally:
                    tmp_path.unlink(missing_ok=True)

        except ImportError:
            log.error("[AutoLearner] local_trainer not available — "
                      "run: pip install transformers peft accelerate bitsandbytes")
        finally:
            self._training_active = False
            self._last_train_time = time.time()
            self._save_last_train_time()
            duration = (time.time() - run_start) / 60
            log.info(f"[AutoLearner] ═══ Training cycle complete ({duration:.1f} min) ═══")

    def _filter_pool_for_role(self, role: str) -> list[dict]:
        """Load training pool and filter to a specific agent role."""
        examples = []
        try:
            with open(TRAINING_POOL, encoding="utf-8") as f:
                for line in f:
                    try:
                        ex = json.loads(line.strip())
                        if ex.get("agent_role") == role or not ex.get("agent_role"):
                            examples.append(ex)
                    except Exception:
                        pass
        except FileNotFoundError:
            pass
        # Sort by score descending — best examples first
        return sorted(examples, key=lambda x: x.get("score", 5.0), reverse=True)

    # ── MAIN ENTRY POINT ──────────────────────────────────────────────────────
    async def run_forever(self):
        """
        Start both loops as concurrent background tasks.
        Call this once at cosmos_kernel startup:

            from cosmos.auto_learner import AutoLearner
            learner = AutoLearner()
            asyncio.create_task(learner.run_forever())
        """
        log.info("[AutoLearner] Starting autonomous learning system...")
        log.info(f"[AutoLearner] Judge: {self.cfg.judge_model} (local, zero credits)")
        log.info(f"[AutoLearner] Score threshold: {self.cfg.score_threshold}/10")
        log.info(f"[AutoLearner] Training interval: every {self.cfg.train_interval/3600:.0f}h")

        # Score immediately on startup to catch any backlog
        await self._score_pending()
        await self._bootstrap_pool_if_empty()

        # Run both loops concurrently
        await asyncio.gather(
            self._score_loop(),
            self._train_loop(),
        )
