"""
NEXUS EXTERNAL SIGNAL FEED — nexus_signal_feed.py
Pulls real market signals from 3 free sources and saves to nexus_signal.json
The swarm reads this file for task inspiration instead of self-referential loops.

RAM:  ~15MB (Python + stdlib only)
CPU:  Negligible (sleeps 10min between polls)
Auth: None required
"""
import json, time, logging, re, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR       = Path(__file__).parent
SIGNAL_FILE    = BASE_DIR / "nexus_signal.json"
LOG_FILE       = BASE_DIR / "nexus_feed.log"
POLL_INTERVAL  = 600   # 10 minutes
MAX_LEN        = 120   # max chars per sanitized headline
HEADERS        = {"User-Agent": "NEXUS-SignalFeed/1.0"}

# ── INJECTION BLOCKLIST ───────────────────────────────────────────────────────
_BAD = [
    "ignore previous", "ignore all", "disregard", "system prompt",
    "<script", "eval(", "exec(", "base64", "subprocess", "rm -rf",
    "override instructions", "forget previous"
]

def _sanitize(text: str) -> str:
    """Strip HTML, block injections, limit length — safe for LLM consumption."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)          # Strip HTML tags
    text = re.sub(r"&[a-z]+;", " ", text)         # Strip HTML entities
    if any(b in text.lower() for b in _BAD):
        return ""                                  # Drop entire headline
    text = re.sub(r"[^\w\s\-\.,!?%$&'/()@+:\"']", " ", text)  # Whitelist chars
    return text[:MAX_LEN].strip()

# ── SOURCE 1: Yahoo Finance RSS ───────────────────────────────────────────────
def fetch_yahoo():
    try:
        url = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=NVDA,SPY,AI,PLTR&region=US&lang=en-US"
        req = urllib.request.Request(url, headers=HEADERS)
        r   = urllib.request.urlopen(req, timeout=10)
        root = ET.fromstring(r.read().decode("utf-8", errors="ignore"))
        for item in root.findall(".//item")[:5]:
            t = item.find("title")
            if t is not None and t.text:
                clean = _sanitize(t.text)
                if clean:
                    return {"source": "Yahoo Finance", "headline": clean}
    except Exception as e:
        logging.warning(f"[FEED] Yahoo failed: {e}")
    return None

# ── SOURCE 2: Hacker News RSS ─────────────────────────────────────────────────
_HN_KEYWORDS = ["ai", "model", "llm", "agent", "trading", "market", "code",
                 "tool", "data", "startup", "gpu", "neural", "algorithm"]

def fetch_hackernews():
    try:
        req  = urllib.request.Request("https://news.ycombinator.com/rss", headers=HEADERS)
        r    = urllib.request.urlopen(req, timeout=10)
        root = ET.fromstring(r.read().decode("utf-8", errors="ignore"))
        for item in root.findall(".//item")[:10]:
            t = item.find("title")
            if t is not None and t.text:
                clean = _sanitize(t.text)
                if clean and any(kw in clean.lower() for kw in _HN_KEYWORDS):
                    return {"source": "HackerNews", "headline": clean}
    except Exception as e:
        logging.warning(f"[FEED] HackerNews failed: {e}")
    return None

# ── SOURCE 3: CoinGecko Free API ──────────────────────────────────────────────
def fetch_coingecko():
    try:
        url = ("https://api.coingecko.com/api/v3/coins/markets"
               "?vs_currency=usd&order=market_cap_desc&per_page=3&sparkline=false")
        req  = urllib.request.Request(url, headers=HEADERS)
        r    = urllib.request.urlopen(req, timeout=10)
        data = json.loads(r.read().decode())
        if data:
            c   = data[0]
            chg = c.get("price_change_percentage_24h") or 0.0
            direction = "surging" if chg > 2 else ("crashing" if chg < -2 else ("up" if chg > 0 else "down"))
            headline  = _sanitize(
                f"{c['name']} {direction} {abs(chg):.1f}% in 24h to ${c['current_price']:,.0f}"
            )
            return {
                "source":    "CoinGecko",
                "headline":  headline,
                "coin":      c["name"],
                "price":     c["current_price"],
                "change_24h": chg
            }
    except Exception as e:
        logging.warning(f"[FEED] CoinGecko failed: {e}")
    return None

# ── TASK BUILDER ──────────────────────────────────────────────────────────────
def build_task(yahoo, hn, gecko) -> str | None:
    """Combine signals into a structured swarm task template."""
    parts = []
    if yahoo:  parts.append(f"[MARKET NEWS] {yahoo['headline']}")
    if hn:     parts.append(f"[AI TREND] {hn['headline']}")
    if gecko:  parts.append(f"[CRYPTO SIGNAL] {gecko['headline']}")
    if not parts:
        return None

    signals = " | ".join(parts)
    return (
        f"REAL-WORLD SIGNAL ANALYSIS TASK: Based on live signals — {signals} — "
        f"identify one specific, actionable opportunity for VeilPiercer (AI trading intelligence). "
        f"[STEP 1/3]: Identify the key pattern or event. "
        f"[STEP 2/3]: Connect it to a VeilPiercer feature or gap. "
        f"[STEP 3/3]: Propose a concrete next action for the swarm."
    )

# ── MAIN POLL LOOP ────────────────────────────────────────────────────────────
def poll():
    yahoo  = fetch_yahoo()
    hn     = fetch_hackernews()
    gecko  = fetch_coingecko()
    hits   = sum(1 for x in [yahoo, hn, gecko] if x)

    task = build_task(yahoo, hn, gecko)
    if not task:
        logging.warning("[FEED] No valid signals collected — swarm stays self-directed")
        return

    payload = {
        "ts":      datetime.now(timezone.utc).isoformat(),
        "task":    task,
        "hits":    hits,
        "sources": {"yahoo": yahoo, "hacker_news": hn, "coingecko": gecko}
    }
    SIGNAL_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logging.info(f"[FEED] ✅ Signal saved — {hits}/3 sources | Task: {task[:100]}...")

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE)]
    )
    logging.info("=" * 60)
    logging.info(" NEXUS SIGNAL FEED ONLINE")
    logging.info(f" Sources: Yahoo Finance | Hacker News | CoinGecko")
    logging.info(f" Poll interval: {POLL_INTERVAL}s | Output: {SIGNAL_FILE.name}")
    logging.info("=" * 60)

    poll()  # First poll immediately on startup
    while True:
        time.sleep(POLL_INTERVAL)
        poll()

if __name__ == "__main__":
    main()
