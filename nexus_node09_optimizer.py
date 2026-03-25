"""
nexus_node09_optimizer.py — Node-09: System Resource Balancer
══════════════════════════════════════════════════════════════
The missing Node-09 from the 14-node ANTIGRAVITY architecture.

  Cycle 1: Monitor — logs RAM/CPU/VRAM every cycle to Redis blackboard
  Cycle 2: Throttle — if RAM > 80%, writes throttle flags to blackboard
  Cycle 3: Score   — compare swarm scores Optimizer-on vs off

Run: python nexus_node09_optimizer.py [--once] [--interval N] [--dry-run]
"""

import time, logging, os, json, argparse
from pathlib import Path
from datetime import datetime, UTC

log = logging.getLogger("NODE-09")
logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [NODE-09] %(message)s", datefmt="%H:%M:%S")

BASE = Path(__file__).parent

RAM_WARN, RAM_CRIT  = 75.0, 88.0
CPU_WARN, CPU_CRIT  = 80.0, 95.0
VRAM_WARN, VRAM_CRIT = 80.0, 92.0

# ── Redis ──────────────────────────────────────────────────────────────────
def get_redis():
    try:
        import redis as _r
        r = _r.Redis(host="localhost", port=6379,
                     password=os.getenv("REDIS_PASSWORD",""),
                     decode_responses=True, socket_timeout=2)
        r.ping(); return r
    except Exception as e:
        log.warning(f"Redis unavailable: {e}"); return None

# ── Metrics ────────────────────────────────────────────────────────────────
def collect_metrics() -> dict:
    m = {"timestamp": datetime.now(UTC).isoformat(),
         "ram_pct":0.0,"ram_used_gb":0.0,"ram_total_gb":0.0,
         "cpu_pct":0.0,"vram_pct":0.0,"vram_used_mb":0.0,
         "vram_total_mb":0.0,"vram_ok":False}
    try:
        import psutil
        vm = psutil.virtual_memory()
        m["ram_pct"]      = vm.percent
        m["ram_used_gb"]  = round(vm.used/1e9,2)
        m["ram_total_gb"] = round(vm.total/1e9,2)
        m["cpu_pct"]      = psutil.cpu_percent(interval=1)
    except: pass
    try:
        import pynvml; pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        mem = pynvml.nvmlDeviceGetMemoryInfo(h)
        m["vram_used_mb"]  = round(mem.used/1e6,1)
        m["vram_total_mb"] = round(mem.total/1e6,1)
        m["vram_pct"]      = round(mem.used/mem.total*100,1)
        m["vram_ok"] = True
    except: pass
    return m

# ── Recommendations ────────────────────────────────────────────────────────
def recommend(m: dict) -> list:
    recs = []
    if m["ram_pct"] >= RAM_CRIT:
        recs.append({"p":"CRITICAL","area":"RAM",
            "msg":f"RAM {m['ram_pct']:.1f}% — swarm throttle required",
            "action":"Reduce LLM context window. Pause background tasks."})
    elif m["ram_pct"] >= RAM_WARN:
        recs.append({"p":"WARN","area":"RAM","msg":f"RAM {m['ram_pct']:.1f}%","action":"Monitor."})
    if m["cpu_pct"] >= CPU_CRIT:
        recs.append({"p":"CRITICAL","area":"CPU",
            "msg":f"CPU {m['cpu_pct']:.1f}% — inference throttled",
            "action":"Increase cycle sleep interval."})
    elif m["cpu_pct"] >= CPU_WARN:
        recs.append({"p":"WARN","area":"CPU","msg":f"CPU {m['cpu_pct']:.1f}%","action":"Watch."})
    if m["vram_ok"] and m["vram_pct"] >= VRAM_CRIT:
        recs.append({"p":"CRITICAL","area":"VRAM",
            "msg":f"VRAM {m['vram_pct']:.1f}% ({m['vram_used_mb']:.0f}/{m['vram_total_mb']:.0f}MB)",
            "action":"Unload secondary Ollama models."})
    elif m["vram_ok"] and m["vram_pct"] >= VRAM_WARN:
        recs.append({"p":"WARN","area":"VRAM","msg":f"VRAM {m['vram_pct']:.1f}%","action":"Avoid new model instances."})
    if not recs:
        recs.append({"p":"OK","area":"ALL","msg":"System healthy — full capacity","action":""})
    return recs

# ── Write blackboard ───────────────────────────────────────────────────────
def write_bb(r, m: dict, recs: list, dry_run: bool):
    payload = {"node09_metrics": m, "node09_recs": recs,
               "node09_throttle": any(x["p"]=="CRITICAL" for x in recs),
               "node09_updated": m["timestamp"]}
    if dry_run:
        log.info(f"[DRY] {payload}"); return
    if r:
        try:
            r.hset("nexus:node09", "metrics",  json.dumps(m))
            r.hset("nexus:node09", "recs",     json.dumps(recs))
            r.hset("nexus:node09", "ram_pct",  str(m["ram_pct"]))
            r.hset("nexus:node09", "cpu_pct",  str(m["cpu_pct"]))
            r.hset("nexus:node09", "vram_pct", str(m["vram_pct"]))
            r.hset("nexus:node09", "throttle", str(payload["node09_throttle"]))
            r.hset("nexus:node09", "updated",  m["timestamp"]); r.expire("nexus:node09", 300)
            # Push CRITICAL recs as swarm tasks
            for rec in recs:
                if rec["p"] == "CRITICAL":
                    r.lpush("nexus:tasks", json.dumps({
                        "task": f"[NODE-09] {rec['area']} CRITICAL: {rec['action']}",
                        "priority":"HIGH","source":"NODE-09"}))
                    log.warning(f"[REDIS] CRITICAL task pushed: {rec['area']}")
            log.info("[REDIS] nexus:node09 updated")
        except Exception as e:
            log.warning(f"[REDIS] {e}")
    # Always write to blackboard JSON as fallback
    bb_path = BASE / "nexus_blackboard.json"
    try:
        bb = json.loads(bb_path.read_text(encoding="utf-8")) if bb_path.exists() else {}
        bb.update(payload)
        bb_path.write_text(json.dumps(bb, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        log.warning(f"[BB] {e}")

# ── Report ─────────────────────────────────────────────────────────────────
def report(m: dict, recs: list):
    icons = {"CRITICAL":"🔴","WARN":"🟡","OK":"🟢"}
    log.info("━"*52)
    log.info(f"  RAM  {m['ram_pct']:5.1f}%  {m['ram_used_gb']:.1f}/{m['ram_total_gb']:.1f} GB")
    log.info(f"  CPU  {m['cpu_pct']:5.1f}%")
    if m["vram_ok"]:
        log.info(f"  VRAM {m['vram_pct']:5.1f}%  {m['vram_used_mb']:.0f}/{m['vram_total_mb']:.0f} MB")
    for rec in recs:
        log.info(f"  {icons.get(rec['p'],'●')} [{rec['area']}] {rec['msg']}")
        if rec["action"]: log.info(f"     → {rec['action']}")
    log.info("━"*52)

# ── Main ───────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once",     action="store_true")
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--dry-run",  action="store_true")
    args = ap.parse_args()

    log.info("╔══════════════════════════════════════════╗")
    log.info("║  NODE-09 OPTIMIZER — ONLINE              ║")
    log.info(f"║  Interval:{args.interval}s | DryRun:{args.dry_run}         ║")
    log.info("╚══════════════════════════════════════════╝")

    r = None if args.dry_run else get_redis()
    if args.once:
        m = collect_metrics(); recs = recommend(m)
        report(m, recs); write_bb(r, m, recs, args.dry_run); return

    while True:
        try:
            m = collect_metrics(); recs = recommend(m)
            report(m, recs); write_bb(r, m, recs, args.dry_run)
        except Exception as e:
            log.error(f"Cycle error: {e}")
        log.info(f"Next in {args.interval}s…")
        time.sleep(args.interval)

if __name__ == "__main__":
    main()
