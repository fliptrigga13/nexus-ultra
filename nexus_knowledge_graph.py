"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  NEXUS KNOWLEDGE GRAPH — Neuro-Symbolic Memory Engine                       ║
║                                                                              ║
║  Neural part:   nomic-embed-text embeds all KG nodes (offline, Ollama)      ║
║  Symbolic part: NetworkX graph encodes causal agent-output relationships     ║
║  Foresight:     semantic diff detects ontology drift between cycles          ║
║  Injection:     top-5 historical patterns pushed into SUPERVISOR context     ║
║                                                                              ║
║  Schema:                                                                     ║
║    PAIN ──converts_via──► COPY ──posted_on──► CHANNEL                       ║
║    BUYER ──has_pain──► PAIN                                                  ║
║    CYCLE ──produced──► PATTERN ──scored──► SCORE                            ║
║    AGENT ──generated──► OUTPUT                                               ║
║                                                                              ║
║  Usage:                                                                      ║
║    kg = NexusKnowledgeGraph()                                                ║
║    kg.update(agent_outputs, score=0.82, mvp="COPYWRITER", cycle_id="c042")  ║
║    context = kg.get_supervisor_context(task)   # inject before each cycle   ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import logging
import re
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

import httpx
import networkx as nx
import numpy as np

# ── CONFIG ────────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent
KG_FILE       = BASE_DIR / "nexus_kg.json"          # persistent graph store
KG_EMBED_FILE = BASE_DIR / "nexus_kg_embeddings.json"  # cycle embedding history
OLLAMA_BASE   = "http://127.0.0.1:11434"
EMBED_MODEL   = "nomic-embed-text"

DRIFT_THRESHOLD = 0.12   # cosine distance > this = new ontology territory
MAX_CYCLES_STORED = 200   # keep last N cycles in persistent store
MAX_PATTERNS_INJECT = 6   # max historical patterns injected into SUPERVISOR

log = logging.getLogger("NEXUS-KG")
log.setLevel(logging.INFO)
if not log.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s [KG] %(message)s"))
    log.addHandler(h)


# ══════════════════════════════════════════════════════════════════════════════
# TAG PARSER — extract structured knowledge from agent outputs
# ══════════════════════════════════════════════════════════════════════════════

class TagParser:
    """
    Parses NEXUS agent output tags into structured knowledge triples.
    Handles all known tag formats and extracts entities + relations.
    """

    # Patterns matched per tag type
    _PATTERNS = {
        "buyer": re.compile(
            r'\[BUYER:\s*(?:platform=(?P<platform>\S+))?\s*'
            r'(?:source=(?P<source>\S+))?\s*'
            r'(?:pain=(?P<pain>[^\]]+?))?\s*'
            r'(?:readiness=(?P<readiness>HIGH|MED|LOW))?\s*\]',
            re.IGNORECASE | re.DOTALL
        ),
        "competitor_gap": re.compile(
            r'\[COMPETITOR_GAP:\s*(?P<tool>[^\]]+?)\s+fails at\s+(?P<failure>[^\]]+?)'
            r'(?:\s*—\s*VeilPiercer solves this via\s*(?P<solution>[^\]]+?))?\s*\]',
            re.IGNORECASE
        ),
        "channel_signal": re.compile(
            r'\[CHANNEL_SIGNAL:\s*(?P<community>[^\]]+?)\s+has\s+(?P<count>\S+)\s+posts[^\]]*?\]',
            re.IGNORECASE
        ),
        "score": re.compile(
            r'\[SCORE:\s*(?P<score>[01]?\.\d+|1\.0)\]',
            re.IGNORECASE
        ),
        "mvp": re.compile(
            r'\[MVP:\s*(?P<agent>[A-Z_]+)\]',
            re.IGNORECASE
        ),
        "evidence_check": re.compile(
            r'\[EVIDENCE_CHECK:\s*(?P<verdict>PASS|FAIL[^\]]*)\]',
            re.IGNORECASE
        ),
        "sentinel_clear": re.compile(
            r'\[SENTINEL_CLEAR:\s*(?P<what>[^\]]+)\]',
            re.IGNORECASE
        ),
        "sentinel_lockdown": re.compile(
            r'\[SENTINEL_LOCKDOWN:\s*(?P<what>[^\]]+)\]',
            re.IGNORECASE
        ),
        "metacog": re.compile(
            r'\[METACOG:\s*(?P<verdict>SHARP|SHALLOW|DRIFT|LOOP)\]',
            re.IGNORECASE
        ),
        "execute": re.compile(
            r'\[EXECUTE:\s*(?P<verdict>READY|REFINE[^\]]*|TRASH[^\]]*)\]',
            re.IGNORECASE
        ),
        "best_channel": re.compile(
            r'\[BEST_CHANNEL:\s*(?P<channel>[^\]—]+?)(?:\s*—\s*reason=(?P<reason>[^\]]+?))?\s*(?:CVR_estimate=(?P<cvr>\S+))?\s*\]',
            re.IGNORECASE
        ),
        "objective": re.compile(
            r'\[OBJECTIVE:\s*(?P<obj>[^\]]+)\]',
            re.IGNORECASE
        ),
        "reddit_reply": re.compile(
            r'\[REDDIT_REPLY:\s*(?P<subreddit>r/\S+)\](?P<body>.*?)\[/REDDIT_REPLY\]',
            re.IGNORECASE | re.DOTALL
        ),
        "offer_strength": re.compile(
            r'\[OFFER_STRENGTH:\s*(?P<val>[^\]]+)\]',
            re.IGNORECASE
        ),
        "conversion_block": re.compile(
            r'\[CONVERSION_BLOCK:\s*(?P<block>[^\]]+?)\s*(?:—\s*fix=(?P<fix>[^\]]+))?\]',
            re.IGNORECASE
        ),
    }

    def parse(self, agent_name: str, text: str) -> list[dict]:
        """
        Parse agent output text → list of knowledge triples.
        Each triple: {tag, agent, entities, relation_hint}
        """
        results = []
        cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

        for tag_type, pattern in self._PATTERNS.items():
            for match in pattern.finditer(cleaned):
                g = {k: (v.strip() if isinstance(v, str) else v)
                     for k, v in match.groupdict().items() if v}
                if g:
                    results.append({
                        "tag":      tag_type,
                        "agent":    agent_name,
                        "entities": g,
                        "raw":      cleaned[:120],
                    })

        return results


# ══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE GRAPH BUILDER — maps triples → NetworkX graph
# ══════════════════════════════════════════════════════════════════════════════

class KGBuilder:
    """Converts parsed triples into NetworkX directed graph nodes and edges."""

    def __init__(self, G: nx.DiGraph):
        self.G = G

    def _add_node(self, node_id: str, **attrs):
        if not self.G.has_node(node_id):
            self.G.add_node(node_id, hits=1, **attrs)
        else:
            self.G.nodes[node_id]["hits"] = self.G.nodes[node_id].get("hits", 0) + 1
            self.G.nodes[node_id].update(attrs)

    def _add_edge(self, src: str, dst: str, relation: str, **attrs):
        if self.G.has_edge(src, dst):
            self.G[src][dst]["weight"] = self.G[src][dst].get("weight", 1) + 1
        else:
            self.G.add_edge(src, dst, relation=relation, weight=1, **attrs)

    def ingest(self, triple: dict, cycle_id: str):
        tag = triple["tag"]
        agent = triple["agent"]
        e = triple["entities"]

        agent_node = f"AGENT:{agent}"
        self._add_node(agent_node, type="agent", label=agent)

        if tag == "buyer":
            pain_text = e.get("pain", "unknown_pain")[:80]
            pain_id = f"PAIN:{pain_text[:40]}"
            channel_id = f"CHANNEL:{e.get('platform', e.get('source', 'unknown'))}"
            readiness = e.get("readiness", "UNKNOWN")

            self._add_node(pain_id, type="pain", label=pain_text, readiness=readiness)
            self._add_node(channel_id, type="channel", label=channel_id.split(":")[-1])
            self._add_edge(agent_node, pain_id, "detected_pain")
            self._add_edge(pain_id, channel_id, "found_on")

        elif tag == "reddit_reply":
            sub = e.get("subreddit", "unknown")
            body = e.get("body", "")[:80]
            copy_id = f"COPY:{cycle_id}:{sub}"
            channel_id = f"CHANNEL:{sub}"
            self._add_node(copy_id, type="copy", label=body, channel=sub)
            self._add_node(channel_id, type="channel", label=sub)
            self._add_edge(agent_node, copy_id, "generated_copy")
            self._add_edge(copy_id, channel_id, "targets_channel")

        elif tag == "best_channel":
            ch = e.get("channel", "unknown")
            cvr = e.get("cvr", "?")
            channel_id = f"CHANNEL:{ch.strip()}"
            self._add_node(channel_id, type="channel", label=ch, cvr=cvr)
            self._add_edge(agent_node, channel_id, "recommends_channel",
                           reason=e.get("reason", ""))

        elif tag == "score":
            score_val = float(e.get("score", 0))
            cycle_node = f"CYCLE:{cycle_id}"
            self._add_node(cycle_node, type="cycle", label=cycle_id, score=score_val)
            self._add_edge(agent_node, cycle_node, "scored_cycle")

        elif tag == "conversion_block":
            block = e.get("block", "unknown")[:60]
            fix = e.get("fix", "")[:60]
            block_id = f"BLOCK:{block[:30]}"
            self._add_node(block_id, type="conversion_block", label=block, fix=fix)
            self._add_edge(agent_node, block_id, "identified_block")

        elif tag == "competitor_gap":
            tool = e.get("tool", "unknown")[:40]
            failure = e.get("failure", "")[:60]
            tool_id = f"COMPETITOR:{tool}"
            self._add_node(tool_id, type="competitor", label=tool, gap=failure)
            self._add_edge(agent_node, tool_id, "identified_gap")

        elif tag == "objective":
            obj_id = f"OBJECTIVE:{cycle_id}"
            self._add_node(obj_id, type="objective", label=e.get("obj", "")[:80])
            self._add_edge(agent_node, obj_id, "set_objective")

        elif tag in ("sentinel_lockdown",):
            risk_id = f"RISK:{e.get('what', '')[:40]}"
            self._add_node(risk_id, type="risk", label=e.get("what", "")[:80])
            self._add_edge(agent_node, risk_id, "detected_risk")

        elif tag == "metacog":
            verdict = e.get("verdict", "UNKNOWN")
            meta_id = f"METACOG:{cycle_id}"
            self._add_node(meta_id, type="metacog", label=verdict, cycle=cycle_id)

        elif tag == "execute":
            verdict = e.get("verdict", "UNKNOWN")
            exec_id = f"EXECUTE:{cycle_id}"
            self._add_node(exec_id, type="execute", label=verdict, cycle=cycle_id)


# ══════════════════════════════════════════════════════════════════════════════
# EMBEDDING ENGINE — nomic-embed-text via Ollama (offline)
# ══════════════════════════════════════════════════════════════════════════════

async def embed_text(text: str, client: Optional[httpx.AsyncClient] = None) -> Optional[list[float]]:
    """Embed a text string using nomic-embed-text. Returns vector or None."""
    try:
        close_after = client is None
        if close_after:
            client = httpx.AsyncClient(timeout=30.0)
        try:
            r = await client.post(f"{OLLAMA_BASE}/api/embeddings", json={
                "model": EMBED_MODEL,
                "prompt": text
            })
            if r.status_code == 200:
                return r.json().get("embedding")
        finally:
            if close_after:
                await client.aclose()
    except Exception as e:
        log.warning(f"Embed failed: {e}")
    return None


def cosine_distance(a: list[float], b: list[float]) -> float:
    """Cosine distance between two embedding vectors (0=identical, 1=orthogonal)."""
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom < 1e-9:
        return 1.0
    return float(1.0 - np.dot(va, vb) / denom)


# ══════════════════════════════════════════════════════════════════════════════
# PATTERN EXTRACTOR — reads KG for historical insights
# ══════════════════════════════════════════════════════════════════════════════

class PatternExtractor:
    """Extracts actionable patterns from the KG for SUPERVISOR context injection."""

    def __init__(self, G: nx.DiGraph):
        self.G = G

    def top_channels(self, n: int = 3) -> list[dict]:
        """Channels with highest edge weight (most agent recommendations)."""
        channels = [
            (nid, data) for nid, data in self.G.nodes(data=True)
            if data.get("type") == "channel"
        ]
        scored = []
        for nid, data in channels:
            in_w = sum(self.G[src][nid].get("weight", 1) for src in self.G.predecessors(nid))
            scored.append((in_w, nid, data))
        scored.sort(reverse=True)
        return [{"channel": nid.split(":")[-1], "hits": w, "cvr": d.get("cvr", "?")}
                for w, nid, d in scored[:n]]

    def top_pains(self, n: int = 4) -> list[dict]:
        """Pain points with highest detection frequency and readiness."""
        pains = [
            (nid, data) for nid, data in self.G.nodes(data=True)
            if data.get("type") == "pain"
        ]
        high_first = sorted(pains, key=lambda x: (
            x[1].get("readiness", "LOW") == "HIGH",
            x[1].get("hits", 0)
        ), reverse=True)
        return [{"pain": d.get("label", nid)[:60], "readiness": d.get("readiness", "?"),
                 "hits": d.get("hits", 0)}
                for nid, d in high_first[:n]]

    def top_blocks(self, n: int = 2) -> list[dict]:
        """Most-flagged conversion blockers."""
        blocks = [
            (nid, data) for nid, data in self.G.nodes(data=True)
            if data.get("type") == "conversion_block"
        ]
        by_hits = sorted(blocks, key=lambda x: x[1].get("hits", 0), reverse=True)
        return [{"block": d.get("label", "?")[:50], "fix": d.get("fix", "")}
                for _, d in by_hits[:n]]

    def top_competitors(self, n: int = 2) -> list[dict]:
        """Competitor gaps most frequently flagged."""
        comps = [
            (nid, data) for nid, data in self.G.nodes(data=True)
            if data.get("type") == "competitor"
        ]
        by_hits = sorted(comps, key=lambda x: x[1].get("hits", 0), reverse=True)
        return [{"tool": d.get("label", "?"), "gap": d.get("gap", "")}
                for _, d in by_hits[:n]]

    def recent_metacog_verdicts(self, n: int = 3) -> list[str]:
        """Last N METACOG verdicts — tells SUPERVISOR reasoning quality trend."""
        metas = [
            (nid, data) for nid, data in self.G.nodes(data=True)
            if data.get("type") == "metacog"
        ]
        # Sort by cycle_id (lexicographic — works for cycle timestamps/ids)
        metas.sort(key=lambda x: x[1].get("cycle", ""), reverse=True)
        return [d.get("label", "?") for _, d in metas[:n]]


# ══════════════════════════════════════════════════════════════════════════════
# MAIN CLASS — NexusKnowledgeGraph
# ══════════════════════════════════════════════════════════════════════════════

class NexusKnowledgeGraph:
    """
    Persistent neuro-symbolic knowledge graph for the NEXUS swarm.

    Lifecycle:
        1. After each cycle: kg.update(outputs, score, mvp, cycle_id)
        2. Before each cycle: kg.get_supervisor_context(task) → inject into SUPERVISOR role
        3. Drift: kg.is_new_territory() → True if semantic drift > threshold
    """

    def __init__(self):
        self.G = nx.DiGraph()
        self.parser = TagParser()
        self.builder = KGBuilder(self.G)
        self.extractor = PatternExtractor(self.G)
        self._cycle_embeddings: list[dict] = []   # [{cycle, embedding, drift}]
        self._total_cycles = 0
        self._last_drift = 0.0
        self._load()
        log.info(f"✅ KG online — {self.G.number_of_nodes()} nodes | "
                 f"{self.G.number_of_edges()} edges | "
                 f"{self._total_cycles} cycles indexed")

    # ── PERSISTENCE ─────────────────────────────────────────────────────────

    def _load(self):
        """Load KG from disk on startup."""
        if KG_FILE.exists():
            try:
                data = json.loads(KG_FILE.read_text(encoding="utf-8"))
                self.G = nx.node_link_graph(data.get("graph", {}))
                self.builder = KGBuilder(self.G)
                self.extractor = PatternExtractor(self.G)
                self._total_cycles = data.get("total_cycles", 0)
                log.info(f"  Loaded KG: {self.G.number_of_nodes()} nodes from disk")
            except Exception as e:
                log.warning(f"  KG load failed (fresh start): {e}")

        if KG_EMBED_FILE.exists():
            try:
                self._cycle_embeddings = json.loads(
                    KG_EMBED_FILE.read_text(encoding="utf-8")
                )
                self._cycle_embeddings = self._cycle_embeddings[-MAX_CYCLES_STORED:]
            except Exception:
                pass

    def _save(self):
        """Persist KG and embeddings to disk."""
        try:
            data = {
                "graph": nx.node_link_data(self.G),
                "total_cycles": self._total_cycles,
                "saved_at": datetime.now(UTC).isoformat(),
            }
            KG_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            # Trim embeddings to MAX_CYCLES_STORED
            trimmed = self._cycle_embeddings[-MAX_CYCLES_STORED:]
            KG_EMBED_FILE.write_text(
                json.dumps(trimmed, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            log.warning(f"  KG save failed: {e}")

    # ── CORE UPDATE ─────────────────────────────────────────────────────────

    def update(
        self,
        agent_outputs: list[dict],    # [{"agent": "COPYWRITER", "text": "..."}, ...]
        score: float = 0.0,
        mvp: str = "",
        cycle_id: Optional[str] = None,
    ):
        """
        Ingest a completed swarm cycle into the knowledge graph.
        Call this AFTER each cycle completes.

        agent_outputs: list of {agent, text} dicts (from blackboard)
        """
        if cycle_id is None:
            cycle_id = f"c{int(time.time())}"

        # Parse all agent outputs into triples
        all_triples = []
        for entry in agent_outputs:
            agent_name = entry.get("agent", "UNKNOWN").upper()
            text = entry.get("text", "")
            triples = self.parser.parse(agent_name, text)
            all_triples.extend(triples)

        # Ingest triples into KG
        for triple in all_triples:
            self.builder.ingest(triple, cycle_id)

        # Add score node
        cycle_node = f"CYCLE:{cycle_id}"
        self.G.add_node(cycle_node, type="cycle", label=cycle_id,
                        score=score, mvp=mvp, ts=datetime.now(UTC).isoformat())

        self._total_cycles += 1

        # Embed cycle representation async (fire-and-forget if no event loop)
        cycle_summary = self._summarise_for_embed(all_triples, score, mvp)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._embed_cycle(cycle_id, cycle_summary))
            else:
                asyncio.run(self._embed_cycle(cycle_id, cycle_summary))
        except Exception:
            pass  # embedding optional — never blocks swarm

        self._save()
        log.info(f"  KG update: cycle={cycle_id} score={score:.2f} "
                 f"triples={len(all_triples)} nodes={self.G.number_of_nodes()}")

    def _summarise_for_embed(self, triples: list[dict], score: float, mvp: str) -> str:
        """Create a text summary of this cycle for embedding."""
        parts = [f"score={score:.2f} mvp={mvp}"]
        for t in triples[:12]:
            entities_str = " ".join(f"{k}={v}" for k, v in t["entities"].items()
                                    if isinstance(v, str))[:60]
            parts.append(f"{t['tag']}:{entities_str}")
        return " | ".join(parts)

    async def _embed_cycle(self, cycle_id: str, summary: str):
        """Embed cycle summary and compute drift from previous cycle."""
        embedding = await embed_text(summary)
        if embedding is None:
            return

        drift = 0.0
        if self._cycle_embeddings:
            prev_emb = self._cycle_embeddings[-1].get("embedding")
            if prev_emb:
                drift = cosine_distance(prev_emb, embedding)
                self._last_drift = drift
                if drift > DRIFT_THRESHOLD:
                    log.info(f"  🔀 ONTOLOGY DRIFT detected: {drift:.3f} > {DRIFT_THRESHOLD} "
                             f"— new territory in cycle {cycle_id}")

        self._cycle_embeddings.append({
            "cycle_id": cycle_id,
            "embedding": embedding,
            "drift": drift,
            "ts": datetime.now(UTC).isoformat(),
        })

        # Save embeddings file
        try:
            trimmed = self._cycle_embeddings[-MAX_CYCLES_STORED:]
            KG_EMBED_FILE.write_text(
                json.dumps(trimmed, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            pass

    # ── FORESIGHT QUERIES ────────────────────────────────────────────────────

    def get_supervisor_context(self, task: str = "") -> str:
        """
        Generate a formatted context string with KG-derived patterns.
        Inject this into SUPERVISOR system prompt before each cycle.

        This is the "foresight" mechanism — the SUPERVISOR sees what has
        actually worked historically before deciding what to do next.
        """
        if self.G.number_of_nodes() < 3:
            return ""   # not enough data yet

        parts = ["[KG_MEMORY: What the swarm has learned across all cycles]"]

        # Top-performing channels
        channels = self.extractor.top_channels(3)
        if channels:
            ch_str = " | ".join(
                f"{c['channel']} (seen {c['hits']}x{', CVR~' + c['cvr'] if c['cvr'] != '?' else ''})"
                for c in channels
            )
            parts.append(f"[KG_CHANNEL_SIGNAL: {ch_str}]")

        # Most common high-readiness pain points
        pains = self.extractor.top_pains(4)
        if pains:
            pain_str = " | ".join(
                f"'{p['pain'][:45]}' (readiness={p['readiness']}, seen {p['hits']}x)"
                for p in pains
            )
            parts.append(f"[KG_PAIN_PATTERNS: {pain_str}]")

        # Conversion blockers
        blocks = self.extractor.top_blocks(2)
        if blocks:
            block_str = " | ".join(
                f"{b['block']}{' -> fix: ' + b['fix'] if b['fix'] else ''}"
                for b in blocks
            )
            parts.append(f"[KG_CONVERSION_BLOCKS: {block_str}]")

        # Competitor gaps
        comps = self.extractor.top_competitors(2)
        if comps:
            comp_str = " | ".join(
                f"{c['tool']} fails at: {c['gap'][:40]}"
                for c in comps
            )
            parts.append(f"[KG_COMPETITOR_GAPS: {comp_str}]")

        # Reasoning quality trend (METACOG verdicts)
        verdicts = self.extractor.recent_metacog_verdicts(3)
        if verdicts:
            parts.append(f"[KG_REASONING_TREND: last 3 cycles = {' -> '.join(verdicts)}]")

        # Drift warning if in new ontology territory
        if self._last_drift > DRIFT_THRESHOLD:
            parts.append(
                f"[KG_ONTOLOGY_DRIFT: {self._last_drift:.3f} — this cycle is exploring "
                f"NEW territory. Be more exploratory, less prescriptive.]"
            )

        # Summary stats
        parts.append(
            f"[KG_STATS: {self._total_cycles} cycles indexed | "
            f"{self.G.number_of_nodes()} knowledge nodes | "
            f"{self.G.number_of_edges()} relationships]"
        )

        return "\n".join(parts)

    def is_new_territory(self) -> bool:
        """True if the last cycle drifted into unexplored ontology space."""
        return self._last_drift > DRIFT_THRESHOLD

    def get_stats(self) -> dict:
        """Return KG statistics for dashboard/monitoring."""
        return {
            "nodes": self.G.number_of_nodes(),
            "edges": self.G.number_of_edges(),
            "total_cycles": self._total_cycles,
            "last_drift": round(self._last_drift, 4),
            "is_new_territory": self.is_new_territory(),
            "top_channels": self.extractor.top_channels(3),
            "top_pains": self.extractor.top_pains(3),
            "node_types": {
                str(k): int(v)
                for k, v in zip(*np.unique(
                    [d.get("type", "unknown") for _, d in self.G.nodes(data=True)],
                    return_counts=True
                ))
            } if self.G.number_of_nodes() > 0 else {},
        }

    # ── SYMBOLIC QUERY ENGINE ────────────────────────────────────────────────

    def find_conversion_path(self) -> Optional[str]:
        """
        Symbolic reasoning: find the highest-weight path from PAIN → CHANNEL.
        This is the neuro-symbolic bridge — LLM-extracted data, graph-reasoned path.
        Returns a formatted string describing the optimal conversion path found.
        """
        pain_nodes = [n for n, d in self.G.nodes(data=True) if d.get("type") == "pain"
                      and d.get("readiness") == "HIGH"]
        channel_nodes = [n for n, d in self.G.nodes(data=True) if d.get("type") == "channel"]

        if not pain_nodes or not channel_nodes:
            return None

        best_path = None
        best_weight = 0

        for pain in pain_nodes[:5]:    # limit search for speed
            for channel in channel_nodes[:5]:
                try:
                    # Find path with highest cumulative edge weight
                    if nx.has_path(self.G, pain, channel):
                        paths = list(nx.all_simple_paths(self.G, pain, channel, cutoff=4))
                        for path in paths[:3]:
                            weight = sum(
                                self.G[path[i]][path[i+1]].get("weight", 1)
                                for i in range(len(path)-1)
                            )
                            if weight > best_weight:
                                best_weight = weight
                                best_path = path
                except nx.NetworkXNoPath:
                    continue

        if best_path:
            path_str = " -> ".join(n.split(":")[-1][:30] for n in best_path)
            return f"[KG_CONVERSION_PATH: {path_str} (strength={best_weight})]"

        return None


# ── SINGLETON ─────────────────────────────────────────────────────────────────

_kg_instance: Optional[NexusKnowledgeGraph] = None

def get_kg() -> NexusKnowledgeGraph:
    """Return the singleton KG instance (load once, reuse)."""
    global _kg_instance
    if _kg_instance is None:
        _kg_instance = NexusKnowledgeGraph()
    return _kg_instance


# ══════════════════════════════════════════════════════════════════════════════
# STANDALONE TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 70)
    print("NEXUS KNOWLEDGE GRAPH — SELF TEST")
    print("=" * 70)

    kg = NexusKnowledgeGraph()

    # Simulate a swarm cycle
    test_outputs = [
        {
            "agent": "SCOUT",
            "text": "[BUYER: platform=Reddit source=r/selfhosted pain=I want full privacy but cloud context defeats the point readiness=HIGH]"
                    "[CHANNEL_SIGNAL: r/selfhosted has 12 posts this week about local LLM monitoring]"
        },
        {
            "agent": "COPYWRITER",
            "text": "[REDDIT_REPLY: r/selfhosted]Running local models for privacy while hitting a cloud context engine defeats the point. "
                    "I built VeilPiercer for exactly this — logs everything on device, zero cloud calls. $197 one-time at veil-piercer.com[/REDDIT_REPLY]"
        },
        {
            "agent": "CONVERSION_ANALYST",
            "text": "[BEST_CHANNEL: r/selfhosted — reason=privacy-first audience CVR_estimate=4.2%]"
                    "[CONVERSION_BLOCK: Price anchoring vs free tools — fix=lead with offline/ownership angle]"
        },
        {
            "agent": "REWARD",
            "text": "[SCORE: 0.78][MVP: COPYWRITER]"
        },
        {
            "agent": "METACOG",
            "text": "[METACOG: SHARP]"
        },
    ]

    kg.update(test_outputs, score=0.78, mvp="COPYWRITER", cycle_id="test_c001")

    print("\n— KG Stats —")
    stats = kg.get_stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")

    print("\n— SUPERVISOR Context (what gets injected) —")
    ctx = kg.get_supervisor_context("Get VeilPiercer customer via Reddit")
    print(ctx if ctx else "  (not enough data yet for full context)")

    print("\n— Conversion Path (symbolic) —")
    path = kg.find_conversion_path()
    print(path or "  (no HIGH-readiness pain nodes yet)")

    print("\n— Embedding test (requires Ollama running) —")
    async def test_embed():
        vec = await embed_text("offline AI agent monitoring tool")
        if vec:
            print(f"  Embedding dims: {len(vec)} ✅")
        else:
            print("  Embedding failed (Ollama not running or nomic-embed-text not pulled)")

    asyncio.run(test_embed())
    print("\n" + "=" * 70)
