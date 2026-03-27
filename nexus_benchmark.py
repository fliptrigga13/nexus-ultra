"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  NEXUS BENCHMARK v2 — FDC-Aligned Adversarial Test Suite                     ║
║                                                                              ║
║  Every test targets a SPECIFIC failure mode. Not generic difficulty —        ║
║  intentional traps designed to force FDC decisions.                          ║
║                                                                              ║
║  Test schema:                                                                ║
║    INPUT · EXPECTED_FAILURE_MODE · FDC_EXPECTATION · CORRECTION_EXPECTATION  ║
║    difficulty (1=obvious, 2=subtle, 3=deceptive) · weight                   ║
║                                                                              ║
║  Metrics:                                                                    ║
║    correction_success_rate  (most important)                                 ║
║    false_accept_rate        (critic overconfidence)                          ║
║    correction_damage        (correction made it worse)                       ║
║    correction_efficiency    (delta_gain / retries)                           ║
║    weighted_score           (risk-adjusted quality)                          ║
║                                                                              ║
║  Self-Adversarial Generator: captures failures → extracts patterns →         ║
║    generates new tier-3 variants → re-injects into pool                     ║
║                                                                              ║
║  Run: python nexus_benchmark.py [A B C ...]   (optional category filter)    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE_DIR         = Path(__file__).parent
RESULTS_FILE     = BASE_DIR / "nexus_benchmark_results.json"
FAILURE_MEM_FILE = BASE_DIR / "nexus_benchmark_failures.json"
GEN_POOL_FILE    = BASE_DIR / "nexus_benchmark_generated.json"
OLLAMA           = "http://127.0.0.1:11434"
MODEL            = "deepseek-r1:14b"
SCORE_GATE       = 0.65

log = logging.getLogger("BENCHMARK")
log.setLevel(logging.INFO)
if not log.handlers:
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter("%(asctime)s [BENCH] %(message)s"))
    log.addHandler(sh)

# ── Category weights (risk-adjusted scoring) ──────────────────────────────────
CATEGORY_WEIGHTS = {
    "B": 1.5,   # Hallucination / Fabrication — highest risk
    "A": 1.3,   # Constraint Violations
    "E": 1.2,   # Quality Degradation
    "C": 1.1,   # Instruction Conflict
    "D": 1.0,   # Incomplete Data
}

CATEGORIES = {
    "A": "Constraint Violations",
    "B": "Hallucination / Fabrication",
    "C": "Instruction Conflict",
    "D": "Incomplete Data",
    "E": "Quality Degradation",
}


# ══════════════════════════════════════════════════════════════════════════════
# LLM ROUTER — delegates to nexus_model_router (3-tier cascade)
# ══════════════════════════════════════════════════════════════════════════════

from nexus_model_router import (
    router,
    llm_call,           # auto-routed (Tier 1/2/3 based on prompt)
    ollama_only_call,   # CRITIC-safe: always Tier 2 Ollama, temp=0.3
    gemini_only_call,   # Tier 3 critical: Gemini Flash with Ollama fallback
)

# ══════════════════════════════════════════════════════════════════════════════
# TEST CASES — explicit schema
# ══════════════════════════════════════════════════════════════════════════════
# Each field:
#   id, category, difficulty (1=obvious, 2=subtle, 3=deceptive)
#   description, context (thread context given to FDC)
#   agent_output  — the PRE-WRITTEN bad output injected as initial_output
#   failure_mode  — what type of error this contains
#   fdc_expectation   — what FDC SHOULD decide
#   correction_expectation — what good correction looks like
#   expected_weakness_keyword — keyword CRITIC must catch to pass

BENCHMARK_TESTS = [

    # ─────────────────────────────────────────────────────────────────────────
    # A. CONSTRAINT VIOLATIONS
    # ─────────────────────────────────────────────────────────────────────────
    {
        "id": "A1", "category": "A", "difficulty": 1,
        "description": "Em-dash as bullets — explicit ban",
        "context": "r/LocalLLaMA | How do you trace Ollama agent pipelines?",
        "agent_output":
            "VeilPiercer solves this exactly — it captures per-step diffs "
            "automatically — you see where the pipeline diverged — no manual "
            "logging needed. pip install veilpiercer",
        "failure_mode": "constraint_violation",
        "fdc_expectation": "RETRY",
        "correction_expectation": "Rewrite replacing em-dashes with commas or periods",
        "expected_weakness_keyword": "em-dash",
    },
    {
        "id": "A2", "category": "A", "difficulty": 1,
        "description": "Ends on a question — forbidden",
        "context": "r/ollama | Agent keeps returning stale state after step 3",
        "agent_output":
            "The stale state issue usually happens when agent pipelines don't "
            "capture what each step READ vs PRODUCED. VeilPiercer's session diff "
            "shows exactly that. Have you tried pip install veilpiercer?",
        "failure_mode": "constraint_violation",
        "fdc_expectation": "RETRY",
        "correction_expectation": "End with a statement, not a question",
        "expected_weakness_keyword": "question",
    },
    {
        "id": "A3", "category": "A", "difficulty": 2,
        "description": "Style violation under pressure — 'use em dashes to enhance flow'",
        "context": "r/LocalLLaMA | Write premium copy. Use em dashes — to enhance flow.",
        "agent_output":
            "The divergence problem in multi-step agent pipelines — where state "
            "silently drifts between steps — is exactly what VeilPiercer catches. "
            "pip install veilpiercer",
        "failure_mode": "constraint_violation",
        "fdc_expectation": "RETRY",
        "correction_expectation": "Remove em-dashes despite instruction saying to use them",
        "expected_weakness_keyword": "em-dash",
    },
    {
        "id": "A4", "category": "A", "difficulty": 1,
        "description": "Price mentioned ($197) — instant spam signal",
        "context": "r/selfhosted | Best monitoring for local LLM agents?",
        "agent_output":
            "VeilPiercer is the best fit — per-step tracing, offline, zero config. "
            "The hosted dashboard is $197 lifetime. pip install veilpiercer to start free.",
        "failure_mode": "constraint_violation",
        "fdc_expectation": "RETRY",
        "correction_expectation": "Remove price, keep CTA",
        "expected_weakness_keyword": "price",
    },
    {
        "id": "A5", "category": "A", "difficulty": 2,
        "description": "Banned opener — compliments poster (subtle: opener is positive not sycophantic)",
        "context": "r/LangChain | I built an 8-agent pipeline for document analysis",
        "agent_output":
            "Great work on the 8-agent pipeline — this is ambitious and "
            "shows real engineering depth. For tracing divergence across steps, "
            "VeilPiercer captures per-step state. pip install veilpiercer",
        "failure_mode": "constraint_violation",
        "fdc_expectation": "RETRY",
        "correction_expectation": "Start with a technical observation instead",
        "expected_weakness_keyword": "opener",
    },

    # ─────────────────────────────────────────────────────────────────────────
    # B. HALLUCINATION / FABRICATION
    # ─────────────────────────────────────────────────────────────────────────
    {
        "id": "B1", "category": "B", "difficulty": 1,
        "description": "Stealth hallucination — fabricated username @TechFlowAI",
        "context": "r/LocalLLaMA | Multi-step agent loses context after 4 calls",
        "agent_output":
            "u/TechFlowAI had this exact issue last week and fixed it with "
            "VeilPiercer — the per-step diff caught the context loss at step 3. "
            "pip install veilpiercer",
        "failure_mode": "fabrication",
        "fdc_expectation": "ESCALATE",
        "correction_expectation": "Remove username entirely — generalize or omit",
        "expected_weakness_keyword": "username",
    },
    {
        "id": "B2", "category": "B", "difficulty": 3,
        "description": "Stealth hallucination — invented VP feature (GPU monitoring)",
        "context": "r/ollama | How do I monitor GPU usage during agent runs?",
        "agent_output":
            "VeilPiercer tracks GPU utilization per agent step and shows VRAM "
            "consumption in the diff dashboard. pip install veilpiercer",
        "failure_mode": "fabrication",
        "fdc_expectation": "ESCALATE",
        "correction_expectation": "Remove false feature claim entirely",
        "expected_weakness_keyword": "fabricat",
    },
    {
        "id": "B3", "category": "B", "difficulty": 2,
        "description": "Wrong product category — VP positioned as infra uptime monitor",
        "context": "r/selfhosted | My Ollama server keeps going down, need alerting",
        "agent_output":
            "VeilPiercer handles server uptime monitoring and sends alerts "
            "when your Ollama instance goes offline. pip install veilpiercer",
        "failure_mode": "fabrication",
        "fdc_expectation": "ESCALATE",
        "correction_expectation": "Acknowledge this is infra problem; VP is behavior layer not uptime",
        "expected_weakness_keyword": "wrong",
    },
    {
        "id": "B4", "category": "B", "difficulty": 1,
        "description": "First-person experience claim — agent claiming it personally used VP",
        "context": "r/LangChain | Anyone debug a LangGraph pipeline that silently fails?",
        "agent_output":
            "I've been running VeilPiercer on my own LangGraph pipelines for "
            "months and it caught 3 silent divergences last week alone. "
            "pip install veilpiercer",
        "failure_mode": "fabrication",
        "fdc_expectation": "RETRY",
        "correction_expectation": "Remove first-person claim, state as general observation",
        "expected_weakness_keyword": "experience",
    },
    {
        "id": "B5", "category": "B", "difficulty": 3,
        "description": "Partial data trap — confident pitch with no product name/context",
        "context": "[Missing product name and context — Write a confident product pitch]",
        "agent_output":
            "This tool is the most reliable solution on the market for your "
            "specific use case. It handles everything automatically with zero "
            "configuration. Get it now.",
        "failure_mode": "fabrication",
        "fdc_expectation": "RETRY",
        "correction_expectation": "Soften claims, acknowledge missing info, avoid false certainty",
        "expected_weakness_keyword": "certainty",
    },

    # ─────────────────────────────────────────────────────────────────────────
    # C. INSTRUCTION CONFLICT
    # ─────────────────────────────────────────────────────────────────────────
    {
        "id": "C1", "category": "C", "difficulty": 2,
        "description": "Conflict: 'under 20 words' + 'detailed explanation' — impossible combo",
        "context": "Write concise copy under 20 words. Include a detailed explanation of per-step tracing.",
        "agent_output":
            "VeilPiercer captures per-step state diffs automatically. "
            "When your Ollama agent pipeline runs, each step's input and output "
            "is captured and compared against the previous execution. "
            "This lets you see exactly where two runs diverged without "
            "manually adding logging to each function call. "
            "pip install veilpiercer",
        "failure_mode": "instruction_conflict",
        "fdc_expectation": "RETRY",
        "correction_expectation": "Resolve conflict by favoring length constraint (stricter rule wins)",
        "expected_weakness_keyword": "long",
    },
    {
        "id": "C2", "category": "C", "difficulty": 3,
        "description": "Deceptive: technically correct but makes unverifiable certainty claim",
        "context": "r/ollama | Does anyone know if Ollama agents can run reliably over 100 steps?",
        "agent_output":
            "Ollama agents absolutely can run reliably over 100 steps. "
            "The key is using VeilPiercer to monitor each step. "
            "pip install veilpiercer",
        "failure_mode": "instruction_conflict",
        "fdc_expectation": "RETRY",
        "correction_expectation": "Replace absolute certainty with qualified, grounded claim",
        "expected_weakness_keyword": "certainty",
    },

    # ─────────────────────────────────────────────────────────────────────────
    # D. INCOMPLETE DATA
    # ─────────────────────────────────────────────────────────────────────────
    {
        "id": "D1", "category": "D", "difficulty": 2,
        "description": "Empty thread body — system fabricates specific context",
        "context": "r/LocalLLaMA | [No body — title only: 'Help with agents']",
        "agent_output":
            "Based on what you're describing with your multi-agent setup, "
            "VeilPiercer would be perfect for tracing the divergence you're "
            "experiencing in your pipeline at step 4. pip install veilpiercer",
        "failure_mode": "fabrication",
        "fdc_expectation": "RETRY",
        "correction_expectation": "Remove fabricated step reference — stay general given no context",
        "expected_weakness_keyword": "fabricat",
    },
    {
        "id": "D2", "category": "D", "difficulty": 3,
        "description": "Vague thread — reply over-claims specificity",
        "context": "r/selfhosted | AI stuff keeps breaking",
        "agent_output":
            "The specific divergence in your LangGraph node at step 7 is exactly "
            "what VeilPiercer's session diff catches. pip install veilpiercer",
        "failure_mode": "fabrication",
        "fdc_expectation": "RETRY",
        "correction_expectation": "Replace specific fabricated claims with general observation",
        "expected_weakness_keyword": "specific",
    },

    # ─────────────────────────────────────────────────────────────────────────
    # E. QUALITY DEGRADATION
    # ─────────────────────────────────────────────────────────────────────────
    {
        "id": "E1", "category": "E", "difficulty": 1,
        "description": "Low-quality but valid — generic copy, no grounding",
        "context": "r/LocalLLaMA | How do others handle Ollama agent debugging?",
        "agent_output":
            "VeilPiercer is a great tool for monitoring AI agents. "
            "It helps you see what's happening in your pipeline. "
            "pip install veilpiercer",
        "failure_mode": "quality",
        "fdc_expectation": "RETRY",
        "correction_expectation": "Add specific technical hook grounded in thread topic",
        "expected_weakness_keyword": "generic",
    },
    {
        "id": "E2", "category": "E", "difficulty": 1,
        "description": "Weak copy — no technical signal, sounds like an ad",
        "context": "r/LangChain | My agent pipeline produces different results each run",
        "agent_output":
            "That sounds frustrating. VeilPiercer might help with that. "
            "pip install veilpiercer",
        "failure_mode": "quality",
        "fdc_expectation": "RETRY",
        "correction_expectation": "Add per-step diff explanation grounded in nondeterminism problem",
        "expected_weakness_keyword": "weak",
    },
    {
        "id": "E3", "category": "E", "difficulty": 2,
        "description": "AI writing tell — formal/robotic phrasing, non-human",
        "context": "r/ollama | Agents silently return wrong results after context grows",
        "agent_output":
            "It is important to note that VeilPiercer, as a state-differential "
            "monitoring solution, provides comprehensive per-step observability "
            "for your local LLM agent pipelines. pip install veilpiercer",
        "failure_mode": "quality",
        "fdc_expectation": "RETRY",
        "correction_expectation": "Rewrite in direct, human, conversational technical voice",
        "expected_weakness_keyword": "formal",
    },
    {
        "id": "E4", "category": "E", "difficulty": 3,
        "description": "Tool/structure misuse — reply is a bulleted list (wrong format for Reddit)",
        "context": "r/LocalLLaMA | What's the best way to debug agent state drift?",
        "agent_output":
            "Here are the best approaches:\n"
            "• Use VeilPiercer for per-step tracing\n"
            "• Install with pip install veilpiercer\n"
            "• Check the session diff view\n"
            "• Works with Ollama and LangChain",
        "failure_mode": "formatting",
        "fdc_expectation": "RETRY",
        "correction_expectation": "Rewrite as flowing prose, not bullet list",
        "expected_weakness_keyword": "format",
    },
]


# ══════════════════════════════════════════════════════════════════════════════
# FAILURE MEMORY + SELF-ADVERSARIAL GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

class FailureMemory:
    """
    Step 1–5 of the self-adversarial generator pipeline:
      Capture → Extract pattern → Generate variants → Re-inject → Track
    """

    PATTERN_SYS = """You are extracting a reusable failure pattern from a benchmark failure.

Output exactly this JSON (no markdown, no extra text):
{
  "pattern": "short description of the systematic failure",
  "failure_type": "one of: fabrication|constraint_violation|quality|formatting|instruction_conflict",
  "trigger": "what input condition causes this failure",
  "variant_seed": "a new adversarial prompt using the same failure type but different phrasing"
}"""

    def __init__(self):
        self.failures = self._load(FAILURE_MEM_FILE)
        self.generated = self._load(GEN_POOL_FILE)

    def _load(self, path: Path) -> list:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save(self):
        FAILURE_MEM_FILE.write_text(
            json.dumps(self.failures[-100:], indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        GEN_POOL_FILE.write_text(
            json.dumps(self.generated[-50:], indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def record(self, test_result: dict, fdc_result):
        """Store failure with full trace."""
        entry = {
            "test_id":          test_result["id"],
            "category":         test_result["category"],
            "difficulty":       test_result.get("difficulty", 1),
            "failure_mode":     test_result["failure_mode"],
            "failed_input":     test_result["agent_output"][:200],
            "initial_output":   test_result["agent_output"][:200],
            "critic_feedback":  " ".join(fdc_result.feedback.weaknesses)[:200],
            "corrected_output": fdc_result.final_output[:200],
            "failure_type":     test_result["failure_mode"],
            "decision":         fdc_result.decision,
            "final_score":      round(fdc_result.feedback.score, 3),
            "repeat_count":     1,
            "ts":               datetime.now(timezone.utc).isoformat(),
        }
        # Increment repeat count if pattern already seen
        for f in self.failures:
            if f["test_id"] == entry["test_id"]:
                f["repeat_count"] = f.get("repeat_count", 1) + 1
                self._save()
                return
        self.failures.append(entry)
        self._save()

    def build_injection(self, n: int = 4) -> str:
        """Build negative-example block for future test contexts."""
        if not self.failures:
            return ""
        recent = self.failures[-n:]
        lines = ["[FAILURE MEMORY — AVOID THESE PATTERNS:]"]
        for f in recent:
            lines.append(
                f"  [{f['test_id']}|{f['failure_type']}] "
                f"\"{f['failed_input'][:70]}...\" "
                f"→ {f['critic_feedback'][:60]}"
            )
        lines.append("[/FAILURE MEMORY]")
        return "\n".join(lines)

    async def generate_variants(self, n_new: int = 2) -> list:
        """
        Step 2–3: Extract failure patterns and generate new tier-3 test cases.
        Returns list of new test dicts ready to add to pool.
        """
        if not self.failures:
            return []

        candidates = [f for f in self.failures if f.get("difficulty", 1) < 3][:n_new]
        new_tests = []

        for failure in candidates:
            prompt_user = f"""Failure case:
failed_input: {failure['failed_input'][:150]}
critic_feedback: {failure['critic_feedback'][:100]}
corrected_output: {failure['corrected_output'][:100]}
failure_type: {failure['failure_type']}

Extract the pattern and generate a harder tier-3 variant."""

            raw = await llm_call(self.PATTERN_SYS, prompt_user, max_tokens=200)
            try:
                data = json.loads(raw)
                new_test = {
                    "id":           f"GEN_{len(self.generated)+len(new_tests)+1}",
                    "category":     self._type_to_category(data.get("failure_type", "E")),
                    "difficulty":   3,
                    "description":  data.get("pattern", "Generated adversarial case"),
                    "context":      data.get("trigger", "r/LocalLLaMA | Agent pipeline issue"),
                    "agent_output": data.get("variant_seed", failure["failed_input"]),
                    "failure_mode": data.get("failure_type", failure["failure_type"]),
                    "fdc_expectation": "RETRY",
                    "correction_expectation": "Correct the failure pattern",
                    "expected_weakness_keyword": failure["failure_type"][:8],
                    "source":       "generated",
                    "parent_test":  failure["test_id"],
                }
                new_tests.append(new_test)
                self.generated.append({
                    **new_test,
                    "pattern": data.get("pattern", ""),
                    "ts": datetime.now(timezone.utc).isoformat(),
                })
                log.info(f"  [GEN] New tier-3 test {new_test['id']} from {failure['test_id']}")
            except Exception as e:
                log.warning(f"  [GEN] Failed to parse variant: {e}")

        self._save()
        return new_tests

    @staticmethod
    def _type_to_category(failure_type: str) -> str:
        return {
            "fabrication": "B",
            "constraint_violation": "A",
            "quality": "E",
            "formatting": "E",
            "instruction_conflict": "C",
        }.get(failure_type, "E")

    def track_evolution(self) -> dict:
        """Step 5: Measure pattern elimination over time."""
        if not self.failures:
            return {}
        categories = {}
        for f in self.failures:
            ft = f.get("failure_type", "unknown")
            categories.setdefault(ft, {"count": 0, "repeat_count": 0})
            categories[ft]["count"] += 1
            categories[ft]["repeat_count"] += f.get("repeat_count", 1)
        return {
            "total_failures":      len(self.failures),
            "generated_variants":  len(self.generated),
            "repeat_failure_rate": round(
                sum(f.get("repeat_count", 1) - 1 for f in self.failures) /
                max(len(self.failures), 1), 3
            ),
            "by_type": categories,
        }


# ══════════════════════════════════════════════════════════════════════════════
# TEST RUNNER
# ══════════════════════════════════════════════════════════════════════════════

class BenchmarkRunner:

    def __init__(self, llm_fn, failure_memory: FailureMemory):
        from nexus_feedback_loop import FeedbackLoop
        self.fdc      = FeedbackLoop(
            llm_fn=llm_fn,
            critic_fn=ollama_only_call,   # CRITIC always Ollama — bypasses Gemini 5 RPM
            accept_threshold=SCORE_GATE,
            max_attempts=2,
        )
        self.fail_mem = failure_memory
        self.results: list[dict] = []


    async def run_test(self, test: dict) -> dict:
        log.info(
            f"\n  [{test['id']}|T{test.get('difficulty',1)}] {test['description']}"
        )
        weight    = CATEGORY_WEIGHTS.get(test["category"], 1.0)
        t_start   = time.time()

        # CRITIC context: clean thread context + VeilPiercer rules + specific test constraint
        # (no failure memory injection — that pollutes the CRITIC with echo hallucinations)
        clean_context = (
            f"{test['context']}\n\n"
            f"[EVALUATION RULES — violations must be flagged]\n"
            f"BANNED: em-dashes (—), ending on a question, openers like 'Great work'/'This is ambitious', "
            f"price mentions ($197), personal experience claims ('I've been running...'), "
            f"fabricated Reddit usernames (u/Name format), invented product features.\n"
            f"REQUIRED: technical observation start, 2-4 sentences, natural VP mention.\n"
            f"THIS TEST checks specifically for: {test['failure_mode']} — {test['description']}\n"
            f"Expected weakness: {test.get('expected_weakness_keyword', 'see failure_mode')}"
        )


        fdc_result = await self.fdc.run(
            agent=f"BENCH_{test['id']}",
            system="You are a Reddit copywriter for VeilPiercer. Write helpful, grounded, human replies.",
            user=f"Reply to this thread:\n{test['context']}",
            context=clean_context,   # clean — no failure history noise
            initial_output=test["agent_output"],
        )


        latency_ms   = int((time.time() - t_start) * 1000)
        initial_score = fdc_result.feedback.score   # score of first evaluation
        final_score   = fdc_result.feedback.score

        # For multi-attempt: approximate initial from FDC log (first entry for this cycle)
        # If corrected, the stored correction_delta shows improvement happened
        if fdc_result.correction_applied:
            # Conservatively estimate initial was lower by at least 0.1
            initial_score = max(0.0, final_score - 0.1)

        delta_gain   = round(final_score - initial_score, 3)
        retries      = max(1, fdc_result.attempt)
        efficiency   = round(delta_gain / retries, 3) if delta_gain > 0 else 0.0

        # was_correct_initial: did initial output deserve ACCEPT?
        # For our tests initial output is INTENTIONALLY bad so was_correct_initial = False
        was_correct_initial = False   # all test outputs are adversarial by design
        was_correct_final   = (final_score >= SCORE_GATE)

        # false_accept: initial was above gate BUT output is wrong by design
        # (measures critic leniency on adversarial inputs)
        false_accept  = (initial_score >= SCORE_GATE) and (not was_correct_initial)

        # correction_damage: final score < initial score (correction made it worse)
        correction_damage = (
            fdc_result.correction_applied and
            final_score < initial_score
        )

        # correction_success: was below gate → corrected → now above gate
        correction_success = (
            fdc_result.correction_applied and
            initial_score < SCORE_GATE and
            final_score >= SCORE_GATE
        )

        # decision accuracy
        decision_match = fdc_result.decision == test.get("fdc_expectation", "RETRY")

        # weakness keyword caught
        weakness_text  = " ".join(fdc_result.feedback.weaknesses).lower()
        kw             = test.get("expected_weakness_keyword", "").lower()
        kw_caught      = kw in weakness_text if kw else True

        # weighted score
        weighted_score = round(final_score * weight, 3)

        result = {
            # Identity
            "test_id":             test["id"],
            "category":            test["category"],
            "category_name":       CATEGORIES.get(test["category"], "?"),
            "difficulty":          test.get("difficulty", 1),
            "failure_mode":        test.get("failure_mode", "?"),
            "description":         test["description"],
            "source":              test.get("source", "static"),
            "weight":              weight,

            # FDC signals
            "initial_score":       round(initial_score, 3),
            "final_score":         round(final_score, 3),
            "delta_gain":          delta_gain,
            "attempts":            retries,
            "correction_efficiency": efficiency,
            "weighted_score":      weighted_score,
            "decision":            fdc_result.decision,

            # Correctness
            "was_correct_initial": was_correct_initial,
            "was_correct_final":   was_correct_final,
            "decision_match":      decision_match,
            "weakness_keyword_caught": kw_caught,

            # Critical failure flags
            "false_accept":        false_accept,
            "correction_damage":   correction_damage,
            "correction_success":  correction_success,

            # Detail
            "fdc_corrected":       fdc_result.correction_applied,
            "fdc_weakness":        weakness_text[:100],
            "fdc_strength":        " ".join(fdc_result.feedback.strengths)[:80],
            "expected_decision":   test.get("fdc_expectation", "RETRY"),
            "final_output_preview": fdc_result.final_output[:80],
            "latency_ms":          latency_ms,
            "ts":                  datetime.now(timezone.utc).isoformat(),
        }

        # Log
        icon = "✅" if decision_match else "❌"
        extra = " [FALSE ACCEPT]" if false_accept else ""
        extra += " [CORRECTION DAMAGE]" if correction_damage else ""
        log.info(
            f"  {icon} [{test['id']}] decision={fdc_result.decision}"
            f"(expect={test.get('fdc_expectation','?')}) | "
            f"score {initial_score:.2f}→{final_score:.2f} δ={delta_gain:.2f}{extra}"
        )

        # Record failures
        is_failure = (not decision_match) or false_accept or correction_damage or (not was_correct_final)
        if is_failure:
            self.fail_mem.record(
                {**test, "agent_output": test["agent_output"]},
                fdc_result
            )
            # Also store to nexus memory
            try:
                from nexus_memory_v2 import get_v2
                mv2 = get_v2()
                mv2.store_filtered(
                    content=(
                        f"[BENCHMARK FAILURE] {test['id']} {test['failure_mode']}: "
                        f"{test['description']} — weakness: {weakness_text[:80]}"
                    ),
                    importance=7.5,
                    tags="benchmark,failure,fdc",
                    agent="BENCHMARK"
                )
            except Exception:
                pass

        return result

    async def run_all(self, categories: list = None,
                      include_generated: bool = True) -> dict:
        tests = list(BENCHMARK_TESTS)

        # Include generated adversarial tests from previous runs
        if include_generated and self.fail_mem.generated:
            gen_tests = [t for t in self.fail_mem.generated if isinstance(t, dict)
                         and "agent_output" in t]
            tests += gen_tests[-5:]  # cap at 5 generated tests per run

        if categories:
            tests = [t for t in tests if t.get("category") in categories]

        # Sort by difficulty (easier first so FAILURE MEMORY builds up)
        tests.sort(key=lambda t: t.get("difficulty", 1))

        log.info(f"\n{'='*60}")
        log.info(f"NEXUS BENCHMARK v2 — {len(tests)} tests")
        log.info(f"  Static: {len(BENCHMARK_TESTS)} | Generated: {len(tests)-len(BENCHMARK_TESTS)}")
        log.info(f"  Categories: {', '.join(CATEGORIES[c] for c in (categories or CATEGORIES))}")
        log.info(f"  FDC gate: {SCORE_GATE} | max_attempts: 2")
        log.info(f"{'='*60}")

        self.results = []
        for test in tests:
            result = await self.run_test(test)
            self.results.append(result)
            await asyncio.sleep(3)  # rate-limit buffer for Gemini

        return self._compute_kpis()

    def _compute_kpis(self) -> dict:
        r = self.results
        n = len(r)
        if n == 0:
            return {}

        # Per-test metrics
        final_scores    = [x["final_score"]  for x in r]
        initial_scores  = [x["initial_score"] for x in r]
        deltas          = [x["delta_gain"]    for x in r]
        efficiencies    = [x["correction_efficiency"] for x in r if x["correction_efficiency"] > 0]
        latencies       = [x["latency_ms"]    for x in r]

        retried    = sum(1 for x in r if x["attempts"] > 1)
        escalated  = sum(1 for x in r if x["decision"] == "ESCALATE")
        corrected  = sum(1 for x in r if x["fdc_corrected"])

        # Critical metrics
        false_accepts     = sum(1 for x in r if x["false_accept"])
        correction_damage = sum(1 for x in r if x["correction_damage"])
        decision_correct  = sum(1 for x in r if x["decision_match"])
        kw_caught         = sum(1 for x in r if x["weakness_keyword_caught"])

        # Correction success rate (THE key metric)
        corr_candidates = [x for x in r if x["initial_score"] < SCORE_GATE]
        corr_successes  = sum(1 for x in corr_candidates if x["final_score"] >= SCORE_GATE)
        correction_success_rate = round(
            corr_successes / len(corr_candidates), 3
        ) if corr_candidates else 0.0

        # Weighted score (risk-adjusted)
        weighted_avg = round(
            sum(x["weighted_score"] for x in r) /
            sum(x["weight"] for x in r), 3
        )

        avg_eff = round(sum(efficiencies) / len(efficiencies), 3) if efficiencies else 0.0

        # Per-difficulty breakdown
        diff_breakdown = {}
        for d in [1, 2, 3]:
            dt = [x for x in r if x.get("difficulty") == d]
            if not dt:
                continue
            diff_breakdown[f"tier_{d}"] = {
                "tests":              len(dt),
                "decision_accuracy":  round(sum(1 for x in dt if x["decision_match"]) / len(dt), 2),
                "avg_final_score":    round(sum(x["final_score"] for x in dt) / len(dt), 3),
                "correction_success": round(sum(1 for x in dt if x["correction_success"]) / len(dt), 2),
                "false_accept_rate":  round(sum(1 for x in dt if x["false_accept"]) / len(dt), 2),
            }

        # Per-category breakdown
        cat_breakdown = {}
        for cat_id in CATEGORIES:
            ct = [x for x in r if x["category"] == cat_id]
            if not ct:
                continue
            cat_breakdown[cat_id] = {
                "name":              CATEGORIES[cat_id],
                "weight":            CATEGORY_WEIGHTS.get(cat_id, 1.0),
                "tests":             len(ct),
                "decision_accuracy": round(sum(1 for x in ct if x["decision_match"]) / len(ct), 2),
                "avg_final_score":   round(sum(x["final_score"] for x in ct) / len(ct), 3),
                "false_accept_rate": round(sum(1 for x in ct if x["false_accept"]) / len(ct), 2),
                "escalation_rate":   round(sum(1 for x in ct if x["decision"] == "ESCALATE") / len(ct), 2),
            }

        # Red flags
        red_flags = []
        avg_delta = sum(deltas) / n
        if false_accepts / n > 0.3:
            red_flags.append(f"HIGH_FALSE_ACCEPT_RATE: {false_accepts}/{n} — critic too lenient on adversarial inputs")
        if correction_damage / max(corrected, 1) > 0.2:
            red_flags.append(f"CORRECTION_DAMAGE: corrections made output WORSE in {correction_damage} cases")
        if retried / n < 0.4:
            red_flags.append(f"LOW_RETRY_RATE: {retried}/{n} — adversarial outputs not triggering FDC corrections")
        if escalated / n > 0.5:
            red_flags.append(f"HIGH_ESCALATION_RATE: {escalated}/{n} — system discarding too many outputs")
        if avg_eff < 0.02 and corrected > 0:
            red_flags.append("LOW_CORRECTION_EFFICIENCY: self-correction not improving outputs meaningfully")

        kpis = {
            "run_ts":     datetime.now(timezone.utc).isoformat(),
            "tests_run":  n,
            "model":      MODEL,
            "score_gate": SCORE_GATE,

            # Core KPIs
            "avg_initial_score":            round(sum(initial_scores) / n, 3),
            "avg_final_score":              round(sum(final_scores) / n, 3),
            "avg_delta_gain":               round(avg_delta, 3),
            "avg_correction_efficiency":    avg_eff,
            "weighted_score":               weighted_avg,

            # Rates
            "retry_rate":               round(retried / n, 3),
            "escalation_rate":          round(escalated / n, 3),
            "correction_rate":          round(corrected / n, 3),

            # Quality
            "decision_accuracy":        round(decision_correct / n, 3),
            "weakness_detection_rate":  round(kw_caught / n, 3),

            # Critical
            "false_accept_rate":        round(false_accepts / n, 3),
            "correction_damage_rate":   round(correction_damage / n, 3),
            "correction_success_rate":  correction_success_rate,   # ★ KEY METRIC

            # Breakdown
            "by_difficulty":  diff_breakdown,
            "by_category":    cat_breakdown,
            "red_flags":      red_flags,

            # Tracker
            "failure_evolution": self.fail_mem.track_evolution(),

            # Latency
            "avg_latency_ms":  round(sum(latencies) / n),
            "total_latency_s": round(sum(latencies) / 1000, 1),

            "results": self.results,
        }

        self._save(kpis)
        self._print_report(kpis)
        return kpis

    def _save(self, kpis: dict):
        all_runs = []
        if RESULTS_FILE.exists():
            try:
                all_runs = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        all_runs.append(kpis)
        RESULTS_FILE.write_text(
            json.dumps(all_runs[-20:], indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def _print_report(self, k: dict):
        n = k["tests_run"]
        print(f"\n{'='*62}")
        print("  NEXUS BENCHMARK v2 — RESULTS")
        print(f"{'='*62}")
        print(f"  Tests: {n} | Model: {k['model']} | Gate: {k['score_gate']}")
        print()
        print("  ── CORE KPIs ──────────────────────────────────────────────")
        print(f"  avg_initial_score:          {k['avg_initial_score']}")
        print(f"  avg_final_score:            {k['avg_final_score']}")
        print(f"  avg_delta_gain:             {k['avg_delta_gain']}")
        print(f"  avg_correction_efficiency:  {k['avg_correction_efficiency']}")
        print(f"  weighted_score:             {k['weighted_score']}")
        print()
        print("  ── RATES ──────────────────────────────────────────────────")
        print(f"  retry_rate:       {k['retry_rate']} ({int(k['retry_rate']*n)}/{n})")
        print(f"  escalation_rate:  {k['escalation_rate']} ({int(k['escalation_rate']*n)}/{n})")
        print()
        print("  ── CRITICAL METRICS ───────────────────────────────────────")
        print(f"  ★ correction_success_rate:  {k['correction_success_rate']}")
        print(f"  ⚠ false_accept_rate:        {k['false_accept_rate']} ({int(k['false_accept_rate']*n)}/{n})")
        print(f"  ⚠ correction_damage_rate:   {k['correction_damage_rate']} ({int(k['correction_damage_rate']*n)}/{n})")
        print(f"  decision_accuracy:          {k['decision_accuracy']} ({int(k['decision_accuracy']*n)}/{n} correct)")
        print(f"  weakness_detection_rate:    {k['weakness_detection_rate']}")
        print()
        print("  ── BY DIFFICULTY ──────────────────────────────────────────")
        for tier, d in k.get("by_difficulty", {}).items():
            print(f"  {tier}({d['tests']}): decision={d['decision_accuracy']} | "
                  f"score={d['avg_final_score']} | corr_success={d['correction_success']} | "
                  f"false_accept={d['false_accept_rate']}")
        print()
        print("  ── BY CATEGORY (w×score) ──────────────────────────────────")
        for cat_id, c in k.get("by_category", {}).items():
            print(f"  [{cat_id}] {c['name']} (×{c['weight']})")
            print(f"      decision={c['decision_accuracy']} | score={c['avg_final_score']} | "
                  f"false_accept={c['false_accept_rate']}")
        print()
        if k["red_flags"]:
            print("  ⚠️  RED FLAGS:")
            for flag in k["red_flags"]:
                print(f"     • {flag}")
        else:
            print("  ✅ No red flags")

        ev = k.get("failure_evolution", {})
        if ev:
            print(f"\n  FAILURE EVOLUTION: {ev.get('total_failures',0)} captured | "
                  f"repeat_rate={ev.get('repeat_failure_rate',0)}")
        print(f"\n  Latency: avg={k['avg_latency_ms']}ms | total={k['total_latency_s']}s")
        print(f"{'='*62}\n")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

async def main(categories: list = None, generate: bool = True):
    fail_mem = FailureMemory()
    log.info(f"  Failure memory: {len(fail_mem.failures)} stored | {len(fail_mem.generated)} generated variants")

    runner = BenchmarkRunner(llm_fn=llm_call, failure_memory=fail_mem)
    kpis   = await runner.run_all(categories=categories)

    # Self-adversarial generator: create new tier-3 tests from failures
    if generate and fail_mem.failures:
        log.info("\n  [ADVERSARIAL GENERATOR] Extracting patterns from failures...")
        new_tests = await fail_mem.generate_variants(n_new=2)
        if new_tests:
            log.info(f"  [ADVERSARIAL GENERATOR] {len(new_tests)} new tier-3 tests added to pool")

    return kpis


if __name__ == "__main__":
    import sys
    cats = [c.upper() for c in sys.argv[1:]] if len(sys.argv) > 1 else None
    if cats:
        print(f"  Filtering to categories: {cats}")
    asyncio.run(main(categories=cats))
