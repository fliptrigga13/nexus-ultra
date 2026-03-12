"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║  NEXUS MYCELIUM — MYCORRHIZAL THOUGHT WEB                                   ║
║                                                                               ║
║  Inspired by: Physarum polycephalum (slime mold) + mycorrhizal networks     ║
║                                                                               ║
║  KEY DIFFERENCES FROM nexus_antennae.py (pheromones):                      ║
║                                                                               ║
║  PHEROMONES (antennae):          MYCELIUM (this):                          ║
║  ─────────────────────────────   ─────────────────────────────────────     ║
║  Push-deposit + evaporate        PULL-based (sinks draw nutrients)          ║
║  Unidirectional trails           BIDIRECTIONAL hyphal flow                  ║
║  Fixed 6×6 topology              STRUCTURAL GROWTH/PRUNING (edges born+die) ║
║  Short-term memory (evaporates)  PERSISTENT consolidation (grows stronger)  ║
║  No resource cost                NUTRIENT ACCOUNTING (nodes earn/spend)     ║
║  No new nodes                    EMERGENT BRIDGE NODES (relay hyphae)       ║
║                                                                               ║
║  ALGORITHM:                                                                  ║
║  1. REWARD score → inject nutrient into MVP agent node                      ║
║  2. Sink-pull: hungry (low-nutrient) nodes draw flow toward themselves       ║
║  3. Flux updates bidirectional edge weights (Hagen-Poiseuille analogy)      ║
║  4. Hebbian growth: heavily-used paths thicken (r += α × flow²)            ║
║  5. Anti-Hebbian pruning: unused paths thin (r -= β per tick)               ║
║  6. Bridge emergence: when 2 non-adjacent co-activate → fuse relay node     ║
║  7. Write mycelial state to blackboard + bias file for evolution engine     ║
║                                                                               ║
║  Two timescales:                                                             ║
║  PSO   = fast numerical weight tuning (seconds, REWARD→GPU)                 ║
║  Mycelium = slow structural topology tuning (minutes, REWARD→graph)         ║
║                                                                               ║
║  100% Offline · No API · Pure graph dynamics                                ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import math
import random
import logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict

BASE_DIR       = Path(__file__).parent
BLACKBOARD     = BASE_DIR / "nexus_blackboard.json"
MYCELIUM_FILE  = BASE_DIR / "nexus_mycelium.json"
BIAS_FILE      = BASE_DIR / "nexus_mycelium_bias.json"
MYCELIUM_LOG   = BASE_DIR / "mycelium.log"

# ── TIMING ────────────────────────────────────────────────────────────────────
TICK_INTERVAL  = 20          # seconds per tick
FLOW_STEPS     = 8           # Hagen-Poiseuille iterations per tick

# ── GROWTH / DECAY PARAMETERS ─────────────────────────────────────────────────
ALPHA          = 0.12        # Hebbian growth rate (used path thickens)
BETA           = 0.015       # Anti-Hebbian decay (unused path thins)
MIN_RADIUS     = 0.05        # Minimum hyphal radius before pruning
MAX_RADIUS     = 5.0         # Maximum hyphal thickness
BRIDGE_THRESH  = 0.65        # Co-activation score to spawn bridge node
MAX_BRIDGES    = 4           # Maximum bridge nodes at once

# ── BASE AGENT NODES ──────────────────────────────────────────────────────────
BASE_NODES = ["SUPERVISOR", "PLANNER", "RESEARCHER", "DEVELOPER", "VALIDATOR", "REWARD"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MYCELIUM] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(MYCELIUM_LOG, encoding="utf-8"),
    ]
)
log = logging.getLogger("MYCELIUM")


# ══════════════════════════════════════════════════════════════════════════════
# HYPHAL GRAPH — the mycelial network structure
# ══════════════════════════════════════════════════════════════════════════════
class HyphalGraph:
    """
    Bidirectional weighted graph where edges = hyphal tubes.
    Edge state: {'radius': float, 'flow': float, 'age': int, 'born': str}
    Node state: {'nutrient': float, 'sink_strength': float, 'co_activation': dict}
    """

    def __init__(self):
        self.nodes: dict = {}   # node_id → {'nutrient', 'sink', 'co_act'}
        self.edges: dict = {}   # (u,v) → {'radius', 'flow', 'age'}
        self.bridges: list = [] # bridge node ids
        self._init_base()

    def _init_base(self):
        for n in BASE_NODES:
            self.nodes[n] = {
                "nutrient": 0.5,
                "sink_strength": 0.5,
                "co_activation": {},
            }
        # Connect every base node pair (undirected)
        for i, u in enumerate(BASE_NODES):
            for v in BASE_NODES[i+1:]:
                key = self._key(u, v)
                self.edges[key] = {
                    "radius": 0.3,
                    "flow": 0.0,
                    "age": 0,
                    "born": datetime.utcnow().isoformat(),
                }

    def _key(self, u: str, v: str) -> tuple:
        return (min(u,v), max(u,v))

    def edge(self, u: str, v: str) -> dict:
        return self.edges.get(self._key(u, v), {"radius": 0.0, "flow": 0.0})

    def neighbors(self, u: str) -> list:
        nbs = []
        for (a,b), _ in self.edges.items():
            if a == u and b in self.nodes: nbs.append(b)
            if b == u and a in self.nodes: nbs.append(a)
        return nbs

    def all_nodes(self) -> list:
        return list(self.nodes.keys())

    # ── INJECT NUTRIENT INTO NODE ──────────────────────────────────────────────
    def inject(self, node: str, amount: float):
        if node in self.nodes:
            self.nodes[node]["nutrient"] = min(5.0,
                self.nodes[node]["nutrient"] + amount)
            log.info(f"  ✦ INJECT {node} +{amount:.3f} → {self.nodes[node]['nutrient']:.3f}")

    # ── SET SINK STRENGTH ──────────────────────────────────────────────────────
    def set_sink(self, node: str, strength: float):
        if node in self.nodes:
            self.nodes[node]["sink_strength"] = max(0.0, min(1.0, strength))

    # ── RECORD CO-ACTIVATION ───────────────────────────────────────────────────
    def co_activate(self, node_a: str, node_b: str, score: float):
        """Record that two nodes collaborated this cycle with given score."""
        for a, b in [(node_a, node_b), (node_b, node_a)]:
            if a in self.nodes:
                co = self.nodes[a].setdefault("co_activation", {})
                co[b] = min(1.0, co.get(b, 0.0) * 0.8 + score * 0.2)  # EMA

    # ── HAGEN-POISEUILLE FLOW ─────────────────────────────────────────────────
    def compute_flows(self, steps: int = FLOW_STEPS):
        """
        Physarum-inspired flow computation.
        Flow ∝ (pressure_u - pressure_v) × radius⁴ / length
        Pressure ≈ nutrient - sink_strength (like osmotic potential)
        """
        nodes = self.nodes
        for _ in range(steps):
            # Compute pressure per node
            pressure = {}
            for nid, nd in nodes.items():
                pressure[nid] = nd["nutrient"] - nd["sink_strength"]

            for key, edge in self.edges.items():
                u, v = key
                if u not in nodes or v not in nodes: continue
                r = max(MIN_RADIUS * 0.5, edge["radius"])
                conductance = (r ** 4)   # Hagen-Poiseuille: Q ∝ r⁴
                dp = pressure[u] - pressure[v]
                flow = conductance * dp   # can be + or - (bidirectional)
                edge["flow"] = float(flow)

                # Nutrient actually moves (small fraction per step)
                transfer = flow * 0.02
                nodes[u]["nutrient"] = max(0.0, nodes[u]["nutrient"] - transfer)
                nodes[v]["nutrient"] = min(5.0, nodes[v]["nutrient"] + transfer)

    # ── HEBBIAN GROWTH ─────────────────────────────────────────────────────────
    def grow(self):
        """
        Used paths thicken. Unused paths thin.
        r(t+1) = r(t) + α×|flow|² - β
        """
        pruned = []
        for key, edge in list(self.edges.items()):
            u, v = key
            # Skip if either node was just pruned
            if u not in self.nodes or v not in self.nodes: continue

            flow_sq = edge["flow"] ** 2
            r = edge["radius"]
            r_new = r + ALPHA * flow_sq - BETA
            r_new = max(0.0, min(MAX_RADIUS, r_new))
            edge["radius"] = r_new
            edge["age"] += 1

            if r_new < MIN_RADIUS and edge["age"] > 10:
                pruned.append(key)
                log.info(f"  ✂ PRUNE hyphal {u}↔{v} (radius died at {r_new:.4f})")

        for key in pruned:
            del self.edges[key]

    # ── BRIDGE EMERGENCE ───────────────────────────────────────────────────────
    def maybe_spawn_bridge(self) -> str | None:
        """
        If two non-directly-connected nodes have high co-activation,
        spawn a relay bridge node between them.
        """
        if len(self.bridges) >= MAX_BRIDGES:
            return None

        for nid, nd in self.nodes.items():
            if nid in self.bridges: continue
            for partner, score in nd.get("co_activation", {}).items():
                if partner in self.bridges: continue
                key = self._key(nid, partner)
                direct_r = self.edges.get(key, {}).get("radius", 0)
                # Spawn bridge if co-activation high but direct link weak
                if score >= BRIDGE_THRESH and direct_r < 0.5:
                    bridge_id = f"BRIDGE_{nid[:3]}_{partner[:3]}"
                    if bridge_id not in self.nodes:
                        self.nodes[bridge_id] = {
                            "nutrient": 0.3,
                            "sink_strength": 0.3,
                            "co_activation": {},
                        }
                        self.bridges.append(bridge_id)
                        # Connect bridge to both parents
                        for parent in [nid, partner]:
                            bkey = self._key(bridge_id, parent)
                            self.edges[bkey] = {
                                "radius": 0.4,
                                "flow": 0.0,
                                "age": 0,
                                "born": datetime.utcnow().isoformat(),
                            }
                        log.info(f"  🌿 BRIDGE EMERGED: {bridge_id} ({nid}↔{partner}, co-act={score:.2f})")
                        return bridge_id
        return None

    # ── PRUNE WEAK BRIDGES ─────────────────────────────────────────────────────
    def prune_bridges(self):
        """Remove bridge nodes whose connections have all died."""
        dead = []
        for bid in list(self.bridges):
            connected = any(
                (bid in key) for key in self.edges
            )
            if not connected:
                dead.append(bid)
                del self.nodes[bid]
                log.info(f"  💀 BRIDGE DIED: {bid}")
        for bid in dead:
            self.bridges.remove(bid)

    # ── SERIALISE ─────────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "nodes": {k: {
                "nutrient": round(v["nutrient"], 4),
                "sink_strength": round(v["sink_strength"], 4),
            } for k, v in self.nodes.items()},
            "edges": {f"{k[0]}↔{k[1]}": {
                "radius": round(v["radius"], 4),
                "flow":   round(v["flow"], 4),
                "age":    v["age"],
            } for k, v in self.edges.items()},
            "bridges": self.bridges,
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
        }


# ══════════════════════════════════════════════════════════════════════════════
# MYCELIUM TICK
# ══════════════════════════════════════════════════════════════════════════════
async def tick(graph: HyphalGraph, tick_num: int):
    log.info(f"\n{'─'*60}")
    log.info(f"🍄 MYCELIUM TICK {tick_num} | nodes={len(graph.nodes)} edges={len(graph.edges)}")

    # ── READ BLACKBOARD ────────────────────────────────────────────────────────
    bb = {}
    if BLACKBOARD.exists():
        try: bb = json.loads(BLACKBOARD.read_text(encoding="utf-8"))
        except: pass

    last_score = float(bb.get("last_score", 0.5))
    last_mvp   = bb.get("last_mvp", "")
    outputs    = bb.get("outputs", [])
    rogue_outs = bb.get("rogue_outputs", [{}])[-1]

    # ── INJECT NUTRIENTS FROM REWARD SIGNAL ───────────────────────────────────
    # MVP agent gets injected based on reward score
    if last_mvp and last_mvp in graph.nodes:
        graph.inject(last_mvp, last_score * 1.5)

    # All agents get small baseline injection
    for n in BASE_NODES:
        graph.inject(n, 0.05)

    # Sink strength = inverse of nutrient (hungry = strong pull)
    for n in BASE_NODES:
        nutrient = graph.nodes[n]["nutrient"]
        hunger = max(0.1, 1.0 - nutrient / 3.0)
        graph.set_sink(n, hunger)

    # ── CO-ACTIVATION FROM CONSECUTIVE OUTPUTS ────────────────────────────────
    for i in range(len(outputs)-1):
        a = outputs[i].get("agent","")
        b = outputs[i+1].get("agent","")
        if a in graph.nodes and b in graph.nodes and a != b:
            q = min(1.0, len(outputs[i].get("text",""))/400)
            graph.co_activate(a, b, last_score * q)

    # Also record rogue agent co-activations
    metacog_q = float(rogue_outs.get("quality_score", 0.5))
    for rogue in ["METACOG","ROGUE","ADVERSARY","HACKER_ENGINEER"]:
        if rogue in graph.nodes:
            graph.set_sink(rogue, 0.3)  # rogues moderate hunger
        if last_mvp in graph.nodes and rogue not in BASE_NODES:
            graph.co_activate(last_mvp, rogue, metacog_q)

    # ── FLOW COMPUTATION (sink-pull Hagen-Poiseuille) ──────────────────────────
    graph.compute_flows()

    # ── HEBBIAN GROWTH / PRUNING ───────────────────────────────────────────────
    graph.grow()

    # ── BRIDGE EMERGENCE ──────────────────────────────────────────────────────
    new_bridge = graph.maybe_spawn_bridge()
    graph.prune_bridges()

    # ── FIND STRONGEST MYCELIAL PATH ─────────────────────────────────────────
    # Path = chain of thickest edges (like nutrient highway)
    strongest_edges = sorted(
        [(k, v["radius"]) for k,v in graph.edges.items()],
        key=lambda x: -x[1]
    )[:5]
    log.info("  🍄 Strongest hyphae: " + " | ".join(
        f"{k[0]}↔{k[1]}:{r:.3f}" for k,r in strongest_edges
    ))
    log.info(f"  🍄 Nutrient: { {k: round(v['nutrient'],2) for k,v in graph.nodes.items() if k in BASE_NODES} }")

    # ── WRITE MYCELIUM STATE TO FILE ──────────────────────────────────────────
    state = graph.to_dict()
    state["tick"] = tick_num
    state["ts"] = datetime.utcnow().isoformat()
    state["strongest_paths"] = [
        {"edge": f"{k[0]}↔{k[1]}", "radius": round(r,4)}
        for k,r in strongest_edges
    ]
    MYCELIUM_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── WRITE EVOLUTION BIAS FILE ──────────────────────────────────────────────
    # Tell evolution engine which agents have strongest mycelial connections
    # → bias crossover to prefer these agent pairs
    bias = {}
    for k, r in strongest_edges:
        pair = f"{k[0]}+{k[1]}"
        bias[pair] = round(r / MAX_RADIUS, 4)  # normalised 0-1
    bias["emergent_bridges"] = graph.bridges
    bias["ts"] = datetime.utcnow().isoformat()
    BIAS_FILE.write_text(json.dumps(bias, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── PUSH BACK TO BLACKBOARD ───────────────────────────────────────────────
    bb["mycelial_state"] = {
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
        "bridges": graph.bridges,
        "tick": tick_num,
        "strongest_path": strongest_edges[0][0] if strongest_edges else [],
    }
    bb["mycelial_nutrient"] = {k: round(v["nutrient"],3)
                               for k,v in graph.nodes.items()}
    BLACKBOARD.write_text(json.dumps(bb, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"  ✅ Tick {tick_num} complete. Bridges: {graph.bridges}")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
async def main():
    log.info("="*60)
    log.info("🍄 NEXUS MYCELIUM — MYCORRHIZAL THOUGHT WEB ONLINE")
    log.info(f"   Base nodes:    {BASE_NODES}")
    log.info(f"   Tick interval: {TICK_INTERVAL}s")
    log.info(f"   Growth α={ALPHA}  Decay β={BETA}  Max bridges={MAX_BRIDGES}")
    log.info(f"   Bridge threshold: {BRIDGE_THRESH}")
    log.info("="*60)
    log.info("")
    log.info("  KEY ARCHITECTURE:")
    log.info("  antennae.py → push-deposit pheromones (short memory)")
    log.info("  mycelium.py → pull-based sink flow   (long-term structure)")
    log.info("  PSO         → fast numerical weights  (seconds)")
    log.info("  mycelium    → slow structural tuning  (minutes/hours)")
    log.info("")

    graph = HyphalGraph()
    tick_num = 0

    while True:
        tick_num += 1
        try:
            await tick(graph, tick_num)
        except Exception as e:
            log.error(f"❌ Tick {tick_num} error: {e}")
        await asyncio.sleep(TICK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
