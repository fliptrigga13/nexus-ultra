"""
nexus_reply_monitor.py — Reddit reply notifier for MaleficentAct7454
Polls Reddit every 2 minutes, shows Windows toast if anyone replies to your comments.
Run in a separate terminal: python -X utf8 nexus_reply_monitor.py
"""
import time, json, ctypes, urllib.request, urllib.error, os, sys

REDDIT_USERNAME = "MaleficentAct7454"
POLL_INTERVAL   = 120   # seconds between checks
HEADERS         = {"User-Agent": "NexusReplyMonitor/1.0 (by MaleficentAct7454)"}

# Threads to watch: (thread_id, label)
WATCHED_THREADS = [
    ("1s393wi", "Privacy thread: cloud context leak"),
    ("1s3b4ye", "What are you building with local LLMs"),
]

# ─── Windows toast via PowerShell ──────────────────────────────────────────────
def toast(title: str, message: str):
    """Fire a Windows 10/11 toast notification via PowerShell."""
    ps_cmd = (
        f"Add-Type -AssemblyName System.Windows.Forms; "
        f"$n = New-Object System.Windows.Forms.NotifyIcon; "
        f"$n.Icon = [System.Drawing.SystemIcons]::Information; "
        f"$n.BalloonTipTitle = '{title}'; "
        f"$n.BalloonTipText = '{message}'; "
        f"$n.Visible = $true; "
        f"$n.ShowBalloonTip(8000); "
        f"Start-Sleep -Seconds 9; "
        f"$n.Dispose()"
    )
    os.system(f'powershell -WindowStyle Hidden -Command "{ps_cmd}"')
    # Also print to console
    print(f"\n[NOTIFICATION] {title}: {message}\n")


# ─── Reddit fetch helper ────────────────────────────────────────────────────────
def fetch_json(url: str):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"[fetch error] {url}: {e}")
        return None


def get_thread_comments(thread_id: str):
    """Return flat list of all comments in a thread."""
    data = fetch_json(f"https://www.reddit.com/r/LocalLLaMA/comments/{thread_id}.json?limit=200")
    if not data or len(data) < 2:
        return []
    comments = []
    def walk(lst):
        for item in lst:
            if item.get("kind") == "t1":
                d = item["data"]
                comments.append({
                    "id":     d["id"],
                    "author": d.get("author", ""),
                    "body":   d.get("body", "")[:120],
                    "parent": d.get("parent_id", ""),
                })
                if d.get("replies") and isinstance(d["replies"], dict):
                    walk(d["replies"]["data"]["children"])
    walk(data[1]["data"]["children"])
    return comments


def get_my_comment_ids(thread_id: str):
    """Return set of comment IDs posted by REDDIT_USERNAME in thread."""
    return {
        c["id"] for c in get_thread_comments(thread_id)
        if c["author"].lower() == REDDIT_USERNAME.lower()
    }


# ─── Main loop ─────────────────────────────────────────────────────────────────
def main():
    print(f"[MONITOR] Watching {len(WATCHED_THREADS)} thread(s) as u/{REDDIT_USERNAME}")
    print(f"[MONITOR] Polling every {POLL_INTERVAL}s. Press Ctrl+C to stop.\n")

    # Seed: record all comment IDs already seen in each thread
    seen: dict[str, set] = {}
    my_ids: dict[str, set] = {}
    for tid, label in WATCHED_THREADS:
        comments = get_thread_comments(tid)
        seen[tid]   = {c["id"] for c in comments}
        my_ids[tid] = {c["id"] for c in comments if c["author"].lower() == REDDIT_USERNAME.lower()}
        print(f"[MONITOR] Thread '{label}': {len(seen[tid])} comments seen, {len(my_ids[tid])} yours")

    toast("NEXUS Monitor Active", f"Watching {len(WATCHED_THREADS)} Reddit threads for replies")

    while True:
        time.sleep(POLL_INTERVAL)
        print(f"[MONITOR] Checking at {time.strftime('%H:%M:%S')}...")

        for tid, label in WATCHED_THREADS:
            comments = get_thread_comments(tid)
            if not comments:
                continue

            # Update my comment IDs
            my_ids[tid].update(
                c["id"] for c in comments
                if c["author"].lower() == REDDIT_USERNAME.lower()
            )

            # Check for new comments that reply to mine
            for c in comments:
                if c["id"] in seen[tid]:
                    continue
                seen[tid].add(c["id"])
                parent_id = c["parent"].replace("t1_", "")
                if parent_id in my_ids[tid]:
                    msg = f"u/{c['author']}: {c['body']}"
                    print(f"[REPLY] {label} — {msg}")
                    toast(f"Reddit reply in '{label}'", msg)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[MONITOR] Stopped.")
