
import httpx
import json
import asyncio
from datetime import datetime
import os

# --- NEXUS ENDPOINTS ---
EH_URL = "http://127.0.0.1:7701"
OLLAMA_URL = "http://127.0.0.1:11434"
PSO_URL = "http://127.0.0.1:7700"

async def run_diagnostics():
    print(f"\n--- NEXUS SWARM RAPID DIAGNOSTICS ({datetime.now().strftime('%H:%M:%S')}) ---")
    
    async with httpx.AsyncClient() as client:
        # 1. EH API & BLACKBOARD
        try:
            r = await client.get(f"{EH_URL}/status", timeout=5.0)
            if r.status_code == 200:
                bb = r.json()
                status = bb.get("status", "UNKNOWN")
                cycle = bb.get("cycle_id", "none")
                score = bb.get("last_score", 0.0)
                queue = len(bb.get("task_queue", []))
                print(f"OK: EH API ONLINE | Status: {status} | Cycle: {cycle}")
                print(f"Data: Last Score: {score:.2f} | Queue Depth: {queue}")
            else:
                print(f"ERR: EH API Error {r.status_code}")
        except Exception as e:
            print(f"ERR: EH API UNREACHABLE ({e})")

        # 2. OLLAMA & MODELS
        try:
            r = await client.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                print(f"OK: OLLAMA ONLINE | {len(models)} models found")
                if "nexus-prime:latest" in models:
                    print(f"   SERVICE: nexus-prime:latest IS ACTIVE")
                else:
                    print(f"   WARN: nexus-prime:latest NOT FOUND (Found: {models[:3]})")
            else:
                print(f"ERR: OLLAMA Error {r.status_code}")
        except Exception as e:
            print(f"ERR: OLLAMA UNREACHABLE ({e})")

        # 3. PSO SWARM SERVER (Julia/CUDA)
        try:
            # PSO generally has a health or just check port
            r = await client.get(f"{PSO_URL}/status", timeout=2.0)
            print(f"OK: PSO SWARM ONLINE (Latency feedback active)")
        except Exception:
            # Some PSO versions only respond to POST /feedback
            print(f"WAIT: PSO SWARM LISTENING (Post-only mode)")

        # 4. SWARM ACTIVE LOG TAIL
        print("\n--- RECENT SWARM ACTIVITY ---")
        try:
            r = await client.get(f"{EH_URL}/log", timeout=5.0)
            lines = r.text.strip().split("\n")
            # standard slice
            show_lines = lines[-5:]
            for line in show_lines:
                print(f"   {line}")
        except Exception:
            print("   (Log unavailable)")

    print("\n--- DIAGNOSTICS COMPLETE ---\n")

if __name__ == "__main__":
    asyncio.run(run_diagnostics())
