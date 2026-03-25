"""
╔══════════════════════════════════════════════════════════════════════╗
║  NEXUS ULTRA — FULL POWER MODE UNLOCK                               ║
║  Run this ONCE after installing 32GB RAM                            ║
║  Reverts all low-RAM throttles. Saves to nexus_swarm_loop.py.      ║
╚══════════════════════════════════════════════════════════════════════╝

Usage:
    python UNLOCK_FULL_POWER.py
"""

import re
from pathlib import Path

TARGET = Path(__file__).parent / "nexus_swarm_loop.py"

PATCHES = [
    # LOOP_INTERVAL: 45s → 30s
    (
        "LOOP_INTERVAL    = 45   # seconds between full swarm cycles (raised: more breathing room on low RAM)",
        "LOOP_INTERVAL    = 30   # seconds between full swarm cycles"
    ),
    # MAX_MEMORY: 100 → 200
    (
        "MAX_MEMORY       = 100  # max memory entries kept (halved: less disk+parse overhead)",
        "MAX_MEMORY       = 200  # max memory entries kept"
    ),
    # LITE_THRESHOLD: 15 → 20
    (
        "LITE_THRESHOLD   = 15   # RAM PROTECTION: tightened — switch to lite model earlier (was 20)",
        "LITE_THRESHOLD   = 20   # RAM PROTECTION: if exceeded, agent switches to lite model"
    ),
    # Semaphore: 1 → 2
    (
        "_OLLAMA_SEM = asyncio.Semaphore(1)",
        "_OLLAMA_SEM = asyncio.Semaphore(2)  # 32GB: 2 concurrent Ollama calls safe"
    ),
    # num_ctx: 1024 → 2048
    (
        '"num_ctx": 1024   # halved from 2048 — cuts KV-cache RAM usage by ~50%',
        '"num_ctx": 2048   # 32GB: full context window restored'
    ),
    # DEFAULT_TOKEN_BUDGET: 512 → 768
    (
        "_DEFAULT_TOKEN_BUDGET = 512",
        "_DEFAULT_TOKEN_BUDGET = 768"
    ),
    # Prune SCOUT threshold: 85 → 92
    (
        "elif curr_stats[\"ram_load\"] > 85:",
        'elif curr_stats["ram_load"] > 92:  # 32GB: only prune at near-OOM'
    ),
]

# Token budget block — full restore
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

NEW_BUDGETS = '''    "COPYWRITER":        1200,   # 32GB: sales copy, full completion
    "CLOSER":            1200,   # 32GB: follow-up sequences, full output
    "COMMANDER":          900,   # detailed sales battle plans
    "SCOUT":              900,   # thorough buyer research
    "SUPERVISOR":         768,
    "CONVERSION_ANALYST": 768,
    "OFFER_OPTIMIZER":    600,
    "REWARD":             512,   # structured scoring verdict
    "VALIDATOR":          512,   # short evidence verdicts
    "SENTINEL_MAGNITUDE": 512,   # CLEAR or LOCKDOWN
    "METACOG":            512,
    "EXECUTIONER":        400,   # one line, one verdict'''

PATCHES.append((OLD_BUDGETS, NEW_BUDGETS))

def main():
    content = TARGET.read_text(encoding="utf-8")
    applied = 0
    skipped = 0

    for old, new in PATCHES:
        if old in content:
            content = content.replace(old, new, 1)
            applied += 1
            print(f"  ✅ Applied: {old[:60].strip()}...")
        else:
            skipped += 1
            print(f"  ⚠️  Skip (already patched?): {old[:60].strip()}...")

    TARGET.write_text(content, encoding="utf-8")
    print(f"\n🚀 FULL POWER MODE UNLOCKED — {applied} patches applied, {skipped} skipped.")
    print("   Restart the swarm to activate: python nexus_swarm_loop.py")

if __name__ == "__main__":
    import psutil
    ram_gb = psutil.virtual_memory().total / (1024**3)
    if ram_gb < 28:
        print(f"⚠️  Only {ram_gb:.1f}GB RAM detected. This script is for 32GB systems.")
        print("   Run anyway? (y/n): ", end="")
        if input().strip().lower() != "y":
            print("Aborted.")
            exit()
    main()
