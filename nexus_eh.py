"""
â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
â•‘  NEXUS EH â€” LOCAL COMMAND INJECTION API                   â•‘
â•‘  Port: 7701  â€¢  127.0.0.1 ONLY  â€¢  No auth needed locally      â•‘
â•‘                                                                  â•‘
â•‘  Endpoints:                                                      â•‘
â•‘    GET  /              â€” status dashboard                        â•‘
â•‘    GET  /status        â€” live blackboard snapshot               â•‘
â•‘    GET  /memory        â€” full persistent memory                 â•‘
â•‘    GET  /log           â€” last 50 swarm log lines                â•‘
â•‘    POST /inject        â€” push task into swarm queue             â•‘
â•‘    POST /direct        â€” run ONE-SHOT ollama inference          â•‘
â•‘    POST /flush         â€” clear blackboard + memory              â•‘
â•‘    POST /cycle         â€” force immediate swarm cycle            â•‘
â•‘    GET  /agents        â€” agent roster + live weights            â•‘
â•‘    POST /kill          â€” kill current cycle, skip to next       â•‘
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

Usage:
  python nexus_eh.py

Then from anywhere on this machine:
  curl http://127.0.0.1:7701/status
  curl -X POST http://127.0.0.1:7701/inject -d '{"task":"Analyze X"}' -H 'Content-Type: application/json'
  curl http://127.0.0.1:7701/memory
"""

import asyncio
import json
import time
import os
import logging
from pathlib import Path
from datetime import datetime
from http.server import BaseHTTPRequestHandler
import urllib.parse
import httpx
import subprocess

BASE_DIR    = Path(__file__).parent
BLACKBOARD  = BASE_DIR / "nexus_blackboard.json"
MEMORY_FILE = BASE_DIR / "nexus_memory.json"
LOG_FILE    = BASE_DIR / "swarm_active.log"
EH_PORT     = 7701
OLLAMA      = "http://127.0.0.1:11434"

# -- TOKEN LOADING --
def get_eh_token():
    token_file = BASE_DIR / ".eh_token"
    if token_file.exists():
        return token_file.read_text(encoding="utf-8").strip()
    return None

EH_TOKEN = get_eh_token()

log = logging.getLogger("EH")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

# â”€â”€ SECURITY HELPERS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
ALLOWED_IPS = {"127.0.0.1", "::1", "localhost"}
LOCALHOST_ONLY = {"/flush", "/kill"}  # destructive endpoints stay localhost-only

def check_ip_allowed(ip: str, path: str = "/") -> bool:
    """Allow localhost always. Allow LAN (192.168.x.x / 10.x.x.x) for non-destructive endpoints."""
    if ip in ALLOWED_IPS:
        return True
    if path in LOCALHOST_ONLY:
        return False
    # Allow home LAN and Tailscale ranges
    if ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("100."):
        return True
    return False

def sanitize_task(task: str) -> tuple:
    """Basic injection guard â€” returns (clean_task, error_or_None)."""
    if not task:
        return "", "Empty task"
    if len(task) > 2000:
        return "", "Task too long (max 2000 chars)"
    # Block obvious injection attempts
    blocked = ["__import__", "eval(", "exec(", "os.system", "subprocess"]
    for b in blocked:
        if b in task.lower():
            return "", f"Blocked pattern: {b}"
    return task.strip(), None

# â”€â”€ HELPERS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def read_json(path: Path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def write_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def read_log(n: int = 50) -> list:
    if not LOG_FILE.exists():
        return ["[No log file yet â€” start nexus_swarm_loop.py first]"]
    lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        return []
    return lines[max(0, len(lines)-n):]

# --- IN-MEMORY HOT PATH ---
TASK_QUEUE = []  # Hot queue for sub-millisecond response
BB_CACHE   = {}  # In-memory blackboard snapshot

def load_initial_bb():
    global BB_CACHE, TASK_QUEUE
    BB_CACHE = read_json(BLACKBOARD)
    # Ensure task_queue exists and is a list
    raw_queue = BB_CACHE.get("task_queue", [])
    if not isinstance(raw_queue, list):
        raw_queue = []
    
    # Convert old string-only queue to prioritized dicts if needed
    TASK_QUEUE = []
    for i, t in enumerate(raw_queue):
        if isinstance(t, str):
            TASK_QUEUE.append({"task": t, "priority": 1, "id": f"task_{int(time.time())}_{i}"})
        else:
            TASK_QUEUE.append(t)

load_initial_bb()

def sync_bb_to_disk():
    """Asynchronous/Background persistence."""
    BB_CACHE["task_queue"] = TASK_QUEUE
    write_json(BLACKBOARD, BB_CACHE)

def inject_task(task: str, priority: int = 1) -> dict:
    """Prioritized queue injection."""
    entry = {
        "task": task,
        "priority": priority,
        "id": f"task_{int(time.time()*1000)}",
        "timestamp": datetime.now().isoformat()
    }
    
    if priority > 5: # High priority inserts at the front
        TASK_QUEUE.insert(0, entry)
    else:
        TASK_QUEUE.append(entry)
    
    # Prune queue if it gets too long
    if len(TASK_QUEUE) > 100:
        TASK_QUEUE.pop(-1)
        
    sync_bb_to_disk()
    return {"ok": True, "queued": task, "priority": priority, "queue_depth": len(TASK_QUEUE)}

def force_cycle(task: str = "") -> dict:
    if task:
        inject_task(task, priority=10) # Auto-priority for forced cycles
    else:
        inject_task("__FORCE_CYCLE__", priority=10)
    return {"ok": True, "message": "High-priority cycle injected into hot-path"}

def flush_all() -> dict:
    write_json(BLACKBOARD, {"outputs": [], "task_queue": [], "status": "FLUSHED"})
    write_json(MEMORY_FILE, [])
    return {"ok": True, "message": "Blackboard and memory cleared"}

async def direct_inference(model: str, prompt: str) -> str:
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(f"{OLLAMA}/api/chat", json={
                "model": model,
                "stream": False,
                "messages": [{"role": "user", "content": prompt}],
                "options": {"temperature": 0.7, "num_predict": 512}
            }, timeout=60.0)
            data = r.json()
            return data.get("message", {}).get("content", "[NO OUTPUT]")
        except Exception as e:
            log.warning(f"Ollama error: {e}")
            return f"[ERROR: {e}]"

# â”€â”€ MOBILE DASHBOARD â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def build_mobile_html() -> str:
    bb     = read_json(BLACKBOARD)
    status = bb.get("status", "UNKNOWN")
    task   = bb.get("task", "[none]")
    score  = bb.get("last_score", "â€”")
    mvp    = bb.get("last_mvp", "â€”")
    cycle  = bb.get("cycle_id", "â€”")
    logs   = read_log(15)
    log_html = "".join(f'<div class="ll">{l.replace("<","&lt;")}</div>' for l in logs)
    badge_color = "#00ff41" if status == "RUNNING" else "#ffaa00" if status == "DONE" else "#ff3333"

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="10">
<title>NEXUS Â· Mobile</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#060606;color:#aaccaa;font-family:monospace;font-size:14px;padding:16px;max-width:480px;margin:auto}}
h1{{color:#ff00ff;font-size:16px;letter-spacing:3px;margin-bottom:12px}}
.badge{{display:inline-block;padding:4px 12px;border-radius:4px;font-size:11px;letter-spacing:2px;font-weight:bold;margin-bottom:12px;color:#060606;background:{badge_color}}}
.card{{background:#0a0a0a;border:1px solid #0f2d0f;border-radius:6px;padding:12px;margin-bottom:12px}}
.card h2{{color:#00ccff;font-size:11px;letter-spacing:2px;margin-bottom:8px}}
.row{{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #0a1a0a;font-size:13px}}
.lbl{{color:#2a4a2a}}.val{{color:#fff;text-align:right;max-width:65%}}
textarea{{width:100%;background:#050505;border:1px solid #0f2d0f;color:#00ff41;font-family:monospace;font-size:13px;padding:8px;border-radius:4px;resize:vertical;min-height:60px}}
button{{width:100%;background:none;border:2px solid #00ff41;color:#00ff41;font-family:monospace;font-size:14px;padding:10px;border-radius:4px;margin-top:8px;cursor:pointer;letter-spacing:1px}}
button:active{{background:#00ff4120}}
.ll{{font-size:10px;color:#2a5a2a;padding:1px 0;border-bottom:1px solid #0a1a0a}}
</style></head><body>
<h1>⚡ NEXUS</h1>
<div class="badge">{status}</div>

<div class="card">
  <h2>â–¸ SWARM STATUS</h2>
  <div class="row"><span class="lbl">CYCLE</span><span class="val">{cycle}</span></div>
  <div class="row"><span class="lbl">SCORE</span><span class="val" style="color:#ffaa00">{score}</span></div>
  <div class="row"><span class="lbl">MVP</span><span class="val" style="color:#ff00ff">{mvp}</span></div>
  <div class="row"><span class="lbl">TASK</span><span class="val">{str(task)[:60]}</span></div>
</div>

<div class="card">
  <h2>â–¸ INJECT TASK</h2>
  <textarea id="t" placeholder="Enter task for the swarm..."></textarea>
  <button onclick="inject()">âš¡ INJECT</button>
</div>

<div class="card">
  <h2>â–¸ LIVE LOG</h2>
  <div style="max-height:200px;overflow-y:auto">{log_html}</div>
</div>

<script>
async function inject(){{
  const t=document.getElementById('t').value.trim();
  if(!t)return;
  const r=await fetch('/inject',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{task:t}})}});
  const d=await r.json();
  alert(d.ok?'Injected! Queue: '+d.queue_depth:d.error);
  document.getElementById('t').value='';
}}
</script>
</body></html>"""

# â”€â”€ HTML DASHBOARD â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def build_dashboard_html() -> str:
    bb  = read_json(BLACKBOARD)
    mem = read_json(MEMORY_FILE) if MEMORY_FILE.exists() else []
    if isinstance(mem, dict):
        mem = []
    last_logs = read_log(30)

    status   = bb.get("status", "UNKNOWN")
    task     = bb.get("task", "[none]")
    score    = bb.get("last_score", "â€”")
    mvp      = bb.get("last_mvp", "â€”")
    lesson   = bb.get("last_lesson", "[none]")
    cycle_id = bb.get("cycle_id", "â€”")
    outputs  = bb.get("outputs", [])

    subset = outputs[max(0, len(outputs)-8):]
    agents_html = "".join(
        f'<div class="agent"><span class="ag-name">{o["agent"]}</span>'
        f'<span class="ag-out">{o["text"][:200].replace("<","&lt;")}â€¦</span></div>'
        for o in subset
    )
    mem_html = "".join(
        f'<div class="mem-entry"><span class="mem-score">{e.get("score","?"):.2f}</span>'
        f'<span class="mem-mvp">mvp={e.get("mvp","?")}</span>'
        f'<span class="mem-lesson">{str(e.get("lesson",""))[:120]}</span></div>'
        for e in (mem[-6:] if isinstance(mem, list) else [])
    )
    log_html = "".join(f'<div class="log-line">{l.replace("<","&lt;")}</div>' for l in last_logs)

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta http-equiv="refresh" content="8">
<title>NEXUS EH</title>
<link rel="stylesheet" href="jetbrains-mono.css">
<style>
:root{{--g:#00ff41;--g2:#00cc33;--bg:#060606;--p:#0a0a0a;--bd:#0f2d0f;--red:#ff3333;--yel:#ffaa00;--cya:#00ccff;--mag:#ff00ff;--dim:#2a4a2a;--wht:#aaccaa}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--g);font-family:'JetBrains Mono',monospace;font-size:11px;padding:16px}}
h1{{font-size:14px;letter-spacing:4px;color:var(--mag);margin-bottom:12px}}
h2{{font-size:10px;letter-spacing:3px;color:var(--cya);margin:14px 0 6px;border-bottom:1px solid var(--bd);padding-bottom:3px}}
.badge{{display:inline-block;padding:2px 10px;border:1px solid;border-radius:1px;font-size:9px;letter-spacing:2px;margin-right:6px}}
.badge.g{{border-color:var(--g);color:var(--g)}}.badge.r{{border-color:var(--red);color:var(--red)}}.badge.y{{border-color:var(--yel);color:var(--yel)}}
.row{{display:flex;gap:8px;margin-bottom:4px;font-size:10px}}
.lbl{{color:var(--dim);min-width:90px}}.val{{color:var(--wht)}}
.agent{{padding:4px 0;border-bottom:1px solid #0a1a0a}}
.ag-name{{color:var(--g2);min-width:100px;display:inline-block;letter-spacing:1px}}
.ag-out{{color:#668866;font-size:9px}}
.mem-entry{{padding:3px 0;border-bottom:1px solid #0a1a0a;font-size:9px}}
.mem-score{{color:var(--yel);margin-right:8px}}.mem-mvp{{color:var(--cya);margin-right:8px}}.mem-lesson{{color:#668866}}
.log-line{{font-size:8px;color:#2a5a2a;padding:1px 0}}
form{{margin:4px 0;display:flex;gap:6px;flex-wrap:wrap}}
input[type=text]{{background:#050505;border:1px solid var(--bd);color:var(--g);font-family:inherit;font-size:10px;padding:4px 8px;flex:1;min-width:200px;outline:none}}
button{{background:none;border:1px solid var(--g);color:var(--g);font-family:inherit;font-size:9px;padding:4px 12px;cursor:pointer;letter-spacing:1px}}
button:hover{{box-shadow:0 0 10px var(--g)}}
button.r{{border-color:var(--red);color:var(--red)}}button.r:hover{{box-shadow:0 0 10px var(--red)}}
button.c{{border-color:var(--cya);color:var(--cya)}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
@media(max-width:700px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body>
<h1>⚡ NEXUS EH // 127.0.0.1:7701</h1>

<div style="margin-bottom:10px">
  <span class="badge {'g' if status == 'RUNNING' else 'y' if status == 'DONE' else 'r'}">{status}</span>
  <span class="badge g">OFFLINE Â· NO API</span>
  <span class="badge g">AUTO-REFRESH 8s</span>
</div>

<div class="grid">
<div>
<h2>â–¸ SWARM STATUS</h2>
<div class="row"><span class="lbl">CYCLE</span><span class="val">{cycle_id}</span></div>
<div class="row"><span class="lbl">TASK</span><span class="val">{task[:80]}</span></div>
<div class="row"><span class="lbl">LAST SCORE</span><span class="val" style="color:var(--yel)">{score}</span></div>
<div class="row"><span class="lbl">MVP AGENT</span><span class="val" style="color:var(--mag)">{mvp}</span></div>
<div class="row"><span class="lbl">LESSON</span><span class="val">{str(lesson)[:100]}</span></div>

<h2>â–¸ INJECT TASK</h2>
<form method="POST" action="/inject" onsubmit="return submitInject(event)">
  <input type="text" id="inject-task" placeholder="Enter task to inject into swarm queue...">
  <button type="button" onclick="submitInject()">âš¡ INJECT</button>
  <button type="button" onclick="forceNow()" class="c">â–¶ FORCE NOW</button>
</form>

<h2>â–¸ DIRECT INFERENCE</h2>
<form onsubmit="return directInfer(event)">
  <input type="text" id="d-model" placeholder="model (e.g. nexus-prime:latest)" style="max-width:200px">
  <input type="text" id="d-prompt" placeholder="prompt...">
  <button type="button" onclick="directInfer()">ðŸ§  RUN</button>
</form>
<div id="direct-result" style="margin-top:6px;font-size:9px;color:#668866;max-height:150px;overflow-y:auto"></div>

<h2>â–¸ DANGER ZONE</h2>
<form>
  <button type="button" class="r" onclick="if(confirm('Flush ALL memory?'))fetch('/flush',{{method:'POST'}}).then(()=>location.reload())">â˜  FLUSH ALL</button>
</form>
</div>

<div>
<h2>â–¸ RECENT AGENT OUTPUTS</h2>
<div style="max-height:200px;overflow-y:auto">{agents_html or '<div style="color:var(--dim)">No outputs yet â€” start nexus_swarm_loop.py</div>'}</div>

<h2>â–¸ MEMORY ({len(mem) if isinstance(mem, list) else 0} entries)</h2>
<div style="max-height:140px;overflow-y:auto">{mem_html or '<div style="color:var(--dim)">No memory yet</div>'}</div>

<h2>â–¸ LIVE LOG (last 30 lines)</h2>
<div style="max-height:200px;overflow-y:auto;border:1px solid var(--bd);padding:4px">{log_html}</div>
</div>
</div>

<script>
async function submitInject() {{
  const task = document.getElementById('inject-task').value.trim();
  if(!task) return;
  const r = await fetch('/inject', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{task}})}});
  const d = await r.json();
  alert('Queued: ' + d.queued + '\\nQueue depth: ' + d.queue_depth);
  location.reload();
}}
async function forceNow() {{
  const task = document.getElementById('inject-task').value.trim();
  const r = await fetch('/cycle', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{task}})}});
  const d = await r.json();
  alert(d.message);
}}
async function directInfer() {{
  const model = document.getElementById('d-model').value.trim() || 'nexus-prime:latest';
  const prompt = document.getElementById('d-prompt').value.trim();
  if(!prompt) return;
  document.getElementById('direct-result').textContent = 'â³ Thinking...';
  const r = await fetch('/direct', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{model, prompt}})}});
  const d = await r.json();
  document.getElementById('direct-result').textContent = d.result || d.error;
}}
</script>
</body></html>"""

# â”€â”€ ASYNC HTTP SERVER â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        raw = await asyncio.wait_for(reader.read(8192), timeout=10.0)
        text = raw.decode("utf-8", errors="replace")
        lines = text.split("\r\n")
        first = lines[0].split() if lines else []
        if len(first) < 2:
            writer.close(); return

        method = first[0]
        path   = first[1].split("?")[0]

        # ── AUTH & IP CHECK ─────────────────────────────────────────────────────
        peer = writer.get_extra_info('peername', ('0.0.0.0', 0))
        client_ip = peer[0] if peer else '0.0.0.0'
        
        # Parse headers
        headers_dict = {}
        for h_line in text.split('\r\n')[1:]:
            if ': ' in h_line:
                k, v = h_line.split(': ', 1)
                headers_dict[k.lower()] = v.strip()
        
        auth_token = headers_dict.get('x-eh-token')
        
        is_health = path == '/health'
        is_authed = (auth_token == EH_TOKEN) if (auth_token and EH_TOKEN) else False
        
        # Security Logic: 
        # 1. Health is always public.
        # 2. If Token matches, it's allowed (trusted app).
        # 3. If NO token, strictly only allow Localhost/LAN for non-destructive.
        if not is_health and not is_authed:
            if not check_ip_allowed(client_ip, path):
                 deny = b'HTTP/1.1 401 Unauthorized\r\nContent-Type: application/json\r\n\r\n{"error":"EH Token Required for remote access"}'
                 writer.write(deny); await writer.drain(); writer.close(); return
        # ──────────────────────────────────────────────────────────────────────────
        # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        body = {}
        if method == "POST":
            body_start = text.find("\r\n\r\n")
            if body_start != -1:
                raw_body = text[body_start+4:]
                try:
                    body = json.loads(raw_body)
                except Exception:
                    body = dict(urllib.parse.parse_qsl(raw_body))

        if method == "OPTIONS":
            writer.write(b"HTTP/1.1 200 OK\r\n"
                         b"Access-Control-Allow-Origin: *\r\n"
                         b"Access-Control-Allow-Methods: POST, GET, OPTIONS\r\n"
                         b"Access-Control-Allow-Headers: Content-Type, x-eh-token\r\n"
                         b"Connection: close\r\n\r\n")
            await writer.drain(); writer.close(); return

        # Route
        status = 200
        content_type = "text/html; charset=utf-8"
        response_body = ""

        if path == "/" or path == "/dashboard":
            response_body = build_dashboard_html()

        elif path == "/mobile":
            response_body = build_mobile_html()

        elif path == "/status":
            content_type = "application/json"
            bb = read_json(BLACKBOARD)
            response_body = json.dumps(bb, indent=2, ensure_ascii=False)

        elif path == "/memory":
            content_type = "application/json"
            mem = read_json(MEMORY_FILE) if MEMORY_FILE.exists() else []
            response_body = json.dumps(mem, indent=2, ensure_ascii=False)

        elif path == "/log":
            content_type = "text/plain; charset=utf-8"
            response_body = "\n".join(read_log(100))

        elif path == "/agents":
            content_type = "application/json"
            bb = read_json(BLACKBOARD)
            response_body = json.dumps({
                "outputs": bb.get("outputs", [])[-6:],
                "cycle": bb.get("cycle_id"),
                "status": bb.get("status"),
                "times": bb.get("agent_times", {}),
            }, indent=2)

        elif path == "/inject" and method == "POST":
            content_type = "application/json"
            raw_task = body.get("task", "").strip()
            task, err = sanitize_task(raw_task)  # â† security: blocks injection attempts
            if err:
                status = 400
                response_body = json.dumps({"ok": False, "error": err})
            elif task:
                result = inject_task(task)
                response_body = json.dumps(result)
                log.info(f"[EH] Injected task: {task[:80]}")
            else:
                status = 400
                response_body = json.dumps({"ok": False, "error": "No task provided"})

        elif path == "/cycle" and method == "POST":
            content_type = "application/json"
            task = body.get("task", "").strip()
            result = force_cycle(task)
            response_body = json.dumps(result)
            log.info(f"[EH] Force cycle requested")

        elif path == "/flush" and method == "POST":
            content_type = "application/json"
            result = flush_all()
            response_body = json.dumps(result)
            log.info(f"[EH] FLUSH ALL executed")

        elif path == "/direct" and method == "POST":
            content_type = "application/json"
            model  = body.get("model", "nexus-prime:latest")
            prompt = body.get("prompt", "").strip()
            if prompt:
                result = await direct_inference(model, prompt)
                response_body = json.dumps({"ok": True, "model": model, "result": result})
            else:
                status = 400
                response_body = json.dumps({"ok": False, "error": "No prompt"})

        # ── HUMAN APPROVAL GATE ENDPOINTS ────────────────────────────────────
        elif path == "/pending" and method == "GET":
            content_type = "application/json"
            pf = BASE_DIR / "nexus_pending_approvals.json"
            pending = []
            if pf.exists():
                try:
                    pending = json.loads(pf.read_text(encoding="utf-8"))
                except Exception:
                    pending = []
            waiting = [p for p in pending if p.get("status") == "PENDING"]
            response_body = json.dumps({"ok": True, "pending_count": len(waiting), "items": waiting})
            log.info(f"[EH] /pending → {len(waiting)} items awaiting approval")

        elif path == "/approve" and method == "POST":
            content_type = "application/json"
            bb = read_json(BLACKBOARD)
            if bb.get("membrane_lock"):
                status = 403
                response_body = json.dumps({"ok": False, "error": "MEMBRANE LOCK: " + str(bb.get("membrane_reason"))})
            else:
                entry_id = body.get("id", "").strip()
                pf = BASE_DIR / "nexus_pending_approvals.json"
                if not entry_id:
                    status = 400
                    response_body = json.dumps({"ok": False, "error": "No id provided"})
                elif not pf.exists():
                    status = 404
                    response_body = json.dumps({"ok": False, "error": "No pending approvals file"})
                else:
                    pending = json.loads(pf.read_text(encoding="utf-8"))
                    matched = next((p for p in pending if p["id"] == entry_id), None)
                    if not matched:
                        status = 404
                        response_body = json.dumps({"ok": False, "error": f"ID {entry_id} not found"})
                    else:
                        matched["status"] = "APPROVED"
                        matched["approved_at"] = datetime.now().isoformat()
                        pf.write_text(json.dumps(pending, indent=2, ensure_ascii=False), encoding="utf-8")
                        
                        # Trigger execution if it's code
                        if matched.get("type") == "code_execution":
                            async def run_one_bg(code):
                                try:
                                    await asyncio.to_thread(subprocess.run, ["python", "-c", code], timeout=10)
                                except Exception as e:
                                    log.warning(f"Individual Approval Error: {e}")
                            asyncio.create_task(run_one_bg(matched["code"]))
                        
                        response_body = json.dumps({"ok": True, "id": entry_id, "approved": True})
                        log.info(f"[EH] APPROVED: {entry_id}")

        elif path == "/approve_all" and method == "POST":
            content_type = "application/json"
            pf = BASE_DIR / "nexus_pending_approvals.json"
            if not pf.exists():
                response_body = json.dumps({"ok": True, "approved_count": 0, "message": "No pending file"})
            else:
                try:
                    pending = json.loads(pf.read_text(encoding="utf-8"))
                    waiting = [p for p in pending if p.get("status") == "PENDING"]
                    count = len(waiting)
                    
                    # 1. Update status in-memory immediately
                    for item in waiting:
                        item["status"] = "APPROVED"
                        item["approved_at"] = datetime.now().isoformat()
                    
                    # 2. Save the file immediately so UI shows them as approved/processed
                    pf.write_text(json.dumps(pending, indent=2, ensure_ascii=False), encoding="utf-8")
                    
                    # 3. Trigger execution in background to avoid blocking the event loop
                    async def run_approvals_bg(items_to_run):
                        for item in items_to_run:
                            if item.get("type") == "code_execution":
                                try:
                                    # Use asyncio.create_subprocess_exec or run in thread pool
                                    # For simplicity and reliability in this specific stack, we'll use a thread-safe approach
                                    # but yield control between each run
                                    await asyncio.to_thread(subprocess.run, ["python", "-c", item["code"]], timeout=10)
                                    await asyncio.sleep(0.01) # Yield to other tasks
                                except Exception as e:
                                    log.warning(f"BG Approval Error: {e}")
                    
                    asyncio.create_task(run_approvals_bg(waiting))
                    
                    response_body = json.dumps({"ok": True, "approved_count": count, "message": "Mass approval triggered in background"})
                    log.info(f"[EH] MASS APPROVAL STARTED: {count} items")
                except Exception as e:
                    status = 500
                    response_body = json.dumps({"ok": False, "error": str(e)})

        elif path == "/clear_blocked" and method == "POST":
            content_type = "application/json"
            pf = BASE_DIR / "nexus_pending_approvals.json"
            if pf.exists():
                pf.write_text("[]", encoding="utf-8")
            response_body = json.dumps({"ok": True, "message": "Blocked queue purged"})
            log.info(f"[EH] BLOCKED QUEUE CLEARED")

        elif path == "/reject" and method == "POST":
            content_type = "application/json"
            entry_id = body.get("id", "").strip()
            pf = BASE_DIR / "nexus_pending_approvals.json"
            if not entry_id:
                status = 400
                response_body = json.dumps({"ok": False, "error": "No id provided"})
            elif not pf.exists():
                status = 404
                response_body = json.dumps({"ok": False, "error": "No pending approvals file"})
            else:
                pending = json.loads(pf.read_text(encoding="utf-8"))
                matched = next((p for p in pending if p["id"] == entry_id), None)
                if not matched:
                    status = 404
                    response_body = json.dumps({"ok": False, "error": f"ID {entry_id} not found"})
                else:
                    matched["status"] = "REJECTED"
                    matched["rejected_at"] = datetime.now().isoformat()
                    pf.write_text(json.dumps(pending, indent=2, ensure_ascii=False), encoding="utf-8")
                    response_body = json.dumps({"ok": True, "id": entry_id, "rejected": True})
                    log.info(f"[EH] REJECTED: {entry_id}")

        else:
            status = 404
            content_type = "application/json"
            response_body = json.dumps({"error": f"Unknown route: {method} {path}"})

        body_bytes = response_body.encode("utf-8")
        headers = (
            f"HTTP/1.1 {status} OK\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body_bytes)}\r\n"
            f"Access-Control-Allow-Origin: *\r\n"
            f"Connection: close\r\n\r\n"
        )
        writer.write(headers.encode() + body_bytes)
        await writer.drain()
    except Exception as e:
        log.warning(f"[EH] Request error: {e}")
    finally:
        writer.close()

async def main():
    server = await asyncio.start_server(handle, "0.0.0.0", EH_PORT)
    log.info(f"âš¡ NEXUS EH running on http://127.0.0.1:{EH_PORT}")
    log.info(f"   Phone/LAN:  http://192.168.0.188:{EH_PORT}/mobile")
    log.info(f"   Dashboard:  http://127.0.0.1:{EH_PORT}/")
    log.info(f"   Status:     http://127.0.0.1:{EH_PORT}/status")
    log.info(f"   Memory:     http://127.0.0.1:{EH_PORT}/memory")
    log.info(f"   Log:        http://127.0.0.1:{EH_PORT}/log")
    log.info(f"   Inject:     POST http://127.0.0.1:{EH_PORT}/inject")
    log.info(f"   Direct LLM: POST http://127.0.0.1:{EH_PORT}/direct")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())

