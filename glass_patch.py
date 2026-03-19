import re
import shutil

src = open(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', encoding='utf-8').read()

# 1. Update Google Fonts to newer modern fonts (Outfit for headers, Space Grotesk for body)
src = re.sub(
    r'<link href=\"https://fonts\.googleapis\.com/css2\?[^\"]+\" rel=\"stylesheet\">',
    '<link href=\"https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=Space+Grotesk:wght@300;400;500;700&family=Fira+Code:wght@300;400;500&display=swap\" rel=\"stylesheet\">',
    src
)

# 2. Add extra CSS with modern tech redesign
GLASS_CSS = """
    /* ══════ MODERN TECH 2026 OVERRIDES ══════ */
    /* Fonts */
    body { font-family: 'Space Grotesk', sans-serif !important; background: transparent !important; }
    h1, h2, h3, .price-h, .n-logo, .sec-tag, .btn-primary, .crawl-inner, .crawl-label { 
      font-family: 'Outfit', sans-serif !important; 
    }
    
    /* Global transparency so mesh strictly shines through the whole page */
    body, html { background-color: #020408 !important; }
    #hero, #why, #incidents, #features, #vision, #pricing, footer, #obs-section, .wave-strip, #protocols, #buyers {
      background: transparent !important;
    }
    
    /* Global text visibility with glowing shadows over moving mesh */
    p, li, span, h1, h2, h3, .td-desc, .fc-body, .pc-desc, .why-lead, .btn-ghost {
      text-shadow: 0 4px 16px rgba(0,0,0,0.9), 0 2px 4px rgba(0,0,0,0.8) !important;
      color: #ffffff !important;
      opacity: 1 !important;
      visibility: visible !important;
    }
    .h1-dim { color: rgba(255,255,255,0.75) !important; text-shadow: 0 4px 24px rgba(0,0,0,1) !important; }
    .sec-tag { color: var(--vis) !important; text-shadow: 0 0 12px rgba(0,229,255,0.6) !important; }
    .n-logo { text-shadow: 0 0 16px rgba(0,229,255,0.7) !important; }
    .hero-h1 { text-shadow: 0px 8px 32px rgba(0,0,0,1), 0px 4px 8px rgba(0,0,0,1) !important; }
    
    /* Make tables un-ugly */
    .t-row {
      background: rgba(12, 18, 25, 0.4) !important;
      backdrop-filter: blur(8px); border-radius: 8px; margin-bottom: 6px; 
      border: 1px solid rgba(255,255,255,0.05) !important;
    }
    .t-head { border-bottom: 2px solid rgba(0,229,255,0.4) !important; }

    /* Glassmorphism Cards for features, incidents, UI boxes */
    .p-card, .fc-card, .pc-card, .price-box, 
    div[style*="background:var(--panel)"], div[style*="background: var(--panel)"] {
      background: rgba(8, 12, 16, 0.45) !important;
      backdrop-filter: blur(14px) !important;
      -webkit-backdrop-filter: blur(14px) !important;
      border: 1px solid rgba(0,229,255,0.2) !important;
      box-shadow: 0 12px 40px rgba(0,0,0,0.6) !important;
      border-radius: 12px !important;
    }
    
    /* Fix protocols section originally white-ish */
    #protocols { background: transparent !important; }
    #protocols h2, #buyers h2 { color: white !important; }
    .pc-card { color: white !important; border: 1px solid rgba(255,255,255,0.1) !important; }
    .pc-head { border-bottom: 1px solid rgba(255,255,255,0.1) !important; }

    /* Buttons upgraded to neon 2026 feel */
    .btn-primary {
      background: linear-gradient(135deg, #00e5ff, #0077ff) !important;
      color: white !important;
      border-radius: 6px !important;
      box-shadow: 0 4px 24px rgba(0,229,255,0.4) !important;
      border: 1px solid rgba(255,255,255,0.2) !important;
      text-shadow: 0 2px 4px rgba(0,0,0,0.3) !important;
      font-weight: 800 !important;
    }
    .btn-primary:hover {
      box-shadow: 0 0 36px rgba(0,229,255,0.8) !important;
      transform: translateY(-2px) scale(1.02) !important;
    }
    
    /* Remove the weird white grid borders from 'why' / 'two-col' etc */
    .three-col, .two-col { gap: 24px !important; border: none !important; background: transparent !important; }
    .two-col > div { border: none !important; }
    
    /* Tone down the grid so it doesn't distract from the mesh */
    body::before { opacity: 0.3 !important; }
"""

if 'MODERN TECH 2026 OVERRIDES' not in src:
    src = src.replace('  </style>', GLASS_CSS + '\n  </style>', 1)

with open(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', 'w', encoding='utf-8') as f:
    f.write(src)
shutil.copy(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\public\vp.html')
print("Patched viewport styling to pure Glassmorphism transparency + glowing fonts!")
