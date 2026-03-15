"""
╔══════════════════════════════════════════════════════════════════╗
║  NEXUS BACKDOOR — LOCAL COMMAND INJECTION API                   ║
║  Port: 7701  •  127.0.0.1 ONLY  •  No auth needed locally      ║
║                                                                  ║
║  Endpoints:                                                      ║
║    GET  /              — status dashboard                        ║
║    GET  /status        — live blackboard snapshot               ║
║    GET  /memory        — full persistent memory                 ║
║    GET  /log           — last 50 swarm log lines                ║
║    POST /inject        — push task into swarm queue             ║
║    POST /direct        — run ONE-SHOT ollama inference          ║
║    POST /flush         — clear blackboard + memory              ║
║    POST /cycle         — force immediate swarm cycle            ║
║    GET  /agents        — agent roster + live weights            ║
║    POST /kill          — kill current cycle, skip to next       ║
╚══════════════════════════════════════════════════════════════════╝

Usage:
  python nexus_backdoor.py

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

BASE_DIR    = Path(__file__).parent
BLACKBOARD  = BASE_DIR / "nexus_blackboard.json"
MEMORY_FILE = BASE_DIR / "nexus_memory.json"
LOG_FILE    = BASE_DIR / "swarm_loop.log"
BACKDOOR_PORT = 7701
OLLAMA      = "http://127.0.0.1:11434"

log = logging.getLogger("BACKDOOR")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

# ── SECURITY HELPERS ──────────────────────────────────────────────────────────
ALLOWED_IPS = {"127.0.0.1", "::1", "localhost"}

def check_ip_allowed(ip: str) -> bool:
    """Only allow localhost connections — backdoor is local-only."""
    return ip in ALLOWED_IPS

def sanitize_task(task: str) -> tuple:
    """Basic injection guard — returns (clean_task, error_or_None)."""
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

# ── HELPERS ───────────────────────────────────────────────────────────────────
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
        return ["[No log file yet — start nexus_swarm_loop.py first]"]
    lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-n:]

def inject_task(task: str) -> dict:
    bb = read_json(BLACKBOARD)
    queue = bb.get("task_queue", [])
    queue.append(task)
    bb["task_queue"] = queue
    write_json(BLACKBOARD, bb)
    return {"ok": True, "queued": task, "queue_depth": len(queue)}

def force_cycle(task: str = "") -> dict:
    bb = read_json(BLACKBOARD)
    queue = bb.get("task_queue", [])
    if task:
        queue.insert(0, task)  # front of queue = immediate next
    else:
        queue.insert(0, "__FORCE_CYCLE__")
    bb["task_queue"] = queue
    write_json(BLACKBOARD, bb)
    return {"ok": True, "message": "Cycle will trigger on next interval check"}

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
            return r.json().get("message", {}).get("content", "[NO OUTPUT]")
        except Exception as e:
            return f"[ERROR: {e}]"

# ── HTML DASHBOARD ─────────────────────────────────────────────────────────────
def build_dashboard_html() -> str:
    bb  = read_json(BLACKBOARD)
    mem = read_json(MEMORY_FILE) if MEMORY_FILE.exists() else []
    if isinstance(mem, dict):
        mem = []
    last_logs = read_log(30)

    status   = bb.get("status", "UNKNOWN")
    task     = bb.get("task", "[none]")
    score    = bb.get("last_score", "—")
    mvp      = bb.get("last_mvp", "—")
    lesson   = bb.get("last_lesson", "[none]")
    cycle_id = bb.get("cycle_id", "—")
    outputs  = bb.get("outputs", [])

    agents_html = "".join(
        f'<div class="agent"><span class="ag-name">{o["agent"]}</span>'
        f'<span class="ag-out">{o["text"][:200].replace("<","&lt;")}…</span></div>'
        for o in outputs[-8:]
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
<title>NEXUS BACKDOOR</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
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
<h1>⚡ NEXUS BACKDOOR // 127.0.0.1:7701</h1>

<div style="margin-bottom:10px">
  <span class="badge {'g' if status == 'RUNNING' else 'y' if status == 'DONE' else 'r'}">{status}</span>
  <span class="badge g">OFFLINE · NO API</span>
  <span class="badge g">AUTO-REFRESH 8s</span>
</div>

<div class="grid">
<div>
<h2>▸ SWARM STATUS</h2>
<div class="row"><span class="lbl">CYCLE</span><span class="val">{cycle_id}</span></div>
<div class="row"><span class="lbl">TASK</span><span class="val">{task[:80]}</span></div>
<div class="row"><span class="lbl">LAST SCORE</span><span class="val" style="color:var(--yel)">{score}</span></div>
<div class="row"><span class="lbl">MVP AGENT</span><span class="val" style="color:var(--mag)">{mvp}</span></div>
<div class="row"><span class="lbl">LESSON</span><span class="val">{str(lesson)[:100]}</span></div>

<h2>▸ INJECT TASK</h2>
<form method="POST" action="/inject" onsubmit="return submitInject(event)">
  <input type="text" id="inject-task" placeholder="Enter task to inject into swarm queue...">
  <button type="button" onclick="submitInject()">⚡ INJECT</button>
  <button type="button" onclick="forceNow()" class="c">▶ FORCE NOW</button>
</form>

<h2>▸ DIRECT INFERENCE</h2>
<form onsubmit="return directInfer(event)">
  <input type="text" id="d-model" placeholder="model (e.g. nexus-prime:latest)" style="max-width:200px">
  <input type="text" id="d-prompt" placeholder="prompt...">
  <button type="button" onclick="directInfer()">🧠 RUN</button>
</form>
<div id="direct-result" style="margin-top:6px;font-size:9px;color:#668866;max-height:150px;overflow-y:auto"></div>

<h2>▸ DANGER ZONE</h2>
<form>
  <button type="button" class="r" onclick="if(confirm('Flush ALL memory?'))fetch('/flush',{{method:'POST'}}).then(()=>location.reload())">☠ FLUSH ALL</button>
</form>
</div>

<div>
<h2>▸ RECENT AGENT OUTPUTS</h2>
<div style="max-height:200px;overflow-y:auto">{agents_html or '<div style="color:var(--dim)">No outputs yet — start nexus_swarm_loop.py</div>'}</div>

<h2>▸ MEMORY ({len(mem) if isinstance(mem, list) else 0} entries)</h2>
<div style="max-height:140px;overflow-y:auto">{mem_html or '<div style="color:var(--dim)">No memory yet</div>'}</div>

<h2>▸ LIVE LOG (last 30 lines)</h2>
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
  document.getElementById('direct-result').textContent = '⏳ Thinking...';
  const r = await fetch('/direct', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{model, prompt}})}});
  const d = await r.json();
  document.getElementById('direct-result').textContent = d.result || d.error;
}}
</script>
</body></html>"""

# ── ASYNC HTTP SERVER ──────────────────────────────────────────────────────────
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

        # ── IP ALLOWLIST CHECK ────────────────────────────────────────────────────
        peer = writer.get_extra_info('peername', ('0.0.0.0', 0))
        client_ip = peer[0] if peer else '0.0.0.0'
        if path != '/health' and not check_ip_allowed(client_ip):
            deny = b'HTTP/1.1 403 Forbidden\r\nContent-Type: application/json\r\n\r\n{"error":"IP not allowed"}'
            writer.write(deny); await writer.drain(); writer.close(); return
        # ─────────────────────────────────────────────────────────────────────────
        body = {}
        if method == "POST":
            body_start = text.find("\r\n\r\n")
            if body_start != -1:
                raw_body = text[body_start+4:]
                try:
                    body = json.loads(raw_body)
                except Exception:
                    body = dict(urllib.parse.parse_qsl(raw_body))

        # Route
        status = 200
        content_type = "text/html; charset=utf-8"
        response_body = ""

        if path == "/" or path == "/dashboard":
            response_body = build_dashboard_html()

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
            task, err = sanitize_task(raw_task)  # ← security: blocks injection attempts
            if err:
                status = 400
                response_body = json.dumps({"ok": False, "error": err})
            elif task:
                result = inject_task(task)
                response_body = json.dumps(result)
                log.info(f"[BACKDOOR] Injected task: {task[:80]}")
            else:
                status = 400
                response_body = json.dumps({"ok": False, "error": "No task provided"})

        elif path == "/cycle" and method == "POST":
            content_type = "application/json"
            task = body.get("task", "").strip()
            result = force_cycle(task)
            response_body = json.dumps(result)
            log.info(f"[BACKDOOR] Force cycle requested")

        elif path == "/flush" and method == "POST":
            content_type = "application/json"
            result = flush_all()
            response_body = json.dumps(result)
            log.info(f"[BACKDOOR] FLUSH ALL executed")

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
        log.warning(f"[BACKDOOR] Request error: {e}")
    finally:
        writer.close()

async def main():
    server = await asyncio.start_server(handle, "127.0.0.1", BACKDOOR_PORT)
    log.info(f"⚡ NEXUS BACKDOOR running on http://127.0.0.1:{BACKDOOR_PORT}")
    log.info(f"   Dashboard:  http://127.0.0.1:{BACKDOOR_PORT}/")
    log.info(f"   Status:     http://127.0.0.1:{BACKDOOR_PORT}/status")
    log.info(f"   Memory:     http://127.0.0.1:{BACKDOOR_PORT}/memory")
    log.info(f"   Log:        http://127.0.0.1:{BACKDOOR_PORT}/log")
    log.info(f"   Inject:     POST http://127.0.0.1:{BACKDOOR_PORT}/inject")
    log.info(f"   Direct LLM: POST http://127.0.0.1:{BACKDOOR_PORT}/direct")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
