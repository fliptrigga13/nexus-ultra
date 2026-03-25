"""
╔══════════════════════════════════════════════════════════════════════╗
║  NEXUS ULTRA — LAPTOP-SAFE POWER UNLOCK                             ║
║  Tailored for: i7-13620H | RTX 4060 Laptop GPU | 32GB RAM           ║
║  Constraint: ~4-5 GB free RAM. Laptop thermal limits. Battery aware. ║
║                                                                       ║
║  DO NOT use the desktop UNLOCK_FULL_POWER.py on this machine.        ║
║  Desktop config assumes unconstrained 32GB + desktop GPU TDP.        ║
╚══════════════════════════════════════════════════════════════════════╝

What this does vs the low-RAM baseline:
  ✅ LOOP_INTERVAL:   45s  → 35s    (faster cycles, not max to allow cooling)
  ✅ MAX_MEMORY:      100  → 150    (more context, not 200 to save parse RAM)
  ✅ LITE_THRESHOLD:  15   → 18     (protect RAM, not desktop's 20)
  ✅ Semaphore:       1    → 2      (2 concurrent ollama calls — safe for 32GB)
  ✅ num_ctx:         1024 → 1536   (middle ground — 2048 causes VRAM swaps)
  ✅ Token budgets:   modest boost  (not desktop max — stay under VRAM limit)
  ✅ Prune threshold: 85   → 90     (not desktop's 92 — be more protective)

Laptop safety rules enforced:
  ⚠️  num_ctx kept at 1536 (NOT 2048) — RTX 4060 Laptop has shared VRAM budget
  ⚠️  Semaphore stays at 2 (NOT 3+) — concurrent thermal spike risk on laptop
  ⚠️  LITE_THRESHOLD at 18 (NOT 20) — 4.5GB free means we're already close
  ⚠️  LOOP_INTERVAL at 35 (NOT 30) — laptop needs brief cooldown between cycles

Usage:
    python UNLOCK_LAPTOP_SAFE.py
"""

import re
import psutil
from pathlib import Path

TARGET = Path(__file__).parent / "nexus_swarm_loop.py"

# ── HARDWARE CHECK ────────────────────────────────────────────────────────────
ram_gb      = psutil.virtual_memory().total / (1024**3)
free_ram_gb = psutil.virtual_memory().available / (1024**3)
cpu_count   = psutil.cpu_count(logical=False)

print(f"🔍 Hardware detected:")
print(f"   CPU cores (physical): {cpu_count}")
print(f"   Total RAM:  {ram_gb:.1f} GB")
print(f"   Free  RAM:  {free_ram_gb:.1f} GB")
print()

if ram_gb < 28:
    print(f"⛔  Only {ram_gb:.1f}GB RAM detected. Expected 32GB. Aborting.")
    exit(1)

if free_ram_gb < 3.0:
    print(f"⚠️  WARNING: Free RAM is critically low ({free_ram_gb:.1f} GB).")
    print(f"   Close Chrome tabs, other apps, then re-run this script.")
    print(f"   Continue anyway? (y/n): ", end="")
    if input().strip().lower() != "y":
        print("Aborted. Free up RAM first.")
        exit()

print(f"✅ System checks passed. Applying laptop-safe unlock patches...")
print()

# ── PATCHES ───────────────────────────────────────────────────────────────────
PATCHES = [
    # LOOP_INTERVAL: 45s → 35s (faster than low-RAM, not max — gives laptop cooldown)
    (
        "LOOP_INTERVAL    = 45   # seconds between full swarm cycles (raised: more breathing room on low RAM)",
        "LOOP_INTERVAL    = 35   # seconds between full swarm cycles (laptop-safe: 35s allows CPU/GPU cooldown)"
    ),
    # MAX_MEMORY: 100 → 150 (not 200 — save parse RAM for laptop)
    (
        "MAX_MEMORY       = 100  # max memory entries kept (halved: less disk+parse overhead)",
        "MAX_MEMORY       = 150  # max memory entries kept (laptop-safe: 150 balances context vs RAM)"
    ),
    # LITE_THRESHOLD: 15 → 18 (not desktop's 20 — be protective with 4.5GB free)
    (
        "LITE_THRESHOLD   = 15   # RAM PROTECTION: tightened — switch to lite model earlier (was 20)",
        "LITE_THRESHOLD   = 18   # RAM PROTECTION: laptop-safe threshold (free RAM is tight at ~4-5GB)"
    ),
    # Semaphore: 1 → 2 (safe for 32GB, but not 3+ on laptop thermal limits)
    (
        "_OLLAMA_SEM = asyncio.Semaphore(1)",
        "_OLLAMA_SEM = asyncio.Semaphore(2)  # laptop-safe: 2 concurrent Ollama calls (32GB justified)"
    ),
    # num_ctx: 1024 → 1536 (NOT 2048 — RTX 4060 Laptop VRAM shared with display)
    (
        '"num_ctx": 1024   # halved from 2048 — cuts KV-cache RAM usage by ~50%',
        '"num_ctx": 1536   # laptop-safe: 1536 context (NOT 2048 — RTX 4060 Laptop VRAM budget)'
    ),
    # DEFAULT_TOKEN_BUDGET: 512 → 640 (modest raise, not desktop's 768)
    (
        "_DEFAULT_TOKEN_BUDGET = 512",
        "_DEFAULT_TOKEN_BUDGET = 640  # laptop-safe default"
    ),
    # Prune threshold: 85 → 90 (not desktop's 92 — more protective on low free RAM)
    (
        'elif curr_stats["ram_load"] > 85:',
        'elif curr_stats["ram_load"] > 90:  # laptop-safe: prune at 90% (not desktop\'s 92%)'
    ),
]

# Token budget block — laptop-safe restore (not desktop max)
OLD_BUDGETS = '''    "COPYWRITER":         900,   # sales copy needs full completion
    "CLOSER":             900,   # follow-up sequences need full output
    "COMMANDER":          700,   # plans need numbered steps
    "SCOUT":              700,   # research summaries
    "SUPERVISOR":         600,
    "CONVERSION_ANALYST": 600,
    "OFFER_OPTIMIZER":    500,
    "REWARD":             384,   # structured scoring verdict
    "VALIDATOR":          384,   # short evidence verdicts
    "SENTINEL_MAGNITUDE": 384,   # CLEAR or LOCKDOWN — brief
    "METACOG":            384,
    "EXECUTIONER":        256,   # one line, one verdict'''

NEW_BUDGETS = '''    "COPYWRITER":        1000,   # laptop-safe: sales copy, good completion headroom
    "CLOSER":            1000,   # laptop-safe: follow-up sequences
    "COMMANDER":          800,   # detailed sales battle plans
    "SCOUT":              800,   # thorough buyer research
    "SUPERVISOR":         700,
    "CONVERSION_ANALYST": 600,
    "OFFER_OPTIMIZER":    500,
    "REWARD":             450,   # structured scoring verdict
    "VALIDATOR":          400,   # short evidence verdicts
    "SENTINEL_MAGNITUDE": 400,   # CLEAR or LOCKDOWN
    "METACOG":            400,
    "EXECUTIONER":        320,   # one line, one verdict'''

PATCHES.append((OLD_BUDGETS, NEW_BUDGETS))

# ── APPLY PATCHES ─────────────────────────────────────────────────────────────
def main():
    content = TARGET.read_text(encoding="utf-8")
    applied = 0
    skipped = 0

    for old, new in PATCHES:
        if old in content:
            content = content.replace(old, new, 1)
            applied += 1
            label = old[:70].strip().replace("\n", " ")
            print(f"  ✅ Patched: {label}...")
        else:
            skipped += 1
            label = old[:70].strip().replace("\n", " ")
            print(f"  ⚠️  Skip (already patched or not found): {label}...")

    TARGET.write_text(content, encoding="utf-8")
    print()
    print(f"🚀 LAPTOP-SAFE UNLOCK COMPLETE — {applied} patches applied, {skipped} skipped.")
    print()
    print("   SETTINGS SUMMARY (laptop-safe vs desktop-max):")
    print("   ┌──────────────────────┬──────────────┬──────────────┬──────────────┐")
    print("   │ Setting              │ Low-RAM Base │ Laptop-Safe  │ Desktop Max  │")
    print("   ├──────────────────────┼──────────────┼──────────────┼──────────────┤")
    print("   │ LOOP_INTERVAL        │     45s      │     35s ✅   │     30s ❌   │")
    print("   │ MAX_MEMORY           │     100      │    150  ✅   │    200  ❌   │")
    print("   │ LITE_THRESHOLD (RAM%)│     15%      │     18% ✅   │     20% ❌   │")
    print("   │ Semaphore (concurr.) │      1       │      2  ✅   │      2       │")
    print("   │ num_ctx (KV-cache)   │    1024      │   1536  ✅   │   2048  ❌   │")
    print("   │ Default token budget │     512      │    640  ✅   │    768  ❌   │")
    print("   │ Prune RAM threshold  │     85%      │     90% ✅   │     92% ❌   │")
    print("   └──────────────────────┴──────────────┴──────────────┴──────────────┘")
    print()
    print("   ⚡ Expected outcome:  Score should climb from 0.45 → 0.60+ within 3 cycles")
    print("   🌡️  Watch thermals:   If fans go loud + sustained, run at 40s interval instead")
    print()
    print("   ▶  Restart swarm to activate:")
    print("       Stop current: Ctrl+C in swarm terminal")
    print("       Restart:      python nexus_swarm_loop.py")

if __name__ == "__main__":
    main()
