"""
nexus_milestones.py
═══════════════════════════════════════════════════════════════
Milestone-guided task management for the NEXUS swarm.

Replaces the static/random task string with structured goals.
Redis-backed. Seeds 3 launch milestones on first run.

INTEGRATION in nexus_swarm_loop.py:
    from nexus_milestones import MilestoneTracker, get_tracker
    _milestone_tracker = get_tracker()

    # In run_swarm_cycle():
    milestone = _milestone_tracker.get_active()
    task      = milestone.task_prompt
    context   = _milestone_tracker.build_context(mem_core, milestone.id)

    # Every 100 cycles:
    _milestone_tracker.compress_memories(mem_core, milestone.id)
    mem_core.decay()
═══════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict

log = logging.getLogger("MILESTONES")

# ── DATACLASS ─────────────────────────────────────────────────────────────────

@dataclass
class Milestone:
    id:                str
    name:              str
    task_prompt:       str          # injected directly as the cycle task string
    success_condition: str          # human-readable — checked manually or via signal
    priority:          int          # 1 = highest; lower number = runs first
    status:            str          # ACTIVE | COMPLETE | PAUSED
    memory_tags:       list[str] = field(default_factory=list)


# ── SEEDED LAUNCH MILESTONES ──────────────────────────────────────────────────

_LAUNCH_MILESTONES: list[Milestone] = [
    Milestone(
        id               = "FIRST_CUSTOMER",
        name             = "First Paying Customer",
        task_prompt      = (
            "Find ONE named person or community member who is ready to pay $197 "
            "for VeilPiercer TODAY. Produce paste-ready outreach (Reddit reply, "
            "DM, or email) addressed specifically to them. Reference their exact "
            "pain point. No generic copy."
        ),
        success_condition= "Stripe payment confirmed OR user reports first sale",
        priority         = 1,
        status           = "ACTIVE",
        memory_tags      = ["sales", "scout", "copywriter", "closer", "first_customer"],
    ),
    Milestone(
        id               = "PH_TOP_50",
        name             = "Product Hunt Top 50",
        task_prompt      = (
            "Drive upvotes on https://www.producthunt.com/posts/veilpiercer RIGHT NOW. "
            "Find 3 specific communities, subreddits, or Discord servers where AI agent "
            "users are active today. Produce a ready-to-post message for each. "
            "Prioritise r/LocalLLaMA, r/ollama, and Hacker News."
        ),
        success_condition= "producthunt.com shows position <= 50",
        priority         = 2,
        status           = "ACTIVE",
        memory_tags      = ["ph", "upvotes", "launch", "ph_top_50"],
    ),
    Milestone(
        id               = "FIND_COLLAB",
        name             = "Find a Growth Collaborator",
        task_prompt      = (
            "Find a growth-focused collaborator on r/cofounder, Indie Hackers, or "
            "YC co-founder matching. They must have distribution/marketing experience "
            "and be open to equity or rev-share. Produce a personalised DM ready to send."
        ),
        success_condition= "Collaborator replies and agrees to join",
        priority         = 3,
        status           = "ACTIVE",
        memory_tags      = ["collab", "growth", "cofounder", "find_collab"],
    ),
]


# ── MILESTONE TRACKER ─────────────────────────────────────────────────────────

class MilestoneTracker:
    """
    Redis-backed milestone manager.
    Falls back to in-memory dict if Redis is unavailable.
    """

    _REDIS_KEY = "nexus:milestones"

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._local: dict[str, Milestone] = {}
        self._seed()

    # ── SEED ──────────────────────────────────────────────────────────

    def _seed(self) -> None:
        """Load from Redis (or local). Seed defaults if empty."""
        existing = self._load_all()
        if existing:
            self._local = existing
            log.info(f"[MILESTONE] Loaded {len(existing)} milestones from store")
            return

        for m in _LAUNCH_MILESTONES:
            self._local[m.id] = m
        self._save_all()
        log.info(f"[MILESTONE] Seeded {len(_LAUNCH_MILESTONES)} launch milestones")

    # ── CRUD ──────────────────────────────────────────────────────────

    def get_active(self) -> Milestone:
        """Return the highest-priority ACTIVE milestone."""
        active = [m for m in self._local.values() if m.status == "ACTIVE"]
        if not active:
            # All complete — loop back to priority 1
            log.warning("[MILESTONE] All milestones complete — resetting to FIRST_CUSTOMER")
            self._local["FIRST_CUSTOMER"].status = "ACTIVE"
            self._save_all()
            return self._local["FIRST_CUSTOMER"]
        return min(active, key=lambda m: m.priority)

    def complete(self, milestone_id: str) -> None:
        """Mark a milestone complete. Next cycle picks up the next priority."""
        if milestone_id in self._local:
            self._local[milestone_id].status = "COMPLETE"
            self._save_all()
            nxt = self.get_active()
            log.info(f"[MILESTONE] ✅ COMPLETE: {milestone_id} → Next: {nxt.id}")

    def pause(self, milestone_id: str) -> None:
        if milestone_id in self._local:
            self._local[milestone_id].status = "PAUSED"
            self._save_all()
            log.info(f"[MILESTONE] ⏸ PAUSED: {milestone_id}")

    def resume(self, milestone_id: str) -> None:
        if milestone_id in self._local:
            self._local[milestone_id].status = "ACTIVE"
            self._save_all()
            log.info(f"[MILESTONE] ▶ RESUMED: {milestone_id}")

    def list_all(self) -> list[Milestone]:
        return sorted(self._local.values(), key=lambda m: m.priority)

    # ── CONTEXT BUILDER ───────────────────────────────────────────────

    def build_context(self, mem_core, milestone_id: str, top_k: int = 5) -> str:
        """
        Return a focused memory injection string scoped to this milestone.
        Uses tags_filter so only milestone-relevant memories are surfaced.
        """
        milestone = self._local.get(milestone_id)
        if milestone is None:
            return ""

        tag_query = " ".join(milestone.memory_tags)
        try:
            return mem_core.build_injection(
                query=milestone.task_prompt,
                top_k=top_k,
                tags_filter=milestone_id.lower(),
            )
        except TypeError:
            # Fallback if tags_filter not yet patched into memory core
            return mem_core.build_injection(query=milestone.task_prompt, top_k=top_k)

    # ── MEMORY COMPRESSION ────────────────────────────────────────────

    def compress_memories(self, mem_core, milestone_id: str) -> int:
        """
        Archive low-importance memories tagged to this milestone.
        Keeps the top-3 by importance; archives the rest below threshold.
        Returns number of memories archived.
        """
        milestone = self._local.get(milestone_id)
        if milestone is None:
            return 0

        # Pull all active memories tagged to this milestone
        try:
            rows = mem_core.conn.execute(
                """SELECT id, importance FROM memories
                   WHERE archived=0 AND tags LIKE ?
                   ORDER BY importance DESC""",
                (f"%{milestone_id.lower()}%",)
            ).fetchall()
        except Exception as e:
            log.warning(f"[MILESTONE] compress_memories query failed: {e}")
            return 0

        if len(rows) <= 3:
            return 0  # nothing to compress

        # Keep top-3, archive the rest below importance threshold
        to_archive = [row[0] for row in rows[3:] if row[1] < 4.0]
        for mem_id in to_archive:
            mem_core.archive(mem_id)

        if to_archive:
            log.info(f"[MILESTONE] Compressed {len(to_archive)} memories for {milestone_id}")
        return len(to_archive)

    # ── PERSISTENCE ───────────────────────────────────────────────────

    def _load_all(self) -> dict[str, Milestone]:
        try:
            if self._redis:
                raw = self._redis.get(self._REDIS_KEY)
                if raw:
                    data = json.loads(raw)
                    return {k: Milestone(**v) for k, v in data.items()}
        except Exception as e:
            log.warning(f"[MILESTONE] Redis load failed: {e}")
        return {}

    def _save_all(self) -> None:
        try:
            if self._redis:
                payload = {k: asdict(v) for k, v in self._local.items()}
                self._redis.set(self._REDIS_KEY, json.dumps(payload))
        except Exception as e:
            log.warning(f"[MILESTONE] Redis save failed (in-memory only): {e}")


# ── SINGLETON ─────────────────────────────────────────────────────────────────

_tracker: MilestoneTracker | None = None


def get_tracker(redis_client=None) -> MilestoneTracker:
    global _tracker
    if _tracker is None:
        _tracker = MilestoneTracker(redis_client)
    return _tracker
