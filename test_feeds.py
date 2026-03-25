import urllib.request, xml.etree.ElementTree as ET, json

headers = {"User-Agent": "NEXUS-Feed/1.0"}

# ── TEST 1: Yahoo Finance RSS ──
print("=== TEST 1: Yahoo Finance RSS ===")
try:
    req = urllib.request.Request("https://feeds.finance.yahoo.com/rss/2.0/headline?s=NVDA,SPY,AI&region=US&lang=en-US", headers=headers)
    r = urllib.request.urlopen(req, timeout=10)
    root = ET.fromstring(r.read().decode("utf-8", errors="ignore"))
    items = root.findall(".//item")
    print(f"  Status: OK | Items found: {len(items)}")
    for i in items[:3]:
        t = i.find("title")
        print(f"  HEADLINE: {t.text[:90] if t is not None else 'NONE'}")
except Exception as e:
    print(f"  FAILED: {e}")

print()

# ── TEST 2: Hacker News RSS ──
print("=== TEST 2: Hacker News RSS ===")
try:
    req = urllib.request.Request("https://news.ycombinator.com/rss", headers=headers)
    r = urllib.request.urlopen(req, timeout=10)
    root = ET.fromstring(r.read().decode("utf-8", errors="ignore"))
    items = root.findall(".//item")
    print(f"  Status: OK | Items found: {len(items)}")
    for i in items[:3]:
        t = i.find("title")
        print(f"  HEADLINE: {t.text[:90] if t is not None else 'NONE'}")
except Exception as e:
    print(f"  FAILED: {e}")

print()

# ── TEST 3: CoinGecko API ──
print("=== TEST 3: CoinGecko Free API ===")
try:
    req = urllib.request.Request("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=5&sparkline=false", headers=headers)
    r = urllib.request.urlopen(req, timeout=10)
    data = json.loads(r.read().decode())
    print(f"  Status: OK | Coins returned: {len(data)}")
    for c in data[:3]:
        print(f"  {c['name']}: ${c['current_price']:,.2f} | 24h: {c['price_change_percentage_24h']:+.2f}%")
except Exception as e:
    print(f"  FAILED: {e}")
