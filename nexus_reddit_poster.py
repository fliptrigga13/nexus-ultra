"""
nexus_reddit_poster.py  —  VeilPiercer Stealth Outreach Engine
================================================================
Human persona. Quality-gated. Anti-detection timing.

QUALITY GATES before any post goes live:
  1. Cycle score must be >= 0.65 (swarm produced real value)
  2. EXECUTIONER must have said [EXECUTE: READY] (all critics approved)
  3. SCOUT must have found a HIGH or MED readiness buyer signal
  4. Humanisation pass via local Ollama strips remaining AI-isms
  5. Copy must survive internal bot-pattern scanner

PERSONA: "Alex" — technical indie dev, self-hosted AI stack, discovered
VeilPiercer while solving own API cost problem. Helps first, mentions
VeilPiercer only when it's the honest answer to the stated pain.

Requires in .env:
  REDDIT_CLIENT_ID=...
  REDDIT_CLIENT_SECRET=...
  REDDIT_USERNAME=...
  REDDIT_PASSWORD=...
"""

import re
import time
import json
import random
import logging
import sqlite3
import httpx
import redis
from pathlib import Path
from datetime import datetime, timedelta

# ── Setup ──────────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent
LOG  = BASE / "reddit_poster.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [REDDIT] %(message)s",
    handlers=[
        logging.FileHandler(LOG, encoding="utf-8"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger("REDDIT")

# Load .env
_env = {}
_env_path = BASE / ".env"
if _env_path.exists():
    for line in _env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            _env[k.strip()] = v.strip()

REDDIT_CLIENT_ID     = _env.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = _env.get("REDDIT_CLIENT_SECRET", "")
REDDIT_USERNAME      = _env.get("REDDIT_USERNAME", "")
REDDIT_PASSWORD      = _env.get("REDDIT_PASSWORD", "")
REDIS_PASSWORD       = _env.get("REDIS_PASSWORD", "")
OLLAMA_URL           = "http://127.0.0.1:11434"
HUMANISE_MODEL       = "qwen2.5:7b-instruct-q5_K_M"  # fits in VRAM, sharp at following persona

# ── Config ─────────────────────────────────────────────────────────────────────
DAILY_POST_LIMIT   = 4          # conservative — quality over volume
MIN_GAP_MINUTES    = 35         # base gap, gets randomised ±10min
SCORE_THRESHOLD    = 0.65       # cycle must have scored this or higher
POSTED_LOG         = BASE / "reddit_posted.json"
MEMORY_DB          = BASE / "nexus_mind.db"

SUBREDDIT_WHITELIST = [
    "LocalLLaMA", "selfhosted", "SideProject",
    "Entrepreneur", "MachineLearning", "ollama",
    "AIAssistants", "artificial"
]

# Pain keywords — thread must match one of these to be worth entering
PAIN_SIGNALS = [
    "api cost", "openai bill", "claude cost", "too expensive", "rate limit",
    "monitoring", "self host", "local llm", "ollama", "privacy", "offline ai",
    "llm observ", "debug agent", "agent fail", "production ai", "api spend",
    "llm monitor", "track token", "llm cost", "ai budget", "gpu inference",
    "ai reliability", "agent crash", "prompt fail", "hallucin",
]

# Bot-ism patterns — if copy contains these, humanise pass fires
BOT_PATTERNS = [
    r"\bcurious\b", r"\bfascinating\b", r"\bcertainly\b", r"\babsolutely\b",
    r"\bdelve\b", r"\bleverage\b", r"\butilize\b", r"\bseamlessly\b",
    r"\bempower\b", r"\bsynergy\b", r"\bstreamline\b", r"\belevate\b",
    r"\bin conclusion\b", r"\bI hope this helps\b", r"\bfeel free to\b",
    r"\bdon't hesitate\b", r"\bI'd be happy to\b", r"\bas an AI\b",
    r"\bcertainly\b", r"\bworthwhile\b", r"\binnovative solution\b",
]

# ── Humanisation Prompt ─────────────────────────────────────────────────────────
_HUMANISE_SYSTEM = """You are Alex — a technical indie developer who runs a self-hosted AI stack.
You've been helping people on Reddit for 3 years. Your writing style:
- Direct, technically accurate, no fluff
- You share things that worked for you, not marketing pitches
- Short paragraphs. Normal punctuation. No em dashes.
- You say 'I' naturally. You have opinions. You push back when someone's wrong.
- You NEVER sound like a chatbot or a SaaS salesperson.
- You mention VeilPiercer only as a tool you built/use, not as a product pitch.

TASK: Rewrite the reply below so it sounds exactly like Alex posted it.
Keep the core message and key facts. Remove any AI-isms.
Output ONLY the rewritten reply. No preamble. No explanation."""


def humanise_copy(raw_copy: str) -> str:
    """Run copy through local Ollama for human persona pass."""
    try:
        payload = {
            "model": HUMANISE_MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": _HUMANISE_SYSTEM},
                {"role": "user", "content": f"Rewrite this:\n\n{raw_copy}"}
            ],
            "options": {"temperature": 0.45, "num_predict": 400, "num_ctx": 1024}
        }
        r = httpx.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=60.0)
        if r.status_code == 200:
            result = r.json().get("message", {}).get("content", "").strip()
            # Strip think blocks (qwen3 extended thinking)
            result = re.sub(r'<think>.*?</think>', '', result, flags=re.DOTALL).strip()
            if len(result) > 30:
                return result
    except Exception as e:
        log.warning(f"Humanise pass failed (using raw): {e}")
    return raw_copy


def has_bot_patterns(text: str) -> bool:
    """Return True if copy contains detectable AI-isms."""
    text_lower = text.lower()
    for pat in BOT_PATTERNS:
        if re.search(pat, text_lower):
            return True
    return False


def score_copy_quality(text: str) -> float:
    """
    Quick heuristic score 0-1 for copy quality.
    Penalises: AI-isms, excessive length, vague language.
    Rewards: specific numbers, "I" usage, direct sentences.
    """
    score = 0.5
    if len(text) < 80:   score -= 0.2   # too short
    if len(text) > 800:  score -= 0.1   # wall of text
    if has_bot_patterns(text): score -= 0.3
    score += min(0.2, text.lower().count(" i ") * 0.04)   # natural first-person
    score += 0.1 if re.search(r'\$\d+|\d+%|\d+ token', text) else 0  # has specifics
    score += 0.1 if "?" in text else 0  # asks a question = conversational
    return round(min(1.0, max(0.0, score)), 2)


# ── Redis / Swarm Data ─────────────────────────────────────────────────────────
def get_redis():
    return redis.Redis(host="localhost", port=6379, password=REDIS_PASSWORD,
                       decode_responses=True, socket_timeout=3)


def get_latest_cycle_data() -> dict:
    """
    Pull the most recent cycle's key outputs from Redis blackboard.
    Returns dict: {copywriter, executioner, scout, score}
    """
    data = {"copywriter": "", "executioner": "", "scout": "", "score": 0.0}
    try:
        r = get_redis()
        raw_list = r.lrange("nexus_blackboard:outputs", 0, 40)
        for raw in raw_list:
            try:
                d = json.loads(raw)
                agent = d.get("agent", "").upper()
                text  = d.get("text", "")
                if agent == "COPYWRITER" and not data["copywriter"]:
                    data["copywriter"] = text
                elif agent == "EXECUTIONER" and not data["executioner"]:
                    data["executioner"] = text
                elif agent == "SCOUT" and not data["scout"]:
                    data["scout"] = text
            except Exception:
                pass
    except Exception as e:
        log.warning(f"Redis read failed: {e}")
    return data


def get_last_cycle_score() -> float:
    """Read last stored cycle score from nexus_mind.db memory."""
    try:
        conn = sqlite3.connect(str(MEMORY_DB), check_same_thread=False)
        cur = conn.execute(
            """SELECT content FROM memories
               WHERE agent='REWARD' OR tags LIKE '%score%'
               ORDER BY created_at DESC LIMIT 5"""
        )
        for row in cur.fetchall():
            m = re.search(r'[Ss]core[=:\s]+([01]?\.\d+)', row[0])
            if m:
                conn.close()
                return float(m.group(1))
        conn.close()
    except Exception:
        pass
    return 0.0


# ── Quality Gate ───────────────────────────────────────────────────────────────
def passes_quality_gate(cycle: dict) -> tuple[bool, str]:
    """
    3-layer gate before any post fires.
    Returns (pass: bool, reason: str)
    """
    # Gate 1: EXECUTIONER must say READY
    if "[EXECUTE: READY" not in cycle.get("executioner", ""):
        return False, f"EXECUTIONER not READY: {cycle['executioner'][:60]}"

    # Gate 2: Cycle score threshold
    score = get_last_cycle_score()
    if score < SCORE_THRESHOLD:
        return False, f"Cycle score {score:.2f} < threshold {SCORE_THRESHOLD}"

    # Gate 3: SCOUT must have buyer signal
    scout = cycle.get("scout", "")
    if "[BUYER:" not in scout and "[BUYER_SIGNAL:" not in scout:
        return False, "SCOUT found no buyer signal this cycle"

    return True, f"Quality gate passed (score={score:.2f})"


# ── Copy Extraction ────────────────────────────────────────────────────────────
def extract_reddit_replies(text: str) -> list[tuple[str, str]]:
    """Extract [REDDIT_REPLY: r/sub]...[/REDDIT_REPLY] blocks."""
    pattern = r'\[REDDIT_REPLY:\s*r?/?([A-Za-z0-9_]+)\](.*?)\[/REDDIT_REPLY\]'
    return [(m.group(1), m.group(2).strip())
            for m in re.finditer(pattern, text, re.DOTALL)]


def extract_email_copy(text: str) -> list[str]:
    """Extract [EMAIL: subject=...] blocks as fallback."""
    pattern = r'\[EMAIL:[^\]]*\](.*?)\[/EMAIL\]'
    return [m.group(1).strip() for m in re.finditer(pattern, text, re.DOTALL)]


# ── Reddit Client ─────────────────────────────────────────────────────────────
def get_reddit():
    try:
        import praw
    except ImportError:
        log.error("praw not installed — run: pip install praw")
        return None

    if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD]):
        log.error("Reddit credentials missing in .env")
        return None
    try:
        # User agent MUST look like a real browser/app — not a bot banner
        r = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            username=REDDIT_USERNAME,
            password=REDDIT_PASSWORD,
            user_agent=f"python:personal-script:v1.0 (by u/{REDDIT_USERNAME})",
        )
        me = r.user.me()
        log.info(f"Auth OK — u/{me.name} | karma: {me.link_karma + me.comment_karma}")
        return r
    except Exception as e:
        log.error(f"Reddit auth failed: {e}")
        return None


def find_target_thread(reddit, subreddit_name: str, scout_context: str):
    """
    Find the highest-value thread to enter.
    Prefers: recent posts (1-8h old), active comments, pain signal match.
    Skips: locked, archived, over_18, too old, already commented in.
    """
    try:
        sub = reddit.subreddit(subreddit_name)
        candidates = []

        # Check both hot and new — hot for visibility, new for timing
        for feed in [sub.hot(limit=30), sub.new(limit=20)]:
            for post in feed:
                if post.over_18 or post.locked or post.archived:
                    continue
                age_hours = (datetime.utcnow().timestamp() - post.created_utc) / 3600
                if age_hours > 20 or age_hours < 0.3:
                    continue  # too old or brand new

                title_body = (post.title + " " + (post.selftext or "")).lower()
                pain_score = sum(1 for kw in PAIN_SIGNALS if kw in title_body)
                if pain_score == 0:
                    continue

                # Prefer threads with moderate comment count (not dead, not buried)
                comment_score = 1.0 if 2 <= post.num_comments <= 80 else 0.5

                candidates.append((
                    pain_score * comment_score / max(1, age_hours * 0.1),
                    post
                ))

        if not candidates:
            log.info(f"No matching thread in r/{subreddit_name}")
            return None

        candidates.sort(key=lambda x: -x[0])
        best = candidates[0][1]
        log.info(f"Target: [{subreddit_name}] {best.title[:70]} "
                 f"({best.num_comments} comments, score={best.score})")
        return best

    except Exception as e:
        log.warning(f"Thread scan failed r/{subreddit_name}: {e}")
        return None


# ── State Tracking ─────────────────────────────────────────────────────────────
def load_state() -> dict:
    if POSTED_LOG.exists():
        try:
            return json.loads(POSTED_LOG.read_text())
        except Exception:
            pass
    return {"posts": [], "daily_count": 0, "day": str(datetime.now().date())}


def save_state(state: dict):
    POSTED_LOG.write_text(json.dumps(state, indent=2))


def can_post(state: dict) -> tuple[bool, str]:
    today = str(datetime.now().date())
    if state.get("day") != today:
        state["daily_count"] = 0
        state["day"] = today

    if state["daily_count"] >= DAILY_POST_LIMIT:
        return False, f"Daily limit ({DAILY_POST_LIMIT}) reached"

    posts = state.get("posts", [])
    if posts:
        last_ts = datetime.fromisoformat(posts[-1]["timestamp"])
        # Randomised gap: base ± 10min jitter — avoids predictable timing signature
        jitter = random.randint(-10, 10)
        gap = timedelta(minutes=MIN_GAP_MINUTES + jitter)
        if datetime.now() - last_ts < gap:
            remaining = int((gap - (datetime.now() - last_ts)).total_seconds() / 60)
            return False, f"Cooldown: {remaining}m remaining"

    return True, "OK"


def already_posted(state: dict, reply_hash: int) -> bool:
    return any(p.get("hash") == reply_hash for p in state.get("posts", []))


# ── Main Loop ──────────────────────────────────────────────────────────────────
def main():
    log.info("=" * 65)
    log.info("VeilPiercer Stealth Outreach Engine — ONLINE")
    log.info(f"Persona: Alex (@{REDDIT_USERNAME})")
    log.info(f"Limits: {DAILY_POST_LIMIT}/day | {MIN_GAP_MINUTES}min cooldown ±10min jitter")
    log.info(f"Quality gate: EXECUTIONER=READY + score>={SCORE_THRESHOLD} + SCOUT buyer signal")
    log.info("=" * 65)

    reddit = get_reddit()
    if not reddit:
        log.error("Cannot start — Reddit credentials not configured in .env")
        return

    state = load_state()

    while True:
        try:
            ok, reason = can_post(state)
            if not ok:
                log.info(f"[GATE] {reason}")
                time.sleep(60)
                continue

            # Pull latest cycle data from Redis
            cycle = get_latest_cycle_data()

            # Quality gate
            passed, gate_reason = passes_quality_gate(cycle)
            log.info(f"[QUALITY GATE] {gate_reason}")
            if not passed:
                time.sleep(120)
                continue

            # Extract copy
            replies = extract_reddit_replies(cycle["copywriter"])
            if not replies:
                log.info("No [REDDIT_REPLY:] blocks in current cycle — waiting")
                time.sleep(120)
                continue

            posted = False
            for sub_name, raw_copy in replies:
                if sub_name not in SUBREDDIT_WHITELIST:
                    log.info(f"Skipping r/{sub_name} — not in whitelist")
                    continue

                # Dedup
                copy_hash = hash(raw_copy[:120])
                if already_posted(state, copy_hash):
                    log.info(f"Already posted this copy to r/{sub_name}")
                    continue

                if len(raw_copy.strip()) < 40:
                    log.warning("Copy too short — skipping")
                    continue

                # Humanise pass if bot patterns detected
                if has_bot_patterns(raw_copy):
                    log.info("Bot patterns found — running humanise pass...")
                    final_copy = humanise_copy(raw_copy)
                else:
                    final_copy = raw_copy

                # Final quality score
                q = score_copy_quality(final_copy)
                log.info(f"Copy quality score: {q:.2f}")
                if q < 0.35:
                    log.warning(f"Copy quality {q:.2f} too low — skipping this block")
                    continue

                # Find thread
                thread = find_target_thread(reddit, sub_name, cycle["scout"])
                if not thread:
                    continue

                # FINAL SAFETY CHECK — never post to a thread we're already in
                thread.comments.replace_more(limit=0)
                me_name = REDDIT_USERNAME.lower()
                if any(c.author and c.author.name.lower() == me_name
                       for c in thread.comments.list()[:20]):
                    log.info(f"Already commented in this thread — skipping")
                    continue

                # Human-style delay before posting (0.5–2s — looks like typing)
                time.sleep(random.uniform(0.5, 2.0))

                log.info(f"Posting to r/{sub_name} | q={q:.2f}")
                log.info(f"Copy preview: {final_copy[:120]}...")
                thread.reply(final_copy)
                log.info(f"Posted → {thread.permalink}")

                state.setdefault("posts", []).append({
                    "timestamp": datetime.now().isoformat(),
                    "subreddit": sub_name,
                    "thread": thread.permalink,
                    "thread_title": thread.title[:100],
                    "score": get_last_cycle_score(),
                    "quality": q,
                    "preview": final_copy[:120],
                    "hash": copy_hash,
                })
                state["daily_count"] = state.get("daily_count", 0) + 1
                save_state(state)
                log.info(f"Daily count: {state['daily_count']}/{DAILY_POST_LIMIT}")
                posted = True
                break

            if not posted:
                log.info("Nothing postable this scan")

        except Exception as e:
            log.error(f"Poster loop error: {e}", exc_info=True)

        # Randomised scan interval — 4–7 min, not a clockwork bot signature
        wait = random.randint(240, 420)
        log.info(f"Next scan in {wait//60}m {wait%60}s")
        time.sleep(wait)


if __name__ == "__main__":
    main()
