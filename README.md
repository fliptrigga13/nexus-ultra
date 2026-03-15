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

## License

MIT — do whatever you want with it.

---

*Built on: Ollama · Python · Julia · DeepSeek · Qwen · Llama · Gemma*
