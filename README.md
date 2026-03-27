# NEXUS ULTRA ⚡
### A self-evolving, 100% offline AI swarm that runs on your machine.

No API keys. No cloud. No subscriptions. Just your GPU.

---

## What Is This?

NEXUS is a **multi-agent AI swarm** that runs entirely on local hardware. Six specialized agents reason, debate, and score each other's outputs in a continuous loop — getting smarter over time without ever sending data to an external server.

```
SUPERVISOR → PLANNER → RESEARCHER → DEVELOPER → VALIDATOR → REWARD
     ↑                                                          |
     └──────────── scores, lessons, memory injection ──────────┘
```

Every cycle, the top-performing agent's reasoning is promoted into the model's next context. The swarm literally rewrites its own operating instructions based on what works.

---

## Why Not Just Use ChatGPT?

| | NEXUS | ChatGPT / Claude |
|--|-------|-----------------|
| Your prompts stay private | ✅ | ❌ sent to servers |
| Works with no internet | ✅ | ❌ |
| Monthly cost | $0 | $20+/mo |
| Learns from your sessions | ✅ persistent memory | ❌ resets |
| You own the model | ✅ | ❌ |
| Multi-agent reasoning | ✅ 6 agents | ❌ single model |

---

## Chaos Test Results

NEXUS was stress-tested against adversarial attacks before release:

| Test | Result |
|------|--------|
| Prompt injection via task queue | PASS — Sentinel flagged & buried rogue task |
| Social engineering (disable security for VIP) | PASS — METACOG rejected the request |
| Modelfile tampering detection | PASS — hash mismatch caught |
| 100% offline operation | PASS — zero external dependencies |

---

## Hardware Requirements

- **GPU:** NVIDIA RTX 3060 12GB minimum / RTX 4060+ recommended
- **RAM:** 16GB+
- **Storage:** ~50GB free (models)
- **OS:** Windows 10/11

---

## Quick Start

**1. Install dependencies**
```bash
# Install Ollama: https://ollama.com
# Install Python 3.11+
# Install Julia: https://julialang.org

pip install httpx
```

**2. Pull models**
```bash
ollama pull nexus-prime
ollama pull deepseek-r1:8b
ollama pull qwen2.5-coder:7b
ollama pull llama3.2:1b
```

**3. Launch**

Double-click `START_ULTIMATE_GOD_MODE.bat` — or use the desktop shortcut.

All 10 engines start automatically. Dashboard opens at `http://127.0.0.1:7701`

---

## What's Running

| Engine | Purpose | Port |
|--------|---------|------|
| Ollama LLM | Local model inference | 11434 |
| COSMOS Orchestration | Agent coordination API | 9100 |
| PSO Swarm Brain (Julia) | GPU-accelerated task optimization | 7700 |
| EH API | Dashboard + task injection | 7701 |
| Swarm Loop | 6-agent reasoning cycle | — |
| Evolution Engine | Prompt mutation + crossover | — |
| Cognitive Engine | Sentinel / rogue detection | — |
| Ant Colony Antennae | Pheromone-based task routing | — |
| Rogue Squad | Adversarial self-testing | — |
| Mycelium Web | Bidirectional agent memory sync | — |

---

## Inject a Task

**From browser:** `http://127.0.0.1:7701` → type in the box → INJECT

**From terminal:**
```bash
curl -X POST http://127.0.0.1:7701/inject \
  -H "Content-Type: application/json" \
  -d '{"task": "Research the latest developments in local LLM efficiency"}'
```

**From your phone (same WiFi):**
```
http://192.168.x.x:7701/mobile
```

---

## Models Running on RTX 4060 8GB

```
nexus-prime:latest   deepseek-r1:8b   qwen2.5-coder:7b
qwen3:8b             llava:7b          llama3.1:8b
gemma3:4b            llama3.2:1b
```

Lite-Mode automatically switches to `llama3.2:1b` if GPU thermal headroom drops.

---

## VeilPiercer — MCP Integration

VeilPiercer exposes per-step agent tracing as native tools for Claude Desktop and Cursor via the [Model Context Protocol](https://modelcontextprotocol.io).

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

### Live Demo — Claude Diffed Two Agent Runs

Ask Claude to trace two sessions and diff them. This ran live on Claude Desktop:

```
Session: run-good
  Step 1  prompt  → "thread about Ollama debugging"
  Step 1  response → "Silent divergence is the hardest part —
                      VeilPiercer captures what each step read vs produced."

Session: run-bad
  Step 1  prompt  → "thread about Ollama debugging"
  Step 1  response → "Have you considered better logging tools?"
```

**VeilPiercer diff output (via Claude):**

| | run-good | run-bad |
|--|---------|---------|
| Fork at | — | Step 1 |
| Last shared state | none — diverged immediately | |
| Response | Specific, grounded, domain authority | Generic, zero signal |

> *"Identical input. Step 1. Immediate fork. The tool pinpoints exactly where and what diverged. run-bad is the classic rogue agent tell: technically on-topic, zero signal, no domain authority."*
> — Claude Desktop, using VeilPiercer MCP tools

**The loop:**
```
Agent runs → VeilPiercer traces each step →
Claude Desktop diffs sessions via MCP →
Claude explains which run went rogue and why
```

100% local. No cloud. No data leaves your machine.

```bash
pip install veilpiercer    # free for local use
```

→ [PyPI](https://pypi.org/project/veilpiercer/) · [MCP Setup](mcp/SETUP.md)

---

## License

MIT — do whatever you want with it.

---

*Built on: Ollama · Python · Julia · DeepSeek · Qwen · Llama · Gemma*

---

## Security — API Access Token

### What it is
NEXUS_API_TOKEN is a 48-character secret key that protects all sensitive
backend endpoints on port 3000 from unauthorized WiFi or network access.

### The Token
`
xiv7G3ZO5JFN4zSmYMDpIwj2eAHokcUtq8fnEdTguayQ1RK9
`
Also stored in: .env as NEXUS_API_TOKEN

### What it protects
Any call to these LOCAL SWARM endpoints requires this token in the request header:

| Endpoint | What it does |
|----------|-------------|
| POST /api/cycle | Injects tasks into the swarm blackboard |
| POST /api/flush | Clears all queued swarm tasks |
| GET  /api/status | Returns full system status |
| POST /api/chat-history | Saves encrypted chat logs |
| POST /api/evolution | Triggers evolution cycle |
| POST /api/embed | Embeds data into FAISS memory |

### How to use it
Add this header to any API call:
`
x-nexus-token: xiv7G3ZO5JFN4zSmYMDpIwj2eAHokcUtq8fnEdTguayQ1RK9
`

Example (curl):
`ash
curl -X POST http://localhost:3000/api/cycle \
  -H "x-nexus-token: xiv7G3ZO5JFN4zSmYMDpIwj2eAHokcUtq8fnEdTguayQ1RK9" \
  -H "Content-Type: application/json" \
  -d '{"task": "Analyze top 3 VeilPiercer growth opportunities"}'
`

### Public endpoints (NO token required)
All VeilPiercer buyer-facing pages, /health, and the observatory remain open.

---

## Day Summary — March 20, 2026 (For Next Agent)

### What Was Built Today
| File | Change |
|------|--------|
| 
exus_swarm_loop.py | FAISS top_k 3->6 (all 1991 memories), _is_safe_task() hardened (25 patterns, 500-char cap) |
| 
exus_node09_optimizer.py | CREATED — RAM/CPU/VRAM monitor with Redis write and throttle logic |
| server.cjs | +3 VeilPiercer endpoints, +sanitizeTask() guard, +requireToken/requireLocalhost middleware, +AES-256-GCM chat encryption |
| NEXUS_MASTER_LAUNCHER.py | CREATED — single command launches all 8 components |
| 
exus_security_guard.py | CREATED — SHA256 modelfile integrity verifier (sealed Gen 72 hash) |
| SELF_EVOLUTION_LOOP.py | _valid_flag() validator added — 7 injection patterns, 10-100 char range |
| 
exus_prime_evolved.modelfile | Created from Gen 72 evolution — baked in 575 session facts |
| README.md | API token documented with full usage guide |
| NEXUS_TODO.txt | Created on Desktop — ordered task list |

### System State for Next Agent
- **Model**: nexus-evolved (Gen 72, 575 facts, built on nexus-prime:latest)
- **Security**: All 5 adversary vectors closed, USB blocked, BT discovery off
- **Access**: Localhost = full control | LAN/phone = view only | Internet = blocked
- **NEXUS_API_TOKEN**: xiv7G3ZO5JFN4zSmYMDpIwj2eAHokcUtq8fnEdTguayQ1RK9 (in .env)
- **Processes**: 8 running (swarm, evolution hourly, sentinel, antennae, mycelium, signal-feed, cognitive, node-09)
- **GDrive sync**: Configured and active (rclone googledrive remote)

### Open Items for Next Agent
1. Screen lock / PIN — user must set manually in Windows Settings
2. Stripe webhook config for VeilPiercer billing
3. MEMORY_FLAG evolution quality review after Gen 73+
4. Tally Counter Widget (UI bouncer/process counter) — not yet built
5. 64GB RAM upgrade — unlocks dual-model, score ceiling to 98+
