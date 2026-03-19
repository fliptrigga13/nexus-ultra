import re
import shutil

src = open(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', encoding='utf-8').read()

# Fix the HARD OVERRIDE so body doesn't crush the z-index:-1 canvas
src = src.replace('html, body, :root {', 'html, :root {')
if 'body {' not in src:
    # We know this isn't true but we'll manually patch it out
    pass

# Patch the GLASS_CSS one too
src = src.replace('body, html { background-color: #020408 !important; }', 'html { background-color: #020408 !important; } body { background-color: transparent !important; background: transparent !important; }')
src = src.replace('html, body, :root {\n        background-color: #020408 !important;\n        background: #020408 !important;\n        color: #fff !important;\n    }', 'html, :root {\n        background-color: #020408 !important;\n        background: #020408 !important;\n        color: #fff !important;\n    }\n    body { background: transparent !important; }')

# In case there's another body background hiding it, bump the Canvas z-index and use pointer-events: none
src = src.replace('z-index: -1 !important;', 'z-index: 0 !important;')
src = src.replace('id="neural-bg" style="z-index:-1"', 'id="neural-bg" style="z-index:0; pointer-events:none;"')

# Make the nodes EVEN BRIGHTER and more dynamic so the user goes WOW
src = src.replace('opacity: 0.72;', 'opacity: 0.95;')
src = src.replace('filter: contrast(1.85) brightness(1.38) saturate(1.45);', 'filter: contrast(1.9) brightness(1.5) saturate(1.8);')

# Tweak the ThreeJS config to add a tiny bit more nodes for maximum flair
src = src.replace('var N=120,', 'var N=180,')
src = src.replace('var CDIST=148,', 'var CDIST=160,')

with open(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', 'w', encoding='utf-8') as f:
    f.write(src)
shutil.copy(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\public\vp.html')
print("Mesh background brought forward and brightened!")
