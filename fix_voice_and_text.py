path = r"C:\Users\fyou1\Desktop\New folder\nexus-ultra\nexus_hub.html"
with open(path, 'r', encoding='utf-8', errors='replace') as f:
    c = f.read()

# Direct replacements for garbled sequences (HTML buttons + JS)
fixes = [
    # Button emojis
    ('\u2261\u0192\u00c4\u00d6', '🎙'),   # mic
    ('\u2261\u0192\u00f6\u00a4', '🔄'),   # cycle
    ('\u2261\u0192\u00ba\u2563', '🗑️'),   # clear/trash
    ('\u2261\u0192\u00f9\u00e6', '🧹'),   # flush/broom
    ('\u0393\u00dc\u00ad',       '⚡'),   # lightning (inject button)
    # Arrow in tier headers
    ('\u0393\u00fb\u009b',       '▼'),
    ('\u0393\u00fb\u00a9',       '▲'),    
    ('\u039b\u00fb\u009b',       '▼'),
    ('ΓÇö',                      '—'),
    # Any remaining Γ sequences in JS (comments/strings)
    ('\u0393\u00f2\u00c9',       '═'),
    ('\u0393\u00fb\u00c2',       '─'),
]
for bad, good in fixes:
    c = c.replace(bad, good)

# Also replace the specific button texts that are garbled
import re
c = re.sub(r'>[\u2261]\u0192[\u00c4][\u00d6] MIC<', '>🎙 MIC<', c)
c = re.sub(r'>[\u2261]\u0192[\u00f6][\u00a4] FORCE CYCLE<', '>🔄 FORCE CYCLE<', c)
c = re.sub(r'>[\u2261]\u0192[\u00ba][^\s]+ CLEAR<', '>🗑 CLEAR<', c)
c = re.sub(r'>[\u2261]\u0192[\u00f9][^\s]+ FLUSH BB<', '>🧹 FLUSH BB<', c)

# Fix the tier arrow JS: arr.textContent='...'
c = c.replace("arr.textContent='\u0393\u00fb\u009b'", "arr.textContent='▼'")
c = c.replace("arr.textContent='\u039b\u00fb\u009b'", "arr.textContent='▼'")

# Fix the inject button
c = c.replace('\u0393\u00dc\u00ad INJECT', '⚡ INJECT')
c = c.replace('\u0393\u00dc\u00ad SEND', '⚡ SEND')

# Add TTS support to fire() function - insert after the full response is received
# Find where we addActivity and insert tts speak call
TTS_INJECT = '''  if(full&&typeof addActivity==='function')addActivity('NEXUS',new Date().toISOString().slice(0,19),full);
  // TTS: speak response if enabled
  if(window._ttsOn&&full&&'speechSynthesis'in window){
    window.speechSynthesis.cancel();
    const utt=new SpeechSynthesisUtterance(full.slice(0,500));
    utt.rate=1.1;utt.pitch=0.9;utt.volume=1;
    const voices=window.speechSynthesis.getVoices();
    const pref=voices.find(v=>v.name.includes('Google')&&v.lang.startsWith('en'))||voices.find(v=>v.lang.startsWith('en'));
    if(pref)utt.voice=pref;
    window.speechSynthesis.speak(utt);
  }'''

old_activity = "  if(full&&typeof addActivity==='function')addActivity('NEXUS',new Date().toISOString().slice(0,19),full);"
if old_activity in c:
    c = c.replace(old_activity, TTS_INJECT)
    print("TTS injected into fire()")
else:
    print("WARNING: addActivity line not found, TTS not injected")

# Add TTS toggle button and global TTS state if not present
if '_ttsOn' not in c:
    # Add TTS state variable near other globals
    c = c.replace('let _agentMode=false,_abortCtrl=null;',
                  'let _agentMode=false,_abortCtrl=null;\nwindow._ttsOn=false;')
    print("Added _ttsOn global")

# Add TTS button to btn-row if not there
if 'tts-btn' not in c:
    c = c.replace(
        '<button class="btn btn-mic" id="mic-btn" onclick="toggleMic()">🎙 MIC</button>',
        '<button class="btn btn-mic" id="mic-btn" onclick="toggleMic()">🎙 MIC</button>\n      <button class="btn btn-sec" id="tts-btn" onclick="toggleTTS()" title="Toggle AI voice output">🔊 TTS</button>'
    )
    print("Added TTS button")

# Add toggleTTS function if not there  
if 'function toggleTTS' not in c:
    TTS_FN = '''
// TTS TOGGLE
function toggleTTS(){
  window._ttsOn=!window._ttsOn;
  const btn=document.getElementById('tts-btn');
  if(btn){btn.textContent=window._ttsOn?'🔊 TTS ON':'🔊 TTS';
          btn.style.borderColor=window._ttsOn?'var(--c)':'';
          btn.style.color=window._ttsOn?'var(--c)':'';}
  if(!window._ttsOn)window.speechSynthesis.cancel();
  toast(window._ttsOn?'🔊 AI will speak responses':'🔇 TTS off');
}
'''
    # Insert before toggleMic
    c = c.replace('function toggleMic(){', TTS_FN + 'function toggleMic(){')
    print("Added toggleTTS function")

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
print("All fixes applied.")
