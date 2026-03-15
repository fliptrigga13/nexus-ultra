"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  NEXUS SELF-EVOLUTION LOOP                                                  ║
║  Autonomous overnight AI self-improvement engine                            ║
║  Runs cycles of: reflect → extract → update → evolve → sync                ║
╚══════════════════════════════════════════════════════════════════════════════╝

Each evolution cycle:
  1. REFLECT   — AI analyzes its own recent sessions and memory
  2. SYNTHESIZE — Extracts new facts, patterns, and self-improvements
  3. UPDATE    — Writes new MEMORY_FLAGs into the memory DB
  4. EVOLVE    — Improves system prompt / modelfile for nexus-prime
  5. REPORT    — Logs a readable evolution report
  6. SYNC      — Pushes everything to Google Drive

Run: python SELF_EVOLUTION_LOOP.py [--cycles N] [--once]
Scheduler: runs nightly at 2:00 AM via Task Scheduler
"""

import json, os, sys, time, datetime, re, subprocess, urllib.request, urllib.error
import argparse

# ── CONFIG ────────────────────────────────────────────────────────────────────
ROOT         = r"C:\Users\fyou1\Desktop\New folder\nexus-ultra"
OLLAMA_URL   = "http://127.0.0.1:11434"
HUB_URL      = "http://127.0.0.1:3000"
RCLONE       = r"C:\Users\fyou1\AppData\Local\Microsoft\WinGet\Packages\Rclone.Rclone_Microsoft.Winget.Source_8wekyb3d8bbwe\rclone-v1.73.2-windows-amd64\rclone.exe"
REMOTE       = "googledrive:Nexus-Ultra-Backup/EVOLUTION"
MEMORY_REMOTE = "googledrive:Nexus-Ultra-Backup/MEMORY"

MEMORY_FILE  = os.path.join(ROOT, "nexus_session_facts.json")
EVOLUTION_LOG = os.path.join(ROOT, "evolution_log.json")
EVOLUTION_RPT = os.path.join(ROOT, "evolution_report.md")
MODELFILE    = os.path.join(ROOT, "nexus_prime_evolved.modelfile")
SYSFILE      = os.path.join(ROOT, "nexus_prime_system.txt")

EVOLUTION_MODEL = "nexus-prime:latest"  # reflect with your custom model
FAST_MODEL      = "llama3.2:latest"     # fast model for quick tasks

CYCLE_INTERVAL = 3600  # 1 hour between full cycles (when running continuous)
MAX_FACTS_PER_CYCLE = 8

# ── HELPERS ───────────────────────────────────────────────────────────────────
def log(msg, level="INFO"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    try:
        with open(os.path.join(ROOT, "evolution_run.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except: pass
    return line

def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default if default is not None else {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

def ollama_chat(prompt, model=None, system=None, timeout=120):
    """Call Ollama /api/chat, return response text."""
    model = model or FAST_MODEL
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})

    body = json.dumps({"model": model, "messages": msgs, "stream": False}).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read())
            return d.get("message", {}).get("content", "").strip()
    except Exception as e:
        log(f"Ollama error: {e}", "WARN")
        return ""

def hub_get(path):
    """GET from hub server."""
    try:
        with urllib.request.urlopen(f"{HUB_URL}{path}", timeout=5) as r:
            return json.loads(r.read())
    except:
        return {}

def hub_post(path, data=None):
    """POST to hub server."""
    try:
        body = json.dumps(data or {}).encode()
        req = urllib.request.Request(f"{HUB_URL}{path}", data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"ok": False, "error": str(e)}

def rclone_sync(src, dst):
    try:
        subprocess.run([RCLONE, "copyto", src, dst, "--log-level", "ERROR"],
                       timeout=30, check=False)
    except: pass

def check_ollama():
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as r:
            d = json.loads(r.read())
            return [m["name"] for m in d.get("models", [])]
    except:
        return []

# ── PHASE 1: REFLECT ─────────────────────────────────────────────────────────
def phase_reflect(gen_num):
    """Gather context: memory, recent missions, queue state."""
    log(f"Phase 1 · REFLECT — Generation {gen_num}")

    # Load current memory
    mem_db = load_json(MEMORY_FILE, {"facts": [], "session_count": 0})
    active_facts = [f for f in mem_db.get("facts", []) if not f.get("stale")]

    # Get recent activity from hub
    missions = hub_get("/missions").get("missions", [])[:10]
    queue    = hub_get("/queue").get("queue", [])[:10]
    svc_st   = hub_get("/api/system-status")

    # Load evolution history
    evo_log = load_json(EVOLUTION_LOG, {"generations": [], "total_facts_added": 0})
    prev_gen = evo_log["generations"][-1] if evo_log["generations"] else None

    context = {
        "gen_num": gen_num,
        "active_facts": active_facts,
        "missions": missions,
        "queue": queue,
        "svc_status": svc_st,
        "prev_generation": prev_gen,
        "session_count": mem_db.get("session_count", 0),
        "total_facts": len(mem_db.get("facts", [])),
    }

    log(f"  · {len(active_facts)} active facts, {len(missions)} missions, session #{context['session_count']}")
    return context

# ── PHASE 2: SYNTHESIZE ──────────────────────────────────────────────────────
def phase_synthesize(ctx):
    """Use AI to analyze context and extract new knowledge."""
    log("Phase 2 · SYNTHESIZE — AI self-analysis")

    facts_txt = "\n".join(f"  {i+1}. {f['content']}" for i,f in enumerate(ctx["active_facts"][:15]))
    missions_txt = "\n".join(f"  - {m.get('task', m.get('description', str(m)))[:120]}" for m in ctx["missions"])
    prev_txt = ""
    if ctx["prev_generation"]:
        pg = ctx["prev_generation"]
        prev_txt = f"\nLast evolution (Gen {pg.get('gen_num',0)}): added {pg.get('facts_added',0)} facts, score={pg.get('quality_score',0):.2f}"

    system_prompt = """You are the Nexus Prime self-evolution engine. Your job is to:
1. Analyze current knowledge and recent activity
2. Identify patterns, gaps, and improvement opportunities  
3. Generate new [MEMORY_FLAG: fact] entries that are SPECIFIC, ACTIONABLE, and NOVEL
4. Suggest improvements to your own system prompt
5. Score the quality of the current knowledge base (0.0-1.0)

Rules:
- MEMORY_FLAG facts must be concrete (not vague), e.g. "[MEMORY_FLAG: User prefers concise code answers without explanation]"
- Only generate facts you're confident are true based on the evidence
- Each fact must be unique — don't repeat existing facts
- Maximum """ + str(MAX_FACTS_PER_CYCLE) + """ new facts per cycle"""

    prompt = f"""## NEXUS EVOLUTION CYCLE — Generation {ctx['gen_num']}

### Current Knowledge Base ({len(ctx['active_facts'])} active facts):
{facts_txt if facts_txt else '  [Empty — first generation]'}

### Recent Mission Queue:
{missions_txt if missions_txt else '  [No recent missions]'}
{prev_txt}

### Task:
1. Analyze the knowledge base for gaps and patterns
2. Generate up to {MAX_FACTS_PER_CYCLE} new [MEMORY_FLAG: <fact>] entries
3. Identify 1-3 areas where the AI should improve
4. Suggest a 1-2 sentence addition to the system prompt that would improve future responses
5. Rate the current knowledge base quality: [QUALITY_SCORE: 0.XX]

Format your response with clear sections:
## NEW MEMORIES
[MEMORY_FLAG: fact1]
[MEMORY_FLAG: fact2]
...

## IMPROVEMENT AREAS
- Area 1
- Area 2

## SYSTEM PROMPT ENHANCEMENT
<enhancement text>

## QUALITY SCORE
[QUALITY_SCORE: 0.XX]"""

    log("  · Calling Ollama for self-analysis...")
    response = ollama_chat(prompt, model=EVOLUTION_MODEL, system=system_prompt, timeout=180)

    if not response:
        log("  · Primary model failed, trying fast model...", "WARN")
        response = ollama_chat(prompt, model=FAST_MODEL, system=system_prompt, timeout=120)

    if not response:
        log("  · AI synthesis failed — check Ollama", "ERROR")
        return {"response": "", "flags": [], "improvements": [], "prompt_enhancement": "", "quality_score": 0.0}

    # Parse response
    flags = re.findall(r'\[MEMORY_FLAG:\s*([^\]]+)\]', response, re.IGNORECASE)
    flags = [f.strip() for f in flags if len(f.strip()) > 10][:MAX_FACTS_PER_CYCLE]

    improvements = re.findall(r'[-•]\s*(.+)', response)
    improvements = [i.strip() for i in improvements if len(i.strip()) > 10][:5]

    enhancement_m = re.search(r'## SYSTEM PROMPT ENHANCEMENT\s*\n(.+?)(?=##|\Z)', response, re.DOTALL)
    enhancement = enhancement_m.group(1).strip()[:500] if enhancement_m else ""

    qs_m = re.search(r'\[QUALITY_SCORE:\s*([\d.]+)\]', response)
    quality_score = float(qs_m.group(1)) if qs_m else 0.5

    log(f"  · Extracted {len(flags)} new facts, quality_score={quality_score:.2f}")
    return {
        "response": response,
        "flags": flags,
        "improvements": improvements,
        "prompt_enhancement": enhancement,
        "quality_score": quality_score
    }

# ── PHASE 3: UPDATE MEMORY ───────────────────────────────────────────────────
def phase_update_memory(ctx, synthesis):
    """Write new facts to memory DB, deduplicate."""
    log("Phase 3 · UPDATE — Writing new facts to memory")

    mem_db = load_json(MEMORY_FILE, {"version": 2, "facts": [], "session_count": 0, "world_state": {}})
    existing_contents = {f["content"].lower() for f in mem_db["facts"]}

    added = 0
    for flag in synthesis["flags"]:
        if flag.lower() in existing_contents:
            log(f"  · Skip duplicate: {flag[:60]}")
            continue
        fact = {
            "id": f"evo_{ctx['gen_num']}_{int(time.time())}_{added}",
            "content": flag,
            "type": "evolution",
            "importance": 0.85,
            "created_at": datetime.datetime.now().isoformat(),
            "last_accessed": datetime.datetime.now().isoformat(),
            "access_count": 1,
            "stale": False,
            "tags": ["self-evolution", f"gen-{ctx['gen_num']}"],
            "generation": ctx["gen_num"]
        }
        mem_db["facts"].append(fact)
        existing_contents.add(flag.lower())
        added += 1
        log(f"  · +FACT: {flag[:70]}")

    mem_db["last_evolution"] = datetime.datetime.now().isoformat()
    mem_db["evolution_generation"] = ctx["gen_num"]
    save_json(MEMORY_FILE, mem_db)

    # Also push updated facts to hub server
    hub_post("/api/memory/sync-now", {})

    log(f"  · Added {added} new facts. Total: {len(mem_db['facts'])}")
    return added

# ── PHASE 4: EVOLVE SYSTEM PROMPT ────────────────────────────────────────────
def phase_evolve_prompt(ctx, synthesis):
    """Update the nexus-prime system prompt file with accumulated enhancements."""
    log("Phase 4 · EVOLVE — Updating system prompt")

    sys_prompt = load_current_system_prompt()
    enhancement = synthesis.get("prompt_enhancement", "")

    if enhancement and len(enhancement) > 20:
        # Check if this enhancement is already in the prompt
        if enhancement[:50].lower() not in sys_prompt.lower():
            # Append evolution enhancement
            evolved = sys_prompt + f"\n\n[EVOLUTION GEN {ctx['gen_num']} — {datetime.date.today()}]\n{enhancement}"
            with open(SYSFILE, "w", encoding="utf-8") as f:
                f.write(evolved)
            log(f"  · System prompt enhanced ({len(enhancement)} chars added)")

            # Generate updated Ollama modelfile
            generate_modelfile(evolved, ctx["gen_num"])
        else:
            log("  · Enhancement already present, skipping")
    else:
        log("  · No enhancement to apply")

def load_current_system_prompt():
    if os.path.exists(SYSFILE):
        with open(SYSFILE, "r", encoding="utf-8") as f:
            return f.read()
    return """You are NEXUS PRIME — an advanced AI assistant with sovereign intelligence.
You operate within the Nexus Ultra system on a local RTX 4060 GPU.
You have access to persistent memory, real-time system data, and agent capabilities.
Always be direct, technically precise, and maximize value per response.
Use [MEMORY_FLAG: fact] to flag important facts worth remembering across sessions.
"""

def generate_modelfile(system_prompt, gen_num):
    """Generate an Ollama modelfile with the evolved system prompt."""
    modelfile_content = f"""FROM nexus-prime:latest

# NEXUS PRIME — Evolved System (Generation {gen_num})
# Generated: {datetime.datetime.now().isoformat()}

SYSTEM \"\"\"
{system_prompt[:2000]}
\"\"\"

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER num_ctx 4096
"""
    with open(MODELFILE, "w", encoding="utf-8") as f:
        f.write(modelfile_content)
    log(f"  · Modelfile written: {MODELFILE}")
    log(f"  · To apply: ollama create nexus-evolved -f nexus_prime_evolved.modelfile")

# ── PHASE 5: GENERATE REPORT ──────────────────────────────────────────────────
def phase_report(ctx, synthesis, facts_added, cycle_time):
    """Write a human-readable evolution report."""
    log("Phase 5 · REPORT — Writing evolution report")

    gen = ctx["gen_num"]
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Load history for trend stats
    evo_log = load_json(EVOLUTION_LOG, {"generations": [], "total_facts_added": 0})
    total_added = evo_log.get("total_facts_added", 0) + facts_added

    report = f"""# NEXUS EVOLUTION REPORT — Generation {gen}
**Date:** {now}  
**Cycle time:** {cycle_time:.1f}s  
**Model:** {EVOLUTION_MODEL}  
**Quality score this cycle:** {synthesis['quality_score']:.2f}  
**Total facts in memory:** {ctx['total_facts'] + facts_added}  
**Total facts ever added by evolution:** {total_added}

---

## New Facts Learned ({facts_added})
"""
    for flag in synthesis["flags"]:
        report += f"- {flag}\n"
    if not synthesis["flags"]:
        report += "- *(none this cycle)*\n"

    report += f"""
## Improvement Areas Identified
"""
    for imp in synthesis["improvements"][:3]:
        report += f"- {imp}\n"

    report += f"""
## System Prompt Enhancement
```
{synthesis.get('prompt_enhancement', '(none)') or '(none)'}
```

## Evolution Log (Last 5 Generations)
| Gen | Date | Facts Added | Quality |
|---|---|---|---|
"""
    for g in (evo_log["generations"][-5:]):
        report += f"| {g.get('gen_num','?')} | {g.get('timestamp','?')[:10]} | {g.get('facts_added',0)} | {g.get('quality_score',0):.2f} |\n"
    report += f"| {gen} | {now[:10]} | {facts_added} | {synthesis['quality_score']:.2f} |\n"

    report += f"""
## AI Self-Analysis (Raw)
<details>
<summary>Click to expand</summary>

```
{synthesis.get('response','')[:3000]}
```
</details>

---
*Auto-generated by NEXUS Self-Evolution Loop*
"""

    with open(EVOLUTION_RPT, "w", encoding="utf-8") as f:
        f.write(report)

    # Update evolution log
    evo_log["generations"].append({
        "gen_num": gen,
        "timestamp": now,
        "facts_added": facts_added,
        "quality_score": synthesis["quality_score"],
        "cycle_time_s": cycle_time,
        "improvements": synthesis["improvements"][:3],
        "model": EVOLUTION_MODEL
    })
    evo_log["total_facts_added"] = total_added
    evo_log["last_run"] = now
    save_json(EVOLUTION_LOG, evo_log)

    log(f"  · Report written: {EVOLUTION_RPT}")

# ── PHASE 6: SYNC ─────────────────────────────────────────────────────────────
def phase_sync():
    """Push all evolution artifacts to Google Drive."""
    log("Phase 6 · SYNC — Google Drive upload")

    files = [
        (MEMORY_FILE,   f"{MEMORY_REMOTE}/nexus_session_facts.json"),
        (EVOLUTION_RPT, f"{REMOTE}/evolution_report.md"),
        (EVOLUTION_LOG, f"{REMOTE}/evolution_log.json"),
        (MODELFILE,     f"{REMOTE}/nexus_prime_evolved.modelfile"),
        (SYSFILE,       f"{REMOTE}/nexus_prime_system.txt"),
    ]
    for src, dst in files:
        if os.path.exists(src):
            rclone_sync(src, dst)
            log(f"  · Synced: {os.path.basename(src)}")

# ── MAIN EVOLUTION CYCLE ──────────────────────────────────────────────────────
def run_cycle(gen_num):
    """Run one full evolution cycle."""
    log(f"\n{'='*60}")
    log(f"EVOLUTION CYCLE — Generation {gen_num}")
    log(f"{'='*60}")
    t0 = time.time()

    # Check Ollama is available
    models = check_ollama()
    if not models:
        log("Ollama is offline — waiting 60s then retry", "WARN")
        time.sleep(60)
        models = check_ollama()
        if not models:
            log("Ollama still offline — skipping cycle", "ERROR")
            return False

    log(f"Ollama online: {len(models)} models available")

    ctx        = phase_reflect(gen_num)
    synthesis  = phase_synthesize(ctx)
    facts_added = phase_update_memory(ctx, synthesis)
    phase_evolve_prompt(ctx, synthesis)
    cycle_time = time.time() - t0
    phase_report(ctx, synthesis, facts_added, cycle_time)
    phase_sync()

    log(f"\n✓ Generation {gen_num} complete in {cycle_time:.1f}s")
    log(f"  Facts added: {facts_added}")
    log(f"  Quality: {synthesis['quality_score']:.2f}")
    return True

# ── ENTRY POINT ───────────────────────────────────────────────────────────────
def get_current_generation():
    evo_log = load_json(EVOLUTION_LOG, {"generations": []})
    gens = evo_log.get("generations", [])
    return (gens[-1]["gen_num"] + 1) if gens else 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NEXUS Self-Evolution Loop")
    parser.add_argument("--cycles", type=int, default=0,
                        help="Number of cycles (0=infinite)")
    parser.add_argument("--once", action="store_true",
                        help="Run exactly one cycle then exit")
    parser.add_argument("--interval", type=int, default=CYCLE_INTERVAL,
                        help=f"Seconds between cycles (default: {CYCLE_INTERVAL})")
    args = parser.parse_args()

    log("NEXUS SELF-EVOLUTION LOOP STARTING")
    log(f"Model: {EVOLUTION_MODEL} | Fast: {FAST_MODEL}")
    log(f"Memory: {MEMORY_FILE}")

    # Initialize system prompt if not present
    if not os.path.exists(SYSFILE):
        with open(SYSFILE, "w", encoding="utf-8") as f:
            f.write(load_current_system_prompt())
        log("System prompt initialized")

    gen = get_current_generation()
    cycles_done = 0
    max_cycles = args.cycles if args.cycles > 0 else (1 if args.once else float("inf"))

    while cycles_done < max_cycles:
        try:
            success = run_cycle(gen)
            if success:
                gen += 1
                cycles_done += 1
        except KeyboardInterrupt:
            log("\nEvolution loop stopped by user")
            break
        except Exception as e:
            log(f"Cycle error: {e}", "ERROR")

        if cycles_done < max_cycles:
            log(f"Next cycle in {args.interval}s (press Ctrl+C to stop)...")
            try:
                time.sleep(args.interval)
            except KeyboardInterrupt:
                log("Evolution loop stopped")
                break

    log(f"Evolution loop finished. Total cycles: {cycles_done}, Generations: {gen-1}")
