"""
nexus_metrics_server.py — Prometheus-compatible /metrics endpoint
Exposes NEXUS swarm telemetry in Prometheus text format.

Usage:
  python nexus_metrics_server.py  (runs on port 9090)

Scrape config for prometheus.yml:
  - job_name: 'nexus'
    static_configs:
      - targets: ['localhost:9090']

Or hit directly: curl http://localhost:9090/metrics
"""
import sqlite3, re, os, json
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

BASE = Path(__file__).parent
SWARM_LOG = BASE / "swarm_active.log"
NEXUS_DB  = BASE / "nexus_mind.db"
BB_FILE   = BASE / "nexus_blackboard.json"


def get_metrics() -> str:
    lines = []

    # ── Swarm cycle metrics ──────────────────────────────────────────
    score, gen, mvp_agent = 0.0, 0, "UNKNOWN"
    log_age = 9999

    if SWARM_LOG.exists():
        log_age = (datetime.now().timestamp() - SWARM_LOG.stat().st_mtime)
        log_text = SWARM_LOG.read_text(encoding="utf-8", errors="ignore")
        log_lines = log_text.splitlines()

        for line in reversed(log_lines):
            if "Cycle #" in line and "COMPLETE" in line and score == 0:
                m = re.search(r"Cycle #(\d+).*Score=([\d.]+)", line)
                if m:
                    gen   = int(m.group(1))
                    score = float(m.group(2))
            if "MVP=" in line and not mvp_agent != "UNKNOWN":
                m = re.search(r"MVP=(\w+)", line)
                if m:
                    mvp_agent = m.group(1)
            if score > 0 and gen > 0:
                break

    lines += [
        "# HELP nexus_cycle_score Latest swarm cycle score (0.0-1.0)",
        "# TYPE nexus_cycle_score gauge",
        f"nexus_cycle_score {score:.4f}",
        "",
        "# HELP nexus_cycle_generation Current swarm generation number",
        "# TYPE nexus_cycle_generation counter",
        f"nexus_cycle_generation {gen}",
        "",
        "# HELP nexus_log_age_seconds Seconds since last swarm log write",
        "# TYPE nexus_log_age_seconds gauge",
        f"nexus_log_age_seconds {log_age:.0f}",
    ]

    # ── Memory metrics ───────────────────────────────────────────────
    memory_count = 0
    if NEXUS_DB.exists():
        try:
            conn = sqlite3.connect(NEXUS_DB)
            memory_count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            conn.close()
        except Exception:
            pass

    lines += [
        "",
        "# HELP nexus_memory_total Total swarm memories stored in SQLite",
        "# TYPE nexus_memory_total counter",
        f"nexus_memory_total {memory_count}",
    ]

    # ── Blackboard metrics ───────────────────────────────────────────
    if BB_FILE.exists():
        try:
            bb = json.loads(BB_FILE.read_text(encoding="utf-8"))
            hefs = bb.get("hive_echoflux", 0)
            colony = bb.get("colony_fitness", 0)
            ram_pct = bb.get("node09_metrics", {}).get("ram_pct", 0)
            mem_lock = 1 if bb.get("membrane_lock", False) else 0

            lines += [
                "",
                "# HELP nexus_hive_echoflux H-EFS harmony metric (0-1)",
                "# TYPE nexus_hive_echoflux gauge",
                f"nexus_hive_echoflux {hefs}",
                "",
                "# HELP nexus_colony_fitness PSO colony fitness score",
                "# TYPE nexus_colony_fitness gauge",
                f"nexus_colony_fitness {colony}",
                "",
                "# HELP nexus_ram_pct RAM usage percentage",
                "# TYPE nexus_ram_pct gauge",
                f"nexus_ram_pct {ram_pct}",
                "",
                "# HELP nexus_membrane_lock Whether swarm is in lockdown (1=locked)",
                "# TYPE nexus_membrane_lock gauge",
                f"nexus_membrane_lock {mem_lock}",
            ]
        except Exception:
            pass

    return "\n".join(lines) + "\n"


class MetricsHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress request logs

    def do_GET(self):
        if self.path in ("/metrics", "/metrics/"):
            body = get_metrics().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    port = int(os.environ.get("METRICS_PORT", 9090))
    server = HTTPServer(("0.0.0.0", port), MetricsHandler)
    print(f"[NEXUS-METRICS] Prometheus endpoint live at http://localhost:{port}/metrics")
    server.serve_forever()
