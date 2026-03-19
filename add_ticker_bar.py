"""add_ticker_bar.py — Remove LAUNCH50, add sticky bottom news crawl"""
import re, shutil

src = open(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', encoding='utf-8').read()

# ── 1. Remove any LAUNCH50 coupon references ─────────────────────────────────
src = re.sub(r'LAUNCH50[^\n<"]*', '', src, flags=re.IGNORECASE)
src = re.sub(r'50%\s*off[^\n<"]*', '', src, flags=re.IGNORECASE)
src = re.sub(r'coupon[^\n<"]*LAUNCH[^\n<"]*', '', src, flags=re.IGNORECASE)
# Remove any p-badge or badge elements that mention LAUNCH50 or coupon
src = re.sub(r'<[^>]*class="p-badge"[^>]*>.*?</[^>]+>', '', src, flags=re.DOTALL)

# ── 2. Inject sticky bottom news bar CSS before </style> ─────────────────────
NEWS_CSS = """
    /* ══════════ STICKY BOTTOM NEWS CRAWL ══════════ */
    #news-crawl {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      z-index: 9996;
      height: 38px;
      background: rgba(0,229,255,1);
      display: flex;
      align-items: center;
      overflow: hidden;
      border-top: 2px solid rgba(0,0,0,0.2);
      box-shadow: 0 -4px 24px rgba(0,229,255,0.35);
    }
    #news-crawl .crawl-label {
      flex-shrink: 0;
      background: #020408;
      color: var(--vis);
      font-family: 'Unbounded', sans-serif;
      font-weight: 900;
      font-size: 9px;
      letter-spacing: 3px;
      padding: 0 18px;
      height: 100%;
      display: flex;
      align-items: center;
      border-right: 1px solid rgba(0,229,255,0.3);
      white-space: nowrap;
    }
    #news-crawl .crawl-track {
      flex: 1;
      overflow: hidden;
      height: 100%;
      display: flex;
      align-items: center;
    }
    #news-crawl .crawl-inner {
      display: flex;
      white-space: nowrap;
      animation: newscrawl 28s linear infinite;
      font-family: 'Unbounded', sans-serif;
      font-weight: 700;
      font-size: 10px;
      letter-spacing: 2px;
      color: #020408;
      text-transform: uppercase;
    }
    #news-crawl .crawl-inner span { margin: 0 56px; flex-shrink: 0; }
    #news-crawl .crawl-inner .sep { color: rgba(0,0,0,0.35); font-weight:300; margin: 0 12px; }
    @keyframes newscrawl {
      0%   { transform: translateX(0); }
      100% { transform: translateX(-50%); }
    }
    /* push footer content up above the crawl bar */
    body { padding-bottom: 38px; }
"""
src = src.replace('  </style>', NEWS_CSS + '\n  </style>', 1)

# ── 3. Inject news bar HTML right after <body> ────────────────────────────────
MSG = "THIS WEEK ONLY &mdash; VEILPIERCER&#x2019;S LAUNCH PRICE IS 13.333% CHEAPER THAN IT WILL BE NEXT WEEK"
SEP = '<span class="sep">&#9632;</span>'
BAR_HTML = f"""
<div id="news-crawl">
  <div class="crawl-label">&#9654;&nbsp;BREAKING</div>
  <div class="crawl-track">
    <div class="crawl-inner">
      <span>{MSG}</span>{SEP}
      <span>VEILPIERCER LAUNCHES THIS WEEK AT $197 &mdash; PRICE INCREASES PERMANENTLY AFTER 7 DAYS</span>{SEP}
      <span>{MSG}</span>{SEP}
      <span>VEILPIERCER LAUNCHES THIS WEEK AT $197 &mdash; PRICE INCREASES PERMANENTLY AFTER 7 DAYS</span>{SEP}
    </div>
  </div>
</div>
"""

# Insert right after the opening body content (after <body> or after cursor divs)
if '<div id="cur"' in src:
    src = src.replace('<div id="cur"', BAR_HTML + '\n<div id="cur"', 1)
elif '<div id="cur-r"' in src:
    src = src.replace('<div id="cur-r"', BAR_HTML + '\n<div id="cur-r"', 1)
else:
    src = src.replace('<body>', '<body>\n' + BAR_HTML, 1)

# ── 4. Write and deploy ───────────────────────────────────────────────────────
out = r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html'
open(out, 'w', encoding='utf-8').write(src)
shutil.copy(out, r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\public\vp.html')
print('DONE — bytes:', len(src))
