# VeilPiercer MCP — Setup Guide

## What This Does
Registers VeilPiercer as a native tool in Claude Desktop and Cursor.
Once registered, Claude / Cursor can call `start_session`, `trace_step`, and `diff_sessions`
directly — no code needed.

---

## Claude Desktop

Edit `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "veilpiercer": {
      "command": "python",
      "args": ["C:\\Users\\fyou1\\Desktop\\New folder\\nexus-ultra\\mcp\\server.py"],
      "env": {}
    }
  }
}
```

Then restart Claude Desktop. You'll see "veilpiercer" appear in the tools panel.

---

## Cursor

Edit `.cursor/mcp.json` in your project root (or `~/.cursor/mcp.json` for global):

```json
{
  "mcpServers": {
    "veilpiercer": {
      "command": "python",
      "args": ["C:\\Users\\fyou1\\Desktop\\New folder\\nexus-ultra\\mcp\\server.py"]
    }
  }
}
```

Restart Cursor. VeilPiercer tools appear in Cursor's MCP panel.

---

## Test It Works

After registering, ask Claude:

> "Start a VeilPiercer session called 'test-run', trace a step with prompt='hello' and response='world', then show me the session."

You should see Claude call `start_session` and `trace_step` automatically.

---

## Smoke Test (CLI)

```powershell
cd "C:\Users\fyou1\Desktop\New folder\nexus-ultra"
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | python mcp/server.py
```

Should return JSON listing all three tools.

---

## Files
```
mcp/
  server.py      ← MCP server (run this)
  manifest.json  ← Tool definitions
  SETUP.md       ← This file
```
