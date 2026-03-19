import asyncio
import json
import httpx
from pathlib import Path
from nexus_swarm_loop import run_swarm_cycle, RedisBlackboard, Memory, MEMORY_FILE, OLLAMA

async def single_cycle_audit():
    bb = RedisBlackboard()
    mem = Memory(MEMORY_FILE)
    
    task = "Perform a strict, metric-based audit of current system state and suggest architecture optimizations."
    
    print(f"--- STARTING AUDIT CYCLE ---")
    async with httpx.AsyncClient() as client:
        # Check Ollama
        try:
            await client.get(f"{OLLAMA}/api/tags", timeout=5.0)
            print("Ollama: ONLINE")
        except:
            print("Ollama: OFFLINE")
            return

        score, mvp, lesson = await run_swarm_cycle(task, bb, mem, client)
        
        print("\n--- RESULTS ---")
        print(f"Score: {score}")
        print(f"MVP:   {mvp}")
        print(f"Lesson: {lesson}")

if __name__ == "__main__":
    asyncio.run(single_cycle_audit())
