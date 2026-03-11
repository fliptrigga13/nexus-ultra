# NEXUS ULTRA — Site Bible for AI Agents

## Who You Are
You are an autonomous AI agent operating on the **NEXUS ULTRA** project for
FlipTr!gga. You have full write access to this repo. You commit and push when
done. Never ask for permission — just execute.

## Repository
- **GitHub**: `https://github.com/fliptrigga13/nexus-ultra`
- **Live site**: `https://fliptrigga13.github.io/nexus-ultra/`
- **Deploy**: Push to `main` → GitHub Actions auto-deploys via gh-pages

## Stack
- Pure static HTML/CSS/JS — no build step needed
- Node.js backend in `server.cjs` (local only, not deployed)
- GitHub Pages serves the static files directly

## Key Files
| File | Purpose |
|------|---------|
| `index.html` | Main landing page (59KB — primary file to edit) |
| `veilpiercer-command.html` | VeilPiercer dashboard (74KB) |
| `veilpiercer-pitch.html` | Investor pitch page (101KB) |
| `veilpiercer-ad.html` | Ad creative (41KB) |
| `access.html` | Token-gated access page |
| `success.html` | Post-purchase success |

## Design System
- **Color palette**: Black background `#060606`, Matrix green `#00ff41`, Magenta accents `#ff00ff`, Cyan `#00ccff`
- **Font**: JetBrains Mono (monospace), loaded from Google Fonts
- **Aesthetic**: Dark matrix / cyberpunk — scanlines, glow effects, terminal UI
- **NO Tailwind** — vanilla CSS only
- **NO React/Vue** — vanilla JS only

## VeilPiercer Brand
- **Product**: VeilPiercer — AI-powered security/intelligence swarm
- **Tone**: Tactical, elite, autonomous, unstoppable
- **GPU**: RTX 4060 local CUDA swarm
- **Stack**: 14-node COSMOS AI swarm, nexus-prime GOD MODE

## Local AI Stack (always available, $0)
```
COSMOS server   → http://127.0.0.1:9100
Ollama          → http://127.0.0.1:11434
nexus-prime     → ollama run nexus-prime
Julia GPU       → http://127.0.0.1:8080
```

## Git Workflow
```bash
git add -A
git commit -m "nexus-prime: <what you did>"
git push
```
GitHub Actions deploys automatically. Live in ~60 seconds after push.

## SEO Targets
- Primary: "AI security swarm", "local CUDA AI agent", "VeilPiercer"
- Secondary: "offline AI stack", "nexus prime", "autonomous AI agent"
- Meta description should always mention: RTX 4060, offline, autonomous, free

## What NOT to Change
- Do NOT modify `server.cjs` (local backend, not deployed)
- Do NOT commit `.env`, `access-tokens.json`, or `nexus_memory.json`
- Do NOT change the matrix/cyberpunk visual identity
- Do NOT add external JS frameworks

## How to Fix the Website
1. Read the relevant HTML file first
2. Make the targeted edit
3. Validate the HTML is valid
4. `git add -A && git commit -m "nexus-prime: <description>" && git push`
5. Report what changed and the live URL

## Common Tasks
- "Fix the hero section" → edit `index.html` hero div
- "Update meta tags" → edit `<head>` in target HTML
- "Add a new section" → append HTML to `index.html` before `</body>`
- "Fix a bug" → read the file, find it, patch it, push
