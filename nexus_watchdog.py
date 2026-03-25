"""
nexus_watchdog.py — 2-Hour Swarm Monitor
Checks every 5 min. Logs issues. Auto-restarts swarm/server if they die.
"""
import subprocess, time, sqlite3, json, os
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).parent
LOG  = BASE / "logs" / "watchdog.log"
LOG.parent.mkdir(exist_ok=True)

CHECKS = 0
ISSUES = []

def ts():
    return datetime.now().strftime("%H:%M:%S")

def wlog(msg):
    line = f"[{ts()}] {msg}"
    print(line)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def proc_running(pattern):
    try:
        out = subprocess.check_output(
            ["powershell", "-Command",
             f"(Get-WmiObject Win32_Process | Where-Object {{ $_.CommandLine -match '{pattern}' }}).ProcessId"],
            text=True, timeout=10
        ).strip()
        return bool(out)
    except:
        return False

def restart_swarm():
    wlog(">>> AUTO-RESTART: nexus_swarm_loop.py")
    subprocess.Popen(
        ["C:\\Python314\\python.exe", "nexus_swarm_loop.py"],
        cwd=str(BASE), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

def restart_server():
    wlog(">>> AUTO-RESTART: server.cjs")
    subprocess.Popen(
        ["node", "server.cjs"],
        cwd=str(BASE), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

def restart_cloudflared():
    wlog(">>> AUTO-RESTART: cloudflared tunnel")
    subprocess.Popen(
        ["cloudflared", "tunnel", "run"],
        cwd=str(BASE), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

def check_scores():
    try:
        log_file = BASE / "logs" / "swarm_clean_restart_err.log"
        if not log_file.exists():
            log_file = BASE / "swarm_active.log"
        if not log_file.exists():
            return None
        lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        scores = [l for l in lines if "Score=" in l]
        if scores:
            last = scores[-1]
            score_part = [p for p in last.split() if p.startswith("Score=")]
            if score_part:
                return float(score_part[0].split("=")[1])
    except:
        pass
    return None

def check_lockdowns():
    try:
        log_file = BASE / "logs" / "swarm_clean_restart_err.log"
        if not log_file.exists():
            return 0
        content = log_file.read_text(encoding="utf-8", errors="ignore")
        # Count lockdowns in last 30 minutes of logs
        recent = content.split("[SENTINEL_LOCKDOWN")
        return len(recent) - 1
    except:
        return 0

def check_ram():
    try:
        out = subprocess.check_output(
            ["powershell", "-Command",
             "(Get-WmiObject Win32_OperatingSystem | Select-Object -ExpandProperty FreePhysicalMemory)"],
            text=True, timeout=10
        ).strip()
        free_kb = int(out)
        total_out = subprocess.check_output(
            ["powershell", "-Command",
             "(Get-WmiObject Win32_OperatingSystem | Select-Object -ExpandProperty TotalVisibleMemorySize)"],
            text=True, timeout=10
        ).strip()
        total_kb = int(total_out)
        pct_used = ((total_kb - free_kb) / total_kb) * 100
        return round(pct_used, 1)
    except:
        return None

def run_check():
    global CHECKS
    CHECKS += 1
    wlog(f"=== CHECK #{CHECKS} ===")

    # 1. Swarm running?
    swarm_ok = proc_running("nexus_swarm_loop")
    if not swarm_ok:
        wlog("ISSUE: Swarm loop NOT running — restarting!")
        ISSUES.append(f"[{ts()}] Swarm died — auto-restarted")
        restart_swarm()
        time.sleep(5)
    else:
        wlog(f"OK: Swarm running")

    # 2. Server running?
    server_ok = proc_running("server.cjs")
    if not server_ok:
        wlog("ISSUE: server.cjs NOT running — restarting!")
        ISSUES.append(f"[{ts()}] Server died — auto-restarted")
        restart_server()
        time.sleep(5)
    else:
        wlog(f"OK: Server running")

    # 3. Cloudflared tunnel running?
    cf_ok = proc_running("cloudflared")
    if not cf_ok:
        wlog("ISSUE: cloudflared NOT running — restarting tunnel!")
        ISSUES.append(f"[{ts()}] cloudflared died — auto-restarted")
        restart_cloudflared()
        time.sleep(5)
    else:
        wlog(f"OK: cloudflared tunnel running")

    # 4. Latest score
    score = check_scores()
    if score is not None:
        if score < 0.20:
            wlog(f"WARN: Low score {score} — monitoring")
            ISSUES.append(f"[{ts()}] Low score: {score}")
        else:
            wlog(f"OK: Score {score}")
    else:
        wlog("INFO: Score not yet available")

    # 5. RAM
    ram = check_ram()
    if ram and ram > 90:
        wlog(f"WARN: RAM at {ram}% — critical!")
        ISSUES.append(f"[{ts()}] RAM critical: {ram}%")
    elif ram:
        wlog(f"OK: RAM {ram}%")

    # 6. Memory count
    try:
        conn = sqlite3.connect(str(BASE / "nexus_mind.db"))
        count = conn.execute("SELECT COUNT(*) FROM memories WHERE archived=0").fetchone()[0]
        conn.close()
        wlog(f"OK: {count} active memories")
    except:
        wlog("WARN: Could not read nexus_mind.db")

    wlog(f"Issues so far: {len(ISSUES)}")

def main():
    wlog("=== NEXUS WATCHDOG STARTED (2-hour monitor) ===")
    wlog(f"Will check every 5 minutes. Log: {LOG}")

    end_time = time.time() + (2.5 * 3600)  # 2.5 hours
    interval = 5 * 60  # 5 minutes

    while time.time() < end_time:
        run_check()
        wlog(f"Next check in 5 min. Sleeping...")
        time.sleep(interval)

    wlog("=== WATCHDOG SUMMARY ===")
    wlog(f"Total checks: {CHECKS}")
    wlog(f"Total issues: {len(ISSUES)}")
    for issue in ISSUES:
        wlog(f"  - {issue}")
    wlog("=== WATCHDOG COMPLETE ===")

if __name__ == "__main__":
    main()
