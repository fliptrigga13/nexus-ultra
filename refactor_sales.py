import sys

vs = r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\veilpiercer-sales.html'
with open(vs, 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Inject missing CSS
css_file = r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\missing_css.txt'
with open(css_file, 'r', encoding='utf-8') as f:
    missing_css = f.read()

# If Observatory CSS wasn't added yet, append to the end of <style>
if '/* ═════════ OBSERVATORY ═════════ */' not in text:
    text = text.replace('  </style>', '\n' + missing_css + '\n  </style>', 1)

# 2. Extract #pricing
start_pricing = '  <!-- ═══════════════════ PRICING ═══════════════════ -->'
end_pricing = '  <!-- ═══════════════════ FAQ ═══════════════════ -->'
idx_ps = text.find(start_pricing)
idx_pe = text.find(end_pricing)

if idx_ps == -1 or idx_pe == -1:
    print('Failed to find pricing block')
    sys.exit()

pricing_html = text[idx_ps:idx_pe]

# Remove from original location
text = text[:idx_ps] + text[idx_pe:]

# 3. Rewrite hero-content
start_hero = '    <div class="hero-content">'
end_hero = '    </div>\n\n    <div class="hero-ticker-wrap reveal">'
idx_hs = text.find(start_hero)
idx_he = text.find(end_hero)

new_hero = """    <div class="hero-content">
      <div class="hero-eye reveal">AI Agent Observatory · Production Control Plane</div>
      <h1 class="hero-h1 reveal" style="font-size: clamp(30px, 5vw, 60px); line-height: 1.1; margin-bottom: 24px;">
        I BUILT VEILPIERCER BECAUSE I WAS TIRED OF RUNNING MY AI AGENTS INTO A <span class="h1-red">BLACK BOX.</span>
      </h1>
      <p class="hero-sub reveal" style="text-align:left; font-size:16px; line-height:1.6; max-width:800px; margin: 0 auto; margin-bottom: 40px;">
        I ran 53,000 operations on my own machine and realized I had no idea what they were actually doing until the bill hit or something broke. Datadog wanted $400 a month for "cloud visibility" that didn't even let me stop a rogue loop.<br><br>
        So I built a real-time, mission-control dashboard that runs 100% locally.
      </p>

      <div class="hero-stats reveal" style="text-align:left; max-width:800px; margin: 0 auto; display:block;">
        <h3 style="color:var(--vis); margin-bottom:16px; font-size:20px; font-family:'Unbounded',sans-serif;">The Pitch</h3>
        <ul style="list-style:none; padding:0; margin:0; display:flex; flex-direction:column; gap:16px; font-size:14px; color:rgba(221,234,245,.8);">
          <li><strong style="color:var(--vis)">👁 See Every Move:</strong> Real-time observability into every agent decision, live on your machine.</li>
          <li><strong style="color:var(--vis)">⚡ Total Control:</strong> 4 instant protocols (Lockdown, Amplify, Selective, Nominal) to freeze or ramp up your swarm on the fly.</li>
          <li><strong style="color:var(--vis)">🔒 Zero Cloud, Zero Monthly:</strong> Privacy-first. No data leaves your hardware. No subscriptions.</li>
          <li><strong style="color:var(--vis)">🚀 Built for 2026:</strong> Fully integrated for the newest NVIDIA Vera Rubin and NemoClaw stacks.</li>
        </ul>
        <div style="margin-top:24px; padding:16px; border:1px solid rgba(0,229,255,.3); background:rgba(0,229,255,.05); border-radius:8px;">
           <strong style="color:var(--vis);">Visuals Upgraded:</strong> Transferred the standard 2D canvas out and implemented an ultra-premium, high-performance 3D WebGL background (Three.js) utilizing our new GTC 2026 paradigms. Updated the swarm visuals to include high-density purple diamond "Tensor Cores" orbiting the mesh.
        </div>
        <p style="margin-top:24px; font-style:italic; font-size:16px; color:#fff;">
          One-time payment. Full source code. <strong style="color:var(--vis)">$197 and it's yours forever.</strong><br>
          If your agents are doing things you didn't expect and you don't know why—this is how you fix that.
        </p>
      </div>
      <div class="hero-ctas reveal" style="margin-top:40px;">
        <a href="#pricing" class="btn-primary">View Pricing Below</a>
        <a href="#why" class="btn-ghost">See why it matters →</a>
      </div>
"""

if idx_hs != -1 and idx_he != -1:
    text = text[:idx_hs] + new_hero + text[idx_he:]
else:
    print('Failed to find hero section')

# 4. Insert pricing immediately under WAVE STRIP 1
wave_strip = '  <!-- WAVE STRIP 1 -->\n  <canvas class="strip" id="strip1"></canvas>\n'
idx_wave = text.find(wave_strip)

if idx_wave == -1:
    # fallback, right before WHY
    wave_strip = '  <!-- ═══════════════════ WHY ═══════════════════ -->'
    idx_wave = text.find(wave_strip)

if idx_wave != -1:
    idx_insert = idx_wave + len(wave_strip)
    text = text[:idx_insert] + '\n' + pricing_html + '\n' + text[idx_insert:]

with open(vs, 'w', encoding='utf-8') as f:
    f.write(text)
print('Successfully rewritten hero, moved pricing, and injected Observatory CSS')
