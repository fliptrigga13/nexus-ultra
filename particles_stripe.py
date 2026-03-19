import re
import shutil

src = open(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', encoding='utf-8').read()

# 1. Wire up the top header CTA directly to Stripe
src = re.sub(
    r'<a href="[^"]*"[^>]*class="n-cta"[^>]*>.*?</a>',
    '<a href="https://buy.stripe.com/00w5kv0Q1dcVgCkgHSbsc03" target="_blank" rel="noopener" class="n-cta">GET ACCESS &rarr;</a>',
    src, flags=re.DOTALL
)

# 2. Add "tiny particles" floating background layer in ThreeJS
# Look for where the line segments are added to the scene
anchor = 'scene.add(lSeg);'
particles_code = """
  // ── Inject tiny background particles ─────────────────────
  var ptGeo = new THREE.BufferGeometry();
  var ptCount = 800; // lots of tiny grains
  var ptPos = new Float32Array(ptCount * 3);
  for(var i=0; i<ptCount*3; i+=3){
      ptPos[i] = rr(-W*1.5, W*1.5);
      ptPos[i+1] = rr(-H*1.5, H*1.5);
      ptPos[i+2] = rr(-500, 200); // deep background
  }
  ptGeo.setAttribute('position', new THREE.BufferAttribute(ptPos, 3));
  var ptMat = new THREE.PointsMaterial({
      size: 1.8,
      color: 0x00e5ff,
      transparent: true,
      opacity: 0.35,
      blending: THREE.AdditiveBlending,
      sizeAttenuation: true
  });
  window.ptSystem = new THREE.Points(ptGeo, ptMat);
  scene.add(window.ptSystem);
  // ─────────────────────────────────────────────────────────
"""

if 'window.ptSystem' not in src:
    src = src.replace(anchor, anchor + '\n' + particles_code)

# Rotate the particles very slowly in the render loop 'tick'
# "cam.lookAt(scene.position);" is a great anchor
tick_anchor = 'cam.lookAt(scene.position);'
tick_particles = '  if(window.ptSystem){ window.ptSystem.rotation.y += 0.0003; window.ptSystem.rotation.x += 0.00015; }\n'

if 'window.ptSystem.rotation' not in src:
    src = src.replace(tick_anchor, tick_anchor + '\n' + tick_particles)

with open(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', 'w', encoding='utf-8') as f:
    f.write(src)
shutil.copy(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\public\vp.html')
print("Particles and Stripe correctly applied!")
