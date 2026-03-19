import time
import json
import requests
import logging
from pathlib import Path
from datetime import datetime

# --- CONFIGURATION ---
EH_API_URL = "http://127.0.0.1:7701"
LOG_FILE = Path("c:/Users/fyou1/Desktop/New folder/nexus-ultra/swarm_active.log")
MEMORY_FILE = Path("c:/Users/fyou1/Desktop/New folder/nexus-ultra/nexus_memory.json")
SENTINEL_LOG = Path("c:/Users/fyou1/Desktop/New folder/nexus-ultra/sentinel_v2.log")

# Safety Thresholds
MIN_SCORE_THRESHOLD = 0.4
ANOMALY_LATENCY_MAX = 60.0  # seconds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SENTINEL-V2] %(message)s",
    handlers=[
        logging.FileHandler(SENTINEL_LOG),
        logging.StreamHandler()
    ]
)

log = logging.getLogger("SENTINEL")

class SentinelMembraneV2:
    def __init__(self):
        self.last_processed_cycle = None
        log.info("Sentinel Membrane V2 Initialized. Monitoring Swarm Integrity...")

    def check_health(self):
        try:
            r = requests.get(f"{EH_API_URL}/status", timeout=5)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            log.error(f"Cannot reach EH API: {e}")
        return None

    def enforce_lockdown(self, reason):
        log.warning(f"!!! TRIGGERING LOCKDOWN: {reason} !!!")
        try:
            # In a real scenario, we would have a specific lockdown endpoint or adjust weights
            # For now, we inject a high-priority halt/review task
            requests.post(f"{EH_API_URL}/inject", json={
                "task": f"[SENTINEL CRITICAL] System Integrity Compromised: {reason}. All autonomous actions paused.",
                "priority": 100
            })
            # Force Nominal/Lockdown mode via script if available
            requests.post(f"{EH_API_URL}/approve_all") # Clear queue to stop "rogue" loops
        except Exception as e:
            log.error(f"Lockdown enforcement failed: {e}")

    def monitor_memory(self):
        if not MEMORY_FILE.exists():
            return

        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                memory = json.load(f)
            
            if not memory:
                return

            last_entry = memory[-1]
            if last_entry.get("cycle") != self.last_processed_cycle:
                self.last_processed_cycle = last_entry.get("cycle")
                score = last_entry.get("score", 1.0)
                
                log.info(f"Cycle {self.last_processed_cycle} Score: {score}")
                
                if score < MIN_SCORE_THRESHOLD:
                    self.enforce_lockdown(f"Low Performance Score ({score}) in cycle {self.last_processed_cycle}")

        except Exception as e:
            log.error(f"Memory monitoring error: {e}")

    def check_integrity(self):
        manifest_path = Path("c:/Users/fyou1/Desktop/New folder/nexus-ultra/.integrity_manifest.json")
        if not manifest_path.exists():
            return True # Or log error

        try:
            with open(manifest_path, "r") as f:
                manifest = json.load(f)
            
            import hashlib
            for filename, expected_hash in manifest.items():
                file_path = Path(f"c:/Users/fyou1/Desktop/New folder/nexus-ultra/{filename}")
                if not file_path.exists():
                    self.enforce_lockdown(f"Missing Critical File: {filename}")
                    return False
                
                sha256_hash = hashlib.sha256()
                with open(file_path, "rb") as f:
                    for byte_block in iter(lambda: f.read(4096), b""):
                        sha256_hash.update(byte_block)
                
                actual_hash = sha256_hash.hexdigest().upper()
                if actual_hash != expected_hash:
                    self.enforce_lockdown(f"Integrity Violation: {filename} was modified!")
                    return False
            return True
        except Exception as e:
            log.error(f"Integrity check failed: {e}")
            return False

    def run(self):
        while True:
            # 1. Check File Integrity
            if not self.check_integrity():
                log.warning("Integrity check failed. System compromised.")
            
            # 2. Check API Health
            health = self.check_health()
            if health:
                # Check for queue bloat
                queue_depth = health.get("queue_depth", 0)
                if queue_depth > 15:
                    self.enforce_lockdown(f"Queue Bloat Detected: {queue_depth} pending tasks")

            # 3. Monitor Memory Scores
            self.monitor_memory()
            time.sleep(10) # 10s heartbeat

if __name__ == "__main__":
    sentinel = SentinelMembraneV2()
    sentinel.run()
