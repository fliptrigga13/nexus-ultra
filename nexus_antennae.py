"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║  NEXUS ANTENNAE — ANT COLONY COMMUNICATION PROTOCOL                          ║
║                                                                               ║
║  Each agent is a NODE with ANTENNAE.                                        ║
║  Agents communicate like ants — through PHEROMONE TRAILS left in the        ║
║  environment (blackboard = the nest). Successful paths strengthen.          ║
║  Failure paths evaporate. The colony learns as ONE.                         ║
║                                                                               ║
║  Ant Colony Mechanics:                                                       ║
║  ┌─────────────────────────────────────────────────────────────────┐        ║
║  │  [Agent Node] → deposits PHEROMONE(success_score, path_id)     │        ║
║  │  [Agent Node] → smells PHEROMONE → follows strongest trail     │        ║
║  │  [Colony]     → STIGMERGY = indirect coordination via nest     │        ║
║  │  [Quorum]     → agents vote → consensus activates behavior     │        ║
║  │  [Hive Mind]  → emergent global pattern from local signals     │        ║
║  └─────────────────────────────────────────────────────────────────┘        ║
║                                                                               ║
║  Pheromone Trails:                                                           ║
║    τ(t+1) = (1-ρ) × τ(t) + Σ Δτᵢ    (ACO update rule)                    ║
║    ρ = evaporation rate (0.08 per tick)                                     ║
║    Δτ = 1/distance (inverse of task difficulty score)                       ║
║                                                                               ║
║  100% Offline · No API · Pure stigmergic intelligence                       ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import time
import math
import random
import logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict

BASE_DIR       = Path(__file__).parent
BLACKBOARD     = BASE_DIR / "nexus_blackboard.json"
PHEROMONE_MAP  = BASE_DIR / "nexus_pheromones.json"
HIVE_MIND      = BASE_DIR / "nexus_hive_mind.json"
COLONY_LOG     = BASE_DIR / "colony.log"

TICK_INTERVAL  = 15      # seconds per colony tick
EVAPORATION    = 0.08    # ρ — pheromone decay rate per tick
MIN_PHEROMONE  = 0.01    # threshold before trail disappears
QUORUM_THRESH  = 0.6     # fraction of agents needed for consensus
MAX_TRAIL_AGE  = 200     # ticks before trail too old to matter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ANTENNAE] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(COLONY_LOG, encoding="utf-8"),
    ]
)
log = logging.getLogger("ANTENNAE")

# ── AGENT NODES ───────────────────────────────────────────────────────────────
NODES = ["SUPERVISOR", "PLANNER", "RESEARCHER", "DEVELOPER", "VALIDATOR", "REWARD"]

# ── PHEROMONE MAP (the nest environment) ──────────────────────────────────────
class PheromoneMap:
    """
    The colony's shared environment — a stigmergic field.
    Like an ant nest floor covered in chemical trails.
    Agents read and deposit here without direct communication.
    """
    def __init__(self, path: Path):
        self.path = path
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                self.trails = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self.trails = {}
        else:
            self.trails = {}
        # Init trail for every agent→agent edge (antenna connections)
        for src in NODES:
            for dst in NODES:
                key = f"{src}→{dst}"
                if key not in self.trails:
                    self.trails[key] = {"strength": 0.1, "deposits": 0, "age": 0}
        self._save()

    def _save(self):
        self.path.write_text(json.dumps(self.trails, indent=2, ensure_ascii=False), encoding="utf-8")

    def deposit(self, from_agent: str, to_agent: str, delta: float):
        """Agent deposits pheromone on path from_agent → to_agent."""
        key = f"{from_agent}→{to_agent}"
        trail = self.trails.setdefault(key, {"strength": 0.1, "deposits": 0, "age": 0})
        trail["strength"] = min(10.0, trail["strength"] + delta)
        trail["deposits"] = trail.get("deposits", 0) + 1
        trail["last_deposit"] = datetime.utcnow().isoformat()
        self._save()

    def evaporate(self):
        """Apply ACO evaporation: τ(t+1) = (1-ρ) × τ(t)"""
        changed = False
        for key, trail in list(self.trails.items()):
            old = trail["strength"]
            trail["strength"] = max(MIN_PHEROMONE, old * (1 - EVAPORATION))
            trail["age"] = trail.get("age", 0) + 1
            # Prune ancient zero-value trails
            if trail["strength"] <= MIN_PHEROMONE * 1.1 and trail.get("age", 0) > MAX_TRAIL_AGE:
                trail["strength"] = MIN_PHEROMONE  # reset but keep structure
            changed = True
        if changed:
            self._save()

    def smell(self, from_agent: str) -> dict:
        """Ant 'smells' all trails from this node — returns strengths."""
        trails = {}
        for dst in NODES:
            key = f"{from_agent}→{dst}"
            trails[dst] = self.trails.get(key, {}).get("strength", MIN_PHEROMONE)
        return trails

    def strongest_path(self, from_agent: str) -> str:
        """Find the next node with strongest pheromone trail."""
        trails = self.smell(from_agent)
        trails.pop(from_agent, None)  # don't route to self
        return max(trails.items(), key=lambda x: x[1])[0] if trails else random.choice(NODES)

    def colony_map(self) -> dict:
        """Full pheromone topology for dashboard display."""
        return {k: round(v["strength"], 4) for k, v in self.trails.items()}

# ── HIVE MIND (collective emergent intelligence) ──────────────────────────────
class HiveMind:
    """
    Shared consciousness of the colony.
    Emerges from: pheromone consensus + quorum votes + distilled lessons.
    All agents can READ this. None OWNS it. It belongs to the colony.
    """
    def __init__(self, path: Path):
        self.path = path
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                self.state = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self.state = {}
        else:
            self.state = {
                "dominant_strategy": "EXPLORE",
                "quorum_votes": {},
                "collective_rules": [],
                "total_ticks": 0,
                "colony_fitness": 0.5,
                "active_path": [],
                "signals": [],
            }
        self._save()

    def _save(self):
        self.path.write_text(json.dumps(self.state, indent=2, ensure_ascii=False), encoding="utf-8")

    def vote(self, agent: str, signal: str, confidence: float):
        """Agent casts a vote into hive consciousness."""
        votes = self.state.setdefault("quorum_votes", {})
        votes.setdefault(signal, {})[agent] = confidence
        # Check quorum
        if self._quorum_reached(signal):
            self._crystallize_rule(signal, votes[signal])
        self._save()

    def _quorum_reached(self, signal: str) -> bool:
        votes = self.state.get("quorum_votes", {}).get(signal, {})
        avg_confidence = sum(votes.values()) / len(votes) if votes else 0
        quorum_fraction = len(votes) / len(NODES)
        return quorum_fraction >= QUORUM_THRESH and avg_confidence >= 0.6

    def _crystallize_rule(self, signal: str, votes: dict):
        """Quorum reached — crystallize into permanent colony rule."""
        rule = {
            "rule": signal,
            "confidence": sum(votes.values()) / len(votes),
            "consensus_agents": list(votes.keys()),
            "crystallized": datetime.utcnow().isoformat(),
        }
        rules = self.state.setdefault("collective_rules", [])
        # Don't duplicate
        if not any(r["rule"] == signal for r in rules):
            rules.append(rule)
            rules[:] = sorted(rules, key=lambda r: r["confidence"], reverse=True)[:30]
            log.info(f"[QUORUM] Rule crystallized: '{signal}' (confidence={rule['confidence']:.2f})")
        self.state["quorum_votes"].pop(signal, None)  # clear votes
        self._save()

    def broadcast(self, agent: str, message: str):
        """Ant signals via antenna — added to colony signal buffer."""
        signals = self.state.setdefault("signals", [])
        signals.append({
            "from": agent,
            "msg": message[:200],
            "ts": datetime.utcnow().isoformat(),
        })
        # Keep last 100 signals
        self.state["signals"] = signals[-100:]
        self._save()

    def update_fitness(self, score: float):
        """EMA update of colony-wide fitness."""
        self.state["colony_fitness"] = round(
            0.8 * self.state.get("colony_fitness", 0.5) + 0.2 * score, 4
        )
        self.state["total_ticks"] = self.state.get("total_ticks", 0) + 1
        self._save()

    def get_rules(self, n: int = 5) -> list:
        return self.state.get("collective_rules", [])[:n]

    def get_strategy(self) -> str:
        fitness = self.state.get("colony_fitness", 0.5)
        if fitness < 0.4:   return "EXPLORE"   # low score → explore new paths
        elif fitness < 0.6: return "EXPLOIT"   # medium → exploit known paths
        else:                return "REFINE"    # high → refine best paths

# ── ANTENNA TICK ─────────────────────────────────────────────────────────────
async def tick(pheromones: PheromoneMap, hive: HiveMind):
    """One tick of the colony clock."""
    tick_num = hive.state.get("total_ticks", 0)
    log.info(f"[TICK {tick_num}] Strategy={hive.get_strategy()} Colony fitness={hive.state.get('colony_fitness',0.5):.3f}")

    # Read blackboard for latest swarm outputs
    bb = {}
    if BLACKBOARD.exists():
        try:
            bb = json.loads(BLACKBOARD.read_text(encoding="utf-8"))
        except Exception:
            pass

    outputs = bb.get("outputs", [])
    last_score = bb.get("last_score", 0.5)
    last_mvp   = bb.get("last_mvp", "")
    last_lesson= bb.get("last_lesson", "")

    # 1. EVAPORATE all trails
    pheromones.evaporate()

    # 2. DEPOSIT pheromones based on swarm outputs
    for i, out in enumerate(outputs[-6:]):
        agent = out.get("agent", "")
        text  = out.get("text", "")
        if not agent or agent == "MEMORY":
            continue
        # Quality estimate from output length + keywords
        quality = min(1.0, len(text) / 400.0)
        if any(kw in text for kw in ["[PASS]", "[VALIDATED]", "[SCORE:", "production", "optimized"]):
            quality = min(1.0, quality + 0.2)

        # Deposit on path to next agent and from previous
        if i > 0:
            prev_agent = outputs[-6:][i-1].get("agent", "")
            if prev_agent and prev_agent in NODES and agent in NODES:
                delta = quality / (1 + abs(i - 3))  # ACO: 1/distance
                pheromones.deposit(prev_agent, agent, delta)

        # MVP reward: deposit on all outgoing edges from MVP
        if agent == last_mvp and last_score > 0.6:
            for dst in NODES:
                pheromones.deposit(agent, dst, last_score * 0.5)
            hive.broadcast(agent, f"MVP signal deposited (score={last_score:.2f})")

    # 3. VOTE — agents cast quorum votes based on observations
    if last_lesson:
        for node in NODES:
            # Each agent "reads" the lesson and votes on a rule
            trail_strengths = pheromones.smell(node)
            strongest = max(trail_strengths.items(), key=lambda x: x[1])
            if strongest[1] > 0.5:
                signal = f"Route via {strongest[0]} for high-quality outputs"
                hive.vote(node, signal, min(1.0, strongest[1] / 2.0))

    # 4. UPDATE HIVE FITNESS
    hive.update_fitness(last_score)

    # 5. ACTIVE PATH — the colony's current best pipeline route
    active_path = []
    cursor = "SUPERVISOR"
    visited = set()
    for _ in range(len(NODES)):
        active_path.append(cursor)
        visited.add(cursor)
        nxt = pheromones.strongest_path(cursor)
        if nxt in visited:
            break
        cursor = nxt
    hive.state["active_path"] = active_path
    hive.state["dominant_strategy"] = hive.get_strategy()

    # 6. PROPAGATE back to blackboard so hub dashboard sees it
    bb["colony_pheromones"] = pheromones.colony_map()
    bb["colony_fitness"]    = hive.state.get("colony_fitness", 0.5)
    bb["colony_strategy"]   = hive.get_strategy()
    bb["active_path"]       = active_path
    bb["collective_rules"]  = hive.get_rules(5)
    bb["hive_signals"]      = hive.state.get("signals", [])[-10:]
    BLACKBOARD.write_text(json.dumps(bb, indent=2, ensure_ascii=False), encoding="utf-8")

    log.info(f"[COLONY] Active path: {' → '.join(active_path)}")
    log.info(f"[COLONY] Rules: {len(hive.state.get('collective_rules',[]))}")
    log.info(f"[COLONY] Strongest trails: {sorted(pheromones.colony_map().items(), key=lambda x:-x[1])[:3]}")

# ── MAIN ──────────────────────────────────────────────────────────────────────
async def main():
    log.info("="*60)
    log.info("🐜 NEXUS ANTENNAE — ANT COLONY PROTOCOL ONLINE")
    log.info(f"   Nodes: {NODES}")
    log.info(f"   Tick:  {TICK_INTERVAL}s")
    log.info(f"   ρ (evaporation): {EVAPORATION}")
    log.info(f"   Quorum threshold: {QUORUM_THRESH*100:.0f}%")
    log.info("="*60)

    pheromones = PheromoneMap(PHEROMONE_MAP)
    hive       = HiveMind(HIVE_MIND)

    tick_num = 0
    while True:
        tick_num += 1
        try:
            await tick(pheromones, hive)
        except Exception as e:
            log.error(f"[TICK ERROR] {e}")
        await asyncio.sleep(TICK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
