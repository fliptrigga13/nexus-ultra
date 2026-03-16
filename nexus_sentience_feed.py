
import json
import os
import glob
from datetime import datetime, timezone

# ── CONFIG ───────────────────────────────────────────────────────────────────
BLACKBOARD_PATH = r"c:\Users\fyou1\Desktop\New folder\nexus-ultra\nexus_blackboard.json"
FEEDBACK_PATH = r"c:\Users\fyou1\Desktop\New folder\nexus-ultra\feedback.json"
LOG_PATH = r"c:\Users\fyou1\Desktop\New folder\nexus-ultra\nexus.log"
ROOT_DIR = r"c:\Users\fyou1\Desktop\New folder\nexus-ultra"

def _ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def inject_task(task_text):
    try:
        if os.path.exists(BLACKBOARD_PATH):
            with open(BLACKBOARD_PATH, "r", encoding="utf-8") as f:
                bb = json.load(f)
        else:
            bb = {}
        
        queue = bb.get("task_queue", [])
        queue.append(task_text)
        bb["task_queue"] = queue
        
        with open(BLACKBOARD_PATH, "w", encoding="utf-8") as f:
            json.dump(bb, f, indent=2, ensure_ascii=False)
        print(f"  [SENTIENCE] Injected task: {task_text[:60]}...")
    except Exception as e:
        print(f"  [SENTIENCE] Injection failed: {e}")

def feed_system_state():
    """Feeds agents the current project file modifications and recent feedback."""
    print(f"[{_ts()}] Generating Sentience Feed...")
    
    # 1. Recent File Changes
    files = glob.glob(os.path.join(ROOT_DIR, "*.*"))
    # Filter out big logs and binary stuff
    files = [f for f in files if f.split(".")[-1] in ["html", "cjs", "py", "ps1", "txt", "md"]]
    files.sort(key=os.path.getmtime, reverse=True)
    recent_changes = [os.path.basename(f) for f in files[:8]]
    
    # 2. Recent Feedback
    feedback_summary = "No recent feedback found."
    if os.path.exists(FEEDBACK_PATH):
        try:
            with open(FEEDBACK_PATH, "r", encoding="utf-8") as f:
                fd = json.load(f)
                if fd:
                    last = fd[-1]
                    feedback_summary = f"Last Rating: {last.get('rating')}/10. Comment: {last.get('suggestion', 'No comment')}"
        except: pass

    # 3. Log Errors
    log_anomalies = "None detected."
    if os.path.exists(LOG_PATH):
        try:
            with open(LOG_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()[-100:]
                errors = [l.strip() for l in lines if "ERROR" in l or "ERR" in l]
                if errors:
                    log_anomalies = f"{len(errors)} anomalies detected in last 100 lines."
        except: pass

    sentience_report = f"""
[SENSORY FEED: NEXUS INTERNAL STATE — {_ts()}]
● RECENT ARCHITECTURE CHANGES: {', '.join(recent_changes)}
● LOG ANOMALIES: {log_anomalies}
● MARKET FEEDBACK: {feedback_summary}

TASK: Review the internal state above. 
1. Are the recent file changes aligned with the Intelligence Manifesto (Observability vs Noise)?
2. If log anomalies exist, propose a fix script.
3. If market feedback mentions a pain point, create a task to improve the BUNDLE/ asset related to it.
"""
    inject_task(sentience_report)

if __name__ == "__main__":
    feed_system_state()
