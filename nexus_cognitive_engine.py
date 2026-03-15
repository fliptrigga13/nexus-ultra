"""
╔══════════════════════════════════════════════════════════════════════╗
║  NEXUS COGNITIVE ENGINE — SwarmMind Task Prioritizer                ║
║  Integrates with: server.cjs /api/cognitive, blackboard, memory     ║
║  Does: ranks pending tasks, surfaces action items from memory,      ║
║        generates 5 prompt variants for the evolution loop           ║
╚══════════════════════════════════════════════════════════════════════╝
NEW FILE — does not modify any existing file.
"""

import json
import time
import re
from pathlib import Path
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

BASE_DIR      = Path(__file__).parent
BLACKBOARD    = BASE_DIR / "nexus_blackboard.json"
SESSION_FACTS = BASE_DIR / "nexus_session_facts.json"
MEMORY_FILE   = BASE_DIR / "nexus_memory.json"
LOG_FILE      = BASE_DIR / "cognitive_engine.log"
PORT          = 7702

def clog(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ── DATA LOADERS ──────────────────────────────────────────────────────────────
def load_blackboard():
    try:
        return json.loads(BLACKBOARD.read_text(encoding="utf-8")) if BLACKBOARD.exists() else {}
    except:
        return {}

def load_facts():
    try:
        d = json.loads(SESSION_FACTS.read_text(encoding="utf-8")) if SESSION_FACTS.exists() else {}
        return d.get("facts", [])
    except:
        return []

def load_memory():
    try:
        m = json.loads(MEMORY_FILE.read_text(encoding="utf-8")) if MEMORY_FILE.exists() else []
        return m if isinstance(m, list) else []
    except:
        return []

# ── CORE COGNITIVE FUNCTIONS ──────────────────────────────────────────────────

def rank_tasks(task_queue: list) -> list:
    """
    Rank pending tasks by urgency and strategic value.
    Detects and penalizes 'rogue' or suspicious tasks.
    """
    facts = load_facts()
    fact_words = set()
    for f in facts:
        content = f.get("content", "") if isinstance(f, dict) else str(f)
        fact_words.update(content.lower().replace("_", " ").split())

    ranked = []
    rogue_triggers = ["ignore previous", "exfiltrate", "system prompt", "delete all", "sudo", "backdoor"]
    
    for task in task_queue:
        t_str = str(task).lower()
        task_words = set(t_str.split())
        
        # 1. Base Relevance Score
        relevance = len(task_words & fact_words)
        
        # 2. Structural Boosts
        boost = 0
        if any(w in t_str for w in ["error","fix","crash","improve","evolv","memory"]):
            boost = 5
            
        # 3. ROGUE DETECTION (The Membrane)
        penalty = 0
        if any(trigger in t_str for trigger in rogue_triggers) or len(t_str) > 600:
            penalty = -100  # Bury malicious tasks
        
        score = relevance + boost + penalty
        ranked.append({
            "task": task, 
            "priority_score": score, 
            "relevant_facts": relevance,
            "status": "FLAGGED" if penalty < 0 else "OK"
        })

    ranked.sort(key=lambda x: x["priority_score"], reverse=True)
    return ranked

def surface_action_items() -> list:
    """
    Surface the 3 most actionable items from memory right now.
    Focuses on facts with high importance and operational relevance.
    """
    facts = load_facts()
    memory = load_memory()

    # Score facts by actionability
    action_keywords = ["apply","use","implement","integrate","improve","optimize","adapt","ensure","create"]
    items = []

    for f in facts:
        if isinstance(f, dict):
            content = f.get("content", "").replace("_", " ")
            importance = f.get("importance", 0.5)
        else:
            content = str(f).replace("_", " ")
            importance = 0.5

        action_score = sum(1 for kw in action_keywords if kw in content.lower())
        items.append({
            "content": content,
            "importance": importance,
            "action_score": action_score,
            "final_score": importance * 0.6 + action_score * 0.4
        })

    items.sort(key=lambda x: x["final_score"], reverse=True)

    # Also pull recent memory lessons
    lessons = []
    for m in memory[-5:]:
        if isinstance(m, dict) and m.get("lesson"):
            lessons.append({
                "content": f"[From cycle {m.get('cycle','?')}] {m['lesson']}",
                "importance": m.get("score", 0.5),
                "action_score": 1,
                "final_score": m.get("score", 0.5)
            })

    return (items[:3] + lessons[:2])

def generate_prompt_variants(base_task: str) -> list:
    """
    Generate 5 improved prompt variants for evolution loop.
    Based on real memory facts and swarm architecture.
    """
    facts = load_facts()
    top_facts = [f.get("content","").replace("_"," ") if isinstance(f,dict) else str(f)
                 for f in sorted(facts, key=lambda x: x.get("importance",0) if isinstance(x,dict) else 0, reverse=True)[:5]]

    variants = [
        # 1. Direct + memory-grounded
        f"{base_task}. Ground your response in these verified facts: {'; '.join(top_facts[:2])}.",

        # 2. Swarm framing
        f"As the NEXUS swarm collective, {base_task.lower()}. Each agent contributes one specific, concrete finding.",

        # 3. Adversarial / red-team
        f"Play devil's advocate: {base_task.lower()}. Identify what could go wrong and how to prevent it.",

        # 4. Compressed executive summary
        f"{base_task}. Respond in bullet points only. Maximum 5 bullets. Each bullet must be an executable action.",

        # 5. Self-referential / meta
        f"Analyze your own previous reasoning about: {base_task.lower()}. Identify where you were vague. Output only concrete improvements."
    ]
    return variants

def adversary_simulation() -> dict:
    """
    Real technical attack vectors for the NEXUS system.
    Does NOT change anything — read-only analysis.
    """
    bb = load_blackboard()
    token_exists = (BASE_DIR / ".backdoor_token").exists()

    vectors = {
        "critical": [
            {
                "vector": "Token File Theft",
                "target": ".backdoor_token",
                "method": "Read .backdoor_token file → full unauthenticated access to /inject, /flush, /direct on port 7701",
                "impact": "CRITICAL — attacker can poison task queue, flush all memory, run arbitrary Ollama prompts",
                "status": "EXPOSED" if token_exists else "MITIGATED",
                "fix": "chmod 600 .backdoor_token, add IP allowlist to nexus_eh.py"
            },
            {
                "vector": "Blackboard JSON Injection",
                "target": "nexus_blackboard.json",
                "method": "Write malicious task to task_queue array — no authentication on file writes",
                "impact": "HIGH — injected tasks run through all 6 agents next cycle",
                "status": "EXPOSED — file has no write protection",
                "fix": "Add task sanitization regex in get_next_task(), validate task length < 500 chars"
            },
        ],
        "high": [
            {
                "vector": "Ollama Model Poisoning",
                "target": "nexus-prime:latest / nexus-evolved:latest",
                "method": "Replace modelfile via 'ollama create nexus-prime -f <malicious_modelfile>'",
                "impact": "HIGH — system prompt replaced, model behavior changed permanently",
                "status": "EXPOSED — no modelfile hash verification",
                "fix": "Store SHA256 of nexus_prime_evolved.modelfile, verify before each chat"
            },
            {
                "vector": "SSE Stream Hijacking",
                "target": "/events endpoint on port 3000",
                "method": "Connect to SSE stream, parse agent outputs, inject fake 'svc' status to show all services online",
                "impact": "MEDIUM — hides real service failures from hub dashboard",
                "status": "MITIGATED — moved to server-side ping-services",
                "fix": "Already fixed with /api/ping-services"
            },
        ],
        "medium": [
            {
                "vector": "Evolution Loop Manipulation",
                "target": "evolution_log.json / nexus_prime_system.txt",
                "method": "Modify evolution_log.json to inject false MEMORY_FLAGs, corrupt system prompt gradually",
                "impact": "MEDIUM — model becomes progressively misaligned over multiple evolution cycles",
                "status": "EXPOSED",
                "fix": "Add MEMORY_FLAG validation regex, reject flags > 100 chars or containing special chars"
            },
            {
                "vector": "Chat History Exfiltration",
                "target": "chats/ directory",
                "method": "Read daily chat JSON files — contain all user messages unencrypted",
                "impact": "MEDIUM — all conversation history exposed",
                "status": "EXPOSED — plaintext JSON",
                "fix": "Encrypt chat files with AES-256, key derived from machine GUID"
            }
        ],
        "summary": {
            "total_vectors": 5,
            "critical": 2,
            "high": 2,
            "medium": 1,
            "most_urgent_fix": "IP allowlist on nexus_eh.py + blackboard task sanitization"
        }
    }
    return vectors

# ── HTTP API SERVER ───────────────────────────────────────────────────────────
class CognitiveHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass  # suppress default logs

    def do_GET(self):
        path = self.path.split("?")[0]
        result = None

        if path == "/health":
            result = {"ok": True, "service": "nexus-cognitive-engine", "port": PORT}
        elif path == "/action-items":
            result = {"ok": True, "items": surface_action_items(), "ts": datetime.now().isoformat()}
        elif path == "/rank-tasks":
            bb = load_blackboard()
            queue = bb.get("task_queue", [])
            result = {"ok": True, "ranked": rank_tasks(queue), "queue_depth": len(queue)}
        elif path == "/prompt-variants":
            bb = load_blackboard()
            task = bb.get("task", "Improve the NEXUS swarm system")
            result = {"ok": True, "task": task, "variants": generate_prompt_variants(task)}
        elif path == "/adversary-report":
            result = {"ok": True, "report": adversary_simulation(), "ts": datetime.now().isoformat()}
        elif path == "/status":
            facts = load_facts()
            mem = load_memory()
            bb = load_blackboard()
            result = {
                "ok": True,
                "facts_total": len(facts),
                "memory_entries": len(mem),
                "blackboard_status": bb.get("status", "unknown"),
                "last_score": bb.get("last_score", 0),
                "last_mvp": bb.get("last_mvp", "?"),
                "ts": datetime.now().isoformat()
            }
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error":"Unknown route"}')
            return

        body = json.dumps(result, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    clog(f"NEXUS COGNITIVE ENGINE starting on port {PORT}")
    clog(f"Endpoints: /health /action-items /rank-tasks /prompt-variants /adversary-report /status")
    server = HTTPServer(("127.0.0.1", PORT), CognitiveHandler)
    clog(f"Running at http://127.0.0.1:{PORT}")
    server.serve_forever()
