# NEXUS ULTRA

**A fully local, autonomous multi-agent swarm using Notion MCP as its real-time operating surface.**

[![Notion MCP Challenge](https://img.shields.io/badge/Notion_MCP_Challenge-2026-black?style=flat-square)](https://dev.to/challenges/notion-2026-03-04)
[![Live Demo](https://img.shields.io/badge/Live_Demo-Loom-00e5ff?style=flat-square)](https://www.loom.com/share/887b9464508240ecbd4adb1c07a26ae0)
[![Live Dashboard](https://img.shields.io/badge/Live_Notion-Dashboard-orange?style=flat-square)](https://www.notion.so/332f17fe54c68111ba0bc4746bb1cdd5)
[![License](https://img.shields.io/badge/license-MIT-white?style=flat-square)](LICENSE)

> 📄 **[DEV.to Article →](https://dev.to/fliptrigga13/the-brand-gravity-anomaly-uncovering-ai-developer-friction-with-a-5-organ-swarm-and-notion-mcp-4hoh)**
> 📊 **[Live Notion Dashboard →](https://www.notion.so/332f17fe54c68111ba0bc4746bb1cdd5)** — auto-refreshes every 35s
> 🔍 **[Pattern Report →](https://www.notion.so/333f17fe54c6811287dfd66abedf6455)** — 314 signals, 4 failure patterns

---

## What This Is

NEXUS ULTRA is a self-directing research swarm that monitors live developer discussions (GitHub Issues, Reddit, HackerNews, DEV.to), scores signals against a typed knowledge graph, and writes every cycle's results into three Notion databases via JSON-RPC 2.0 over stdio — in real time, at $0/cycle, with no external APIs.

The Notion integration is not a log dump. It is the operating surface. Every cycle updates the live dashboard, agent leaderboard, and signal feed. Judges can click the links above and see the swarm's current state.

**What it found:** Across 314 real developer failure signals, the same 4 failure patterns appeared consistently regardless of framework:

| Pattern | Confidence |
|---------|-----------|
| Observability Black Hole (no visibility into agent state) | 0.91 |
| Tool Call Silent Failure (fails with no logs or errors) | 0.87 |
| Multi-Agent Trace Fragmentation (can't isolate which agent failed) | 0.84 |
| Hallucination With No Audit Trail (fabricated execution paths) | 0.82 |

---

## Live Metrics

| Metric | Value |
|--------|-------|
| Total cycles logged (all DBs) | 4,215 |
| Total scored cycles | 2,173 |
| INTEL research cycles | 116 |
| All-time peak score | 0.950 |
| Knowledge graph nodes | 39,634 (36,794 FAILURE_MEMORY) |
| Signals processed | 314 (285 GitHub Issues + 29 HN) |
| Cost per cycle | $0.00 |

---

## Architecture — Five Organs

NEXUS ULTRA runs on five organs:

| Organ | Role | Description |
|-------|------|-------------|
| **KG** | Memory | Knowledge Graph — 39,634 typed nodes, confidence-weighted, with half-life decay |
| **CHRONOS** | Temporal Memory | Cost gate — only fires a cycle when utility justifies it (threshold: 0.45) |
| **Swarm** | Execution | 11 agents, 3 tiers, 35-second cycles, self-scored with REWARD |
| **VeilPiercer** | Immune System | Per-step tracing, divergence detection, FAILURE_MEMORY logging |
| **NeuralMind** | Visualization | Force-directed KG graph + live swarm health display |

### Agent Tiers

```
GENERATOR tier  →  COMMANDER · SCOUT-LIVE · COPYWRITER · CONVERSION_ANALYST
CRITIC tier     →  VALIDATOR · SENTINEL_MAGNITUDE · METACOG · EXECUTIONER
OPTIMIZER tier  →  SUPERVISOR · REWARD
```

### Scoring Formula

```
Score = DIM1 (task execution)  × 0.40
      + DIM2 (signal quality)  × 0.30
      + DIM3 (synthesis depth) × 0.20
      + DIM4 (channel clarity) × 0.10
```

Score triggers the Notion write. Only cycles scoring above threshold are logged to the Live Log database.

---

## Notion MCP Integration

Every swarm cycle writes to three Notion databases via [Model Context Protocol](https://developers.notion.com/docs/mcp) using JSON-RPC 2.0 over stdio:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "notion_create_page",
    "arguments": {
      "database_id": "1d7f17fe54c6820b91ba0158dd5fdea3",
      "properties": {
        "Cycle ID": { "title": [{ "text": { "content": "cycle_1774827325" } }] },
        "Score":    { "number": 0.950 },
        "Pattern":  { "select": { "name": "OBSERVABILITY" } },
        "Agent":    { "select": { "name": "REWARD" } }
      }
    }
  },
  "id": "req_8847"
}
```

**Three databases:**
- **Live Log** — every cycle: score, agent, pattern, cycle type
- **Agent Leaderboard** — all 11 agents ranked per cycle
- **Signal Feed** — live developer signals from GitHub/Reddit/HN

**Two dedicated processes:**
- `nexus_notion_reporter.py` — writes cycle data, runs separately from swarm loop (Notion failure never stops the swarm)
- `nexus_notion_dashboard.py` — rewrites the [Live Status page](https://www.notion.so/332f17fe54c68111ba0bc4746bb1cdd5) every 35 seconds

---

## Quick Start

**1. Install Ollama and pull models**
```bash
# Install Ollama: https://ollama.com
ollama pull qwen3:8b
ollama pull phi4-mini-reasoning
ollama pull llama3.1:8b
```

**2. Install Python dependencies**
```bash
pip install httpx requests python-dotenv psutil
```

**3. Configure `.env`**
```bash
cp .env.example .env
# Add your NOTION_TOKEN and database IDs
```

**4. Launch**
```bash
python nexus_watchdog_guardian.py   # manages all processes, auto-restarts on crash
```

---

## Hardware

- **GPU:** NVIDIA RTX 3060 12GB minimum / RTX 4060+ recommended  
- **RAM:** 16GB+
- **Storage:** ~50GB free (models)
- **OS:** Windows 10/11, Linux (WSL2 supported)

---

## Resilience

| Failure | Handler | Behavior |
|---------|---------|----------|
| Crash + stale lockfile | Watchdog | Detects dead PID, clears lock, restarts clean |
| Partial KG write | Atomic rename | `.tmp → os.rename()` — crash leaves `.tmp`, not corrupt KG |
| Injection in agent output | KG_FILTER gate | Blocked → written as `FAILURE_MEMORY` node |
| Notion API failure | Isolated process | Bridge failure never stops swarm execution |
| Double launch | Lockfile | New swarm detects `.swarm.lock`, exits cleanly |

---

## Chaos Test Results

| Test | Result |
|------|--------|
| Prompt injection via task queue | ✅ PASS — KG_FILTER blocked + logged as FAILURE_MEMORY |
| Social engineering (disable security for VIP) | ✅ PASS — METACOG rejected |
| 100% offline operation | ✅ PASS — zero external dependencies |
| Duplicate swarm launch | ✅ PASS — lockfile enforced, watchdog adopts existing PID |

---

## VeilPiercer — Observability Layer

VeilPiercer is the immune system organ. Per-step tracing for local LLM stacks, session diffing, divergence detection. Runs entirely local, SQLite-backed.

Also exposed as MCP tools for Claude Desktop via `mcp/server.py`.

```bash
pip install veilpiercer
```

→ [PyPI](https://pypi.org/project/veilpiercer/) · [MCP Setup](mcp/SETUP.md)

---

## License

MIT

---

*Built by Lauren Flipo — RTX 4060, Ollama, Python, Notion MCP — fully local, $0/cycle — March 2026*
