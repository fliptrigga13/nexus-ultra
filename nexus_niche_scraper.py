"""
nexus_niche_scraper.py — Real Buyer Signal Intake
Hits Reddit JSON API, HN Algolia, and RSS for VeilPiercer's target communities.
Pushes scored, relevant posts into Redis task queue as structured swarm tasks.
Run standalone or import and call run_once() / start_loop() from swarm startup.
"""
import json, time, logging, re
from pathlib import Path
from datetime import datetime

import httpx

log = logging.getLogger("NICHE-SCRAPER")
logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")

CONFIG_FILE = Path(__file__).parent / "nexus_niche_config.json"
REDIS_TASK_KEY = "nexus_blackboard:task_queue"

# ── Load config ───────────────────────────────────────────────────────────────
def load_config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        cfg = json.load(f)
    client_name = cfg["active_client"]
    return cfg["clients"][client_name], client_name

# ── Relevance scoring ─────────────────────────────────────────────────────────
def score_relevance(text: str, cfg: dict) -> float:
    """Token overlap score against keywords + pain signals (0.0–1.0)."""
    text_lower = text.lower()
    all_signals = cfg["keywords"] + cfg["pain_signals"]
    hits = sum(1 for s in all_signals if s.lower() in text_lower)
    return min(1.0, hits / max(1, len(all_signals) * 0.3))

# ── Fetch Reddit JSON API ──────────────────────────────────────────────────────
def fetch_reddit(url: str, timeout: int = 10) -> list[dict]:
    headers = {"User-Agent": "VeilPiercer/1.0 (niche intelligence scraper)"}
    try:
        r = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
        r.raise_for_status()
        data = r.json()
        posts = []
        for child in data.get("data", {}).get("children", []):
            p = child.get("data", {})
            title = p.get("title", "")
            body  = p.get("selftext", "")[:600]
            score = p.get("score", 0)
            url_  = f"https://reddit.com{p.get('permalink','')}"
            if title:
                posts.append({"title": title, "body": body, "score": score, "url": url_})
        log.info(f"  Reddit: {len(posts)} posts from {url[:60]}")
        return posts
    except Exception as e:
        log.warning(f"  Reddit fetch failed ({url[:50]}): {e}")
        return []

# ── Fetch HN Algolia API ───────────────────────────────────────────────────────
def fetch_hn(url: str, timeout: int = 10) -> list[dict]:
    try:
        r = httpx.get(url, timeout=timeout)
        r.raise_for_status()
        hits = r.json().get("hits", [])
        posts = []
        for h in hits:
            title = h.get("title", "")
            body  = h.get("story_text", "") or ""
            url_  = h.get("url", "") or f"https://news.ycombinator.com/item?id={h.get('objectID','')}"
            if title:
                posts.append({"title": title, "body": body[:600], "score": h.get("points", 0), "url": url_})
        log.info(f"  HN: {len(posts)} posts")
        return posts
    except Exception as e:
        log.warning(f"  HN fetch failed ({url[:50]}): {e}")
        return []

# ── Format as swarm task ───────────────────────────────────────────────────────
def format_as_task(post: dict, cfg: dict, client_name: str) -> str:
    niche = cfg["niche"]
    title = post["title"]
    body  = post["body"][:400] if post["body"] else "(no body)"
    return (
        f"[NICHE SIGNAL — {client_name}] "
        f"Analyze this real user post for intelligence relevant to: {niche}\n\n"
        f"TITLE: {title}\n"
        f"CONTENT: {body}\n\n"
        f"Extract and output:\n"
        f"1. PRIMARY_PAIN_POINT: the core frustration or need expressed\n"
        f"2. SENTIMENT: 0.0 (negative) to 1.0 (positive)\n"
        f"3. BUYER_INTENT: low/medium/high — are they likely to pay for a solution?\n"
        f"4. SIGNAL_STRENGTH: how actionable is this for VeilPiercer marketing?\n"
        f"5. RECOMMENDED_ACTION: one concrete next step based on this signal"
    )

# ── Redis push ─────────────────────────────────────────────────────────────────
def push_to_redis(tasks: list[str]):
    try:
        from dotenv import load_dotenv
        import os, redis as redis_lib
        load_dotenv()
        pw = os.getenv("REDIS_PASSWORD", "")
        r = redis_lib.Redis(host="localhost", port=6379, password=pw, decode_responses=True)

        q_raw = r.get(REDIS_TASK_KEY)
        q = json.loads(q_raw) if q_raw else []
        # Prepend niche tasks so they run before self-tasks
        q = tasks + q
        r.set(REDIS_TASK_KEY, json.dumps(q))
        log.info(f"[REDIS] Pushed {len(tasks)} niche tasks to queue (total: {len(q)})")
    except Exception as e:
        log.warning(f"[REDIS] Push failed (saving to niche_queue_fallback.json): {e}")
        with open("niche_queue_fallback.json", "w") as f:
            json.dump(tasks, f, indent=2)

# ── Save report ────────────────────────────────────────────────────────────────
def save_report(scored_posts: list[dict], client_name: str):
    report = {
        "client": client_name,
        "scraped_at": datetime.utcnow().isoformat(),
        "total_scraped": len(scored_posts),
        "top_signals": scored_posts[:10]
    }
    with open("nexus_niche_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    log.info(f"[REPORT] Saved {len(scored_posts)} signals to nexus_niche_report.json")

# ── Main scrape run ────────────────────────────────────────────────────────────
def run_once(dry_run: bool = False) -> list[str]:
    cfg, client_name = load_config()
    log.info(f"[SCRAPER] Running for client: {client_name}")
    log.info(f"[SCRAPER] Sources: {len(cfg['urls'])} URLs")

    all_posts = []
    for url in cfg["urls"]:
        if "reddit.com" in url:
            all_posts.extend(fetch_reddit(url))
        elif "algolia" in url or "hn." in url:
            all_posts.extend(fetch_hn(url))
        time.sleep(1)  # polite rate limiting

    # Score each post for relevance
    scored = []
    for post in all_posts:
        combined = f"{post['title']} {post['body']}"
        rel = score_relevance(combined, cfg)
        if rel >= cfg.get("min_relevance_score", 0.2):
            post["relevance"] = rel
            scored.append(post)

    # Sort by relevance + upvotes
    scored.sort(key=lambda p: (p["relevance"], p.get("score", 0)), reverse=True)

    # Take top N
    max_tasks = cfg.get("max_tasks_per_scrape", 5)
    top = scored[:max_tasks]

    log.info(f"[SCRAPER] {len(all_posts)} posts fetched → {len(scored)} relevant → {len(top)} selected")

    # Format as swarm tasks
    tasks = [format_as_task(p, cfg, client_name) for p in top]

    if dry_run:
        log.info("[DRY RUN] Tasks (not pushed to Redis):")
        for i, t in enumerate(tasks, 1):
            print(f"\n--- Task {i} ---\n{t[:300]}\n")
    else:
        push_to_redis(tasks)

    save_report(scored, client_name)
    return tasks

# ── Loop mode ─────────────────────────────────────────────────────────────────
def start_loop():
    cfg, client_name = load_config()
    interval = cfg.get("scrape_interval_minutes", 30) * 60
    log.info(f"[SCRAPER] Loop mode — scraping every {interval//60} minutes")
    while True:
        run_once()
        time.sleep(interval)

if __name__ == "__main__":
    import sys
    if "--test" in sys.argv or "--dry" in sys.argv:
        run_once(dry_run=True)
    elif "--loop" in sys.argv:
        start_loop()
    else:
        run_once()
