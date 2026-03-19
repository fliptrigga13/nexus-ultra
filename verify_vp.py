s = open(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', encoding='utf-8').read()
checks = [
    ('neural-bg canvas',    'id="neural-bg"' in s),
    ('z-index -1 CSS',      'z-index: -1' in s),
    ('wall canvas',         'obs-wall-canvas' in s),
    ('dual canvas setup',   'obs-canvas' in s and 'obs-wall-canvas' in s),
    ('Physarum sense',      'function sense(' in s),
    ('wall drawing',        "mode==='wall'" in s),
    ('30fps cap',           'FPS_INTERVAL' in s),
    ('grid overlay',        'body::before' in s),
    ('opaque sections',     'rgba(8,12,16,0.96)' in s),
    ('197 price',           '197' in s),
    ('stripe link',         'buy.stripe.com/00w5kv0Q1dcVgCkgHSbsc03' in s),
    ('news crawl',          'news-crawl' in s),
    ('threejs cdn',         'three.min.js' in s),
]
for name, ok in checks:
    print(('OK   ' if ok else 'FAIL ') + name)
