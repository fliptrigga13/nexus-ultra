import re

path = r"C:\Users\fyou1\Desktop\New folder\nexus-ultra\nexus_hub.html"
with open(path, 'r', encoding='utf-8', errors='replace') as f:
    c = f.read()

# Find the old fire() function by a unique pattern and replace the whole block
old_pattern = re.compile(
    r'async function fire\(\)\{[^}]+fetch\([\'\"]/api/inject[\'"].*?\}\s*\}',
    re.DOTALL
)

new_fire = '''let _agentMode=false,_abortCtrl=null;
function showStop(on){const sb=document.getElementById('stop-btn'),fb=document.getElementById('fire-btn');if(sb)sb.style.display=on?'inline-flex':'none';if(fb)fb.style.opacity=on?'.4':'';}
function stopAll(){if(_abortCtrl){_abortCtrl.abort();_abortCtrl=null;}showStop(false);const st=document.getElementById('ai-status');if(st)st.textContent='';toast('\\u2b1b Stopped');}
function toggleAgentMode(){
  _agentMode=!_agentMode;
  const btn=document.getElementById('agent-btn');
  if(btn){btn.classList.toggle('agent-active',_agentMode);btn.textContent=_agentMode?'\\ud83d\\udfe0 AGENT ACTIVE':'\\ud83e\\udd16 AGENT MODE';}
  const ind=document.getElementById('mode-indicator'),ta=document.getElementById('task-in'),ia=document.getElementById('input-area');
  if(_agentMode){if(ind){ind.innerHTML='\\ud83e\\udd16 <b style="color:var(--orange)">AGENT MODE</b> \\u2014 AI runs real commands';ind.style.color='var(--orange)';}if(ta)ta.placeholder='Agent: tell AI what to DO';if(ia){ia.style.borderColor='var(--orange)';ia.style.boxShadow='0 0 12px rgba(255,107,53,.3)';}}
  else{if(ind){ind.innerHTML='\\ud83d\\udcac CHAT MODE \\u2014 AI answers | Click <b style="color:var(--orange)">AGENT MODE</b> to run commands';ind.style.color='#333';}if(ta)ta.placeholder='Chat: ask a question...';if(ia){ia.style.borderColor='';ia.style.boxShadow='';}}
  toast(_agentMode?'\\ud83e\\udd16 AGENT MODE ON':'\\ud83d\\udcac Chat mode');
}
async function fire(){
  const t=document.getElementById('task-in').value.trim();
  if(!t){toast('Enter a message first');return;}
  document.getElementById('task-in').value='';
  addBubble('YOU',t,'','user');scrollChat();
  const model=(document.getElementById('sel-model')||{}).value||'nexus-prime:latest';
  const ctx=(document.getElementById('sel-ctx')||{}).value||'';
  const fmt=(document.getElementById('sel-fmt')||{}).value||'';
  const cogAdd=typeof getCognitivePrompt==='function'?getCognitivePrompt():'';
  const systemAddon=[ctx&&'Domain: '+ctx,fmt&&'Format: '+fmt,cogAdd].filter(Boolean).join(' | ');
  const agDiv=document.createElement('div');agDiv.className='msg agent';
  const hd=document.createElement('div');hd.className='msg-head';hd.textContent='NEXUS \\u00b7 '+new Date().toLocaleTimeString('en-US',{hour12:false});
  const bub=document.createElement('div');bub.className='bubble';bub.textContent='';
  agDiv.appendChild(hd);agDiv.appendChild(bub);document.getElementById('chat-window').appendChild(agDiv);scrollChat();
  const st=document.getElementById('ai-status');if(st)st.textContent='\\u26a1 Generating...';
  _abortCtrl=new AbortController();showStop(true);
  let full='';
  try{
    const r=await fetch('/chat/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:t,model,systemAddon}),signal:_abortCtrl.signal});
    if(!r.ok){bub.textContent='Error: server returned '+r.status+'. Is Ollama running?';showStop(false);if(st)st.textContent='';return;}
    const reader=r.body.getReader();const dec=new TextDecoder();let buf='';
    while(true){
      const{done,value}=await reader.read();if(done)break;
      buf+=dec.decode(value,{stream:true});
      const lines=buf.split('\\n');buf=lines.pop();
      for(const ln of lines){
        if(!ln.startsWith('data:'))continue;
        try{const d=JSON.parse(ln.slice(5));if(d.token){full+=d.token;bub.textContent=full;scrollChat();}if(d.error)bub.textContent='Error: '+d.error;}catch{}
      }
    }
    if(!full)bub.textContent='[No response - is Ollama running? Try: ollama serve]';
  }catch(e){
    if(e.name!=='AbortError')bub.textContent='Error: '+e.message;
    else bub.textContent=(full||'')+'[stopped]';
  }
  showStop(false);_abortCtrl=null;if(st)st.textContent='';
  if(full&&typeof addActivity==='function')addActivity('NEXUS',new Date().toISOString().slice(0,19),full);
}'''

match = old_pattern.search(c)
if match:
    c = c[:match.start()] + new_fire + c[match.end():]
    with open(path, 'w', encoding='utf-8') as f:
        f.write(c)
    print(f"SUCCESS: fire() replaced at pos {match.start()}-{match.end()}")
else:
    # Try a simpler pattern - just find "async function fire(){" block
    start = c.find('async function fire(){')
    if start == -1:
        start = c.find('async function fire(){\n')
    if start == -1:
        print("ERROR: Could not find fire() function. Searching for nearby context...")
        idx = c.find('/api/inject')
        print(f"  Found /api/inject at index: {idx}")
        print(f"  Context: {repr(c[max(0,idx-100):idx+100])}")
    else:
        # Find the closing brace by counting braces
        depth = 0
        end = start
        in_func = False
        for i in range(start, min(start+2000, len(c))):
            if c[i] == '{':
                depth += 1
                in_func = True
            elif c[i] == '}':
                depth -= 1
                if in_func and depth == 0:
                    end = i + 1
                    break
        print(f"Found fire() at {start}-{end}")
        print(f"Current content: {repr(c[start:end][:200])}")
        c = c[:start] + new_fire + c[end:]
        with open(path, 'w', encoding='utf-8') as f:
            f.write(c)
        print("SUCCESS: fire() replaced by brace-counting method")
