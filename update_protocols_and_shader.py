import sys

vs = r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\veilpiercer-sales.html'
with open(vs, 'r', encoding='utf-8') as f:
    text = f.read()

css_injection = """
    /* ══════ TYPOGRAPHY OVERRIDES ══════ */
    .fc-title { font-size: 18px !important; letter-spacing: 0px !important; line-height: 1.3 !important; }
    .fc-body { font-size: 13px !important; color: rgba(221, 234, 245, 0.8) !important; line-height: 1.7 !important; }
    .pc-name { font-size: 20px !important; font-weight: 900 !important; font-family: 'Unbounded', sans-serif !important; margin-bottom: 8px !important; }
    .pc-desc { font-size: 14px !important; color: rgba(255,255,255,0.9) !important; line-height: 1.6 !important; margin-bottom: 8px !important; text-shadow: none !important; }
    .pc-when { font-size: 12px !important; color: rgba(0,229,255,0.8) !important; margin-top: 12px !important; border-top: 1px solid rgba(0,229,255,0.2); padding-top: 12px !important; }
    .pc-trigger { font-size: 11px !important; color: var(--gold) !important; letter-spacing: 1px !important; margin-bottom: 12px !important; text-transform: uppercase !important; }
"""

if '/* ══════ TYPOGRAPHY OVERRIDES ══════ */' not in text:
    text = text.replace('  </style>', css_injection + '\n  </style>', 1)
    with open(vs, 'w', encoding='utf-8') as f:
        f.write(text)
    print("Injected CSS")
else:
    print("CSS already injected")

