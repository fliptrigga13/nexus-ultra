import json
import time
import logging
from pathlib import Path
from datetime import datetime

BASE_DIR    = Path(__file__).parent
BLACKBOARD  = BASE_DIR / "nexus_blackboard.json"
SENTINEL_LOG = BASE_DIR / "internal_sentinel.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [HIVE-SENTINEL] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(SENTINEL_LOG, encoding="utf-8"),
    ]
)
log = logging.getLogger("SENTINEL")

def read_bb():
    if BLACKBOARD.exists():
        try: return json.loads(BLACKBOARD.read_text(encoding="utf-8"))
        except: return {}
    return {}

def write_bb(data):
    BLACKBOARD.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def safe_float(val, default=0.5):
    """Convert val to float safely — returns default on None, empty str, or any error."""
    if val is None:
        return default
    try:
        f = float(val)
        if f != f or f == float('inf') or f == float('-inf'):
            return default
        return f
    except (TypeError, ValueError):
        return default

def get_last_score_from_redis():
    """Try to read the latest swarm score directly from Redis."""
    try:
        import redis as _redis
        _redis_pass = None
        _env_path = BASE_DIR / ".env"
        if _env_path.exists():
            for line in _env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("REDIS_PASSWORD="):
                    _redis_pass = line.split("=", 1)[1].strip()
                    break
        r = _redis.Redis(host="localhost", port=6379, password=_redis_pass,
                         decode_responses=True, socket_timeout=2)
        score_str = r.get("nexus:last_score")
        if score_str is not None:
            return safe_float(score_str, 0.5)
        latest = r.lrange("nexus:score_history", -1, -1)
        if latest:
            return safe_float(latest[0], 0.5)
    except Exception:
        pass
    return None

def calculate_h_efs(bb, redis_score=None):
    """
    Calculates the internal Hive EchoFlux Score (H-EFS).
    Echo (Consensus): High Reward scores + High Metacog Quality.
    Flux (Entropy): Rogue severity + Executioner HALT verdicts.
    """
    if redis_score is not None:
        last_reward = redis_score
    else:
        last_reward = safe_float(bb.get("last_score"), 0.5)

    metacog_q = safe_float(bb.get("metacog_quality"), 0.5)
    echo = (last_reward * 0.5 + metacog_q * 0.5)

    flux = 0.1
    rogue_outs = bb.get("rogue_outputs", [])
    if isinstance(rogue_outs, list) and rogue_outs:
        last_rogue = rogue_outs[-1]
        if isinstance(last_rogue, dict):
            rogue_text = last_rogue.get("ROGUE", "").upper()
            if "EXPLOIT: HIGH" in rogue_text or "SEVERITY: HIGH" in rogue_text:
                flux += 0.4
            elif "SEVERITY: MED" in rogue_text:
                flux += 0.2
            exec_text = last_rogue.get("EXECUTIONER", "").upper()
            if "VERDICT: TERMINATE" in exec_text or "HALT REQUIRED" in exec_text:
                flux += 0.5
            elif "REFACTOR" in exec_text:
                flux += 0.2

    flux = min(1.0, flux)
    h_efs = float(echo * 0.6 + (1.0 - flux) * 0.4)
    return float(round(h_efs, 3))

def main():
    log.info("="*60)
    log.info("NEXUS INTERNAL SENTINEL — VEIL PIERCER PROTOCOL")
    log.info("   Monitoring hive for cognitive entropy...")
    log.info("="*60)

    while True:
        try:
            bb = read_bb()
            redis_score = get_last_score_from_redis()
            score = calculate_h_efs(bb, redis_score)

            is_locked = bb.get("membrane_lock", False)
            if score < 0.35 and not is_locked:
                log.warning(f"HIVE HARMONY CRITICAL ({score}) — PIERCING THE VEIL...")
                log.warning("!!! COGNITIVE QUARANTINE ACTIVATED !!!")
                bb["membrane_lock"] = True
                bb["membrane_reason"] = "Excessive Internal Entropy detected by Veil Piercer protocol"
            elif score > 0.6 and is_locked:
                log.info(f"✅ HIVE HARMONY RESTORED ({score}) — MEMBRANE DISSIPATED.")
                bb["membrane_lock"] = False
                bb["membrane_reason"] = None

            bb["hive_echoflux"] = score
            write_bb(bb)

            src = f"redis={redis_score:.3f}" if redis_score is not None else "bb_file"
            log.info(f"H-EFS: {score} | LOCK: {bb.get('membrane_lock', False)} | src={src}")

        except Exception as e:
            log.error(f"Sentinel Error: {e}")

        time.sleep(15)

if __name__ == "__main__":
    main()
