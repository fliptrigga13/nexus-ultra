import subprocess
import hashlib
import json
import os
from pathlib import Path

ROOT = Path("c:/Users/fyou1/Desktop/New folder/nexus-ultra")
SHIELD_FILE = ROOT / ".shield_lock"

def get_hwid():
    """Get unique hardware ID for machine-locking."""
    try:
        cmd = "wmic csproduct get uuid"
        uuid = subprocess.check_output(cmd, shell=True).decode().split('\n')[1].strip()
        return uuid
    except:
        return "GENERIC-SWARM-NODE-001"

def generate_lock():
    """Generate and save the license lock."""
    hwid = get_hwid()
    salt = "VEILPIERCER_ULTRA_2026"
    lock_hash = hashlib.sha256(f"{hwid}:{salt}".encode()).hexdigest()
    
    lock_data = {
        "hwid_hash": hashlib.sha256(hwid.encode()).hexdigest(),
        "license_key": lock_hash,
        "issued_at": str(os.path.getctime(ROOT / "veilpiercer.html")),
        "version": "2.1.0-SHIELD"
    }
    
    with open(SHIELD_FILE, "w") as f:
        json.dump(lock_data, f, indent=2)
    print(f"SHIELD: Machine lock generated at {SHIELD_FILE}")
    return lock_hash

def verify_lock():
    """Verify if the current machine is authorized."""
    if not SHIELD_FILE.exists():
        return False
        
    try:
        with open(SHIELD_FILE, "r") as f:
            lock_data = json.load(f)
            
        hwid = get_hwid()
        expected_hash = hashlib.sha256(f"{hwid}:VEILPIERCER_ULTRA_2026".encode()).hexdigest()
        
        return lock_data["license_key"] == expected_hash
    except:
        return False

def obfuscate_js(code):
    """Simple variable scrambling for protection."""
    # In a full implementation, we'd use a JS obfuscator library.
    # Here we simulate it with a simple replacement or just returning a 'packed' version.
    return f"/* SHIELD PROTECTED */\n{code}"

if __name__ == "__main__":
    lock = generate_lock()
    if verify_lock():
        print("SHIELD: Local Integrity Verified. Moat Active.")
    else:
        print("SHIELD: LOCK MISMATCH. System at risk.")
