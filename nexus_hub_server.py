"""
NEXUS HUB SERVER — Permanent disk-read API on :7702
Serves nexus_blackboard.json + nexus_memory.json directly from disk.
Never loses connection — reads files fresh on each request.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
import json, os, uvicorn

app = FastAPI(title="Nexus Hub Server", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ROOT = os.path.dirname(os.path.abspath(__file__))
BLACKBOARD = os.path.join(ROOT, "nexus_blackboard.json")
MEMORY     = os.path.join(ROOT, "nexus_memory.json")
TOPOLOGY   = os.path.join(ROOT, "nexus_topology.json")

def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

@app.get("/")
def root():
    return {"ok": True, "service": "nexus-hub-server", "port": 7702}

@app.get("/health")
def health():
    return {"ok": True, "status": "online"}

@app.get("/blackboard")
def blackboard():
    data = read_json(BLACKBOARD, {})
    return JSONResponse(content=data)

@app.get("/memory")
def memory():
    data = read_json(MEMORY, [])
    return JSONResponse(content=data)

@app.get("/topology")
def topology():
    data = read_json(TOPOLOGY, {})
    return JSONResponse(content=data)

@app.get("/status")
def status():
    bb   = read_json(BLACKBOARD, {})
    mem  = read_json(MEMORY, [])
    return {
        "ok": True,
        "blackboard_entries": len(bb.get("outputs", bb)) if isinstance(bb, dict) else len(bb),
        "memory_entries": len(mem) if isinstance(mem, list) else 0,
        "outputs": bb.get("outputs", [])[-20:] if isinstance(bb, dict) else [],
        "last_score": bb.get("last_score"),
        "last_mvp": bb.get("last_mvp"),
    }

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8', errors='replace') if hasattr(sys.stdout, 'reconfigure') else None
    print("[NEXUS HUB SERVER] Starting on :7702 (permanent disk-read)")
    uvicorn.run(app, host="0.0.0.0", port=7702, log_level="warning")
