"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  GOD NODE — Constitutional Layer                                            ║
║  The one entity that watches the watchers.                                  ║
║                                                                             ║
║  Four responsibilities:                                                     ║
║    1. Schema Sovereignty   — only valid node types may exist               ║
║    2. Score Archaeology    — detect REWARD drift across cycles              ║
║    3. Null Zone Cartography — map where the system consistently fails       ║
║    4. Quorum Signature     — cryptographic KG integrity hash               ║
║                                                                             ║
║  Immutable: never called by any agent. Never shaped by utility_score.      ║
║  Runs between cycles. Writes one JSON. God Node owns the rules.            ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import json
import re
import hashlib
from datetime import datetime, timezone
UTC = timezone.utc
from pathlib import Path
from collections import defaultdict

BASE          = Path(__file__).parent
KG_PATH       = BASE / "nexus_kg.json"
LOG_PATH      = BASE / "log_swarm_err.txt"
GOD_NODE_FILE = BASE / "nexus_god_node_state.json"

# ── Constitutional schema — only these node types are valid ───────────────────
VALID_NODE_TYPES = {
    "agent", "copy", "evidence", "pain", "failure_memory",
    "channel", "axiom", "god_node", "divergence",
    "memory_flag", "task", "milestone", "mycelium"
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def log(msg):
    ts = datetime.now(UTC).strftime("%H:%M:%S")
    print(f"[{ts}] [GOD_NODE] {msg}")

def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default

def atomic_write(path, data):
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)

# ── 1. Schema Sovereignty ─────────────────────────────────────────────────────

def check_schema(nodes: list) -> dict:
    """Find any nodes with invalid types. Flag them. Never delete — flag."""
    violations = []
    type_counts = defaultdict(int)
    for node in nodes:
        ntype = node.get("type", "unknown").lower()
        type_counts[ntype] += 1
        if ntype not in VALID_NODE_TYPES:
            violations.append({
                "id":   node.get("id", "?"),
                "type": ntype,
                "label": node.get("label", "")[:60]
            })

    return {
        "valid":       len(violations) == 0,
        "violations":  violations[:10],  # cap report at 10
        "type_counts": dict(type_counts),
        "total_nodes": len(nodes)
    }

# ── 2. Score Archaeology ──────────────────────────────────────────────────────

def extract_cycle_scores(log_path: Path) -> list:
    """Extract all completed cycle scores from swarm log."""
    scores = []
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'Cycle #(\d+) COMPLETE\. Score=([\d.]+)', text):
            scores.append({
                "cycle": int(m.group(1)),
                "score": float(m.group(2))
            })
    except Exception as e:
        log(f"Score extraction error: {e}")
    return scores

def score_archaeology(scores: list) -> dict:
    """Detect REWARD drift. Compare recent window vs baseline."""
    if len(scores) < 5:
        return {"status": "insufficient_data", "cycles": len(scores)}

    all_s  = [s["score"] for s in scores]
    recent = all_s[-10:]   # last 10 cycles
    baseline_n = min(20, len(all_s) // 2)
    baseline   = all_s[:baseline_n]

    baseline_mean = sum(baseline) / len(baseline)
    recent_mean   = sum(recent)   / len(recent)
    drift         = round(recent_mean - baseline_mean, 4)

    # Null zones: task types with consistently low scores
    # (using cycle index mod 3 as a proxy since we don't have task labels yet)
    low_cycles = [s for s in scores if s["score"] < 0.55]

    result = {
        "baseline_mean":     round(baseline_mean, 4),
        "baseline_cycles":   baseline_n,
        "recent_mean":       round(recent_mean, 4),
        "recent_cycles":     len(recent),
        "drift":             drift,
        "drift_alert":       abs(drift) > 0.10,
        "low_score_cycles":  len(low_cycles),
        "total_cycles":      len(scores),
        "score_range":       [round(min(all_s), 3), round(max(all_s), 3)],
    }

    if result["drift_alert"]:
        direction = "POSITIVE" if drift > 0 else "NEGATIVE"
        log(f"⚠️  REWARD DRIFT ALERT: {direction} drift of {drift:.3f} detected")
    else:
        log(f"Score archaeology clean. Drift: {drift:+.4f} | Recent mean: {recent_mean:.3f}")

    return result

# ── 3. Null Zone Cartography ──────────────────────────────────────────────────

def map_null_zones(nodes: list, scores: list) -> list:
    """Identify knowledge domains where the system consistently fails."""
    null_zones = []

    # Check FAILURE_MEMORY nodes with low utility scores
    failure_nodes = [
        n for n in nodes
        if n.get("type", "").lower() in ("failure_memory", "divergence")
        and n.get("utility_score", 1.0) < 0.3
    ]
    if failure_nodes:
        null_zones.append({
            "zone":        "persistent_failures",
            "evidence":    f"{len(failure_nodes)} failure nodes with low utility",
            "node_count":  len(failure_nodes),
            "action":      "Route Shadow mutations to target these failure patterns"
        })

    # Low score cycles
    if scores:
        low = [s for s in scores if s["score"] < 0.50]
        if len(low) > len(scores) * 0.3:
            null_zones.append({
                "zone":       "below_floor_cycles",
                "evidence":   f"{len(low)}/{len(scores)} cycles scored below 0.50",
                "pct":        round(len(low)/len(scores)*100),
                "action":     "Shadow Mutator: increase critic pressure on low-score domains"
            })

    # Nodes never attributed (utility_score still at init 0.5, hits=0)
    cold_nodes = [
        n for n in nodes
        if n.get("utility_score", 0.5) == 0.5 and n.get("hits", 0) == 0
        and n.get("type") not in ("god_node", "agent")
    ]
    if len(cold_nodes) > 20:
        null_zones.append({
            "zone":       "cold_knowledge",
            "evidence":   f"{len(cold_nodes)} nodes never retrieved or attributed",
            "node_count": len(cold_nodes),
            "action":     "KG breathing: flag for CHRONOS decay priority"
        })

    return null_zones

# ── 4. Quorum Signature ───────────────────────────────────────────────────────

def compute_quorum(nodes: list) -> str:
    """SHA-256 hash of schema structure and top-confidence node IDs."""
    # Hash: sorted node types + sorted top-10 node IDs by confidence
    type_sig    = "|".join(sorted(VALID_NODE_TYPES))
    top_ids     = sorted(
        nodes,
        key=lambda n: n.get("confidence", 0),
        reverse=True
    )[:10]
    id_sig = "|".join(n.get("id","?") for n in top_ids)
    raw    = f"{type_sig}::{id_sig}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]

# ── Specialist Routing Rules ──────────────────────────────────────────────────

def load_specialists() -> list:
    """Load any promoted specialists from shadow/specialists/"""
    specialist_dir = BASE / "shadow" / "specialists"
    specialists = []
    if specialist_dir.exists():
        for f in specialist_dir.glob("*.json"):
            try:
                s = json.loads(f.read_text(encoding="utf-8"))
                specialists.append(s)
            except Exception:
                pass
    return specialists

# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    log("GOD NODE awakening...")

    kg_data = load_json(KG_PATH, {})
    # Handle both flat and networkx node_link format
    nodes = kg_data.get("nodes", []) or kg_data.get("graph", {}).get("nodes", [])
    log(f"KG loaded: {len(nodes)} nodes")

    # 1. Schema sovereignty
    schema = check_schema(nodes)
    if not schema["valid"]:
        log(f"⚠️  Schema violations: {len(schema['violations'])} invalid node types found")
        for v in schema["violations"][:3]:
            log(f"   [{v['type']}] {v['id']}")
    else:
        log(f"Schema integrity: CLEAN ({schema['total_nodes']} nodes, {len(schema['type_counts'])} types)")

    # 2. Score archaeology
    scores = extract_cycle_scores(LOG_PATH)
    archaeology = score_archaeology(scores)

    # 3. Null zone cartography
    null_zones = map_null_zones(nodes, scores)
    if null_zones:
        log(f"Null zones identified: {len(null_zones)}")
        for z in null_zones:
            log(f"   [{z['zone']}] → {z['action']}")
    else:
        log("No null zones detected. System operating in known territory.")

    # 4. Quorum signature
    quorum = compute_quorum(nodes)
    log(f"Quorum signature: {quorum}")

    # Load existing God Node state to detect quorum drift
    existing = load_json(GOD_NODE_FILE, {})
    prev_quorum = existing.get("quorum_sig", "")
    quorum_changed = prev_quorum and prev_quorum != quorum

    if quorum_changed:
        log(f"⚠️  QUORUM CHANGED: {prev_quorum} → {quorum}")
        log("   KG schema or top nodes have shifted since last God Node run")

    # Load specialist routing rules
    specialists = load_specialists()

    # Write God Node state
    god_node_state = {
        "id":                  "GOD_NODE_PRIME",
        "type":                "god_node",
        "immutable":           True,
        "last_run":            datetime.now(UTC).isoformat(),
        "quorum_sig":          quorum,
        "quorum_changed":      quorum_changed,
        "prev_quorum":         prev_quorum,
        "schema":              schema,
        "score_archaeology":   archaeology,
        "null_zones":          null_zones,
        "specialists":         specialists,
        "valid_node_types":    sorted(VALID_NODE_TYPES),
        "constitutional_version": 1,
        "writeable_by":        "GOD_NODE_PRIME_ONLY",
        "total_cycles_seen":   len(scores)
    }

    atomic_write(GOD_NODE_FILE, god_node_state)
    log(f"God Node state written to {GOD_NODE_FILE.name}")
    log(f"Summary: schema={'CLEAN' if schema['valid'] else 'VIOLATIONS'} | "
        f"drift={archaeology.get('drift',0):+.4f} | "
        f"null_zones={len(null_zones)} | "
        f"quorum={'CHANGED' if quorum_changed else 'STABLE'}")

    return god_node_state

if __name__ == "__main__":
    run()
