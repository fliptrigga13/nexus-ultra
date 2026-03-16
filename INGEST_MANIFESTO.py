
import json
import os
import uuid
from datetime import datetime, timezone

FACTS_FILE = r"c:\Users\fyou1\Desktop\New folder\nexus-ultra\nexus_session_facts.json"
MANIFESTO_FILE = r"c:\Users\fyou1\Desktop\New folder\nexus-ultra\EVOLUTION-MANIFESTO.md"

def ingest():
    if not os.path.exists(MANIFESTO_FILE):
        print(f"Error: {MANIFESTO_FILE} not found.")
        return

    with open(MANIFESTO_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract sections as facts
    facts_to_add = [
        "VeilPiercer v2.0 introduces the Observatory Paradigm: Intelligence = Visibility + Safety + Privacy.",
        "The Biological Swarm Sentinel uses Julia/CUDA kernels for high-concurrency state management.",
        "System stability is managed by the Swarm Sentinel免疫系统 (immune system): MEMORY_GUARD.ps1 and night_watch.ps1.",
        "Commercial synergy: Project intelligence improvements must manifest as features in the buyer BUNDLE/ (SDKs, Hub).",
        "Persistent cognitive memory flows through nexus_session_facts.json; agents must synthesize discoveries into MEMORY_FLAGS.",
        "The project goal is 100% offline autonomy using local LLMs (Ollama) and local telemetry."
    ]

    try:
        with open(FACTS_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
    except Exception as e:
        print(f"Error loading {FACTS_FILE}: {e}")
        return

    timestamp = datetime.now(timezone.utc).isoformat() + "Z"
    new_count = 0

    for fact in facts_to_add:
        # Avoid duplicates
        if any(fact in f["content"] for f in db["facts"]):
            continue
        
        entry = {
            "id": f"manifesto_{uuid.uuid4().hex[:8]}",
            "content": f"[INTELLIGENCE DIRECTIVE] {fact}",
            "type": "evolution",
            "importance": 0.95,
            "created_at": timestamp,
            "last_accessed": timestamp,
            "access_count": 1,
            "stale": False,
            "tags": ["veilpiercer", "directive", "v2.0"],
            "generation": 50 # Jumping to Gen 50 for priority
        }
        db["facts"].insert(0, entry) # Add to top
        new_count += 1

    with open(FACTS_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2)

    print(f"Ingested {new_count} high-priority intelligence directives into NEXUS memory.")

if __name__ == "__main__":
    ingest()
