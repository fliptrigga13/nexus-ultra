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

def calculate_h_efs(bb):
    """
    Calculates the internal Hive EchoFlux Score (H-EFS).
    
    Echo (Consensus): 
        - High Reward scores (>0.8)
        - High Metacog Quality scores (>0.8)
    Flux (Entropy):
        - Rogue Exploit detections (High severity = high entropy)
        - Executioner HALT or REJECT verdicts
        - High Latency in swarm cycles
    """
    # 1. Echo Component
    last_reward = float(bb.get("last_score", 0.5))
    metacog_q   = float(bb.get("metacog_quality", 0.5))
    echo = (last_reward * 0.5 + metacog_q * 0.5)
    
    # 2. Flux Component
    flux = 0.1 # Baseline entropy
    
    # Check Rogue Findings
    rogue_outs = bb.get("rogue_outputs", [])
    if rogue_outs:
        last_rogue = rogue_outs[-1]
        rogue_text = last_rogue.get("ROGUE", "").upper()
        if "EXPLOIT: HIGH" in rogue_text or "SEVERITY: HIGH" in rogue_text:
            flux += 0.4
        elif "SEVERITY: MED" in rogue_text:
            flux += 0.2
            
        # Executioner Factor
        exec_text = last_rogue.get("EXECUTIONER", "").upper()
        if "VERDICT: TERMINATE" in exec_text or "HALT REQUIRED" in exec_text:
            flux += 0.5
        elif "REFACTOR" in exec_text:
            flux += 0.2

    # Normalize Flux to 0-1
    flux = min(1.0, flux)
    
    # Composite EchoFlux (Biological Strategy: High Echo & Low Flux = Harmony)
    h_efs = float(echo * 0.6 + (1.0 - flux) * 0.4)
    return float(round(h_efs, 3))

def main():
    log.info("="*60)
    log.info("🌀 NEXUS INTERNAL SENTINEL — VEIL PIERCER PROTOCOL")
    log.info("   Monitoring hive for cognitive entropy...")
    log.info("="*60)

    while True:
        try:
            bb = read_bb()
            score = calculate_h_efs(bb)
            
            # THE MEMBRANE LOGIC
            # If entropy is too high/harmony too low, pierce the veil.
            is_locked = bb.get("membrane_lock", False)
            
            if score < 0.35 and not is_locked:
                log.warning(f"⚠️ HIVE HARMONY CRITICAL ({score}) — PIERCING THE VEIL...")
                log.warning("!!! COGNITIVE QUARANTINE ACTIVATED !!!")
                bb["membrane_lock"] = True
                bb["membrane_reason"] = "Excessive Internal Entropy detected by Veil Piercer protocol"
            elif score > 0.6 and is_locked:
                log.info(f"✅ HIVE HARMONY RESTORED ({score}) — MEMBRANE DISSIPATED.")
                bb["membrane_lock"] = False
                bb["membrane_reason"] = None
            
            bb["hive_echoflux"] = score
            write_bb(bb)
            
            log.info(f"H-EFS: {score} | LOCK: {bb.get('membrane_lock', False)}")
            
        except Exception as e:
            log.error(f"Sentinel Error: {e}")
            
        time.sleep(15)

if __name__ == "__main__":
    main()
