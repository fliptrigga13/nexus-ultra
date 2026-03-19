"""fix_zindex.py — Fix z-index so all content is visible above the neural mesh"""
import re, shutil

src = open(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', encoding='utf-8').read()

# ── 1. Fix the neural-bg canvas inline style to z-index:-1 ───────────────────
# Replace any instance of z-index:0 on the neural-bg canvas
src = re.sub(
    r'(id="neural-bg"[^>]*style="[^"]*?)z-index:\s*\d+',
    r'\g<1>z-index:-1',
    src
)

# ── 2. Replace the entire VISIBILITY PATCH CSS block with a clean version ─────
OLD_VIS_PATCH = re.compile(
    r'/\* ══════════ VISIBILITY PATCH ══════════ \*/.*?/\* ══════════ UPGRADED OBSERVATORY',
    re.DOTALL
)

NEW_VIS_CSS = """/* ══════════ VISIBILITY PATCH v2 ══════════ */
    /* Neural mesh fixed far behind all content */
    #neural-bg {
      position: fixed !important;
      z-index: -1 !important;
      pointer-events: none !important;
    }

    /* Faint grid overlay — helps eyes track nodes, improves perceived performance */
    body::before {
      content: '';
      position: fixed;
      inset: 0;
      z-index: -1;
      pointer-events: none;
      background-image:
        linear-gradient(rgba(0,229,255,0.025) 1px, transparent 1px),
        linear-gradient(90deg, rgba(0,229,255,0.025) 1px, transparent 1px);
      background-size: 64px 64px;
    }

    /* All sections render above neural canvas naturally — no isolation needed */
    #hero, #why, #incidents, #features, #vision, #pricing, footer,
    #protocols, #buyers, #obs-section, #statband, .wave-strip {
      position: relative;
    }

    /* Dark sections get opaque backgrounds so text is 100% readable */
    #why      { background: rgba(8,12,16,0.96) !important; }
    #incidents{ background: rgba(4,6,8,0.97)   !important; }
    #features { background: rgba(8,12,16,0.96) !important; }
    #vision   { background: rgba(4,6,8,0.96)   !important; }
    #pricing  { background: rgba(8,12,16,0.96) !important; }
    footer    { background: rgba(4,6,8,0.97)   !important; }
    #obs-section { background: rgba(4,6,8,0.97) !important; }
    .wave-strip  { background: rgba(8,12,16,0.98) !important; }

    /* Hero: dark radial vignette so h1 pops over the neural mesh */
    #hero {
      background: transparent;
    }
    #hero::before {
      content: '';
      position: absolute;
      inset: 0;
      z-index: 0;
      pointer-events: none;
      background: radial-gradient(
        ellipse 85% 100% at 25% 45%,
        rgba(4,6,8,0.78) 0%,
        rgba(4,6,8,0.0) 100%
      );
    }
    .hero-content   { position: relative; z-index: 2; }
    .hero-grid      { z-index: 1; }
    .hero-ticker-wrap { position: relative; z-index: 2; }

    /* Make the dim headline text slightly more visible */
    .h1-dim { color: rgba(221,234,245,0.22) !important; }

    /* Stat band (cyan bg) sits above neural mesh fine */
    #statband { position: relative; }

    /* ══════════ UPGRADED OBSERVATORY"""

src = OLD_VIS_PATCH.sub(NEW_VIS_CSS, src)

# ── 3. Also fix the neural-bg inline style via the Three.js script block ──────
# In the injected canvas tag, make sure it has z-index:-1
src = src.replace(
    "style=\"position:fixed;top:0;left:0;width:100vw;height:100vh;z-index:0;",
    "style=\"position:fixed;top:0;left:0;width:100vw;height:100vh;z-index:-1;"
)
src = src.replace(
    "style='position:fixed;top:0;left:0;width:100vw;height:100vh;z-index:0;",
    "style='position:fixed;top:0;left:0;width:100vw;height:100vh;z-index:-1;"
)

# ── 4. Fix the IntersectionObserver reveal — make sure all items start visible 
#    in case the observer doesn't fire (fallback: add transition starting visible)
REVEAL_FIX = """
    /* Reveal fallback — items visible by default, animate in when observed */
    .reveal {
      opacity: 0;
      transform: translateY(18px);
      transition: opacity 0.6s ease, transform 0.6s ease;
    }
    .reveal.in {
      opacity: 1 !important;
      transform: translateY(0) !important;
    }
"""
if '.reveal {' not in src:
    src = src.replace('  </style>', REVEAL_FIX + '\n  </style>', 1)

# ── 5. Make sure IntersectionObserver script exists and runs ──────────────────
OBS_SCRIPT = """
// Scroll reveal
(function(){
  var items = document.querySelectorAll('.reveal');
  if (!items.length) return;
  var io = new IntersectionObserver(function(entries){
    entries.forEach(function(e){
      if(e.isIntersecting){ e.target.classList.add('in'); io.unobserve(e.target); }
    });
  }, { threshold: 0.08 });
  items.forEach(function(el){ io.observe(el); });
  // Fallback: reveal all after 1.5s in case observer fails
  setTimeout(function(){
    items.forEach(function(el){ el.classList.add('in'); });
  }, 1500);
})();
"""

# Only add if not already present
if "Scroll reveal" not in src:
    src = src.replace('</body>', '<script>\n' + OBS_SCRIPT + '\n</script>\n</body>', 1)

# ── 6. Fix ngrok tunnel — use free static domain with correct flag ─────────────
# (nothing to change in HTML for this)

# ── 7. Write and deploy ───────────────────────────────────────────────────────
out = r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html'
open(out, 'w', encoding='utf-8').write(src)
shutil.copy(out, r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\public\vp.html')
print('DONE — bytes:', len(src), ' lines:', src.count('\n'))
