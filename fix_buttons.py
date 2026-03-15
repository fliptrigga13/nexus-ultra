path = r"C:\Users\fyou1\Desktop\New folder\nexus-ultra\nexus_hub.html"

with open(path, 'rb') as f:
    data = f.read()

# Work at byte level for remaining garbled sequences
# Find & replace byte patterns
replacements = [
    # ΓÜí = bytes CE DC AD in latin-1 view, but in our file after previous fixes
    # Let's find what bytes ΓÜí actually are in the file
    # ⚡ = U+26A1 = UTF-8 bytes: E2 9A A1
    # If stored as mojibake from CP1252: C3 8E C3 9C C2 AD or similar
    # Force replace the fire button text
    (b'\xe2\x9a\xa1', b'\xe2\x9a\xa1'),  # ⚡ already correct - skip
]

# Find instances of garbled INJECT button
idx = data.find(b'INJECT')
if idx > 0:
    snippet = data[max(0,idx-20):idx+10]
    print(f"Before INJECT: {snippet!r}")
    
idx = data.find(b'FORCE CYCLE')
if idx > 0:
    snippet = data[max(0,idx-20):idx+15]
    print(f"Before FORCE CYCLE: {snippet!r}")

# Now just hardcode the correct button HTML
with open(path, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Nuclear fix: just replace the whole btn-row content
old_row = content[content.find('<div id="btn-row">'):content.find('</div>', content.find('<div id="btn-row">'))+6]
print(f"Current btn-row: {repr(old_row[:300])}")

new_row = '''<div id="btn-row">
      <button class="btn btn-fire" onclick="fire()">⚡ SEND</button>
      <button class="btn btn-mic" id="mic-btn" onclick="toggleMic()">🎙 MIC</button>
      <button class="btn btn-sec" id="tts-btn" onclick="toggleTTS()" title="Toggle AI voice">🔊 TTS</button>
      <button class="btn btn-sec" onclick="forceCycle()">🔄 FORCE CYCLE</button>
      <button class="btn btn-sec" onclick="clearChat()">🗑 CLEAR</button>
      <button class="btn btn-danger" onclick="flushBB()">🧹 FLUSH BB</button>
      <button id="stop-btn" class="btn btn-danger" onclick="stopAll()" style="display:none">⬛ STOP</button>
    </div>'''

if '<div id="btn-row">' in content:
    content = content[:content.find('<div id="btn-row">')] + new_row + content[content.find('</div>', content.find('<div id="btn-row">'))+6:]
    print("btn-row replaced!")
else:
    print("ERROR: btn-row not found")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Done.")
