"""safe_tweak.py — Only safe string replacements on the clean 118KB vp.html"""
import shutil

src = open(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', encoding='utf-8').read()

before = len(src)

# ── Brighten neural mesh: opacity ─────────────────────────────────────────────
src = src.replace('      opacity: 0.55;\n', '      opacity: 0.72;\n')

# ── Brighten neural mesh: filter ─────────────────────────────────────────────
src = src.replace(
    'filter: contrast(1.65) brightness(1.1) saturate(1.25);',
    'filter: contrast(1.85) brightness(1.38) saturate(1.45);'
)

# ── Make grid lines more visible ─────────────────────────────────────────────
src = src.replace('rgba(0,229,255,0.022)', 'rgba(0,229,255,0.042)')

# ── Force all page sections to be visible (override any hidden state) ────────
# We insert this at the start of the extra CSS block
FORCE = """    /* Force visibility — removes any JS/CSS hidden state */
    #hero,#nav,#why,#incidents,#features,#vision,#pricing,footer,
    #obs-section,#statband,#buyers,#protocols{
      visibility:visible!important;
    }
    #hero{display:grid!important;}
    #nav{display:flex!important;}
    #why,#incidents,#features,#vision,#pricing,footer,
    #obs-section,#statband,#buyers,#protocols{display:block!important;}
    .hero-content,.hero-h1,.hero-sub,.hero-stats,.hero-ctas{
      opacity:1!important;transform:none!important;
    }
"""
# Insert at the very top of our extra CSS block
src = src.replace(
    '    /* ══════ NEURAL MESH + GRID ══════ */',
    FORCE + '\n    /* ══════ NEURAL MESH + GRID ══════ */'
)

after = len(src)
print('Before:', before, ' After:', after, ' Delta:', after - before)

# verify
checks = [
    ('opacity 0.72',  'opacity: 0.72;' in src),
    ('brightness 1.38', '1.38' in src),
    ('grid 0.042',    '0.042' in src),
    ('force visible', 'Force visibility' in src),
    ('neural-bg',     'id="neural-bg"' in src),
    ('obs-wall',      'obs-wall-canvas' in src),
    ('stripe',        'buy.stripe.com/00w5kv0Q1dcVgCkgHSbsc03' in src),
]
for name, ok in checks:
    print(('OK   ' if ok else 'FAIL ') + name)

# deploy
out = r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html'
open(out, 'w', encoding='utf-8').write(src)
shutil.copy(out, r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\public\vp.html')
print('DEPLOYED')
