import re

path = r"C:\Users\fyou1\Desktop\New folder\nexus-ultra\server.cjs"
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

# 1. Switch to PowerShell shell + add PS_OPTS constant
c = c.replace(
    "// ── Execute a single tool call ────────────────────────────────────\nasync function executeTool(name, args) {",
    "// ── Execute a single tool call ────────────────────────────────────\nconst _PS = { encoding:'utf8', shell:'powershell.exe', timeout:120000, maxBuffer:4*1024*1024,\n  cwd:'C:\\\\Users\\\\fyou1\\\\Desktop\\\\New folder\\\\nexus-ultra' };\n\nasync function executeTool(name, args) {"
)

# 2. cmd tool: use PowerShell
c = c.replace(
    "      case 'cmd': {\n        const out = execSync(args.command, {\n          encoding: 'utf8', shell: 'cmd.exe',\n          timeout: 120000, maxBuffer: 4 * 1024 * 1024,\n          cwd: 'C:\\\\Users\\\\fyou1\\\\Desktop\\\\New folder\\\\nexus-ultra'\n        });\n        return { ok: true, output: out.slice(0, 3000) || '(no output)' };\n      }",
    "      case 'cmd': {\n        const out = execSync(args.command, { ..._PS });\n        return { ok: true, output: (out||'(no output)').slice(0, 3000) };\n      }"
)

# 3. pip tool: use python -m pip primary via PowerShell
old_pip = """      case 'pip': {
        let pipOut = '';
        try {
          pipOut = execSync(`python -m pip install ${args.package} --quiet`, { ..._PS_OPTS });
        } catch(e1) {
          try {
            pipOut = execSync(`pip install ${args.package}`, { ..._PS_OPTS });
          } catch(e2) {
            return { ok: false, output: `pip failed: ${e1.stderr||e1.message}\\n${e2.stderr||e2.message}` };
          }
        }
        return { ok: true, output: (pipOut||'Already installed.').slice(0,2000)+' (done)' };
      }"""

# Find and replace the existing pip case
pip_pattern = r"      case 'pip': \{.*?\n      \}"
new_pip = """      case 'pip': {
        let pipOut = '';
        try {
          pipOut = execSync(`python -m pip install ${args.package} --quiet`, { ..._PS });
        } catch(e1) {
          try {
            pipOut = execSync(`pip install ${args.package}`, { ..._PS });
          } catch(e2) {
            return { ok: false, output: 'pip failed:\\n' + (e1.stderr||e1.message||'') + '\\n' + (e2.stderr||e2.message||'') };
          }
        }
        return { ok: true, output: (pipOut||'Already installed.').slice(0,2000) + ' \\u2705' };
      }"""
c = re.sub(pip_pattern, new_pip, c, flags=re.DOTALL, count=1)

# 4. npm: use PS
c = c.replace(
    "          { encoding: 'utf8', shell: 'cmd.exe', timeout: 60000, maxBuffer: 2e6,\n            cwd: 'C:\\\\Users\\\\fyou1\\\\Desktop\\\\New folder\\\\nexus-ultra' }",
    "          { ..._PS, timeout: 60000 }"
)

# 5. Default model -> qwen2.5-coder:7b (better tool-use format)
c = c.replace(
    "const { message, model = 'nexus-prime:latest' } = req.body || {};",
    "const { message, model = 'qwen2.5-coder:7b' } = req.body || {};"
)

# 6. MAX_STEPS 15 -> 20
c = c.replace("  const MAX_STEPS = 15;", "  const MAX_STEPS = 20;")

# 7. No-tool retry logic instead of immediate done
c = c.replace(
    """    const tool = parseTool(reply);
    if (!tool) {
      // No tool call — AI is done or gave a plain response
      send('done', reply.trim() || 'Task complete.');
      break;
    }""",
    """    const tool = parseTool(reply);
    if (!tool) {
      noToolStreak = (noToolStreak||0) + 1;
      if (noToolStreak >= 2) { send('done', visibleText||reply.trim()||'Task complete.'); break; }
      messages.push({ role: 'assistant', content: reply });
      messages.push({ role: 'user', content: 'You MUST use a <TOOL> call now. Either take the next action OR call <TOOL>{"name":"done","args":{"summary":"what was done"}}</TOOL> if finished. Do not write text without a tool tag.' });
      continue;
    }
    noToolStreak = 0;"""
)

# 8. Better feedback prompt after tool result
c = c.replace(
    "    messages.push({ role: 'user',      content: `Tool result for ${tool.name}:\\n${result.output}\\n\\nContinue with the next step.` });",
    "    const _st = result.ok ? 'SUCCESS' : 'FAILED';\n    messages.push({ role: 'user', content: `Tool ${_st}. Output:\\n${result.output}\\n\\nNext step: use a <TOOL> call to continue, or call done tool if task is fully complete.` });"
)

# 9. start message
c = c.replace(
    "  send('start', `\ud83e\udd16 NEXUS AGENT starting \u2014 model: ${model}`);",
    "  let noToolStreak = 0;\n  send('start', `\ud83e\udd16 NEXUS AGENT \u2014 model: ${model}`);"
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)

print("PATCHED OK")
# Verify key changes
for needle, label in [
    ("powershell.exe", "PowerShell shell"),
    ("qwen2.5-coder:7b", "model default"),
    ("MAX_STEPS = 20", "max steps"),
    ("noToolStreak", "retry logic"),
    ("python -m pip", "pip primary"),
]:
    found = needle in c
    print(f"  {'OK' if found else 'MISSING'}: {label}")
