
import asyncio
import json
import httpx
from datetime import datetime, timezone

# ── CONFIG ───────────────────────────────────────────────────────────────────
EH_INJECT_URL = "http://127.0.0.1:3000/veilpiercer/command" # Pipe directly into the VP AI if online
ADMIN_TOKEN = "PASTE_YOUR_TOKEN_HERE" # User should put their access token here
BLACKBOARD_PATH = r"c:\Users\fyou1\Desktop\New folder\nexus-ultra\nexus_blackboard.json"

async def inject_to_swarm(task_text):
    # Direct to blackboard for reliability
    try:
        with open(BLACKBOARD_PATH, "r", encoding="utf-8") as f:
            bb = json.load(f)
        queue = bb.get("task_queue", [])
        queue.append(task_text)
        bb["task_queue"] = queue
        with open(BLACKBOARD_PATH, "w", encoding="utf-8") as f:
            json.dump(bb, f, indent=2, ensure_ascii=False)
        print("  [MARKET] Injected into Blackboard.")
    except Exception as e:
        print(f"  [MARKET] Failed to inject: {e}")

async def fetch_ai_security_news():
    """Pulls current 'AI Security' and 'LLM Observability' trends to feed the swarm."""
    print(f"Searching for AI Security Market Intelligence...")
    
    # Using HackerNews search as a free proxy for specialized trends
    query = "AI security observability"
    url = f"https://hn.algolia.com/api/v1/search?query={query}&tags=story"
    
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(url, timeout=10.0)
            hits = r.json().get("hits", [])[:5]
            
            news_items = []
            for hit in hits:
                url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}"
                news_items.append(f"• {hit['title']} ({url})")
            
            if not news_items:
                print("No fresh market news found.")
                return

            market_report = f"""
[MARKET FEED: AI SECURITY & OBSERVABILITY — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}]
Trending developments that affect VeilPiercer's market value:
{chr(10).join(news_items)}

TASK: Review these competitor/market trends. 
1. Is there a new attack vector (like prompt injection) that VeilPiercer's SENTINEL nodes should watch for?
2. Is there a feature in a new tool that we should 'clone' into the VeilPiercer Hub to stay ahead?
3. Generate a sales pitch update for veilpiercer.html based on the most alarming trend found.
"""
            await inject_to_swarm(market_report)
            
        except Exception as e:
            print(f"Market fetch failed: {e}")

if __name__ == "__main__":
    asyncio.run(fetch_ai_security_news())
