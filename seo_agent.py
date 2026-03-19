"""
seo_agent.py — Autonomous SEO Agent for nexus-ultra
Powered by nexus-prime (local, $0) OR Claude API (optional upgrade)
Usage:
    python seo_agent.py              # analyze all HTML files
    python seo_agent.py index.html   # analyze one file
    python seo_agent.py --fix        # analyze AND auto-apply fixes
"""

import sys
import os
import json
import subprocess
import requests
from pathlib import Path
from datetime import datetime

# Force UTF-8 output on Windows to avoid cp1252 crashes
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Config ────────────────────────────────────────────────────────────────────
REPO_ROOT   = Path(__file__).parent
OLLAMA_URL  = "http://127.0.0.1:11434/api/chat"
MODEL       = "llama3.2:1b"                  # fast, free, always on — swap to nexus-prime for deeper analysis
# MODEL     = "nexus-prime:latest"           # deeper but slower (5.4GB)
# MODEL     = "claude-opus-4-5"             # upgrade: set ANTHROPIC_API_KEY env var
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")

HTML_FILES = [
    "index.html",
]

SEO_PROMPT = """You are an SEO expert agent. Analyze this HTML file and return a JSON object with:
{
  "title": "optimized <title> tag content",
  "description": "optimized meta description (150-160 chars)",
  "keywords": ["keyword1", "keyword2", ...],
  "og_title": "Open Graph title",
  "og_description": "Open Graph description",
  "h1": "recommended H1 text if missing or weak",
  "issues": ["list of SEO issues found"],
  "fixes": [
    {"element": "CSS selector or tag", "attribute": "attr name", "value": "new value"}
  ],
  "score": 0-100
}

Site context: VeilPiercer — AI security swarm, RTX 4060, local CUDA, autonomous agents.
Target keywords: AI security swarm, local CUDA AI, VeilPiercer, nexus prime, offline AI.

HTML to analyze:
"""

# ── Inference ─────────────────────────────────────────────────────────────────
def ask_nexus(prompt: str) -> str:
    """Call nexus-prime via Ollama — free, local."""
    r = requests.post(OLLAMA_URL, json={
        "model": MODEL,
        "stream": False,
        "messages": [{"role": "user", "content": prompt}]
    }, timeout=300)
    return r.json()["message"]["content"]

def ask_claude(prompt: str) -> str:
    """Call Claude API — requires ANTHROPIC_API_KEY."""
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    msg = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text

def ask(prompt: str) -> str:
    if ANTHROPIC_KEY:
        print("  [claude api]")
        return ask_claude(prompt)
    print("  [nexus-prime local]")
    return ask_nexus(prompt)

# ── HTML patching ─────────────────────────────────────────────────────────────
def patch_html(file_path: Path, analysis: dict) -> bool:
    """Apply SEO fixes directly to the HTML file."""
    content = file_path.read_text(encoding="utf-8")
    original = content

    # Title
    if analysis.get("title"):
        import re
        title = analysis["title"]
        if "<title>" in content:
            content = re.sub(r'<title>.*?</title>', f'<title>{title}</title>',
                             content, flags=re.DOTALL)
        else:
            content = content.replace("<head>", f"<head>\n  <title>{title}</title>")

    # Meta description
    if analysis.get("description"):
        desc = analysis["description"]
        import re
        if 'name="description"' in content:
            content = re.sub(r'(<meta\s+name="description"\s+content=")[^"]*(")',
                             f'\\g<1>{desc}\\g<2>', content)
        else:
            content = content.replace("</head>",
                f'  <meta name="description" content="{desc}">\n</head>')

    # OG tags
    if analysis.get("og_title"):
        import re
        if 'property="og:title"' in content:
            content = re.sub(r'(<meta\s+property="og:title"\s+content=")[^"]*(")',
                             f'\\g<1>{analysis["og_title"]}\\g<2>', content)
        else:
            content = content.replace("</head>",
                f'  <meta property="og:title" content="{analysis["og_title"]}">\n</head>')

    if analysis.get("og_description"):
        import re
        if 'property="og:description"' in content:
            content = re.sub(r'(<meta\s+property="og:description"\s+content=")[^"]*(")',
                             f'\\g<1>{analysis["og_description"]}\\g<2>', content)
        else:
            content = content.replace("</head>",
                f'  <meta property="og:description" content="{analysis["og_description"]}">\n</head>')

    if content != original:
        file_path.write_text(content, encoding="utf-8")
        return True
    return False

# ── Main ──────────────────────────────────────────────────────────────────────
def analyze_file(html_path: Path, auto_fix: bool = False) -> dict:
    print(f"\n{'='*60}")
    print(f"Analyzing: {html_path.name}")

    content = html_path.read_text(encoding="utf-8", errors="replace")
    # Truncate at 12K chars for the model
    snippet = content[:12000] + ("\n...[truncated]" if len(content) > 12000 else "")

    raw = ask(SEO_PROMPT + snippet)

    # Extract JSON from response
    import re
    match = re.search(r'\{[\s\S]*\}', raw)
    if not match:
        print("  [WARN] No JSON found in response")
        return {}

    try:
        analysis = json.loads(match.group())
    except json.JSONDecodeError:
        print("  [WARN] JSON parse failed — raw:", raw[:200])
        return {}

    # Print report
    print(f"  Score:       {analysis.get('score', '?')}/100")
    print(f"  Title:       {analysis.get('title', '—')[:80]}")
    print(f"  Description: {analysis.get('description', '—')[:80]}")
    print(f"  Issues:      {len(analysis.get('issues', []))} found")
    for issue in analysis.get("issues", []):
        print(f"    • {issue}")

    if auto_fix:
        changed = patch_html(html_path, analysis)
        print(f"  Patched:     {'[OK] changes applied' if changed else 'no changes needed'}")

    return analysis

def git_commit_push(message: str):
    print(f"\n{'='*60}")
    print("Committing & pushing fixes...")
    for cmd in ["git add -A", f'git commit -m "{message}"', "git push"]:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=REPO_ROOT)
        status = "✓" if r.returncode == 0 else "✗"
        print(f"  {status} {cmd}")
        if r.stderr.strip() and r.returncode != 0:
            print(f"    {r.stderr.strip()[:200]}")

def main():
    args = sys.argv[1:]
    auto_fix = "--fix" in args
    args = [a for a in args if not a.startswith("--")]

    target_files = args if args else HTML_FILES

    print("[SEO] NEXUS SEO AGENT")
    print(f"   Model: {'Claude API' if ANTHROPIC_KEY else 'nexus-prime (local, free)'}")
    print(f"   Mode:  {'AUTO-FIX' if auto_fix else 'ANALYZE ONLY'}")
    print(f"   Files: {len(target_files)}")

    results = {}
    for filename in target_files:
        path = REPO_ROOT / filename
        if not path.exists():
            print(f"\n[SKIP] {filename} not found")
            continue
        results[filename] = analyze_file(path, auto_fix=auto_fix)

    if auto_fix:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        git_commit_push(f"🤖 nexus-prime SEO auto-fix — {timestamp}")
        print(f"\n[DONE] Live at: https://fliptrigga13.github.io/nexus-ultra/")

    # Save report
    report_path = REPO_ROOT / "seo_report.json"
    report_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n[REPORT] Full report saved: seo_report.json")

if __name__ == "__main__":
    main()
