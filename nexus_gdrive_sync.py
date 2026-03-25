"""
nexus_gdrive_sync.py — Feedback Loop Google Drive Sync
Uploads swarm cycle evolution data to Google Drive after each cycle.
Stores: cycle scores, top memories, emergent patterns, MVP agents.
Auth: OAuth 2.0 — first run opens browser, token cached in gdrive_token.json
"""
import os, json, sqlite3, datetime, time, logging
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaInMemoryUpload

log = logging.getLogger("GDRIVE-SYNC")
logging.basicConfig(level=logging.INFO)

# ── CONFIG ──────────────────────────────────────────────────────────────────
SCOPES          = ["https://www.googleapis.com/auth/drive.file"]
TOKEN_FILE      = "gdrive_token.json"
CREDS_FILE      = "gdrive_credentials.json"   # download from Google Cloud Console
DRIVE_FOLDER    = "NEXUS-VeilPiercer-Evolution" # folder name in Drive
MEMORY_DB       = "nexus_mind.db"
SWARM_LOG       = "swarm_active.log"
SYNC_INTERVAL   = 300  # sync every 5 minutes (not every cycle — rate limit safe)

# ── AUTH ─────────────────────────────────────────────────────────────────────
def get_drive_service():
    creds = None
    if Path(TOKEN_FILE).exists():
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(CREDS_FILE).exists():
                raise FileNotFoundError(
                    f"\n❌ Missing {CREDS_FILE}.\n"
                    f"   1. Go to: https://console.cloud.google.com/apis/credentials\n"
                    f"   2. Create OAuth 2.0 Client ID (Desktop app)\n"
                    f"   3. Download JSON → save as '{CREDS_FILE}' in nexus-ultra folder\n"
                    f"   4. Run this script again — browser will open for one-time auth\n"
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        log.info("✅ Google Drive auth complete — token cached")
    return build("drive", "v3", credentials=creds)

# ── FOLDER MANAGEMENT ────────────────────────────────────────────────────────
def get_or_create_folder(service, folder_name):
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    if files:
        fid = files[0]["id"]
        log.info(f"📁 Using existing Drive folder: {folder_name} ({fid})")
        return fid
    meta = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
    folder = service.files().create(body=meta, fields="id").execute()
    fid = folder["id"]
    log.info(f"📁 Created Drive folder: {folder_name} ({fid})")
    return fid

# ── DATA COLLECTION ──────────────────────────────────────────────────────────
def collect_snapshot():
    snapshot = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "memories": {},
        "recent_cycles": [],
        "emergent_patterns": [],
    }

    # Memory stats
    try:
        conn = sqlite3.connect(MEMORY_DB)
        total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        avg_imp = conn.execute("SELECT AVG(importance) FROM memories WHERE archived=0").fetchone()[0] or 0
        top_memories = conn.execute(
            "SELECT content, importance, agent, tags FROM memories WHERE archived=0 "
            "ORDER BY importance DESC LIMIT 20"
        ).fetchall()
        snapshot["memories"] = {
            "total": total,
            "avg_importance": round(avg_imp, 2),
            "top_20": [
                {"content": c[:200], "importance": imp, "agent": ag, "tags": tags}
                for c, imp, ag, tags in top_memories
            ]
        }
        # Emergent patterns = memories with importance >= 9.5
        patterns = conn.execute(
            "SELECT content, importance, agent FROM memories WHERE importance >= 9.5 "
            "ORDER BY importance DESC LIMIT 10"
        ).fetchall()
        snapshot["emergent_patterns"] = [
            {"pattern": c[:300], "importance": imp, "agent": ag}
            for c, imp, ag in patterns
        ]
        conn.close()
    except Exception as e:
        snapshot["memories"]["error"] = str(e)

    # Recent cycle scores from swarm_active.log
    try:
        cycles = []
        if Path(SWARM_LOG).exists():
            with open(SWARM_LOG, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "Cycle #" in line and "COMPLETE. Score=" in line:
                        parts = line.strip()
                        cycles.append(parts[-80:])
        snapshot["recent_cycles"] = cycles[-20:]  # last 20 cycles
    except Exception as e:
        snapshot["recent_cycles"] = [f"error: {e}"]

    return snapshot

# ── UPLOAD ───────────────────────────────────────────────────────────────────
def upload_snapshot(service, folder_id, snapshot):
    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"nexus_evolution_{ts}.json"
    content = json.dumps(snapshot, indent=2, ensure_ascii=False).encode("utf-8")

    media = MediaInMemoryUpload(content, mimetype="application/json", resumable=False)
    meta = {"name": filename, "parents": [folder_id]}
    result = service.files().create(body=meta, media_body=media, fields="id,name").execute()
    log.info(f"☁️  Uploaded snapshot: {filename} (id={result['id']})")

    # Also update a rolling 'latest.json' for easy programmatic access
    latest_content = json.dumps(snapshot, indent=2, ensure_ascii=False).encode("utf-8")
    latest_media = MediaInMemoryUpload(latest_content, mimetype="application/json", resumable=False)

    # Check if 'latest.json' exists in folder
    query = f"name='nexus_latest.json' and '{folder_id}' in parents and trashed=false"
    existing = service.files().list(q=query, fields="files(id)").execute().get("files", [])
    if existing:
        service.files().update(
            fileId=existing[0]["id"],
            media_body=latest_media
        ).execute()
    else:
        service.files().create(
            body={"name": "nexus_latest.json", "parents": [folder_id]},
            media_body=latest_media,
            fields="id"
        ).execute()
    log.info("☁️  Updated nexus_latest.json")

# ── MAIN LOOP ────────────────────────────────────────────────────────────────
def run_sync_loop():
    log.info("🔄 NEXUS Google Drive Sync starting...")
    try:
        service = get_drive_service()
    except FileNotFoundError as e:
        print(e)
        return

    folder_id = get_or_create_folder(service, DRIVE_FOLDER)

    while True:
        try:
            snapshot = collect_snapshot()
            upload_snapshot(service, folder_id, snapshot)
            mem_count = snapshot["memories"].get("total", "?")
            avg_imp   = snapshot["memories"].get("avg_importance", "?")
            patterns  = len(snapshot["emergent_patterns"])
            log.info(f"   Memories: {mem_count} | Avg importance: {avg_imp} | Patterns: {patterns}")
        except Exception as e:
            log.error(f"Sync error: {e}")
        time.sleep(SYNC_INTERVAL)

if __name__ == "__main__":
    run_sync_loop()
