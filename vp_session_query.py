"""
vp_session_query.py — CLI bridge for server.cjs to query VP sessions
Called by: node server.cjs via child_process.execFile
Usage:
    python vp_session_query.py sessions
    python vp_session_query.py diff SESSION_A SESSION_B
Output: JSON to stdout
"""
import sys
import json
from vp_session_logger import list_sessions, find_divergence

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "no command"}))
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "sessions":
        data = list_sessions(limit=50)
        print(json.dumps(data))

    elif cmd == "diff":
        if len(sys.argv) < 4:
            print(json.dumps({"error": "diff requires two session IDs"}))
            sys.exit(1)
        result = find_divergence(sys.argv[2], sys.argv[3])
        print(json.dumps(result))

    else:
        print(json.dumps({"error": f"unknown command: {cmd}"}))
        sys.exit(1)

if __name__ == "__main__":
    main()
