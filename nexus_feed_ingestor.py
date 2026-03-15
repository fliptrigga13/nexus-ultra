"""
NEXUS FEED INGESTOR
─────────────────────────────────────────────────────────────────────────────
Pulls clean, authoritative data from free public feeds and injects summaries
directly into the swarm's task queue every hour.

Sources (zero auth, 100% offline-compatible after fetch):
  • HackerNews  — top 5 stories via Firebase JSON API
  • ArXiv       — latest cs.AI abstracts via RSS

Run:  python nexus_feed_ingestor.py
Stops when you Ctrl+C.
"""

import asyncio
import json
import time
import re
import xml.etree.ElementTree as ET
from datetime import datetime, UTC
from pathlib import Path

import httpx

# ── CONFIG ───────────────────────────────────────────────────────────────────
EH_INJECT_URL   = "http://127.0.0.1:7701/inject"
BLACKBOARD_PATH = Path(__file__).parent / "nexus_blackboard.json"
FETCH_INTERVAL  = 3600          # seconds between feed pulls (1 hour)
HN_TOP_N        = 5             # how many HN stories to pull
ARXIV_TOP_N     = 3             # how many ArXiv papers to pull

HN_TOP_URL      = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL     = "https://hacker-news.firebaseio.com/v0/item/{id}.json"
ARXIV_RSS_URL   = "https://export.arxiv.org/rss/cs.AI"

# ── HELPERS ──────────────────────────────────────────────────────────────────
def _ts() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

def _inject_via_blackboard(task: str):
    """Fallback: write directly to blackboard task_queue if EH is down."""
    try:
        if BLACKBOARD_PATH.exists():
            bb = json.loads(BLACKBOARD_PATH.read_text(encoding="utf-8"))
        else:
            bb = {}
        queue = bb.get("task_queue", [])
        queue.append(task)
        bb["task_queue"] = queue
        BLACKBOARD_PATH.write_text(json.dumps(bb, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  [BLACKBOARD] Queued: {task[:80]}...")
    except Exception as e:
        print(f"  [BLACKBOARD] Write failed: {e}")

async def _inject(task: str, client: httpx.AsyncClient):
    """POST task to EH API; fall back to direct blackboard write."""
    try:
        r = await client.post(EH_INJECT_URL, json={"task": task}, timeout=5.0)
        if r.status_code == 200:
            print(f"  [EH] Injected: {task[:80]}...")
            return
    except Exception:
        pass
    # EH offline — write directly
    _inject_via_blackboard(task)

# ── HACKERNEWS ────────────────────────────────────────────────────────────────
async def fetch_hn(client: httpx.AsyncClient) -> list[dict]:
    """Return top N HN stories as {title, url, score, comments}."""
    try:
        r = await client.get(HN_TOP_URL, timeout=10.0)
        ids = r.json()[:HN_TOP_N * 3]   # grab extra in case some are dead
    except Exception as e:
        print(f"  [HN] Failed to fetch top list: {e}")
        return []

    stories = []
    for sid in ids:
        if len(stories) >= HN_TOP_N:
            break
        try:
            r = await client.get(HN_ITEM_URL.format(id=sid), timeout=8.0)
            item = r.json()
            if item and item.get("type") == "story" and item.get("title"):
                stories.append({
                    "title":    item.get("title", ""),
                    "url":      item.get("url", f"https://news.ycombinator.com/item?id={sid}"),
                    "score":    item.get("score", 0),
                    "comments": item.get("descendants", 0),
                })
        except Exception:
            continue
    return stories

# ── ARXIV ─────────────────────────────────────────────────────────────────────
async def fetch_arxiv(client: httpx.AsyncClient) -> list[dict]:
    """Return top N ArXiv cs.AI papers as {title, abstract, link}."""
    try:
        r = await client.get(ARXIV_RSS_URL, timeout=15.0)
        root = ET.fromstring(r.text)
    except Exception as e:
        print(f"  [ARXIV] Failed to fetch RSS: {e}")
        return []

    ns = {"dc": "http://purl.org/dc/elements/1.1/"}
    papers = []
    for item in root.iter("item"):
        if len(papers) >= ARXIV_TOP_N:
            break
        title_el   = item.find("title")
        desc_el    = item.find("description")
        link_el    = item.find("link")
        if title_el is None:
            continue
        title    = (title_el.text or "").strip()
        abstract = re.sub(r"<[^>]+>", "", (desc_el.text or "")).strip() if desc_el is not None else ""
        link     = (link_el.text or "").strip() if link_el is not None else ""
        # Trim abstract to 600 chars
        abstract = abstract[:600] + ("..." if len(abstract) > 600 else "")
        papers.append({"title": title, "abstract": abstract, "link": link})
    return papers

# ── BUILD TASKS ───────────────────────────────────────────────────────────────
def build_hn_task(stories: list[dict]) -> str:
    lines = [f"[FEED: HackerNews Top Stories — {_ts()}]"]
    for i, s in enumerate(stories, 1):
        lines.append(f"{i}. \"{s['title']}\" (score:{s['score']} comments:{s['comments']})")
    lines.append("")
    lines.append(
        "Analyze these trending tech stories. Identify the most technically significant development, "
        "explain why it matters for local AI / offline compute, and suggest one concrete way NEXUS "
        "could learn from or apply this insight."
    )
    return "\n".join(lines)

def build_arxiv_task(papers: list[dict]) -> str:
    lines = [f"[FEED: ArXiv cs.AI Latest Papers — {_ts()}]"]
    for i, p in enumerate(papers, 1):
        lines.append(f"\n{i}. {p['title']}")
        if p["abstract"]:
            lines.append(f"   Abstract: {p['abstract']}")
    lines.append(
        "\n\nReview these AI research papers. Identify the most promising technique applicable to "
        "local LLM inference or multi-agent coordination. Propose a concrete adaptation NEXUS could "
        "implement to improve its own reasoning or efficiency."
    )
    return "\n".join(lines)

# ── MAIN LOOP ─────────────────────────────────────────────────────────────────
async def main():
    print("=" * 60)
    print("  NEXUS FEED INGESTOR")
    print(f"  Interval: {FETCH_INTERVAL // 60} min | EH: {EH_INJECT_URL}")
    print("  Sources: HackerNews · ArXiv cs.AI")
    print("=" * 60)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        while True:
            print(f"\n[{_ts()}] Fetching feeds...")

            hn_stories, arxiv_papers = await asyncio.gather(
                fetch_hn(client),
                fetch_arxiv(client),
            )

            if hn_stories:
                print(f"  [HN]    {len(hn_stories)} stories fetched")
                await _inject(build_hn_task(hn_stories), client)
            else:
                print("  [HN]    No stories (offline?)")

            if arxiv_papers:
                print(f"  [ARXIV] {len(arxiv_papers)} papers fetched")
                await _inject(build_arxiv_task(arxiv_papers), client)
            else:
                print("  [ARXIV] No papers (offline?)")

            print(f"  Sleeping {FETCH_INTERVAL // 60} min until next pull...")
            await asyncio.sleep(FETCH_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nFeed ingestor stopped.")
