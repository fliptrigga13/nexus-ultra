"""
nexus_security_guard.py — Modelfile SHA256 Integrity Verifier
Run this on startup or via NEXUS_MASTER_LAUNCHER to verify
the Ollama modelfile has not been tampered with.

Usage:
    python nexus_security_guard.py            # verify + seal if first run
    python nexus_security_guard.py --verify   # verify only, exit 1 if tampered
    python nexus_security_guard.py --seal     # update the stored hash (after intentional update)
"""

import sys
import json
import hashlib
import logging
import argparse
from pathlib import Path
from datetime import datetime

BASE        = Path(__file__).parent
MODELFILE   = BASE / "nexus_prime_evolved.modelfile"
HASH_FILE   = BASE / ".nexus_modelfile_hash.json"     # hidden file, tracks known-good hash
FALLBACK    = BASE / "nexus_prime.modelfile"           # fallback if evolved doesn't exist

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SECURITY] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger("SECURITY")


def sha256_file(path: Path) -> str:
    """Compute SHA256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_hash_record() -> dict:
    if HASH_FILE.exists():
        try:
            return json.loads(HASH_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_hash_record(record: dict):
    HASH_FILE.write_text(json.dumps(record, indent=2), encoding="utf-8")
    # On Windows, set hidden attribute
    try:
        import subprocess
        subprocess.run(["attrib", "+H", str(HASH_FILE)], capture_output=True)
    except Exception:
        pass


def verify() -> bool:
    """Verify modelfile integrity. Returns True if clean, False if tampered."""
    target = MODELFILE if MODELFILE.exists() else FALLBACK
    if not target.exists():
        log.warning(f"No modelfile found at {target} — skipping verification")
        return True  # Can't verify what doesn't exist

    record = load_hash_record()
    stored = record.get(str(target))

    if not stored:
        log.info(f"No stored hash for {target.name} — sealing now (first run)")
        seal(target)
        return True

    current = sha256_file(target)
    if current == stored["hash"]:
        log.info(f"[OK] {target.name} integrity verified — hash matches")
        log.info(f"     SHA256: {current[:16]}...{current[-8:]}")
        log.info(f"     Sealed: {stored['sealed_at']}")
        return True
    else:
        log.error("=" * 60)
        log.error(f"[!!] MODELFILE TAMPERED: {target.name}")
        log.error(f"     Expected: {stored['hash'][:16]}...{stored['hash'][-8:]}")
        log.error(f"     Found:    {current[:16]}...{current[-8:]}")
        log.error(f"     Sealed at: {stored['sealed_at']}")
        log.error("     ACTION: Do NOT load this model. Review modelfile manually.")
        log.error("     Run with --seal to accept current version if intentional.")
        log.error("=" * 60)
        return False


def seal(target: Path = None):
    """Store current hash as known-good."""
    t = target or (MODELFILE if MODELFILE.exists() else FALLBACK)
    if not t.exists():
        log.warning(f"Cannot seal — {t} not found")
        return
    h = sha256_file(t)
    record = load_hash_record()
    record[str(t)] = {
        "hash": h,
        "file": t.name,
        "size_bytes": t.stat().st_size,
        "sealed_at": datetime.utcnow().isoformat(),
    }
    save_hash_record(record)
    log.info(f"[SEALED] {t.name}")
    log.info(f"  SHA256: {h}")
    log.info(f"  Stored in: {HASH_FILE}")


def main():
    parser = argparse.ArgumentParser(description="NEXUS Modelfile Security Guard")
    parser.add_argument("--verify", action="store_true", help="Verify modelfile integrity (exit 1 if tampered)")
    parser.add_argument("--seal",   action="store_true", help="Seal current modelfile as known-good")
    args = parser.parse_args()

    if args.seal:
        seal()
    elif args.verify:
        ok = verify()
        sys.exit(0 if ok else 1)
    else:
        # Default: verify + seal if first run
        ok = verify()
        if not ok:
            log.error("NEXUS STARTUP BLOCKED — modelfile integrity check failed")
            sys.exit(1)


if __name__ == "__main__":
    main()
