"""
VeilPiercer MCP Server
======================
Exposes VeilPiercer's per-step tracing as MCP tools, compatible with:
  - Claude Desktop (add to claude_desktop_config.json)
  - Cursor (add to .cursor/mcp.json)
  - Any MCP-compatible client

Tools exposed:
  1. start_session  — open a new trace session, returns session_id
  2. trace_step     — log one agent step into a session
  3. diff_sessions  — compare two sessions, returns fork point + diff

Run:
  python mcp/server.py

Register in Claude Desktop:
  See mcp/claude_desktop_config.json
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

# ── MCP SDK ───────────────────────────────────────────────────────────────────
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
    CallToolRequest,
    ListToolsRequest,
    ListToolsResult,
)

# ── VeilPiercer imports ───────────────────────────────────────────────────────
# Adjust path if running server.py from inside mcp/ subdirectory
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

try:
    from veilpiercer.logger import SessionLogger, find_divergence
    VP_AVAILABLE = True
except ImportError:
    VP_AVAILABLE = False

DB_PATH = ROOT / "vp_mcp_sessions.db"

# Active sessions: session_id → SessionLogger (kept open between calls)
_SESSIONS: dict[str, Any] = {}

# ── Server setup ──────────────────────────────────────────────────────────────

server = Server("veilpiercer")

# ── Tool definitions ──────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="start_session",
            description=(
                "Start a new VeilPiercer trace session for an agent pipeline. "
                "Returns a session_id to use in subsequent trace_step calls. "
                "Use this at the beginning of an agent run you want to trace."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Unique name for this session (e.g. 'run-2026-03-27-A'). If omitted, auto-generated."
                    },
                    "agent_name": {
                        "type": "string",
                        "description": "Name of the agent or pipeline being traced.",
                        "default": "agent"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="trace_step",
            description=(
                "Log one step of an agent pipeline into an active VeilPiercer session. "
                "Captures what the step received (prompt/input) and what it produced (response/output). "
                "Call this after each agent step to build a complete trace."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID returned by start_session."
                    },
                    "prompt": {
                        "type": "string",
                        "description": "What this step received as input (the prompt or context)."
                    },
                    "response": {
                        "type": "string",
                        "description": "What this step produced as output."
                    },
                    "step_label": {
                        "type": "string",
                        "description": "Human-readable label for this step (e.g. 'COPYWRITER', 'VALIDATOR').",
                        "default": "step"
                    },
                    "model": {
                        "type": "string",
                        "description": "Model used for this step (e.g. 'llama3.1:8b').",
                        "default": "unknown"
                    },
                    "latency_ms": {
                        "type": "number",
                        "description": "How long this step took in milliseconds.",
                        "default": 0
                    }
                },
                "required": ["session_id", "prompt", "response"]
            }
        ),
        Tool(
            name="diff_sessions",
            description=(
                "Compare two VeilPiercer trace sessions to find where they diverged. "
                "Returns the fork point (which step), the last shared state, and a "
                "side-by-side comparison of all steps. Use this to diagnose why two "
                "runs of the same pipeline produced different outputs."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_a": {
                        "type": "string",
                        "description": "session_id of the first (reference) run."
                    },
                    "session_b": {
                        "type": "string",
                        "description": "session_id of the second run to compare against."
                    }
                },
                "required": ["session_a", "session_b"]
            }
        )
    ]


# ── Tool handlers ─────────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:

    # ── start_session ─────────────────────────────────────────────────────────
    if name == "start_session":
        if not VP_AVAILABLE:
            return [TextContent(type="text", text=(
                "ERROR: veilpiercer package not installed.\n"
                "Run: pip install veilpiercer"
            ))]

        import time
        sid   = arguments.get("session_id") or f"mcp-{int(time.time())}"
        agent = arguments.get("agent_name", "agent")

        try:
            sl = SessionLogger(session_id=sid, agent=agent, db_path=DB_PATH)
            sl.__enter__()
            _SESSIONS[sid] = sl
            return [TextContent(type="text", text=json.dumps({
                "session_id": sid,
                "agent": agent,
                "db_path": str(DB_PATH),
                "status": "open",
                "message": f"Session '{sid}' started. Use trace_step to log each agent step."
            }, indent=2))]
        except Exception as e:
            return [TextContent(type="text", text=f"ERROR starting session: {e}")]

    # ── trace_step ────────────────────────────────────────────────────────────
    elif name == "trace_step":
        if not VP_AVAILABLE:
            return [TextContent(type="text", text="ERROR: veilpiercer not installed.")]

        sid      = arguments.get("session_id", "")
        prompt   = arguments.get("prompt", "")
        response = arguments.get("response", "")
        label    = arguments.get("step_label", "step")
        model    = arguments.get("model", "unknown")
        latency  = int(arguments.get("latency_ms", 0))

        sl = _SESSIONS.get(sid)
        if sl is None:
            # Try to open existing session from DB
            try:
                sl = SessionLogger(session_id=sid, agent="mcp", db_path=DB_PATH)
                sl.__enter__()
                _SESSIONS[sid] = sl
            except Exception as e:
                return [TextContent(type="text", text=(
                    f"ERROR: session '{sid}' not found. Call start_session first.\nDetails: {e}"
                ))]

        try:
            step_count = len(sl._steps) if hasattr(sl, '_steps') else 0
            sl.log_step(
                prompt=prompt,
                response=response,
                state_version=label,
                model=model,
                latency_ms=latency,
                step_type="llm"
            )
            return [TextContent(type="text", text=json.dumps({
                "session_id": sid,
                "step_label": label,
                "step_number": step_count + 1,
                "status": "logged",
                "preview": {
                    "prompt":   prompt[:100] + "..." if len(prompt) > 100 else prompt,
                    "response": response[:100] + "..." if len(response) > 100 else response
                }
            }, indent=2))]
        except Exception as e:
            return [TextContent(type="text", text=f"ERROR logging step: {e}")]

    # ── diff_sessions ─────────────────────────────────────────────────────────
    elif name == "diff_sessions":
        if not VP_AVAILABLE:
            return [TextContent(type="text", text="ERROR: veilpiercer not installed.")]

        sid_a = arguments.get("session_a", "")
        sid_b = arguments.get("session_b", "")

        # Close sessions before diffing so all steps are flushed
        for sid in [sid_a, sid_b]:
            if sid in _SESSIONS:
                try:
                    _SESSIONS[sid].__exit__(None, None, None)
                    del _SESSIONS[sid]
                except Exception:
                    pass

        try:
            diff = find_divergence(sid_a, sid_b, db_path=DB_PATH)

            if not diff.get("diverged"):
                return [TextContent(type="text", text=json.dumps({
                    "diverged": False,
                    "message": f"Sessions '{sid_a}' and '{sid_b}' are identical — no divergence detected.",
                    "session_a": sid_a,
                    "session_b": sid_b
                }, indent=2))]

            # Build human-readable diff
            steps_a = diff.get("steps_a", [])
            steps_b = diff.get("steps_b", [])
            fork    = diff.get("fork_step")
            last    = diff.get("last_shared", "start")

            step_summary = []
            for i, (a, b) in enumerate(zip(steps_a, steps_b), 1):
                same = a.get("response") == b.get("response")
                step_summary.append({
                    "step": i,
                    "label": a.get("state_version", f"step-{i}"),
                    "shared": same,
                    "session_a_response": a.get("response", "")[:120],
                    "session_b_response": b.get("response", "")[:120] if not same else "(same)"
                })

            return [TextContent(type="text", text=json.dumps({
                "diverged": True,
                "fork_step": fork,
                "last_shared_state": last,
                "session_a": sid_a,
                "session_b": sid_b,
                "diagnosis": (
                    f"Sessions diverged at step {fork}. "
                    f"Both were identical through '{last}'. "
                    f"Check step {fork} inputs — this is where the data fork occurred."
                ),
                "step_diff": step_summary
            }, indent=2))]

        except Exception as e:
            return [TextContent(type="text", text=f"ERROR diffing sessions: {e}")]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
