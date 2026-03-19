import subprocess
import re
import hashlib
import json
import os
from pathlib import Path

def get_gpu_uuid():
    """Extract UUID of the first NVIDIA GPU (RTX 4060)."""
    try:
        output = subprocess.check_output(["nvidia-smi", "-L"], encoding="utf-8")
        match = re.search(r"UUID: ([\w-]+)", output)
        return match.group(1) if match else "GPU-NOT-FOUND"
    except Exception:
        return "GPU-UNREACHABLE"

def get_cpu_id():
    """Extract ProcessorID via WMIC."""
    try:
        output = subprocess.check_output(["wmic", "cpu", "get", "processorid"], encoding="utf-8")
        lines = output.strip().split("\n")
        return lines[1].strip() if len(lines) > 1 else "CPU-NOT-FOUND"
    except Exception:
        return "CPU-UNREACHABLE"

def get_baseboard_serial():
    """Extract Baseboard Serial via WMIC."""
    try:
        output = subprocess.check_output(["wmic", "baseboard", "get", "serialnumber"], encoding="utf-8")
        lines = output.strip().split("\n")
        return lines[1].strip() if len(lines) > 1 else "BB-NOT-FOUND"
    except Exception:
        return "BB-UNREACHABLE"

def generate_hbs_key():
    """Combine hardware IDs into a unique Magnitude-Level fingerprint."""
    gpu = get_gpu_uuid()
    cpu = get_cpu_id()
    bb  = get_baseboard_serial()
    
    raw = f"{gpu}:{cpu}:{bb}"
    hbs_hash = hashlib.sha3_256(raw.encode()).hexdigest()
    
    # Generate a 'Secret' that is locked to this hardware
    return {
        "fingerprint": hbs_hash,
        "gpu": gpu,
        "cpu": cpu,
        "baseboard": bb,
        "status": "HARDWARE_BOUND_LOCKED"
    }

if __name__ == "__main__":
    hbs = generate_hbs_key()
    print(json.dumps(hbs, indent=2))
    # Save the 'Biological Identity' for the SENTINEL_MAGNITUDE agent
    identity_file = Path("C:/Users/fyou1/Desktop/New folder/nexus-ultra/nexus_hbs_identity.json")
    with open(identity_file, "w") as f:
        json.dump(hbs, f, indent=2)
    print(f"\n✅ Hardware-Bound Secret (HBS) generated at {identity_file}")
