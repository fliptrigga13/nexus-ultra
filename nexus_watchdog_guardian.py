"""
NEXUS Watchdog — auto-restarts crashed processes
Runs silently in background. Checks every 60 seconds.
All credentials read from .env — nothing exposed externally.
"""
import os, sys, subprocess, time, json, re
from pathlib import Path
from datetime import datetime

BASE    = Path(__file__).parent
PYTHON  = sys.executable
LOG     = BASE / "watchdog.log"
PID_FILE = BASE / ".nexus_launcher_pids.json"

# Processes to keep alive — maps name → launch command
SERVICES = {
    "SWARM":        [PYTHON, "-X", "utf8", "-u", str(BASE / "nexus_swarm_loop.py")],
    # NOTION-SYNC removed: nexus_notion_reporter.py owns all Notion telemetry now.
    # nexus_notion_sync.py has a SyntaxError (bare try at line 220) → crash loop.
    "SENTINEL":     [PYTHON, str(BASE / "nexus_internal_sentinel.py")],
    "NODE09":       [PYTHON, str(BASE / "nexus_node09_optimizer.py")],
    "METRICS":      [PYTHON, str(BASE / "nexus_metrics_server.py")],
    # EVOLUTION removed 2026-03-28: SELF_EVOLUTION_LOOP was corrupting nexus_prime_system.txt
    # and creating duplicate GPU contention. Task Scheduler entry also disabled.
    # Tombstoned here so guardian never respawns it.
}

# Log rotation settings
LOG_ROTATE_MAX_MB  = 50      # rotate when log exceeds this size
LOG_ROTATE_KEEP    = 20_000  # keep this many lines after rotation

# Server started separately via node
NODE_SERVER = BASE / "server.cjs"

def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def wlog(msg):
    line = f"{ts()} [WATCHDOG] {msg}"
    print(line)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def load_env():
    env = {**os.environ}
    env_path = BASE / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                if k and v:
                    env[k] = v
    env["PYTHONIOENCODING"] = "utf-8"
    return env

def is_alive(pid: int) -> bool:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV"],
            capture_output=True, text=True, timeout=5
        )
        return str(pid) in result.stdout
    except Exception:
        return False

def find_running(script_fragment: str) -> int | None:
    """Find a running python process by script name fragment."""
    try:
        # Use PowerShell Get-WmiObject instead of wmic (wmic deprecated/missing on Win11)
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-WmiObject Win32_Process | Where-Object {{$_.CommandLine -like '*{script_fragment}*' -and $_.Name -notmatch 'powershell|pwsh'}} | Select-Object -ExpandProperty ProcessId"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.isdigit() and int(line) > 0:
                return int(line)
    except Exception:
        pass
    return None

running_pids: dict[str, int] = {}

def launch(name: str, cmd: list):
    log_file = open(BASE / f"log_{name.lower().replace('-','_')}.txt", "a", encoding="utf-8")
    env = load_env()
    try:
        proc = subprocess.Popen(
            cmd, env=env, stdout=log_file, stderr=log_file,
            cwd=str(BASE),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
        running_pids[name] = proc.pid
        wlog(f"STARTED {name} (PID {proc.pid})")
    except Exception as e:
        wlog(f"FAILED to start {name}: {e}")

NODE_EXE = r"C:\Program Files\nodejs\node.exe"

def check_node_server():
    """Launch node server if not running."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-WmiObject Win32_Process | Where-Object {$_.CommandLine -like '*server.cjs*'} | Select-Object -ExpandProperty ProcessId"],
            capture_output=True, text=True, timeout=10
        )
        pids = [l.strip() for l in result.stdout.splitlines() if l.strip().isdigit()]
        if not pids and NODE_SERVER.exists():
            node_exe = NODE_EXE if os.path.exists(NODE_EXE) else "node"
            log_file = open(BASE / "log_server.txt", "a", encoding="utf-8")
            env = load_env()
            proc = subprocess.Popen(
                [node_exe, str(NODE_SERVER)], env=env,
                stdout=log_file, stderr=log_file, cwd=str(BASE),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
            wlog(f"STARTED NEXUS-SERVER (PID {proc.pid})")
    except Exception as e:
        wlog(f"check_node_server error: {e}")

def rotate_log(log_path: Path, max_mb: float = LOG_ROTATE_MAX_MB, keep_lines: int = LOG_ROTATE_KEEP):
    """Trim log to last `keep_lines` lines when it exceeds `max_mb` MB."""
    try:
        if not log_path.exists():
            return
        size_mb = log_path.stat().st_size / (1024 * 1024)
        if size_mb < max_mb:
            return
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if len(lines) <= keep_lines:
            return
        trimmed = "\n".join(lines[-keep_lines:]) + "\n"
        log_path.write_text(trimmed, encoding="utf-8")
        wlog(f"LOG ROTATED {log_path.name}: {size_mb:.0f}MB → kept last {keep_lines} lines")
    except Exception as e:
        wlog(f"Log rotation error ({log_path.name}): {e}")


def main():
    os.environ["PYTHONIOENCODING"] = "utf-8"
    wlog("=" * 50)
    wlog("NEXUS WATCHDOG ONLINE — monitoring all services")
    wlog("=" * 50)

    # On first start, find already-running processes (ALL services)
    for name, fragments in [
        ("SWARM",    "nexus_swarm_loop"),
        ("SENTINEL", "nexus_internal_sentinel"),
        ("NODE09",   "nexus_node09_optimizer"),
        ("METRICS",  "nexus_metrics_server"),
        ("EVOLUTION","SELF_EVOLUTION_LOOP"),
    ]:
        pid = find_running(fragments)
        if pid:
            running_pids[name] = pid
            wlog(f"FOUND existing {name} PID {pid}")

    while True:
        try:
            for name, cmd in SERVICES.items():
                script_path = Path(cmd[-1])
                if not script_path.exists():
                    continue  # Script doesn't exist, skip silently

                pid = running_pids.get(name)
                if pid and is_alive(pid):
                    pass  # All good
                else:
                    # Double-check by scanning processes before launching
                    # (guards against stale running_pids after watchdog restart)
                    script_name = Path(cmd[-1]).stem
                    existing_pid = find_running(script_name)
                    if existing_pid:
                        running_pids[name] = existing_pid
                        wlog(f"FOUND stray {name} PID {existing_pid} — adopting")
                    else:
                        wlog(f"DEAD: {name} — restarting...")
                        # Clear stale lockfile before launch (crash may have skipped atexit)
                        if name == "SWARM":
                            lock = Path(cmd[-1]).parent / ".swarm.lock"
                            if lock.exists():
                                try:
                                    old_pid = int(lock.read_text().strip())
                                    if not is_alive(old_pid):
                                        lock.unlink()
                                        wlog(f"Cleared stale .swarm.lock (dead PID {old_pid})")
                                except Exception:
                                    lock.unlink(missing_ok=True)
                        launch(name, cmd)

            # Check node server too
            check_node_server()

            # Rotate large logs
            rotate_log(BASE / "swarm_active.log")
            rotate_log(BASE / "notion_sync.log")
            rotate_log(BASE / "evolution_run.log")

        except Exception as e:
            wlog(f"Watchdog error: {e}")

        time.sleep(60)  # Check every 60 seconds

if __name__ == "__main__":
    main()
