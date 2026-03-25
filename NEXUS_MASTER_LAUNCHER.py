"""
+==================================================================================================================+
|  NEXUS MASTER LAUNCHER                                                                                           |
|  One command to start everything                                                                                 |
|                                                                                                                  |
|  Run:  python NEXUS_MASTER_LAUNCHER.py                                                                           |
|  Or:   python NEXUS_MASTER_LAUNCHER.py --status   (check what's running)                                         |
|        python NEXUS_MASTER_LAUNCHER.py --stop-all (kill all nexus procs)                                         |
+==================================================================================================================+

COMPONENTS LAUNCHED:
  1. nexus_internal_sentinel.py   - H-EFS entropy scoring + membrane lock
  2. nexus_node09_optimizer.py    - RAM/CPU/VRAM monitoring + throttle
  3. nexus_signal_feed.py         - Live market signals -> swarm tasks
  4. nexus_cognitive_engine.py    - SwarmMind task prioritizer (port 7702)
  5. nexus_antennae.py            - Ant colony pheromone routing (15s ticks)
  6. nexus_mycelium.py            - Mycorrhizal structural routing (20s ticks)
  7. SELF_EVOLUTION_LOOP.py       - Overnight self-improvement (hourly)
  8. nexus_telegram_bot.py        - Remote control via Telegram (if configured)
"""

import io
import os
# Force UTF-8 stdout on Windows to avoid cp1252 encode errors
import sys as _sys
if hasattr(_sys.stdout, 'reconfigure'):
    try: _sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
# Set PYTHONIOENCODING to utf-8 at startup so Windows cp1252 never triggers
os.environ["PYTHONIOENCODING"] = "utf-8"
import sys
import sys
import time
import json
import subprocess
import argparse
import signal
from pathlib import Path
from datetime import datetime

BASE   = Path(__file__).parent
PYTHON = sys.executable
ENV    = {**os.environ, "REDIS_PASSWORD": os.getenv("REDIS_PASSWORD", "NEXUS_REDIS_FORT_KNOX_2026")}
PID_FILE = BASE / ".nexus_launcher_pids.json"

# -- COMPONENT DEFINITIONS -----------------------------------------------------
COMPONENTS = [
    {
        "name":    "SENTINEL",
        "script":  "nexus_internal_sentinel.py",
        "desc":    "H-EFS entropy scoring + membrane lock",
        "critical": True,
        "always_run": True,
    },
    {
        "name":    "NODE-09",
        "script":  "nexus_node09_optimizer.py",
        "desc":    "RAM/CPU/VRAM monitor + throttle",
        "critical": True,
        "always_run": True,
    },
    {
        "name":    "SIGNAL-FEED",
        "script":  "nexus_signal_feed.py",
        "desc":    "Live market signals (Yahoo/HN/CoinGecko -> swarm tasks)",
        "critical": False,
        "always_run": True,
    },
    {
        "name":    "COGNITIVE",
        "script":  "nexus_cognitive_engine.py",
        "desc":    "SwarmMind task prioritizer (port 7702)",
        "critical": False,
        "always_run": True,
    },
    {
        "name":    "ANTENNAE",
        "script":  "nexus_antennae.py",
        "desc":    "Ant colony pheromone routing (ACO, 15s ticks)",
        "critical": False,
        "always_run": True,
    },
    {
        "name":    "MYCELIUM",
        "script":  "nexus_mycelium.py",
        "desc":    "Mycorrhizal structural routing (Hagen-Poiseuille, 20s ticks)",
        "critical": False,
        "always_run": True,
    },
    {
        "name":    "EVOLUTION",
        "script":  "SELF_EVOLUTION_LOOP.py",
        "desc":    "Overnight self-improvement (hourly reflect->synthesize->evolve)",
        "args":    ["--interval", "3600"],
        "critical": False,
        "always_run": False,   # opt-in -- runs overnight
    },
    {
        "name":    "TELEGRAM",
        "script":  "nexus_telegram_bot.py",
        "desc":    "Remote control via Telegram",
        "critical": False,
        "always_run": False,   # opt-in -- needs BOT_TOKEN
    },
    {
        "name":    "SWARM",
        "script":  "nexus_swarm_loop.py",
        "desc":    "Main AI swarm loop — 6 agents self-score every 35s",
        "critical": True,
        "always_run": True,
    },
    {
        "name":    "NOTION-SYNC",
        "script":  "nexus_notion_sync.py",
        "desc":    "Pipes swarm data to Notion MCP every 35s",
        "critical": False,
        "always_run": True,
    },
]

# -- NODE SERVICES (non-Python) ------------------------------------------------
NODE_SERVICES = [
    {
        "name": "NEXUS-SERVER",
        "script": "server.cjs",
        "desc": "NEXUS web server (veil-piercer.com + hub)",
        "critical": True,
    },
]

# -- HELPERS -------------------------------------------------------------------
def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = {
        "INFO":  "\033[32m[OK]\033[0m ",
        "WARN":  "\033[33m[!!]\033[0m ",
        "ERROR": "\033[31m[XX]\033[0m ",
        "HEAD":  "\033[36m[>>]\033[0m ",
    }.get(level, "[  ] ")
    print(f"{prefix}{ts}  {msg}")

def load_pids() -> dict:
    if PID_FILE.exists():
        try:
            return json.loads(PID_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_pids(pids: dict):
    PID_FILE.write_text(json.dumps(pids, indent=2), encoding="utf-8")

def is_alive(pid: int) -> bool:
    """Check if a PID is still running on Windows."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV"],
            capture_output=True, text=True, timeout=5
        )
        return str(pid) in result.stdout
    except Exception:
        return False

def script_exists(script: str) -> bool:
    return (BASE / script).exists()

# -- LAUNCH --------------------------------------------------------------------
def launch_component(c: dict, pids: dict):
    name   = c["name"]
    script = c["script"]

    if not script_exists(script):
        log(f"{name} -- script not found: {script}", "WARN")
        return

    # Don't re-launch if already running
    existing_pid = pids.get(name)
    if existing_pid and is_alive(existing_pid):
        log(f"{name} -- already running (PID {existing_pid})", "INFO")
        return

    cmd = [PYTHON, str(BASE / script)] + c.get("args", [])
    log_file = open(BASE / f"log_{name.lower().replace('-', '_')}.txt", "a", encoding="utf-8")

    try:
        proc = subprocess.Popen(
            cmd,
            env=ENV,
            stdout=log_file,
            stderr=log_file,
            cwd=str(BASE),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
        pids[name] = proc.pid
        log(f"{name} -- started (PID {proc.pid}) . {c['desc']}")
    except Exception as e:
        log(f"{name} -- launch failed: {e}", "ERROR")

# -- STATUS REPORT -------------------------------------------------------------
def show_status():
    pids = load_pids()
    bb   = {}
    try:
        bb = json.loads((BASE / "nexus_blackboard.json").read_text(encoding="utf-8"))
    except Exception:
        pass

    print("\n" + "=" * 58)
    print("  NEXUS SYSTEM STATUS")
    print("=" * 58)

    for c in COMPONENTS:
        name = c["name"]
        pid  = pids.get(name, None)
        if pid and is_alive(pid):
            status = f"\033[32m[RUN] PID {pid}\033[0m"
        else:
            status = "\033[31m[OFF]\033[0m"
        print(f"  {name:<15} {status:<30} {c['desc'][:35]}")

    print("-" * 58)
    print(f"  SWARM SCORE  : {bb.get('last_score', '-')}")
    print(f"  STATUS       : {bb.get('status', '-')}")
    print(f"  MEMBRANE LOCK: {bb.get('membrane_lock', False)}")
    print(f"  H-EFS        : {bb.get('hive_echoflux', '-')}")
    print(f"  COLONY FIT   : {bb.get('colony_fitness', '-')}")
    print(f"  NODE-09 RAM  : {bb.get('node09_metrics', {}).get('ram_pct', '-')}%")
    print("=" * 58 + "\n")

# -- STOP ALL ------------------------------------------------------------------
def stop_all():
    pids = load_pids()
    log("Stopping all NEXUS components...", "HEAD")
    for name, pid in pids.items():
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
            else:
                os.kill(pid, signal.SIGTERM)
            log(f"{name} (PID {pid}) -- stopped")
        except Exception as e:
            log(f"{name} -- stop failed: {e}", "WARN")
    save_pids({})

# -- MAIN ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="NEXUS Master Launcher")
    parser.add_argument("--status",   action="store_true", help="Show status of all components")
    parser.add_argument("--stop-all", action="store_true", help="Stop all NEXUS processes")
    parser.add_argument("--all",      action="store_true", help="Also launch opt-in components (Evolution + Telegram)")
    parser.add_argument("--evolution",action="store_true", help="Launch the self-evolution loop")
    parser.add_argument("--telegram", action="store_true", help="Launch Telegram bot (requires BOT_TOKEN set in nexus_telegram_bot.py)")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.stop_all:
        stop_all()
        return

    # -- BANNER ----------------------------------------------------------------
    print("\n" + "=" * 58)
    print("  NEXUS MASTER LAUNCHER -- INITIATING ALL SYSTEMS")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 58)

    pids = load_pids()

    for c in COMPONENTS:
        # Skip opt-in unless flagged
        if not c["always_run"]:
            name = c["name"]
            if not args.all and not (name == "TELEGRAM" and args.telegram) and not (name == "EVOLUTION" and args.evolution):
                log(f"{name} — skipped (opt-in, use --{name.lower()} or --all to enable)")
                continue

        launch_component(c, pids)
        time.sleep(0.4)  # stagger launches to avoid resource spike

    save_pids(pids)

    print()
    log("All core systems launched!", "HEAD")
    log("Logs → log_*.txt files in nexus-ultra/")
    log("Status → python NEXUS_MASTER_LAUNCHER.py --status")
    log("Stop   → python NEXUS_MASTER_LAUNCHER.py --stop-all")
    print()

    # Show live status after 3s
    time.sleep(3)
    show_status()


if __name__ == "__main__":
    main()
