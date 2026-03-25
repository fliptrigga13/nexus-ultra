"""
vp_session_logger.py — VeilPiercer Session Logger
══════════════════════════════════════════════════
Logs every agent prompt/response step to a vp_sessions table in nexus_mind.db.
Attaches state_version to each step so divergence can be detected automatically.

Usage (import into any agent):
    from vp_session_logger import SessionLogger
    sess = SessionLogger(session_id="my-run-001", agent="EXECUTIONER")
    sess.log_step(prompt="...", response="...", state_version="v3")
    sess.close()

Or use the context manager:
    with SessionLogger.new("EXECUTIONER") as sess:
        sess.log_step(prompt=p, response=r, state_version="v3")

Standalone test:
    python vp_session_logger.py --demo
"""

import sqlite3
import uuid
import logging
import argparse
from datetime import datetime, UTC
from pathlib import Path

BASE   = Path(__file__).parent
DB     = BASE / "nexus_mind.db"
log    = logging.getLogger("VP-SESSION")


# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS vp_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT    NOT NULL,
    agent           TEXT    NOT NULL DEFAULT 'UNKNOWN',
    step_index      INTEGER NOT NULL DEFAULT 0,
    state_version   TEXT    NOT NULL DEFAULT 'v0',
    prompt          TEXT    NOT NULL DEFAULT '',
    response        TEXT    NOT NULL DEFAULT '',
    model           TEXT    DEFAULT '',
    latency_ms      INTEGER DEFAULT 0,
    created_at      TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sess_id  ON vp_sessions(session_id);
CREATE INDEX IF NOT EXISTS idx_sess_ver ON vp_sessions(state_version);
CREATE INDEX IF NOT EXISTS idx_sess_agent ON vp_sessions(agent, created_at);
"""


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    for stmt in SCHEMA.strip().split(";"):
        s = stmt.strip()
        if s:
            conn.execute(s)
    conn.commit()
    return conn


# ── Session Logger ────────────────────────────────────────────────────────────

class SessionLogger:
    """Log one agent run as an ordered sequence of steps."""

    def __init__(self, session_id: str = None, agent: str = "UNKNOWN"):
        self.session_id = session_id or f"sess-{uuid.uuid4().hex[:12]}"
        self.agent      = agent
        self.step       = 0
        self._conn      = _get_conn()
        log.info(f"[SESSION] Started {self.session_id} agent={agent}")

    @classmethod
    def new(cls, agent: str = "UNKNOWN") -> "SessionLogger":
        """Auto-generate a session ID."""
        return cls(agent=agent)

    def log_step(
        self,
        prompt: str,
        response: str,
        state_version: str = "v0",
        model: str = "",
        latency_ms: int = 0,
    ):
        """
        Append one step to this session.

        state_version: the version tag of the context/state that was read
                       BEFORE generating this response.  Two sessions that
                       share the same state_version on a given step diverged
                       from the same base — that's the branch point.
        """
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """
            INSERT INTO vp_sessions
                (session_id, agent, step_index, state_version,
                 prompt, response, model, latency_ms, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                self.session_id,
                self.agent,
                self.step,
                state_version,
                prompt[:8000],     # cap to avoid bloat
                response[:8000],
                model,
                latency_ms,
                now,
            ),
        )
        self._conn.commit()
        self.step += 1
        log.debug(f"[SESSION] {self.session_id} step={self.step-1} ver={state_version}")

    def close(self):
        self._conn.close()
        log.info(f"[SESSION] Closed {self.session_id} ({self.step} steps)")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# ── Query Helpers (used by the diff dashboard API) ────────────────────────────

def list_sessions(limit: int = 50) -> list[dict]:
    """Return a summary of recent sessions (for the session picker UI)."""
    conn = _get_conn()
    rows = conn.execute("""
        SELECT
            session_id,
            agent,
            MIN(created_at) AS started_at,
            MAX(created_at) AS ended_at,
            COUNT(*)        AS steps
        FROM vp_sessions
        GROUP BY session_id
        ORDER BY started_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [
        {
            "session_id": r[0],
            "agent":      r[1],
            "started_at": r[2],
            "ended_at":   r[3],
            "steps":      r[4],
        }
        for r in rows
    ]


def get_session_steps(session_id: str) -> list[dict]:
    """Return all steps for one session, ordered by step_index."""
    conn = _get_conn()
    rows = conn.execute("""
        SELECT step_index, state_version, prompt, response, model,
               latency_ms, created_at
        FROM vp_sessions
        WHERE session_id = ?
        ORDER BY step_index
    """, (session_id,)).fetchall()
    conn.close()
    return [
        {
            "step":          r[0],
            "state_version": r[1],
            "prompt":        r[2],
            "response":      r[3],
            "model":         r[4],
            "latency_ms":    r[5],
            "created_at":    r[6],
        }
        for r in rows
    ]


def find_divergence(session_a: str, session_b: str) -> dict:
    """
    Compare two sessions step-by-step.
    Returns the first step where they read a DIFFERENT state_version
    from a previously SHARED state_version — the branch point.
    """
    steps_a = get_session_steps(session_a)
    steps_b = get_session_steps(session_b)

    min_len    = min(len(steps_a), len(steps_b))
    last_shared = None
    fork_step   = None

    for i in range(min_len):
        va = steps_a[i]["state_version"]
        vb = steps_b[i]["state_version"]
        if va == vb:
            last_shared = va
        else:
            fork_step = i
            break

    return {
        "session_a":    session_a,
        "session_b":    session_b,
        "steps_a":      steps_a,
        "steps_b":      steps_b,
        "fork_step":    fork_step,
        "last_shared":  last_shared,
        "diverged":     fork_step is not None,
    }


# ── Demo seeder ───────────────────────────────────────────────────────────────

def seed_demo():
    """Seed two demo sessions that diverge at step 2 for testing."""
    import time

    print("Seeding demo sessions...")

    with SessionLogger("demo-session-A", agent="EXECUTIONER") as s:
        s.log_step("What is the current market signal?",
                   "Detected high buyer intent on r/LocalLLaMA", state_version="v1")
        s.log_step("Should we post to HN?",
                   "Yes — thread about local debugging has 200+ points", state_version="v2")
        s.log_step("Draft the HN comment.",
                   "VeilPiercer gives you full session traceability...", state_version="v3a")
        time.sleep(0.1)

    with SessionLogger("demo-session-B", agent="EXECUTIONER") as s:
        s.log_step("What is the current market signal?",
                   "Spotted competitor move: BaseGrid added branch diffs", state_version="v1")
        s.log_step("Should we post to HN?",
                   "Yes — respond to the debugging agent thread", state_version="v2")
        s.log_step("Draft the HN comment.",
                   "The blind spot in most agent stacks is state visibility...", state_version="v3b")
        time.sleep(0.1)

    result = find_divergence("demo-session-A", "demo-session-B")
    print(f"\nDivergence detected: {result['diverged']}")
    print(f"Fork at step:        {result['fork_step']}")
    print(f"Last shared version: {result['last_shared']}")
    print(f"\nSession A step {result['fork_step']}: {result['steps_a'][result['fork_step']]['state_version']}")
    print(f"Session B step {result['fork_step']}: {result['steps_b'][result['fork_step']]['state_version']}")
    print("\nDemo sessions seeded. Open vp_session_diff.html to view the diff.")

    sessions = list_sessions(10)
    print(f"\nAll sessions in DB ({len(sessions)}):")
    for s in sessions:
        print(f"  {s['session_id']} | {s['agent']} | {s['steps']} steps | {s['started_at']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="Seed demo sessions")
    args = parser.parse_args()
    if args.demo:
        seed_demo()
    else:
        print("Usage: python vp_session_logger.py --demo")
        print("Or import SessionLogger into your agent code.")
