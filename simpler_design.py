import re
import shutil

src = open(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', encoding='utf-8').read()

# 1. Update Fonts to Inter & JetBrains Mono (peak simple modern tech)
src = re.sub(
    r'<link href=\"https://fonts\.googleapis\.com/css2\?[^\"]+\" rel=\"stylesheet\">',
    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">',
    src
)

# Replace CSS font families
src = src.replace("font-family: 'Space Grotesk', sans-serif !important;", "font-family: 'Inter', sans-serif !important;")
src = src.replace("font-family: 'Outfit', sans-serif !important;", "font-family: 'Inter', sans-serif !important; letter-spacing: -0.02em;")
src = src.replace("font-family: 'Fira Code', monospace;", "font-family: 'JetBrains Mono', monospace;")
src = src.replace("font-family: 'Unbounded', sans-serif;", "font-family: 'Inter', sans-serif;")
src = src.replace("font-family:'Unbounded',sans-serif;", "font-family:'Inter',sans-serif; letter-spacing:-0.03em;")
src = src.replace("font-family: 'Cormorant Garamond', serif;", "font-family: 'Inter', sans-serif;")

# Remove heavy glowing text shadow, make it clean and simple
src = re.sub(
    r'text-shadow:\s*0\s+4px\s+16px[^\!]+!important,\s*0\s+2px\s+4px[^\!]+!important;',
    'text-shadow: none !important;',
    src
)
src = src.replace('text-shadow: 0 4px 24px rgba(0,0,0,1) !important;', 'text-shadow: none !important;')
src = src.replace('text-shadow: 0 0 12px rgba(0,229,255,0.6) !important;', 'text-shadow: none !important;')
src = src.replace('text-shadow: 0 0 16px rgba(0,229,255,0.7) !important;', 'text-shadow: none !important;')
src = src.replace('text-shadow: 0px 8px 32px rgba(0,0,0,1), 0px 4px 8px rgba(0,0,0,1) !important;', 'text-shadow: none !important;')

# 2. Tone down the background animations (less bright)
src = src.replace('opacity: 0.95;', 'opacity: 0.3;')
src = src.replace('filter: contrast(1.9) brightness(1.5) saturate(1.8);', 'filter: contrast(1.1) brightness(0.8) saturate(1.0);')
src = src.replace('var al=(1-ed/CDIST)*1.2;', 'var al=(1-ed/CDIST)*0.25;')

# Tone down the button neon so it's clean and direct
src = re.sub(
    r'box-shadow:\s*0\s*4px\s*24px\s*rgba\(0,229,255,0\.4\)\s*!important;',
    'box-shadow: none !important;',
    src
)
src = re.sub(
    r'box-shadow:\s*0\s*0\s*36px\s*rgba\(0,229,255,0\.8\)\s*!important;',
    'box-shadow: 0 4px 12px rgba(0,0,0,0.5) !important;',
    src
)

# 3. Simplify the Hero Text (description and straight to the point)
src = re.sub(
    r'<h1 class="hero-h1">.*?</h1>',
    '<h1 class="hero-h1" style="font-weight: 800; font-size: clamp(48px, 8vw, 110px); color: #fff;">YOUR AGENTS<br><span style="color: rgba(255,255,255,0.4);">FAIL SILENTLY.</span></h1>',
    src, flags=re.DOTALL
)

src = re.sub(
    r'<p class="hero-sub".*?</p>',
    '<p class="hero-sub" style="font-family: \'Inter\', sans-serif; font-size: clamp(16px, 1.8vw, 22px); color: rgba(255,255,255,0.6); max-width: 600px; margin-bottom: 40px; font-weight: 400;">Understand exactly what your AI systems are doing. A simple, local control plane to monitor, debug, and secure your autonomous agents in real-time.</p>',
    src, flags=re.DOTALL
)

# Update node colors to be softer (less neon)
src = src.replace('0x00e5ff', '0x4488aa')
src = src.replace('new THREE.Color(0x00e5ff)', 'new THREE.Color(0x6699bb)')
src = src.replace('new THREE.Color(0xbf00ff)', 'new THREE.Color(0x8877aa)')
src = src.replace('new THREE.Color(0x00ff88)', 'new THREE.Color(0x55aa88)')

with open(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', 'w', encoding='utf-8') as f:
    f.write(src)
shutil.copy(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\public\vp.html')
print("Applied clean layout: Inter fonts, simplified text, muted animations.")
