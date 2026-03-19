"""tweak_vp.py — Targeted tweaks only: remove early access bar, brighten neural mesh, visible grid"""
import re, shutil

src = open(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', encoding='utf-8').read()

# ── 1. Remove EARLY ACCESS / access-gate overlay ─────────────────────────────
# Remove any access bar, countdown timer, gate overlay elements
src = re.sub(r'<div[^>]*id=["\']access[^"\']*["\'][^>]*>.*?</div>', '', src, flags=re.DOTALL)
src = re.sub(r'<section[^>]*id=["\']access[^"\']*["\'][^>]*>.*?</section>', '', src, flags=re.DOTALL)
# Remove any inline "EARLY ACCESS" text blocks or countdown divs
src = re.sub(r'<[^>]+>[^<]*EARLY ACCESS[^<]*</[^>]+>', '', src)
src = re.sub(r'<div[^>]*class="[^"]*(access|gate|countdown|timer|banner-bar)[^"]*"[^>]*>.*?</div>', '', src, flags=re.DOTALL | re.IGNORECASE)

# Also kill any JS that sets a countdown timer
src = re.sub(r'var\s+\w*[Cc]ountdown\w*.*?;', '', src)
src = re.sub(r'setInterval\([^)]*(?:countdown|timer|hours)[^)]*\)', '', src, flags=re.IGNORECASE)

# ── 2. Brighten neural mesh: increase opacity + filter ───────────────────────
# From the CSS block we injected
src = src.replace('opacity: 0.55;', 'opacity: 0.72;')
src = src.replace(
    'filter: contrast(1.65) brightness(1.1) saturate(1.25);',
    'filter: contrast(1.8) brightness(1.35) saturate(1.4);'
)

# ── 3. Make grid lines slightly more visible ─────────────────────────────────
src = src.replace(
    'rgba(0,229,255,0.022) 1px, transparent 1px),\n        linear-gradient(90deg, rgba(0,229,255,0.022)',
    'rgba(0,229,255,0.038) 1px, transparent 1px),\n        linear-gradient(90deg, rgba(0,229,255,0.038)'
)

# ── 4. Force all content sections visible (belt-and-suspenders) ──────────────
# Add a CSS rule that forces visibility on all main sections
FORCE_VIS = """
    /* Force content visibility — belt-and-suspenders */
    #hero, #nav, #why, #incidents, #features, #vision,
    #pricing, footer, #obs-section, #statband, #buyers, #protocols {
      display: block !important;
      visibility: visible !important;
      opacity: 1 !important;
      pointer-events: auto !important;
    }
    #hero { display: grid !important; }
    #nav  { display: flex  !important; }
    .hero-content { opacity: 1 !important; transform: none !important; }
    .reveal { opacity: 1 !important; transform: none !important; }
"""
src = src.replace('  </style>', FORCE_VIS + '\n  </style>', 1)

# ── 5. Write and deploy ───────────────────────────────────────────────────────
out = r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html'
open(out, 'w', encoding='utf-8').write(src)
shutil.copy(out, r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\public\vp.html')
print('DONE bytes:', len(src))

# Quick sanity check
checks = [
    ('neural-bg',     'id="neural-bg"' in src),
    ('opacity 0.72',  'opacity: 0.72;' in src),
    ('brighter filter','1.35' in src),
    ('grid 0.038',    '0.038' in src),
    ('force vis',     'Force content visibility' in src),
    ('obs-wall',      'obs-wall-canvas' in src),
    ('no early gate', 'EARLY ACCESS' not in src),
]
for name,ok in checks:
    print(('OK   ' if ok else 'FAIL ') + name)
