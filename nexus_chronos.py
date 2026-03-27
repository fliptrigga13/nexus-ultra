"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  NEXUS CHRONOS — Temporal Confidence Engine                                  ║
║                                                                              ║
║  Sits between the swarm (Ollama) and the KG (NetworkX):                     ║
║                                                                              ║
║    OLLAMA (neural inference)                                                 ║
║        ↓                                                                     ║
║    CHRONOS (decay · anticipation · arbitration · failure ingestion)          ║
║        ↓                                                                     ║
║    KG (NetworkX — facts + decay curves + DIVERGENCE_NODEs)                  ║
║        ↓                                                                     ║
║    VEILPIERCER (trace every step)                                            ║
║                                                                              ║
║  Four things no other system does simultaneously:                            ║
║  1. DECAY      — every KG fact has a half-life. Unconfirmed facts fade.     ║
║  2. ANTICIPATE — read recent drift trajectory → predict predicted_state_t+1 ║
║  3. ARBITRATE  — contradictory updates → fork node, preserve both branches  ║
║  4. INGEST     — VP session diffs → FAILURE_MEMORY nodes in KG              ║
║                                                                              ║
║  Usage:                                                                      ║
║    from nexus_chronos import get_chronos                                     ║
║    ch = get_chronos(kg)                                                      ║
║    ch.tick()                      # decay all stale facts                   ║
║    ch.reconfirm("PAIN:privacy")   # agent cited this node → reset clock     ║
║    ch.ingest_vp_diffs()           # pipe VP session diffs → KG              ║
║    ok = ch.cost_gate(action_fn)   # utility check before EXECUTOR fires     ║
║    pred = ch.predict_trajectory() # anticipated KG state next cycle         ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import json
import logging
import math
import re
import sqlite3
import time
from datetime import datetime, UTC, timedelta
from pathlib import Path
from typing import Optional, Callable, Any

import networkx as nx

# ── CONFIG ────────────────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).parent
VP_DB          = BASE_DIR / "vp_sessions.db"           # VeilPiercer session DB
CHRONOS_LOG    = BASE_DIR / "nexus_chronos.log"

DEFAULT_HALF_LIFE  = 72.0   # hours — standard fact half-life
MIN_CONFIDENCE     = 0.05   # facts never fully die, just become very uncertain
DECAY_TICK_SECS    = 300    # run decay sweep every 5 minutes (background)
FORK_SIMILARITY    = 0.80   # conflict threshold — above this, merge; below, fork
COST_GATE_THRESH   = 0.35   # utility must exceed this for EXECUTOR to fire

# ── LOGGING ───────────────────────────────────────────────────────────────────
log = logging.getLogger("CHRONOS")
log.setLevel(logging.INFO)
if not log.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s [CHRONOS] %(message)s"))
    log.addHandler(h)


# ══════════════════════════════════════════════════════════════════════════════
# DECAY ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def decay_confidence(
    confidence:     float,
    last_confirmed: str,
    half_life_hours: float = DEFAULT_HALF_LIFE,
    now: Optional[datetime] = None,
) -> float:
    """
    Exponential half-life decay:
        C(t) = C0 * 0.5^(Δt / half_life)

    A fact with confidence=0.95 and half_life=72h will be at:
        0.95 → 0.475 after 72h
        0.95 → 0.238 after 144h
        0.95 → 0.119 after 216h
    """
    if now is None:
        now = datetime.now(UTC)
    try:
        ts = datetime.fromisoformat(last_confirmed)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return max(MIN_CONFIDENCE, confidence * 0.5)   # unknown age → one half-life penaly

    hours_elapsed = max(0.0, (now - ts).total_seconds() / 3600.0)
    decayed = confidence * (0.5 ** (hours_elapsed / max(half_life_hours, 0.1)))
    return max(MIN_CONFIDENCE, round(decayed, 6))


def new_node_decay_fields(
    confidence: float = 0.95,
    half_life_hours: float = DEFAULT_HALF_LIFE,
) -> dict:
    """Return decay metadata fields for a freshly created KG node."""
    return {
        "confidence":      confidence,
        "last_confirmed":  datetime.now(UTC).isoformat(),
        "half_life_hours": half_life_hours,
    }


# ══════════════════════════════════════════════════════════════════════════════
# DIVERGENCE INGESTER — VP session diffs → FAILURE_MEMORY nodes
# ══════════════════════════════════════════════════════════════════════════════

class DivergenceIngester:
    """
    Reads VeilPiercer session DB and pipes divergences into the KG
    as FAILURE_MEMORY nodes.

    A divergence is any pair of sessions running the same agent with
    the same state_version that produced measurably different outputs.
    Stored in KG as:
        {
          type:       "FAILURE_MEMORY"
          agent:      "COPYWRITER"
          fork_step:  42
          condition:  "<sha256 of prompt>"
          outcome_a:  "<first response[:200]>"
          outcome_b:  "<second response[:200]>"
          confidence: 0.80
          ts:         "<iso timestamp>"
        }
    """

    def __init__(self, G: nx.DiGraph):
        self.G = G
        self._last_ingested_rowid = 0
        self._load_watermark()

    def _load_watermark(self):
        """Remember where we left off so we don't re-ingest old diffs."""
        marker_key = "_chronos_last_rowid"
        if self.G.has_node(marker_key):
            self._last_ingested_rowid = self.G.nodes[marker_key].get("rowid", 0)

    def _save_watermark(self):
        marker_key = "_chronos_last_rowid"
        if not self.G.has_node(marker_key):
            self.G.add_node(marker_key, type="meta")
        self.G.nodes[marker_key]["rowid"] = self._last_ingested_rowid

    def ingest(self) -> int:
        """
        Query VP session DB for new divergences and write them as
        FAILURE_MEMORY nodes to the KG. Returns count ingested.
        """
        if not VP_DB.exists():
            log.debug("VP DB not found — skipping divergence ingestion")
            return 0

        ingested = 0
        try:
            conn = sqlite3.connect(str(VP_DB))
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # Find sessions with same agent + state_version but different outputs
            # (those are genuine divergences)
            cur.execute("""
                SELECT
                    a.rowid        AS rowid_a,
                    a.agent        AS agent,
                    a.session_id   AS session_a,
                    b.session_id   AS session_b,
                    a.state_version AS state_ver,
                    a.response     AS response_a,
                    b.response     AS response_b,
                    a.prompt       AS prompt,
                    a.created_at   AS ts
                FROM vp_sessions a
                JOIN vp_sessions b
                    ON  a.agent         = b.agent
                    AND a.state_version = b.state_version
                    AND a.session_id   != b.session_id
                    AND a.rowid         > ?
                WHERE a.response != b.response
                  AND a.response IS NOT NULL
                  AND b.response IS NOT NULL
                ORDER BY a.rowid ASC
                LIMIT 50
            """, (self._last_ingested_rowid,))

            rows = cur.fetchall()
            conn.close()

            for row in rows:
                node_id = (
                    f"DIVERGENCE:{row['agent']}:"
                    f"{row['state_ver']}:"
                    f"{int(time.time()*1000) % 999999}"
                )
                prompt_hash = _short_hash(str(row["prompt"] or ""))
                # Find the original KG fact this divergence traces back to
                # by matching prompt hash against known condition fields
                original_fact_id = next(
                    (nid for nid, d in self.G.nodes(data=True)
                     if d.get("condition") == prompt_hash
                     or _short_hash(str(d.get("label", ""))) == prompt_hash),
                    None
                )
                self.G.add_node(node_id, **{
                    "type":             "FAILURE_MEMORY",
                    "agent":            row["agent"],
                    "fork_step":        row["state_ver"],
                    "condition":        prompt_hash,
                    "outcome_a":        str(row["response_a"] or "")[:200],
                    "outcome_b":        str(row["response_b"] or "")[:200],
                    "session_a":        row["session_a"],
                    "session_b":        row["session_b"],
                    "original_fact_id": original_fact_id,   # traceability link
                    "confidence":       0.80,
                    "last_confirmed":   row["ts"] or datetime.now(UTC).isoformat(),
                    "half_life_hours":  168.0,   # failure memory lives 7 days
                    "ts":               row["ts"] or datetime.now(UTC).isoformat(),
                })
                # Link back to original fact if found
                if original_fact_id and self.G.has_node(original_fact_id):
                    self.G.add_edge(node_id, original_fact_id,
                                    relation="traces_back_to", weight=1)
                self._last_ingested_rowid = max(self._last_ingested_rowid, row["rowid_a"])
                ingested += 1
                log.info(
                    f"  [DIVERGENCE] agent={row['agent']} "
                    f"state={row['state_ver']} original_fact={original_fact_id} "
                    f"-> node {node_id}"
                )

            self._save_watermark()

        except Exception as e:
            log.warning(f"  VP divergence ingestion error (non-fatal): {e}")

        if ingested:
            log.info(f"  Ingested {ingested} VP divergence(s) as FAILURE_MEMORY nodes")
        return ingested

    def ingest_manual(
        self,
        agent: str,
        prompt: str,
        response_a: str,
        response_b: str,
        confidence: float = 0.80,
        original_fact_id: Optional[str] = None,
    ) -> str:
        """
        Manually register a divergence when you have two responses
        to the same prompt. Returns the node_id created.
        original_fact_id: the KG node this failure traces back to.
        """
        node_id = f"DIVERGENCE:{agent}:{_short_hash(prompt)}:{int(time.time())}"
        self.G.add_node(node_id, **{
            "type":             "FAILURE_MEMORY",
            "agent":            agent,
            "fork_step":        0,
            "condition":        _short_hash(prompt),
            "outcome_a":        response_a[:200],
            "outcome_b":        response_b[:200],
            "original_fact_id": original_fact_id,
            "confidence":       confidence,
            "last_confirmed":   datetime.now(UTC).isoformat(),
            "half_life_hours":  168.0,
            "ts":               datetime.now(UTC).isoformat(),
        })
        if original_fact_id and self.G.has_node(original_fact_id):
            self.G.add_edge(node_id, original_fact_id,
                            relation="traces_back_to", weight=1)
        log.info(f"  [DIVERGENCE] Manual ingestion: {node_id} -> fact={original_fact_id}")
        return node_id


# ══════════════════════════════════════════════════════════════════════════════
# CONFLICT ARBITER — fork nodes for contradictory swarm updates
# ══════════════════════════════════════════════════════════════════════════════

class ConflictArbiter:
    """
    When two swarm agents produce contradictory KG updates for the same node,
    instead of merging (which destroys information), create a FORK node:

        PAIN:privacy         (original)
             ├── FORK:A      (agent SCOUT's version, confidence=0.82)
             └── FORK:B      (agent SUPERVISOR's version, confidence=0.75)

    Higher-confidence branch wins but both are preserved.
    VeilPiercer can diff the forks. Full auditability.
    """

    def __init__(self, G: nx.DiGraph):
        self.G = G

    def maybe_fork(
        self,
        node_id:    str,
        agent_a:    str,
        value_a:    dict,
        agent_b:    str,
        value_b:    dict,
    ) -> Optional[str]:
        """
        Create a fork if the two proposed node values are contradictory.
        Returns the ID of the winning branch node, or None if merged cleanly.
        """
        # Compute simple textual similarity as conflict detector
        text_a = json.dumps(value_a, sort_keys=True)
        text_b = json.dumps(value_b, sort_keys=True)
        sim = _text_similarity(text_a, text_b)

        if sim >= FORK_SIMILARITY:
            # Close enough — merge by taking higher-confidence version
            conf_a = value_a.get("confidence", 0.5)
            conf_b = value_b.get("confidence", 0.5)
            winner = value_a if conf_a >= conf_b else value_b
            if self.G.has_node(node_id):
                self.G.nodes[node_id].update(winner)
            log.debug(f"  [ARBITER] Merged {node_id} (sim={sim:.2f} ≥ {FORK_SIMILARITY})")
            return None

        # Significant contradiction — fork it
        ts = datetime.now(UTC).isoformat()
        fork_a = f"FORK:{node_id}:{agent_a}:{int(time.time())}"
        fork_b = f"FORK:{node_id}:{agent_b}:{int(time.time())+1}"

        conf_a = value_a.get("confidence", 0.5)
        conf_b = value_b.get("confidence", 0.5)
        # Weighted fork confidence: mean of both branches.
        # Low mean = weak disagreement (auto-resolvable).
        # High mean = both agents are confident but contradicting — strong conflict.
        fork_confidence = round((conf_a + conf_b) / 2, 4)

        self.G.add_node(fork_a, **{
            **value_a,
            "type":            "FORK_NODE",
            "origin_agent":    agent_a,
            "fork_of":         node_id,
            "fork_confidence": fork_confidence,
            "ts":              ts,
        })
        self.G.add_node(fork_b, **{
            **value_b,
            "type":            "FORK_NODE",
            "origin_agent":    agent_b,
            "fork_of":         node_id,
            "fork_confidence": fork_confidence,
            "ts":              ts,
        })

        # Link forks to original node
        if self.G.has_node(node_id):
            self.G.add_edge(node_id, fork_a, relation="fork_branch", weight=1)
            self.G.add_edge(node_id, fork_b, relation="fork_branch", weight=1)

        # Winner = higher individual confidence branch
        winner_id = fork_a if conf_a >= conf_b else fork_b
        log.info(
            f"  [ARBITER] FORK created for {node_id} "
            f"(sim={sim:.2f}, fork_confidence={fork_confidence:.3f}, winner={winner_id})"
        )
        return winner_id


# ══════════════════════════════════════════════════════════════════════════════
# COST GATE — utility check before EXECUTOR fires
# ══════════════════════════════════════════════════════════════════════════════

class CostGate:
    """
    Symbolic utility gate.  Before EXECUTOR commits any action:
        utility(action) = expected_value - action_cost - env_degradation_risk
    Only fires if utility > COST_GATE_THRESH.

    Costs are estimated from KG state — number of FAILURE_MEMORY nodes
    for the relevant agent, current confidence of target nodes, recent
    METACOG verdicts.
    """

    def __init__(self, G: nx.DiGraph):
        self.G = G

    def evaluate(
        self,
        action_description: str,
        expected_value:     float = 0.7,
        agent:              str   = "UNKNOWN",
    ) -> dict:
        """
        Evaluate whether an action should fire.

        Returns dict with:
            approved: bool
            utility:  float
            reason:   str
        """
        # --- Cost factors ---

        # 1. Failure rate for this agent (from FAILURE_MEMORY nodes)
        agent_failures = sum(
            1 for _, d in self.G.nodes(data=True)
            if d.get("type") == "FAILURE_MEMORY"
            and d.get("agent", "").upper() == agent.upper()
        )
        failure_penalty = min(0.4, agent_failures * 0.05)   # caps at 0.40

        # 2. Low-confidence context (how stale is the surrounding KG?)
        all_confs = [
            d.get("confidence", 1.0)
            for _, d in self.G.nodes(data=True)
            if d.get("type") not in ("FAILURE_MEMORY", "FORK_NODE", "meta")
            and "confidence" in d
        ]
        avg_confidence = sum(all_confs) / max(len(all_confs), 1)
        staleness_cost = (1.0 - avg_confidence) * 0.3   # penalty for stale KG

        # 3. Recent METACOG signal
        meta_nodes = sorted(
            [(n, d) for n, d in self.G.nodes(data=True) if d.get("type") == "metacog"],
            key=lambda x: x[1].get("cycle", ""),
            reverse=True
        )
        recent_verdict = meta_nodes[0][1].get("label", "SHARP") if meta_nodes else "SHARP"
        meta_penalty = {"SHARP": 0.0, "SHALLOW": 0.10, "DRIFT": 0.20, "LOOP": 0.35}.get(
            recent_verdict, 0.10
        )

        # --- Utility ---
        total_cost = failure_penalty + staleness_cost + meta_penalty
        utility = round(expected_value - total_cost, 4)

        approved = utility >= COST_GATE_THRESH
        reason = (
            f"utility={utility:.3f} "
            f"[expected={expected_value:.2f} "
            f"- failures={failure_penalty:.2f} "
            f"- staleness={staleness_cost:.2f} "
            f"- metacog={meta_penalty:.2f}={recent_verdict}]"
        )

        log.info(f"  [COST_GATE] action='{action_description[:40]}' "
                 f"agent={agent} → {'APPROVED' if approved else 'DEFERRED'} | {reason}")

        return {
            "approved": approved,
            "utility":  utility,
            "reason":   reason,
            "verdict":  "APPROVED" if approved else "DEFERRED",
        }

    def gate(
        self,
        action_fn:          Callable,
        action_description: str = "",
        agent:              str = "UNKNOWN",
        expected_value:     float = 0.7,
    ) -> Optional[Any]:
        """
        Gate wrapper. Runs the cost check; if approved, executes action_fn.
        Returns action result or None if deferred.
        """
        result = self.evaluate(action_description, expected_value, agent)
        if result["approved"]:
            return action_fn()
        log.warning(
            f"  [COST_GATE] DEFERRED — {action_description[:60]} | {result['reason']}"
        )
        return None


# ══════════════════════════════════════════════════════════════════════════════
# TRAJECTORY PREDICTOR — anticipate where the KG is heading
# ══════════════════════════════════════════════════════════════════════════════

class TrajectoryPredictor:
    """
    Reads the last N cycle embeddings (drift sequence) and extrapolates
    where the graph is heading. Agents receive predicted_state_t+1
    alongside current_state so they can act ahead of the change.

    Uses simple linear extrapolation of cosine drift scores
    (no GPU, no external model needed).
    """

    def __init__(self, cycle_embeddings: list[dict]):
        self.embeddings = cycle_embeddings

    def predict_drift(self, window: int = 5) -> dict:
        """
        Extrapolate drift trajectory from last N cycles.
        Returns:
            trend:          "ACCELERATING" | "STABLE" | "DECELERATING"
            predicted_drift: float (expected drift in next cycle)
            signal:         str (human-readable)
        """
        drifts = [e.get("drift", 0.0) for e in self.embeddings[-window:]]
        if len(drifts) < 2:
            return {
                "trend": "STABLE",
                "predicted_drift": 0.0,
                "signal": "[CHRONOS_TRAJ: insufficient history for prediction]",
            }

        # Linear regression on drift values
        n = len(drifts)
        x = list(range(n))
        mean_x = sum(x) / n
        mean_y = sum(drifts) / n
        num = sum((x[i] - mean_x) * (drifts[i] - mean_y) for i in range(n))
        den = sum((x[i] - mean_x) ** 2 for i in range(n)) or 1e-9
        slope = num / den

        predicted = max(0.0, mean_y + slope * 1)   # t+1 prediction

        if slope > 0.005:
            trend = "ACCELERATING"
            signal = (
                f"[CHRONOS_TRAJ: drift ACCELERATING slope={slope:.4f} "
                f"predicted_next={predicted:.3f} — explore new territory]"
            )
        elif slope < -0.005:
            trend = "DECELERATING"
            signal = (
                f"[CHRONOS_TRAJ: drift DECELERATING slope={slope:.4f} "
                f"predicted_next={predicted:.3f} — consolidate, don't pivot]"
            )
        else:
            trend = "STABLE"
            signal = (
                f"[CHRONOS_TRAJ: drift STABLE slope={slope:.4f} "
                f"predicted_next={predicted:.3f} — current channel is optimal]"
            )

        return {
            "trend": trend,
            "predicted_drift": round(predicted, 4),
            "signal": signal,
        }

    def get_context_line(self) -> str:
        """Single-line trajectory for injection into agent context."""
        pred = self.predict_drift()
        return pred["signal"]


# ══════════════════════════════════════════════════════════════════════════════
# MAIN CLASS — Chronos
# ══════════════════════════════════════════════════════════════════════════════

class Chronos:
    """
    Temporal confidence engine for the NEXUS knowledge graph.

    Wraps an existing NexusKnowledgeGraph instance and adds:
    - Decay sweep (tick)
    - Node re-confirmation
    - VP divergence ingestion
    - Conflict fork arbitration
    - Cost gate for EXECUTOR
    - Trajectory prediction
    """

    def __init__(self, kg):
        """
        Args:
            kg: NexusKnowledgeGraph instance (from nexus_knowledge_graph.py)
        """
        self.kg     = kg
        self.G      = kg.G
        self.ingester  = DivergenceIngester(self.G)
        self.arbiter   = ConflictArbiter(self.G)
        self.cost_gate = CostGate(self.G)
        self._predictor: Optional[TrajectoryPredictor] = None
        self._last_tick = 0.0
        self._decayed_count = 0
        self._patch_existing_nodes()
        log.info(
            f"✅ CHRONOS online — "
            f"{self.G.number_of_nodes()} nodes patched with decay fields"
        )

    def _patch_existing_nodes(self):
        """Add decay fields to any nodes that were created before CHRONOS."""
        now_iso = datetime.now(UTC).isoformat()
        patched = 0
        for node_id, data in self.G.nodes(data=True):
            if "confidence" not in data:
                data["confidence"]      = 0.90
                data["last_confirmed"]  = now_iso
                data["half_life_hours"] = DEFAULT_HALF_LIFE
                patched += 1
        if patched:
            log.info(f"  Patched {patched} existing nodes with decay metadata")

    # ── DECAY SWEEP ─────────────────────────────────────────────────────────

    def tick(self, force: bool = False) -> dict:
        """
        Run a full decay sweep across all KG nodes.
        Updates confidence based on elapsed time since last_confirmed.
        Only runs if DECAY_TICK_SECS have elapsed (or force=True).

        Returns stats: {swept, decayed, faded (below 0.3), unchanged}
        """
        now = time.time()
        if not force and (now - self._last_tick) < DECAY_TICK_SECS:
            return {}   # too soon

        self._last_tick = now
        dt_now = datetime.now(UTC)
        stats = {"swept": 0, "decayed": 0, "faded": 0, "unchanged": 0}

        for node_id, data in self.G.nodes(data=True):
            if data.get("type") in ("meta",):
                continue
            old_conf = data.get("confidence", 1.0)
            last_c   = data.get("last_confirmed", dt_now.isoformat())
            half_l   = data.get("half_life_hours", DEFAULT_HALF_LIFE)

            new_conf = decay_confidence(old_conf, last_c, half_l, dt_now)
            stats["swept"] += 1

            if abs(new_conf - old_conf) > 0.001:
                data["confidence"] = new_conf
                stats["decayed"] += 1
                if new_conf < 0.30:
                    stats["faded"] += 1
                    log.debug(f"  [DECAY] FADED: {node_id} conf={new_conf:.3f}")
            else:
                stats["unchanged"] += 1

        self._decayed_count += stats["decayed"]
        if stats["decayed"]:
            log.info(
                f"  [DECAY] tick: swept={stats['swept']} "
                f"decayed={stats['decayed']} faded={stats['faded']}"
            )
            # Persist the KG after decay
            try:
                self.kg._save()
            except Exception:
                pass

        return stats

    # ── RE-CONFIRMATION ──────────────────────────────────────────────────────

    def reconfirm(self, node_id: str, confidence_boost: float = 0.0) -> bool:
        """
        Agent cited or validated a KG node → reset its clock.
        Optionally boost confidence (e.g., after strong EVIDENCE_CHECK: PASS).
        Returns True if node was found and confirmed.
        """
        if not self.G.has_node(node_id):
            return False

        data = self.G.nodes[node_id]
        data["last_confirmed"] = datetime.now(UTC).isoformat()
        if confidence_boost > 0:
            data["confidence"] = min(1.0, data.get("confidence", 0.5) + confidence_boost)
        log.debug(f"  [RECONFIRM] {node_id} conf={data['confidence']:.3f}")
        return True

    def reconfirm_by_label(self, label_fragment: str, boost: float = 0.05) -> int:
        """
        Reconfirm all nodes whose label contains label_fragment.
        Use when an agent output mentions a concept — refresh those nodes.
        Returns count reconfirmed.
        """
        confirmed = 0
        frag = label_fragment.lower()
        for node_id, data in self.G.nodes(data=True):
            lbl = str(data.get("label", "") + data.get("type", "")).lower()
            if frag in lbl:
                self.reconfirm(node_id, boost)
                confirmed += 1
        return confirmed

    # ── DIVERGENCE INGESTION ─────────────────────────────────────────────────

    def ingest_vp_diffs(self) -> int:
        """
        Pull new VP session divergences and write as FAILURE_MEMORY nodes.
        Returns count of new divergence nodes created.
        """
        count = self.ingester.ingest()
        if count:
            try:
                self.kg._save()
            except Exception:
                pass
        return count

    def ingest_manual_divergence(
        self,
        agent: str,
        prompt: str,
        response_a: str,
        response_b: str,
        confidence: float = 0.80,
    ) -> str:
        """Register a manually observed divergence. Returns node_id."""
        node_id = self.ingester.ingest_manual(agent, prompt, response_a, response_b, confidence)
        try:
            self.kg._save()
        except Exception:
            pass
        return node_id

    # ── CONFLICT ARBITRATION ─────────────────────────────────────────────────

    def arbitrate(
        self,
        node_id: str,
        agent_a: str,
        value_a: dict,
        agent_b: str,
        value_b: dict,
    ) -> Optional[str]:
        """
        Resolve a conflict between two agent updates to the same KG node.
        Returns winner node_id (forked) or None (merged).
        """
        result = self.arbiter.maybe_fork(node_id, agent_a, value_a, agent_b, value_b)
        try:
            self.kg._save()
        except Exception:
            pass
        return result

    # ── COST GATE ────────────────────────────────────────────────────────────

    def gate(
        self,
        action_fn:          Callable,
        action_description: str   = "",
        agent:              str   = "UNKNOWN",
        expected_value:     float = 0.7,
    ) -> Optional[Any]:
        """Gate an action through the cost/utility check."""
        return self.cost_gate.gate(action_fn, action_description, agent, expected_value)

    def evaluate_action(
        self,
        action_description: str,
        agent: str = "UNKNOWN",
        expected_value: float = 0.7,
    ) -> dict:
        """Evaluate utility without executing. Returns {approved, utility, reason}."""
        return self.cost_gate.evaluate(action_description, expected_value, agent)

    # ── TRAJECTORY PREDICTION ────────────────────────────────────────────────

    def predict_trajectory(self) -> str:
        """
        Predict KG drift trajectory for next cycle.
        Returns a single-line context string for injection into SUPERVISOR.
        """
        embeddings = getattr(self.kg, "_cycle_embeddings", [])
        pred = TrajectoryPredictor(embeddings)
        return pred.get_context_line()

    # ── SUPERVISOR CONTEXT ───────────────────────────────────────────────────

    def get_chronos_context(self, min_confidence: float = 0.30) -> str:
        """
        Generate CHRONOS-specific context lines for SUPERVISOR injection.
        Complements kg.get_supervisor_context() with temporal data.
        """
        parts = []

        # Trajectory
        traj = self.predict_trajectory()
        if traj:
            parts.append(traj)

        # Faded facts (low confidence) — signal to re-verify
        faded = [
            (nid, d) for nid, d in self.G.nodes(data=True)
            if d.get("type") not in ("FAILURE_MEMORY", "FORK_NODE", "meta")
            and d.get("confidence", 1.0) < min_confidence
        ]
        if faded:
            faded_labels = ", ".join(
                d.get("label", nid)[:30] for nid, d in faded[:3]
            )
            parts.append(
                f"[CHRONOS_FADED: {len(faded)} facts below {min_confidence:.0%} confidence "
                f"— needs re-verification: {faded_labels}]"
            )

        # Failure memory summary
        failures = [
            d for _, d in self.G.nodes(data=True)
            if d.get("type") == "FAILURE_MEMORY"
        ]
        if failures:
            agents = {}
            for f in failures:
                a = f.get("agent", "?")
                agents[a] = agents.get(a, 0) + 1
            agent_str = " | ".join(f"{k}:{v}" for k, v in sorted(agents.items()))
            parts.append(
                f"[CHRONOS_FAILURES: {len(failures)} divergence(s) in memory "
                f"— by agent: {agent_str}]"
            )

        # Fork nodes (unresolved conflicts)
        forks = sum(1 for _, d in self.G.nodes(data=True) if d.get("type") == "FORK_NODE")
        if forks:
            parts.append(f"[CHRONOS_FORKS: {forks} unresolved conflict fork(s) in KG]")

        return "\n".join(parts) if parts else ""

    # ── STATS ────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Return CHRONOS engine statistics."""
        nodes = list(self.G.nodes(data=True))
        confs = [d.get("confidence", 1.0) for _, d in nodes if "confidence" in d]
        failures = sum(1 for _, d in nodes if d.get("type") == "FAILURE_MEMORY")
        forks    = sum(1 for _, d in nodes if d.get("type") == "FORK_NODE")
        faded    = sum(1 for c in confs if c < 0.30)

        return {
            "nodes_total":       len(nodes),
            "nodes_with_decay":  len(confs),
            "avg_confidence":    round(sum(confs) / max(len(confs), 1), 4),
            "faded_nodes":       faded,
            "failure_memories":  failures,
            "fork_nodes":        forks,
            "decay_runs":        int(self._decayed_count),
            "last_tick_ago_s":   round(time.time() - self._last_tick, 1),
        }


# ── SINGLETON ─────────────────────────────────────────────────────────────────

_chronos_instance: Optional[Chronos] = None

def get_chronos(kg=None) -> Optional[Chronos]:
    """
    Return singleton CHRONOS instance.
    Pass kg on first call; subsequent calls can omit it.
    """
    global _chronos_instance
    if _chronos_instance is None:
        if kg is None:
            return None
        _chronos_instance = Chronos(kg)
    return _chronos_instance


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _short_hash(text: str) -> str:
    """Fast non-cryptographic hash for prompt fingerprinting."""
    import hashlib
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]


def _text_similarity(a: str, b: str) -> float:
    """
    Jaccard word-overlap similarity. Fast, offline, no embeddings needed.
    Returns 0.0 (no overlap) to 1.0 (identical).
    """
    wa = set(re.findall(r'\w+', a.lower()))
    wb = set(re.findall(r'\w+', b.lower()))
    if not wa and not wb:
        return 1.0
    intersection = wa & wb
    union = wa | wb
    return len(intersection) / max(len(union), 1)


# ══════════════════════════════════════════════════════════════════════════════
# STANDALONE TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 70)
    print("NEXUS CHRONOS — SELF TEST")
    print("=" * 70)

    from nexus_knowledge_graph import get_kg
    kg = get_kg()
    ch = Chronos(kg)

    print("\n-- Stats after init --")
    for k, v in ch.get_stats().items():
        print(f"  {k}: {v}")

    print("\n-- Force decay tick --")
    stats = ch.tick(force=True)
    print(f"  Decay: {stats}")

    print("\n-- Re-confirm a node --")
    nodes = list(kg.G.nodes())
    if nodes:
        test_node = nodes[0]
        ok = ch.reconfirm(test_node, confidence_boost=0.05)
        print(f"  Reconfirmed {test_node}: {ok}")

    print("\n-- Trajectory prediction --")
    traj = ch.predict_trajectory()
    print(f"  {traj}")

    print("\n-- Cost gate evaluation --")
    result = ch.evaluate_action(
        action_description="Post Reddit reply about VeilPiercer to r/selfhosted",
        agent="COPYWRITER",
        expected_value=0.75,
    )
    for k, v in result.items():
        print(f"  {k}: {v}")

    print("\n-- Manual divergence ingestion --")
    node_id = ch.ingest_manual_divergence(
        agent="COPYWRITER",
        prompt="Write a Reddit reply about VeilPiercer for privacy-focused developers.",
        response_a="Running local models for privacy makes sense...",
        response_b="Privacy is critical for AI workflows. VeilPiercer...",
        confidence=0.78,
    )
    print(f"  Created: {node_id}")

    print("\n-- CHRONOS context (for SUPERVISOR) --")
    ctx = ch.get_chronos_context()
    print(ctx if ctx else "  (no context yet — run more cycles)")

    print("\n-- VP diffs ingestion --")
    n = ch.ingest_vp_diffs()
    print(f"  Ingested {n} divergence(s) from VP session DB")

    print("\n-- Final stats --")
    for k, v in ch.get_stats().items():
        print(f"  {k}: {v}")

    print("\n" + "=" * 70)
