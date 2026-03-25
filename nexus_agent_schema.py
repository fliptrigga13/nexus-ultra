"""
nexus_agent_schema.py
═══════════════════════════════════════════════════════════════
Strict coordination contract for every swarm agent.

TWO RESPONSIBILITIES:
  1. lint_output(name, output)       → deterministic pass/fail
  2. build_agent_context(name, bb)   → focused upstream context

No LLM cost. No randomness. Pure rule enforcement.
═══════════════════════════════════════════════════════════════
"""

from __future__ import annotations
from dataclasses import dataclass, field


# ── SCHEMA DEFINITION ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AgentSchema:
    """
    required_tags : at least ONE must appear in the agent's output.
                    If none found → lint score = 0.0 → score capped at 0.30.
    reads_from    : list of agent names whose blackboard outputs this
                    agent receives as context. ["*"] = all agents.
    """
    required_tags: list[str]
    reads_from:    list[str]


# ── AGENT COORDINATION GRAPH ──────────────────────────────────────────────────
# Each entry defines: what output format is required + who feeds this agent.
# Changing a model or prompt never requires touching this file.

AGENT_SCHEMAS: dict[str, AgentSchema] = {

    # ── GENERATOR TIER ────────────────────────────────────────────────
    "COMMANDER": AgentSchema(
        required_tags=["[OBJECTIVE:"],
        reads_from=[],                          # leads — reads memory only
    ),
    "SCOUT": AgentSchema(
        required_tags=["[BUYER:", "[SCOUT_NULL:", "[CHANNEL_SIGNAL:"],
        reads_from=["COMMANDER"],
    ),
    "COPYWRITER": AgentSchema(
        required_tags=["[REDDIT_REPLY:", "[EMAIL:", "[DM:", "[POST_HOOK:", "[COPY_NULL:"],
        reads_from=["COMMANDER", "SCOUT"],
    ),
    "CONVERSION_ANALYST": AgentSchema(
        required_tags=["[BEST_CHANNEL:", "[CONVERSION_BLOCK:"],
        reads_from=["COMMANDER", "SCOUT"],
    ),

    # ── CRITIC TIER ───────────────────────────────────────────────────
    "VALIDATOR": AgentSchema(
        required_tags=["[EVIDENCE_CHECK:"],
        reads_from=["COMMANDER", "SCOUT", "COPYWRITER"],
    ),
    "SENTINEL_MAGNITUDE": AgentSchema(
        required_tags=["[SENTINEL_CLEAR:", "[SENTINEL_LOCKDOWN:"],
        reads_from=["COPYWRITER", "CLOSER", "VALIDATOR"],
    ),
    "METACOG": AgentSchema(
        required_tags=["[METACOG:"],
        reads_from=["COMMANDER", "SCOUT", "COPYWRITER"],
    ),
    "EXECUTIONER": AgentSchema(
        required_tags=["[EXECUTE:"],
        reads_from=["METACOG", "VALIDATOR"],
    ),

    # ── OPTIMIZER TIER ────────────────────────────────────────────────
    "SUPERVISOR": AgentSchema(
        required_tags=["[GOAL:", "[RAISE_BAR:", "[STRESS_TEST:", "[WEAK:", "[STRONG:"],
        reads_from=["*"],                       # sees everything
    ),
    "REWARD": AgentSchema(
        required_tags=["[SCORE:", "[AGENT_SCORES:"],
        reads_from=["*"],                       # evaluates everything
    ),
    "OFFER_OPTIMIZER": AgentSchema(
        required_tags=["[OFFER_STRENGTH:", "[OFFER_TWEAK:"],
        reads_from=["SCOUT", "CONVERSION_ANALYST"],
    ),
    "CLOSER": AgentSchema(
        required_tags=["[FOLLOW_UP_1:", "[CLOSE_LINE:", "[CLOSER_STANDBY:"],
        reads_from=["COPYWRITER", "SCOUT"],
    ),
}


# ── LINT ──────────────────────────────────────────────────────────────────────

def lint_output(agent_name: str, output: str) -> float:
    """
    Deterministic output validator.

    Returns 1.0  — at least one required tag is present.
    Returns 0.0  — no required tags found.
                   Callers must cap the agent's final score at 0.30.

    Unknown agents always return 1.0 (permissive default).
    """
    schema = AGENT_SCHEMAS.get(agent_name.upper())
    if schema is None:
        return 1.0
    return 1.0 if any(tag in output for tag in schema.required_tags) else 0.0


# ── FOCUSED CONTEXT BUILDER ───────────────────────────────────────────────────

def build_agent_context(agent_name: str, blackboard_outputs: dict[str, str]) -> str:
    """
    Returns a focused context string containing ONLY the outputs from
    the agents this agent reads from (per coordination graph).

    blackboard_outputs: { "SCOUT": "<output>", "COMMANDER": "<output>", ... }

    Falls back to empty string if no upstream agents have output yet.
    This keeps early-tier agents from reading stale garbage.
    """
    schema = AGENT_SCHEMAS.get(agent_name.upper())
    if schema is None:
        return ""

    if schema.reads_from == ["*"]:
        # SUPERVISOR / REWARD — see everything
        parts = [f"[{name} OUTPUT]\n{out}" for name, out in blackboard_outputs.items() if out]
    else:
        parts = [
            f"[{src} OUTPUT]\n{blackboard_outputs[src]}"
            for src in schema.reads_from
            if src in blackboard_outputs and blackboard_outputs[src]
        ]

    return "\n\n".join(parts) if parts else ""
