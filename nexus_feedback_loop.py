"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  NEXUS FEEDBACK LOOP — Feedback · Decision · Self-Correction                 ║
║                                                                              ║
║  Wraps any LLM agent call with 3 explicit stages:                           ║
║                                                                              ║
║  ① FEEDBACK     — CRITIC evaluates output on 4 dimensions                   ║
║                   [SCORE] [STRENGTH] [WEAKNESS] [SPECIFIC_FIX]              ║
║                                                                              ║
║  ② DECISION     — Rules engine decides what to do                           ║
║                   ACCEPT   → score >= threshold, no critical weakness        ║
║                   RETRY    → score < threshold, specific fix available       ║
║                   ESCALATE → repeated failure, human/supervisor needed       ║
║                                                                              ║
║  ③ SELF-CORRECT — On RETRY, agent receives own output + critique            ║
║                   and rewrites. Max 2 correction attempts.                   ║
║                                                                              ║
║  All 3 stages are logged + written to nexus_fdc_log.json for traceability.  ║
║                                                                              ║
║  Usage:                                                                      ║
║    from nexus_feedback_loop import FeedbackLoop, FDCResult                  ║
║    fdc = FeedbackLoop(llm_fn=my_async_llm_call)                             ║
║    result = await fdc.run("COPYWRITER", system_prompt, user_prompt, context) ║
║    result.decision  # ACCEPT | RETRY | ESCALATE                             ║
║    result.output    # final accepted output after correction if needed      ║
║    result.trace     # full trace of all stages                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Awaitable

BASE_DIR  = Path(__file__).parent
FDC_LOG   = BASE_DIR / "nexus_fdc_log.json"
FDC_STATS = BASE_DIR / "nexus_fdc_stats.json"

log = logging.getLogger("FDC")
log.setLevel(logging.INFO)
if not log.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s [FDC] %(message)s"))
    log.addHandler(h)


# ══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Feedback:
    """Structured evaluation of an agent's output."""
    score:       float          # 0.0 – 1.0
    strengths:   list[str]      # what the output did well
    weaknesses:  list[str]      # what is wrong / missing
    specific_fix: str           # exact instruction for self-correction
    raw:         str = ""       # raw critic output

@dataclass
class FDCResult:
    """Complete trace of one Feedback→Decision→Correction cycle."""
    agent:          str
    task_context:   str
    attempt:        int         # 1 = first try, 2+ = correction attempt
    original_output: str        # agent output before correction
    feedback:       Feedback
    decision:       str         # ACCEPT | RETRY | ESCALATE
    final_output:   str         # output after correction (or original if accepted)
    correction_applied: bool = False
    correction_delta: str = ""  # what changed between original and corrected
    latency_ms:     int = 0
    ts:             str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["feedback"] = asdict(self.feedback)
        return d


# ══════════════════════════════════════════════════════════════════════════════
# CRITIC SYSTEM PROMPT
# ══════════════════════════════════════════════════════════════════════════════

CRITIC_SYSTEM = """You are a STRICT CRITIC evaluating an AI agent's output.
You evaluate in exactly this format — NO markdown, NO backticks, NO bold, plain text only:

[SCORE: 0.XX]
[STRENGTH: one specific thing done well]
[WEAKNESS: one specific thing that is wrong or missing]
[FIX: exact instruction to improve, max 20 words]

Rules:
- SCORE 0.0-1.0 only. 0.65+ means acceptable. Below = must correct.
- STRENGTH must be concrete ("em-dash used correctly" not "good tone").
- WEAKNESS must name the specific failure (e.g. "contains em-dash", "fabricated username", "ends on question", "no CTA").
- FIX must be actionable in one sentence starting with a verb.
- If output is empty or [LLM_ERROR], score 0.0, FIX = "Retry with shorter prompt."
- Output ONLY the 4 bracketed lines. Nothing before. Nothing after. No markdown."""


CORRECTION_SYSTEM = """You are rewriting your previous output based on critique.
Apply the fix instruction exactly. Keep what was strong. Fix what was weak.
Output ONLY the corrected reply — no explanation, no preamble."""


# ══════════════════════════════════════════════════════════════════════════════
# DECISION ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class DecisionEngine:
    """
    Rules-based decision from feedback score + history.

    ACCEPT   → score >= threshold  AND  no critical failure detected
    RETRY    → score < threshold   AND  attempt < max_attempts
    ESCALATE → repeated failure    OR   critical safety violation
    """

    # Hard escalate — use whole-word regex to avoid substring false positives
    # e.g. 'defi' must not match 'definition', 'crypto' must not match 'cryptography'
    CRITICAL_FAILURE_PATTERNS = [
        r'\bfabricated username\b',
        r'\bfabricated reddit\b',
        r'\bhallucinated username\b',
        r'\binvented feature\b',
        r'\bwrong product category\b',
        r'\bwrong product positioning\b',
        r'\bpositions veilpiercer as\b',
        r'\bcrypto\b',          # whole word: won't match 'cryptography'
        r'\bdefi\b',            # whole word: won't match 'definition', 'specify'
        r'\bpricing error\b',
    ]
    # Legacy list kept for identity check in context-sensitive logic
    CRITICAL_FAILURES = [p.strip(r'\b') for p in CRITICAL_FAILURE_PATTERNS]

    # Constraint violations — fixable formatting errors that must always RETRY,
    # regardless of overall quality score. An em-dash in an otherwise great
    # comment should NEVER be accepted — it's a hard rule violation.
    CONSTRAINT_VIOLATION_PATTERNS = [
        r'em.dash',             # em-dash / em dash / emdash
        r'contains.*—',         # literal em-dash character in weakness
        r'banned',              # 'contains banned word/phrase'
        r'\bprohibited\b',      # prohibited term/character
        r'\bnot allowed\b',
        r'word.?limit',         # exceeds word limit / word count limit
        r'too long',            # output too long
        r'over \d+ words',      # over N words
        r'word count',          # word count exceeded
        r'fabricated url',      # invented links
        r'\bspam\b',            # flagged as spam-like
        r'no product name',     # failed to include product name when required
    ]

    def __init__(self, accept_threshold: float = 0.65, max_attempts: int = 2):
        self.accept_threshold = accept_threshold
        self.max_attempts     = max_attempts

    def decide(self, feedback: Feedback, attempt: int,
               history: list["Feedback"], agent_output: str = "") -> str:
        """
        Returns: ACCEPT | RETRY | ESCALATE

        Logic:
        1. Critical failure in weakness → ESCALATE (with output verification for username claims)
        2. Score >= threshold → ACCEPT
        3. Attempt >= max → ESCALATE (can't keep looping)
        4. Otherwise → RETRY with specific fix
        """
        weakness_lower = " ".join(feedback.weaknesses).lower()

        # Rule 1: Hard escalate — critical content errors (whole-word regex matching)
        for pattern in self.CRITICAL_FAILURE_PATTERNS:
            if re.search(pattern, weakness_lower, re.IGNORECASE):
                # Context-sensitive: username fabrication requires actual u/ or @ in output
                if "username" in pattern or "hallucinated" in pattern:
                    if re.search(r'\bu/\w+|@\w+', agent_output, re.IGNORECASE):
                        log.warning(f"  ⚠️  ESCALATE — verified username fabrication in output")
                        return "ESCALATE"
                    # else: critic hallucinated this — skip
                else:
                    log.warning(f"  ⚠️  ESCALATE — critical failure: '{pattern}' detected")
                    return "ESCALATE"

        # Rule 1.5: Constraint violation — force RETRY even if score >= threshold.
        # These are hard formatting rules that must be obeyed regardless of quality.
        # E.g. a great comment with an em-dash scores 0.85 but MUST be retried.
        for pattern in self.CONSTRAINT_VIOLATION_PATTERNS:
            if re.search(pattern, weakness_lower, re.IGNORECASE):
                log.warning(f"  🚫 CONSTRAINT VIOLATION — force RETRY: '{pattern}' in weakness")
                return "RETRY"

        # Rule 2: Accept if above threshold AND no violations detected
        if feedback.score >= self.accept_threshold:
            return "ACCEPT"

        # Rule 3: Max attempts reached
        if attempt >= self.max_attempts:
            log.warning(f"  ⚠️  ESCALATE — max attempts ({self.max_attempts}) reached")
            return "ESCALATE"

        # Rule 4: Retry with fix
        return "RETRY"



# ══════════════════════════════════════════════════════════════════════════════
# FEEDBACK PARSER
# ══════════════════════════════════════════════════════════════════════════════

def parse_feedback(raw: str) -> Feedback:
    """Parse CRITIC output into structured Feedback. Handles markdown/bold/spacing variants."""
    # Normalise: strip bold markers, backticks, extra whitespace
    text = re.sub(r'[*`_]', '', raw).strip()

    # Try to find SCORE — handles [SCORE: 0.75], SCORE: 0.75, Score: 0.75, etc.
    score_m = re.search(
        r'\[?SCORE:?\s*([01]?\.\d+)\]?', text, re.IGNORECASE
    )
    # Fallback: first standalone decimal in response
    if not score_m:
        score_m = re.search(r'\b(0\.\d{1,2}|1\.0+)\b', text)

    strength_m = re.search(
        r'\[?STRENGTH:?\s*(.+?)\]?(?=\n|\[|$)', text, re.IGNORECASE | re.DOTALL
    )
    weakness_m = re.search(
        r'\[?WEAKNESS:?\s*(.+?)\]?(?=\n|\[|$)', text, re.IGNORECASE | re.DOTALL
    )
    fix_m = re.search(
        r'\[?FIX:?\s*(.+?)\]?(?=\n|\[|$)', text, re.IGNORECASE | re.DOTALL
    )

    score       = float(score_m.group(1)) if score_m else 0.3
    strength    = [strength_m.group(1).strip()[:120]] if strength_m else ["(no strength identified)"]
    weakness    = [weakness_m.group(1).strip()[:120]] if weakness_m else ["(no weakness identified)"]
    specific_fix = fix_m.group(1).strip()[:120] if fix_m else "Rewrite with more specificity."

    # Safety: clamp score
    score = min(1.0, max(0.0, score))

    return Feedback(
        score=score,
        strengths=strength,
        weaknesses=weakness,
        specific_fix=specific_fix,
        raw=raw,
    )


# ══════════════════════════════════════════════════════════════════════════════
# DIFF HELPER
# ══════════════════════════════════════════════════════════════════════════════

def _delta_summary(original: str, corrected: str) -> str:
    """Quick summary of what changed between original and corrected output."""
    orig_words = set(original.lower().split())
    corr_words = set(corrected.lower().split())
    added   = corr_words - orig_words
    removed = orig_words - corr_words
    parts = []
    if added:
        parts.append(f"+{len(added)} words")
    if removed:
        parts.append(f"-{len(removed)} words")
    length_diff = len(corrected) - len(original)
    parts.append(f"length {'+' if length_diff >= 0 else ''}{length_diff} chars")
    return " | ".join(parts) if parts else "minimal change"


# ══════════════════════════════════════════════════════════════════════════════
# FEEDBACK LOOP
# ══════════════════════════════════════════════════════════════════════════════

class FeedbackLoop:
    """
    Main orchestrator: runs FEEDBACK → DECISION → SELF-CORRECTION cycle.

    Parameters:
        llm_fn:   async fn(system: str, user: str, max_tokens: int) -> str
        critic_model: which model to use for the CRITIC (default: same as agent)
        accept_threshold: minimum score to accept (default: 0.65)
        max_attempts: max correction attempts before ESCALATE (default: 2)
    """

    def __init__(
        self,
        llm_fn: Callable[..., Awaitable[str]],
        critic_fn: Optional[Callable[..., Awaitable[str]]] = None,
        accept_threshold: float = 0.65,
        max_attempts: int = 2,
    ):
        self.llm_fn    = llm_fn
        # critic_fn: separate LLM for CRITIC (e.g. Ollama) to avoid Gemini RPM limits
        # If None, falls back to llm_fn
        self.critic_fn = critic_fn or llm_fn
        self.decision  = DecisionEngine(accept_threshold, max_attempts)
        self._history: list[FDCResult] = []
        self._load_log()
        log.info("✅ FeedbackLoop online")

    def _load_log(self):
        if FDC_LOG.exists():
            try:
                existing = json.loads(FDC_LOG.read_text(encoding="utf-8"))
                log.info(f"  📋 {len(existing)} previous FDC cycles loaded")
            except Exception:
                pass

    def _append_log(self, result: FDCResult):
        existing = []
        if FDC_LOG.exists():
            try:
                existing = json.loads(FDC_LOG.read_text(encoding="utf-8"))
            except Exception:
                pass
        existing.append(result.to_dict())
        # Keep last 200 cycles
        existing = existing[-200:]
        FDC_LOG.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        self._update_stats(result)

    def _update_stats(self, result: FDCResult):
        stats = {}
        if FDC_STATS.exists():
            try:
                stats = json.loads(FDC_STATS.read_text(encoding="utf-8"))
            except Exception:
                pass

        stats.setdefault("total", 0)
        stats.setdefault("accepted", 0)
        stats.setdefault("retried", 0)
        stats.setdefault("escalated", 0)
        stats.setdefault("corrected", 0)
        stats.setdefault("avg_score", 0.0)
        stats.setdefault("avg_latency_ms", 0)

        stats["total"] += 1
        if result.decision == "ACCEPT":
            stats["accepted"] += 1
        elif result.decision == "RETRY":
            stats["retried"] += 1
        elif result.decision == "ESCALATE":
            stats["escalated"] += 1
        if result.correction_applied:
            stats["corrected"] += 1

        # Rolling avg score
        n = stats["total"]
        stats["avg_score"] = round(
            (stats["avg_score"] * (n - 1) + result.feedback.score) / n, 4
        )
        stats["avg_latency_ms"] = round(
            (stats["avg_latency_ms"] * (n - 1) + result.latency_ms) / n
        )
        stats["last_updated"] = datetime.now(timezone.utc).isoformat()

        FDC_STATS.write_text(
            json.dumps(stats, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    async def _evaluate(self, agent: str, output: str, context: str) -> Feedback:
        """Run CRITIC evaluation on agent output using critic_fn (Ollama-safe)."""
        critic_user = f"""AGENT: {agent}
TASK CONTEXT: {context[:200]}

AGENT OUTPUT TO EVALUATE:
{output[:800]}

Evaluate the output strictly."""

        raw = await self.critic_fn(CRITIC_SYSTEM, critic_user, max_tokens=120)
        # Debug: show raw output so we can see format issues
        log.info(f"    [CRITIC RAW] {repr(raw[:150])}")
        feedback = parse_feedback(raw)

        log.info(
            f"  ① FEEDBACK [{agent}] score={feedback.score:.2f} "
            f"| strength: {feedback.strengths[0][:50]} "
            f"| weakness: {feedback.weaknesses[0][:50]}"
        )
        return feedback

    async def _correct(self, agent: str, system: str, original_output: str,
                       feedback: Feedback, context: str) -> str:
        """Run self-correction: agent rewrites with critique included."""
        correction_user = f"""TASK CONTEXT: {context[:200]}

YOUR PREVIOUS OUTPUT:
{original_output[:600]}

CRITIC FEEDBACK:
- Score: {feedback.score:.2f}
- Strength (keep this): {feedback.strengths[0]}
- Weakness (fix this): {feedback.weaknesses[0]}
- Specific fix: {feedback.specific_fix}

Now rewrite the output applying the fix exactly."""

        corrected = await self.llm_fn(
            CORRECTION_SYSTEM + "\n\n" + system,
            correction_user,
            max_tokens=300
        )
        log.info(f"  ③ SELF-CORRECT [{agent}] → rewrote output")
        return corrected

    async def run(
        self,
        agent: str,
        system: str,
        user: str,
        context: str = "",
        initial_output: Optional[str] = None,
    ) -> FDCResult:
        """
        Run the full Feedback→Decision→Correction cycle.

        Parameters:
            agent:   name of the agent (for logging)
            system:  agent's system prompt
            user:    user/task prompt
            context: task context string (used by CRITIC)
            initial_output: if already have output, skip first LLM call

        Returns FDCResult with full trace.
        """
        t_start = time.time()
        feedback_history: list[Feedback] = []

        # ── Step 1: Get initial output ─────────────────────────────────────
        if initial_output is not None:
            output = initial_output
            attempt = 1
        else:
            output = await self.llm_fn(system, user, 300)
            attempt = 1

        log.info(f"\n{'='*50}")
        log.info(f"  FDC CYCLE [{agent}] attempt #{attempt}")

        # ── Step 2: FEEDBACK ──────────────────────────────────────────────
        feedback = await self._evaluate(agent, output, context or user[:200])
        feedback_history.append(feedback)

        # ── Step 3: DECISION ──────────────────────────────────────────────
        decision = self.decision.decide(feedback, attempt, feedback_history, agent_output=output)
        log.info(f"  ② DECISION [{agent}] → {decision} (score={feedback.score:.2f})")

        original_output = output
        correction_applied = False
        correction_delta = ""

        # ── Step 4: SELF-CORRECT if RETRY ─────────────────────────────────
        while decision == "RETRY":
            attempt += 1
            log.info(f"  ③ CORRECTING [{agent}] attempt #{attempt}...")

            corrected = await self._correct(agent, system, output, feedback, context or user[:200])
            correction_delta = _delta_summary(output, corrected)
            output = corrected
            correction_applied = True

            # Re-evaluate corrected output
            feedback = await self._evaluate(agent, output, context or user[:200])
            feedback_history.append(feedback)

            # Re-decide
            decision = self.decision.decide(feedback, attempt, feedback_history, agent_output=output)
            log.info(f"  ② RE-DECISION [{agent}] → {decision} (score={feedback.score:.2f})")

        latency = int((time.time() - t_start) * 1000)

        # ── Build result ───────────────────────────────────────────────────
        result = FDCResult(
            agent=agent,
            task_context=(context or user)[:200],
            attempt=attempt,
            original_output=original_output,
            feedback=feedback,
            decision=decision,
            final_output=output,
            correction_applied=correction_applied,
            correction_delta=correction_delta,
            latency_ms=latency,
            ts=datetime.now(timezone.utc).isoformat(),
        )

        self._append_log(result)
        self._history.append(result)

        # ── WRITE SIGNAL TO BLACKBOARD ─────────────────────────────────────
        # Evolution, Mycelium, Colony all read from here.
        # Without this, every subsystem defaults to 0.5 forever.
        try:
            from pathlib import Path as _Path
            import json as _json
            _bb_path = _Path(__file__).parent / "nexus_blackboard.json"
            _bb = {}
            if _bb_path.exists():
                try:
                    _bb = _json.loads(_bb_path.read_text(encoding="utf-8"))
                except Exception:
                    _bb = {}
            _lesson_str = (feedback.weaknesses[0] if feedback.weaknesses else "") or ""
            _bb["last_score"]    = round(float(feedback.score), 4)
            _bb["last_mvp"]      = agent if decision == "ACCEPT" else _bb.get("last_mvp", "")
            _bb["last_lesson"]   = _lesson_str
            _bb["last_agent"]    = agent
            _bb["last_decision"] = decision
            _bb["last_fdc_ts"]   = result.ts
            _outputs = _bb.get("outputs", [])
            _outputs.append({"agent": agent, "text": output[:300], "score": feedback.score})
            _bb["outputs"] = _outputs[-12:]
            _bb_path.write_text(_json.dumps(_bb, indent=2, ensure_ascii=False), encoding="utf-8")
            log.debug(f"  📡 Blackboard: score={feedback.score:.2f} mvp={_bb['last_mvp']}")
        except Exception as _bb_err:
            log.warning(f"  ⚠️  Blackboard write failed: {_bb_err}")

        # Print clean summary
        status_icon = {"ACCEPT": "✅", "RETRY": "🔄", "ESCALATE": "⚠️"}.get(decision, "?")
        log.info(
            f"  {status_icon} FDC COMPLETE [{agent}] "
            f"decision={decision} | score={feedback.score:.2f} | "
            f"corrected={correction_applied} | {latency}ms"
        )
        if correction_applied:
            log.info(f"     delta: {correction_delta}")
        log.info(f"{'='*50}\n")

        return result


    def get_stats(self) -> dict:
        """Return aggregated statistics across all cycles."""
        if FDC_STATS.exists():
            try:
                return json.loads(FDC_STATS.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def get_recent(self, n: int = 10) -> list[dict]:
        """Return last N FDC cycle traces."""
        if FDC_LOG.exists():
            try:
                logs = json.loads(FDC_LOG.read_text(encoding="utf-8"))
                return logs[-n:]
            except Exception:
                pass
        return []


# ══════════════════════════════════════════════════════════════════════════════
# DEMO / STANDALONE RUN
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import httpx as _httpx

    OLLAMA = "http://127.0.0.1:11434"
    MODEL  = "deepseek-r1:14b"

    async def _demo_llm(system: str, user: str, max_tokens: int = 300) -> str:
        async with _httpx.AsyncClient(timeout=90.0) as client:
            r = await client.post(f"{OLLAMA}/api/chat", json={
                "model": MODEL, "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                "options": {"num_predict": max_tokens, "temperature": 0.7}
            })
            return r.json().get("message", {}).get("content", "[NO OUTPUT]")

    async def demo():
        print("=" * 60)
        print("NEXUS FEEDBACK LOOP — DEMO")
        print("Testing Feedback → Decision → Self-Correction")
        print("=" * 60)

        fdc = FeedbackLoop(llm_fn=_demo_llm, accept_threshold=0.65, max_attempts=2)

        # Simulate a COPYWRITER output that needs correction
        task_context = (
            "Reddit thread in r/LocalLLaMA: 'How do you debug Ollama agent pipelines? "
            "My agent runs fine for first 3 tool calls then silently returns wrong data.'"
        )

        copywriter_system = """You are COPYWRITER for VeilPiercer. Write a helpful Reddit reply.
Rules: no em-dashes, no questions at end, max 4 sentences, technical and direct.
Always end with: pip install veilpiercer"""

        copywriter_user = f"""Write a reply to this thread:
{task_context}

The reply should mention that VeilPiercer captures per-step state diffs and shows
exactly where the output diverged from expected."""

        print("\n[RUNNING FDC CYCLE ON COPYWRITER OUTPUT...]\n")
        result = await fdc.run(
            agent="COPYWRITER",
            system=copywriter_system,
            user=copywriter_user,
            context=task_context,
        )

        print("\n── RESULT ──────────────────────────────────────")
        print(f"  DECISION:  {result.decision}")
        print(f"  SCORE:     {result.feedback.score:.2f}")
        print(f"  ATTEMPTS:  {result.attempt}")
        print(f"  CORRECTED: {result.correction_applied}")
        if result.correction_applied:
            print(f"  DELTA:     {result.correction_delta}")
        print(f"\n  FINAL OUTPUT:\n{result.final_output}")

        print("\n── FDC STATS ────────────────────────────────────")
        stats = fdc.get_stats()
        for k, v in stats.items():
            print(f"  {k}: {v}")

    asyncio.run(demo())
