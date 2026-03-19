import re
import shutil

src = open(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', encoding='utf-8').read()

# 1. THREE.JS CRISPNESS & MOUSE INTERACTIVITY
# Turn on antialiasing and improve pixel ratio
src = src.replace('antialias:false', 'antialias:true')
src = src.replace('rend.setPixelRatio(Math.min(devicePixelRatio, 1.5));', 'rend.setPixelRatio(window.devicePixelRatio || 1);')

# Increase node size to be rounder/crunchier
src = src.replace('sz:t>.88?5:(t>.78?3.6:2.2)', 'sz:t>.88?7:(t>.78?5:3.5)')

# Make the lines MUCH brighter and wider perceived by boosting the alpha and color
src = src.replace('var al=(1-ed/CDIST)*.45;', 'var al=(1-ed/CDIST)*1.2;') 

# Significantly increase mouse gravity 
# old: var dx=mx-nd.x,dy=my-nd.y,d2=dx*dx+dy*dy,R2=170*170; if(d2<R2&&d2>1){var s=.006*(1-Math.sqrt(d2)/170);nd.vx+=dx*s;nd.vy+=dy*s;}
src = re.sub(
    r'var dx=mx-nd\.x,dy=my-nd\.y,d2=dx\*dx\+dy\*dy,R2=\d+\*\d+;\s*if\(d2<R2&&d2>1\)\{var s=[^\)]+\);nd\.vx\+=dx\*s;nd\.vy\+=dy\*s;\}',
    'var dx=mx-nd.x,dy=my-nd.y,d2=dx*dx+dy*dy,R2=350*350; if (d2 < R2 && d2 > 1) { var s = 0.05 * (1 - Math.sqrt(d2) / 350); nd.vx += dx * s; nd.vy += dy * s; }',
    src, flags=re.DOTALL
)

# 2. OBSERVATORY WALL REMOVAL AND DECLUTTER
# Remove the wall button
src = re.sub(r'<button class="obs-btn warn-btn" id="btn-wall" onclick="setObs\(\'wall\',this\)">&#9632; WALL</button>', '', src)
# Remove the wall canvas
src = re.sub(r'<!-- Wall canvas:.*?-->\s*<canvas id="obs-wall-canvas"></canvas>', '', src, flags=re.DOTALL)
# Strip wall handling from setObs label
src = src.replace("'wall':'WALL'", "")
# Stop drawing wall
src = re.sub(r'else\s*if\s*\(mode\s*===\s*\'wall\'\)\s*\{\s*drawing\s*=\s*true;.*?wX\.fill\(\);\s*\}', '', src, flags=re.DOTALL)
src = re.sub(r'if\s*\(!drawing\s*\|\|\s*\(window\.__obsMode\|\|\'source\'\)\s*!==\s*\'wall\'\s*\|\|\s*!wX\)\s*return;', 'if (!drawing || (window.__obsMode||\'source\') !== \'fire\') return;', src, flags=re.DOTALL) # wait, mousemove was checking for 'wall'
# Actually, just blow away the wall mousemove handler logic 
src = re.sub(r'pC\.addEventListener\(\'mousemove\',function\(e\)\{[\s\S]*?lastY=p\.y;\s*\}\);', "pC.addEventListener('mousemove', function(e) {});", src)

# 3. PRICE AT TOP & NICE FONTS/COLORS
# Let's ensure the CTA button in the hero clearly says $197
src = re.sub(
    r'<a href="https://buy\.stripe\.com/00w5kv0Q1dcVgCkgHSbsc03"[^>]*class="btn-primary"[^>]*>.*?</a>',
    '<a href="https://buy.stripe.com/00w5kv0Q1dcVgCkgHSbsc03" target="_blank" rel="noopener" class="btn-primary" style="font-size: 16px; padding: 20px 48px; display: inline-flex; align-items: center; justify-content: center; text-align: center; box-shadow: 0 0 40px rgba(0,229,255,0.6) !important; font-weight: 800; border-radius: 12px; animation: pulse 2s infinite;">UNLOCK ACCESS &mdash; $197 ONE-TIME &rarr;</a>',
    src, count=1 # Only target the hero button
)

# Add a CSS pulse animation for the top button
ANIM_CSS = """
    @keyframes pulse {
      0% { box-shadow: 0 0 24px rgba(0,229,255,0.4); }
      50% { box-shadow: 0 0 48px rgba(0,229,255,0.8); }
      100% { box-shadow: 0 0 24px rgba(0,229,255,0.4); }
    }
"""
if '@keyframes pulse' not in src:
    src = src.replace('/* ══════ MODERN TECH 2026 OVERRIDES ══════ */', '/* ══════ MODERN TECH 2026 OVERRIDES ══════ */\n' + ANIM_CSS)

# Ensure background grid is gone entirely since user wants ALL ONE BACKGROUND smoothly 
# (Grid can add clutter)
src = src.replace('rgba(0,229,255,0.015)', 'transparent') 
src = src.replace('rgba(0,229,255,0.028)', 'transparent')

with open(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', 'w', encoding='utf-8') as f:
    f.write(src)
shutil.copy(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\public\vp.html')
print("Applied crisp nodes, extreme interactivity, pared down the wall clutter, and bumped the price to the top hero section!")
