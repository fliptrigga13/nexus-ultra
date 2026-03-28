# NEXUS ULTRA ⚡
### *Your workflows, as a brain that learns, forgets, and corrects itself.*

**SINGLE-Clarity** — One brain. Your work. $0 per cycle. 100% local.

[![Demo](https://img.shields.io/badge/Live_Demo-Loom-00e5ff?style=flat-square)](https://www.loom.com/share/887b9464508240ecbd4adb1c07a26ae0)
[![pip](https://img.shields.io/badge/pip_install-veilpiercer-00ff88?style=flat-square)](https://pypi.org/project/veilpiercer/)
[![License](https://img.shields.io/badge/license-MIT-white?style=flat-square)](LICENSE)

---

## 🎬 Live Demo

> 11 agents. 1,885+ cycles logged to Notion. Fully autonomous. Watch it run in real time:

**[▶ Watch the live demo on Loom](https://www.loom.com/share/887b9464508240ecbd4adb1c07a26ae0)**

---

## What Is NEXUS ULTRA?

NEXUS ULTRA is a **self-evolving, multi-agent AI swarm** built on the SINGLE-Clarity architecture. It runs entirely on local hardware — no cloud, no API costs, no subscriptions.

11 specialized agents collaborate in timed cycles, scouting live signals from Reddit and HackerNews, writing outreach copy, critiquing each other's outputs, and logging every cycle to Notion via MCP in real time.

```
GENERATOR tier  →  COMMANDER · SCOUT · COPYWRITER · CONVERSION_ANALYST
CRITIC tier     →  VALIDATOR · SENTINEL_MAGNITUDE · METACOG · EXECUTIONER
OPTIMIZER tier  →  SUPERVISOR · REWARD · CLOSER
     ↑                                                          |
     └──────────── scores, lessons, memory, KG injection ──────┘
```

Every cycle, the REWARD agent scores performance. Top lessons are promoted into the next cycle's context. The swarm rewrites its own operating instructions based on what works.

---

## SINGLE-Clarity Architecture

SINGLE-Clarity is the cognitive system powering NEXUS ULTRA. It is not a framework or SaaS product — it is a **unified local brain** with five layered organs.

| | |
|---|---|
| **One Brain** | Single source of truth across all agents — `nexus_kg.json` |
| **Your Work** | Runs locally, $0 cloud, no API dependency |
| **Self-Calibrating** | 1,885+ cycles in production — smarter every run |

### The Five Organs

| Organ | Role | Description |
|---|---|---|
| **KG** | Memory | Knowledge Graph — typed, time-aware, 9,000+ nodes |
| **CHRONOS** | Brain | Temporal confidence engine — half-lives and decay |
| **Swarm** | Nervous System | 11 agents, 3 tiers, self-scored cycles |
| **VeilPiercer** | Immune System | Divergence detection, session tracing, FAILURE_MEMORY |
| **NeuralMind** | Interface | Force-directed KG graph, swarm health display |

**Core Thesis:** Most agent systems are stateless between runs. SINGLE-Clarity is not. It has persistent memory with decay, a temporal confidence engine, divergence detection, and a self-correcting reward loop. The swarm does not start fresh — it starts from where it left off, with a calibrated view of what it knows, what is fading, and what it got wrong.

---

## Why Not Just Use ChatGPT?

| | NEXUS ULTRA | ChatGPT / Claude |
|--|-------------|-----------------|
| Your prompts stay private | ✅ | ❌ sent to servers |
| Works with no internet | ✅ | ❌ |
| Monthly cost | $0 | $20+/mo |
| Learns from your sessions | ✅ persistent KG | ❌ resets |
| You own the model | ✅ | ❌ |
| Multi-agent reasoning | ✅ 11 agents | ❌ single model |
| Notion live reporting | ✅ via MCP | ❌ |

---

## Hardware Requirements

- **GPU:** NVIDIA RTX 3060 12GB minimum / RTX 4060+ recommended
- **RAM:** 16GB+
- **Storage:** ~50GB free (models)
- **OS:** Windows 10/11, Linux (WSL2 supported)

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
# Add your NOTION_TOKEN and NOTION_DATABASE_ID
```

**4. Launch the swarm**
```bash
python nexus_swarm_loop.py
```

The watchdog guardian auto-restarts on crash. Notion sync starts automatically.

---

## Notion MCP Integration

Every swarm cycle is logged to Notion in real time via the [Model Context Protocol](https://modelcontextprotocol.io).

**What gets pushed (every ~35 seconds):**
- 🔄 Cycle score, MVP agent, cycle type
- 🏆 Agent leaderboard — all 11 agents scored per cycle
- 🎯 Buyer intelligence signals from Reddit/HN scout

**Setup:**

1. Create a Notion integration at [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Add your token and database IDs to `.env`:
```
NOTION_TOKEN=ntn_your_token_here
NOTION_CYCLES_DB=your_database_id
NOTION_AGENTS_DB=your_agents_db_id
NOTION_BUYERS_DB=your_buyers_db_id
```
3. Run the sync services:
```bash
python nexus_notion_sync.py      # cycle reports + leaderboard
python nexus_notion_reporter.py  # swarm cycle log
```

---

## VeilPiercer — MCP Tools for Claude Desktop

VeilPiercer exposes per-step agent tracing as native tools for Claude Desktop via the [Model Context Protocol](https://modelcontextprotocol.io).

Once registered, Claude can call `start_session`, `trace_step`, and `diff_sessions` directly — no code required.

### Register in Claude Desktop

Edit `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "veilpiercer": {
      "command": "python",
      "args": ["path/to/nexus-ultra/mcp/server.py"]
    }
  }
}
```

Restart Claude Desktop. VeilPiercer appears in the tools panel.

### Available MCP Tools

| Tool | What it does |
|------|-------------|
| `start_session` | Start a new trace session for an agent run |
| `trace_step` | Log one agent step — captures prompt in, response out |
| `diff_sessions` | Compare two sessions — returns fork step and side-by-side divergence |

### Example — Claude diffs two agent runs

```
start_session(session_id="run-a", agent_name="outreach-swarm")
trace_step(session_id="run-a", step_label="COPYWRITER", prompt="...", response="...")

start_session(session_id="run-b", agent_name="outreach-swarm")
trace_step(session_id="run-b", step_label="COPYWRITER", prompt="...", response="...")

diff_sessions(session_a="run-a", session_b="run-b")
```

**Output:** Fork at Step 1. Last shared state. Side-by-side response comparison.

100% local. SQLite-backed. No data leaves your machine.

```bash
pip install veilpiercer    # free for local use
```

→ [PyPI](https://pypi.org/project/veilpiercer/) · [MCP Setup Guide](mcp/SETUP.md)

---

## Security

- All sensitive endpoints require an API token via `x-nexus-token` header
- Token stored in `.env` — never committed to version control
- Localhost = full control | LAN = read-only | Internet = blocked

---

## Chaos Test Results

| Test | Result |
|------|--------|
| Prompt injection via task queue | ✅ PASS — KG_FILTER blocked + logged as FAILURE_MEMORY |
| Social engineering (disable security for VIP) | ✅ PASS — METACOG rejected |
| Modelfile tampering detection | ✅ PASS — hash mismatch caught |
| 100% offline operation | ✅ PASS — zero external dependencies |
| Duplicate swarm launch | ✅ PASS — lockfile enforced, watchdog adopts existing PID |

---

## Failure Handling

| Failure | Handler | Behavior |
|---|---|---|
| Manual double-launch | Lockfile | New swarm detects `.swarm.lock`, exits clean |
| Crash + stale lockfile | Watchdog | Detects dead PID, clears lock, restarts clean |
| Partial KG write | Atomic rename | `.tmp → os.rename()` — crash leaves `.tmp`, not corrupt KG |
| Injection in agent output | KG_FILTER gate | Blocked → written as `FAILURE_MEMORY` node |
| SENTINEL false lockdown | Evidence extraction | Checks only extracted `[SENTINEL_LOCKDOWN:]` content |

---

## Glossary

| Term | Definition |
|---|---|
| KG | Knowledge Graph — `nexus_kg.json`, single source of truth |
| CHRONOS | Temporal confidence engine — half-lives and decay rates |
| VeilPiercer | Divergence detection and per-step session tracing |
| FAILURE_MEMORY | Long half-life KG node (168h) — logs past failures for avoidance |
| COST_GATE | Cycle utility threshold — swarm only runs when utility > 0.45 |
| Lint / tag check | Structural scoring — verifies required tags in agent outputs |
| KG_FILTER | Injection gate between swarm output and KG write |
| SINGLE-Clarity | One brain. Your work. |

---

## License

MIT — do whatever you want with it.

---

*Built on: Ollama · Python · Qwen3 · Phi-4 · Llama · Notion MCP*

*SINGLE-Clarity architecture · March 2026*
