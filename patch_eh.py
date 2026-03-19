import os, re

path = r"c:\Users\fyou1\Desktop\New folder\nexus-ultra\nexus_eh.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Match simply the peer info line as anchor
anchor = "peer = writer.get_extra_info('peername', ('0.0.0.0', 0))"
marker = "# ── IP ALLOWLIST CHECK"

# I'll just find the line indices
lines = content.splitlines()
target_line_idx = -1
for i, line in enumerate(lines):
    if "peer = writer.get_extra_info('peername'" in line:
        target_line_idx = i
        break

if target_line_idx != -1:
    # Go back a few lines to find the marker
    start_idx = target_line_idx - 1
    # Go forward to find the return
    end_idx = target_line_idx + 5
    
    new_auth_block = [
        "        # ── AUTH & IP CHECK ─────────────────────────────────────────────────────",
        "        peer = writer.get_extra_info('peername', ('0.0.0.0', 0))",
        "        client_ip = peer[0] if peer else '0.0.0.0'",
        "        ",
        "        # Parse headers",
        "        headers_dict = {}",
        "        for h_line in text.split('\\r\\n')[1:]:",
        "            if ': ' in h_line:",
        "                k, v = h_line.split(': ', 1)",
        "                headers_dict[k.lower()] = v.strip()",
        "        ",
        "        auth_token = headers_dict.get('x-eh-token')",
        "        ",
        "        is_health = path == '/health'",
        "        is_authed = (auth_token == EH_TOKEN) if (auth_token and EH_TOKEN) else False",
        "        ",
        "        # Security Logic: ",
        "        # 1. Health is always public.",
        "        # 2. If Token matches, it's allowed (trusted app).",
        "        # 3. If NO token, strictly only allow Localhost/LAN for non-destructive.",
        "        if not is_health and not is_authed:",
        "            if not check_ip_allowed(client_ip, path):",
        "                 deny = b'HTTP/1.1 401 Unauthorized\\r\\nContent-Type: application/json\\r\\n\\r\\n{\"error\":\"EH Token Required for remote access\"}'",
        "                 writer.write(deny); await writer.drain(); writer.close(); return",
        "        # ──────────────────────────────────────────────────────────────────────────"
    ]
    lines[start_idx:end_idx] = new_auth_block
    new_content = "\n".join(lines)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Security patch applied via line index.")
else:
    print("Could not find anchor line.")
