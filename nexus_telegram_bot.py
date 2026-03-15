"""
╔══════════════════════════════════════════════════════════════╗
║  NEXUS TELEGRAM BOT — S25 Ultra Remote Control              ║
║  Control your swarm from anywhere via Telegram              ║
╠══════════════════════════════════════════════════════════════╣
║  Commands:                                                   ║
║    /status   — live swarm status + score                    ║
║    /task     — inject a task into the swarm queue           ║
║    /result   — get the latest swarm output                  ║
║    /results  — last 5 agent outputs                         ║
║    /queue    — show current task queue                      ║
║    /flush    — clear the blackboard (danger)                ║
║    /help     — show all commands                            ║
╚══════════════════════════════════════════════════════════════╝

Setup:
  1. Message @BotFather on Telegram → /newbot → get token
  2. Set BOT_TOKEN below
  3. Set ALLOWED_CHAT_ID to your Telegram user ID
     (send any message to @userinfobot to get your ID)
  4. python nexus_telegram_bot.py
"""

import json
import time
import logging
import httpx
from pathlib import Path
from datetime import datetime

# ── CONFIG — SET THESE ────────────────────────────────────────────────────────
BOT_TOKEN       = "PASTE_YOUR_BOT_TOKEN_HERE"
ALLOWED_CHAT_ID = None   # Set to your Telegram user ID (int) for security
                         # e.g. 123456789  — leave None to allow anyone (not recommended)

# ── NEXUS CONFIG ──────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent
BLACKBOARD    = BASE_DIR / "nexus_blackboard.json"
COSMOS_URL    = "http://localhost:9100"
HUB_URL       = "http://localhost:3000"
POLL_INTERVAL = 1   # seconds between Telegram poll cycles

# ── LOGGING ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [TELEGRAM] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BASE_DIR / "telegram_bot.log", encoding="utf-8"),
    ]
)
log = logging.getLogger("telegram_bot")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ── BLACKBOARD HELPERS ────────────────────────────────────────────────────────
def read_bb() -> dict:
    try:
        return json.loads(BLACKBOARD.read_text(encoding="utf-8")) if BLACKBOARD.exists() else {}
    except Exception:
        return {}

def inject_task(task: str) -> dict:
    bb = read_bb()
    queue = bb.get("task_queue", [])
    queue.append(task)
    bb["task_queue"] = queue
    BLACKBOARD.write_text(json.dumps(bb, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"queued": task, "queue_depth": len(queue)}

# ── TELEGRAM API ──────────────────────────────────────────────────────────────
def tg_get(method: str, **params):
    try:
        r = httpx.get(f"{TELEGRAM_API}/{method}", params=params, timeout=10)
        return r.json()
    except Exception as e:
        log.error(f"GET {method} failed: {e}")
        return {}

def tg_post(method: str, **data):
    try:
        r = httpx.post(f"{TELEGRAM_API}/{method}", json=data, timeout=10)
        return r.json()
    except Exception as e:
        log.error(f"POST {method} failed: {e}")
        return {}

def send(chat_id: int, text: str, parse_mode: str = "Markdown"):
    tg_post("sendMessage", chat_id=chat_id, text=text, parse_mode=parse_mode)

# ── COMMAND HANDLERS ──────────────────────────────────────────────────────────
def cmd_status(chat_id: int, _args: str):
    bb = read_bb()
    status   = bb.get("status", "UNKNOWN")
    task     = bb.get("task", "[none]")
    score    = bb.get("last_score", "—")
    mvp      = bb.get("last_mvp", "—")
    q_depth  = len(bb.get("task_queue", []))
    outputs  = len(bb.get("outputs", []))

    emoji = "🟢" if status == "RUNNING" else "🟡" if status == "DONE" else "⚪"

    send(chat_id, (
        f"*NEXUS SWARM STATUS* {emoji}\n\n"
        f"*Status:* `{status}`\n"
        f"*Score:* `{score}`\n"
        f"*MVP Agent:* `{mvp}`\n"
        f"*Queue Depth:* `{q_depth}`\n"
        f"*Total Outputs:* `{outputs}`\n\n"
        f"*Current Task:*\n`{str(task)[:200]}`"
    ))

def cmd_result(chat_id: int, _args: str):
    bb = read_bb()
    outputs = bb.get("outputs", [])
    if not outputs:
        send(chat_id, "⚪ No outputs yet — swarm hasn't completed a cycle.")
        return

    last = outputs[-1]
    agent = last.get("agent", "UNKNOWN")
    text  = last.get("text", "")[:800]
    ts    = last.get("ts", "")[:19]
    score = bb.get("last_score", "—")
    mvp   = bb.get("last_mvp", "—")

    send(chat_id, (
        f"*LAST SWARM OUTPUT*\n\n"
        f"*Agent:* `{agent}` | *Score:* `{score}` | *MVP:* `{mvp}`\n"
        f"*Time:* `{ts}`\n\n"
        f"{text}{'...' if len(last.get('text','')) > 800 else ''}"
    ))

def cmd_results(chat_id: int, args: str):
    bb = read_bb()
    outputs = bb.get("outputs", [])
    n = min(int(args.strip()) if args.strip().isdigit() else 5, 10)
    recent = outputs[-n:][::-1]  # newest first

    if not recent:
        send(chat_id, "⚪ No outputs yet.")
        return

    lines = [f"*LAST {len(recent)} OUTPUTS*\n"]
    for o in recent:
        agent = o.get("agent", "?")
        text  = o.get("text", "")[:150]
        lines.append(f"*[{agent}]*\n`{text}...`\n")

    send(chat_id, "\n".join(lines))

def cmd_task(chat_id: int, args: str):
    if not args.strip():
        send(chat_id, "Usage: `/task your task description here`")
        return
    result = inject_task(args.strip())
    send(chat_id, (
        f"✅ *Task queued!*\n\n"
        f"`{args.strip()[:200]}`\n\n"
        f"*Queue depth:* `{result['queue_depth']}`\n"
        f"Swarm picks up within 30s."
    ))

def cmd_queue(chat_id: int, _args: str):
    bb = read_bb()
    queue = bb.get("task_queue", [])
    if not queue:
        send(chat_id, "✅ Queue is empty — swarm is idle or processing.")
        return

    lines = [f"*TASK QUEUE ({len(queue)} tasks)*\n"]
    for i, t in enumerate(queue[:10], 1):
        lines.append(f"`{i}. {str(t)[:100]}`")
    if len(queue) > 10:
        lines.append(f"_...and {len(queue)-10} more_")

    send(chat_id, "\n".join(lines))

def cmd_flush(chat_id: int, _args: str):
    send(chat_id, "⚠️ Are you sure? Reply `/flushconfirm` to clear the blackboard.")

def cmd_flushconfirm(chat_id: int, _args: str):
    fresh = {"status": "IDLE", "task": "", "outputs": [], "task_queue": [],
             "flushed_at": datetime.utcnow().isoformat()}
    BLACKBOARD.write_text(json.dumps(fresh, indent=2), encoding="utf-8")
    send(chat_id, "☠️ Blackboard flushed. Swarm will restart clean on next cycle.")

def cmd_help(chat_id: int, _args: str):
    send(chat_id, (
        "*NEXUS COMMAND BOT* 🤖\n\n"
        "*/status* — live swarm status\n"
        "*/task \\<text\\>* — inject task into swarm\n"
        "*/result* — latest agent output\n"
        "*/results \\[n\\]* — last N outputs (default 5)\n"
        "*/queue* — show task queue\n"
        "*/flush* — clear blackboard (with confirm)\n"
        "*/help* — this message\n\n"
        f"*Hub:* {HUB_URL}\n"
        f"*veilpiercer.com* → live"
    ))

COMMANDS = {
    "/status":       cmd_status,
    "/result":       cmd_result,
    "/results":      cmd_results,
    "/task":         cmd_task,
    "/queue":        cmd_queue,
    "/flush":        cmd_flush,
    "/flushconfirm": cmd_flushconfirm,
    "/help":         cmd_help,
    "/start":        cmd_help,
}

# ── MAIN POLL LOOP ────────────────────────────────────────────────────────────
def handle_update(update: dict):
    msg = update.get("message", {})
    if not msg:
        return

    chat_id = msg.get("chat", {}).get("id")
    text    = msg.get("text", "").strip()

    if not chat_id or not text:
        return

    # Security: only respond to allowed chat
    if ALLOWED_CHAT_ID and chat_id != ALLOWED_CHAT_ID:
        send(chat_id, "🚫 Unauthorized. This bot is private.")
        log.warning(f"Blocked message from chat_id={chat_id}")
        return

    # Parse command
    parts   = text.split(None, 1)
    cmd     = parts[0].split("@")[0].lower()  # handle /cmd@botname
    args    = parts[1] if len(parts) > 1 else ""

    handler = COMMANDS.get(cmd)
    if handler:
        log.info(f"cmd={cmd} args={args[:50]!r} chat={chat_id}")
        try:
            handler(chat_id, args)
        except Exception as e:
            send(chat_id, f"❌ Error: `{e}`")
            log.error(f"Handler error: {e}")
    else:
        send(chat_id, f"Unknown command: `{cmd}`\nType /help for commands.")

def main():
    if BOT_TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
        print("❌ Set BOT_TOKEN in nexus_telegram_bot.py first!")
        print("   Get a token from @BotFather on Telegram → /newbot")
        return

    log.info("=" * 55)
    log.info("NEXUS TELEGRAM BOT ONLINE")
    log.info(f"  Blackboard: {BLACKBOARD}")
    log.info(f"  Auth: {'CHAT ID ' + str(ALLOWED_CHAT_ID) if ALLOWED_CHAT_ID else 'OPEN (set ALLOWED_CHAT_ID!)'}")
    log.info("=" * 55)

    offset = 0
    # Send startup message if ALLOWED_CHAT_ID is set
    if ALLOWED_CHAT_ID:
        send(ALLOWED_CHAT_ID, "⚡ *NEXUS Bot online.* Type /status to check swarm.")

    while True:
        try:
            data = tg_get("getUpdates", offset=offset, timeout=30, allowed_updates=["message"])
            updates = data.get("result", [])
            for update in updates:
                handle_update(update)
                offset = update["update_id"] + 1
        except Exception as e:
            log.error(f"Poll error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
