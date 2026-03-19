import re
import shutil

src = open(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', encoding='utf-8').read()

# Force absolute black backgrounds to kill ANY white leaks
HARD_BLACK_CSS = """
    /* VERA RUBIN 2026 HARD OVERRIDE */
    html, body, :root {
        background-color: #020408 !important;
        background: #020408 !important;
        color: #fff !important;
    }
    
    #hero, #why, #incidents, #features, #vision, #pricing, footer, #obs-section, .wave-strip, #protocols, #buyers {
      background: transparent !important;
    }
"""

src = src.replace('  </style>', HARD_BLACK_CSS + '\n  </style>', 1)

with open(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', 'w', encoding='utf-8') as f:
    f.write(src)
shutil.copy(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\public\vp.html')
print("Forced absolute black background successfully!")
