import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
"""
╔══════════════════════════════════════════════════════════════════╗
║  NEXUS DAILY OPS REPORT SYSTEM                                  ║
║  Generates daily improvement boards, achievement logs,          ║
║  and next-day briefings for the swarm                           ║
║  Run: python nexus_daily_report.py                              ║
║  Auto: cron job in server.cjs fires at midnight                 ║
╚══════════════════════════════════════════════════════════════════╝
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, date, timedelta
from collections import defaultdict

BASE_DIR     = Path(__file__).parent
MEMORY_FILE  = BASE_DIR / "nexus_memory.json"
EVOLUTION    = BASE_DIR / "evolution_log.json"
BLACKBOARD   = BASE_DIR / "nexus_blackboard.json"
REPORTS_DIR  = BASE_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

TODAY        = date.today().isoformat()
REPORT_FILE  = REPORTS_DIR / f"REPORT_{TODAY}.md"
BOARD_FILE   = REPORTS_DIR / "improvement_board.json"

# ── DATA LOADERS ────────────────────────────────────────────────────────────
def load_json(path: Path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except:
            return {} if "{" in path.read_text(encoding="utf-8")[:1] else []
    return []

def load_memory():
    raw = load_json(MEMORY_FILE)
    if isinstance(raw, list):
        return raw
    return raw.get("memories", [])

def load_evolution():
    raw = load_json(EVOLUTION)
    if isinstance(raw, dict):
        return raw.get("entries", [])
    return raw if isinstance(raw, list) else []

def load_blackboard():
    raw = load_json(BLACKBOARD)
    return raw if isinstance(raw, dict) else {}

# ── ANALYSIS ENGINE ──────────────────────────────────────────────────────────
def analyze_memory(memories: list, target_date: str = TODAY) -> dict:
    """Pull today's cycles from memory."""
    today_entries = [m for m in memories if str(m.get("timestamp", "")).startswith(target_date)]
    all_scores    = [float(m["score"]) for m in today_entries if "score" in m and m["score"] is not None]
    mvp_counts    = defaultdict(int)
    lessons       = []
    achievements  = []
    challenges    = []

    for m in today_entries:
        if m.get("mvp"):
            mvp_counts[m["mvp"]] += 1
        if m.get("lesson"):
            lessons.append(str(m["lesson"])[:200])

    # Extract achievements (high-score cycles) and challenges (low-score)
    for m in today_entries:
        score = float(m.get("score", 0))
        lesson = str(m.get("lesson", ""))[:150]
        if score >= 0.75:
            achievements.append(f"Score {score:.2f} — {lesson}")
        elif score < 0.40:
            challenges.append(f"Score {score:.2f} — {lesson}")

    return {
        "date": target_date,
        "cycle_count": len(today_entries),
        "avg_score": round(sum(all_scores) / len(all_scores), 3) if all_scores else 0.0,
        "peak_score": round(max(all_scores), 3) if all_scores else 0.0,
        "min_score": round(min(all_scores), 3) if all_scores else 0.0,
        "mvp_leaderboard": dict(sorted(mvp_counts.items(), key=lambda x: x[1], reverse=True)),
        "achievements": achievements[:8],
        "challenges": challenges[:5],
        "lessons": lessons[-5:],  # last 5 for brevity
    }

def analyze_evolution(evo_entries: list, target_date: str = TODAY) -> dict:
    today_evo = [e for e in evo_entries if str(e.get("timestamp", "")).startswith(target_date)]
    all_scores = [float(e["quality_score"]) for e in today_evo if "quality_score" in e]
    improvements = []
    for e in today_evo:
        if e.get("improvements"):
            improvements.append(str(e["improvements"])[:200])
    return {
        "generations_today": len(today_evo),
        "facts_added_today": sum(int(e.get("facts_added", 0)) for e in today_evo),
        "avg_quality": round(sum(all_scores) / len(all_scores), 3) if all_scores else 0.0,
        "top_improvements": improvements[-3:],
    }

def build_score_trend(memories: list, days: int = 7) -> list:
    """Build a 7-day score trend for the improvement board."""
    trend = []
    for i in range(days - 1, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        day_entries = [m for m in memories if str(m.get("timestamp", "")).startswith(d)]
        scores      = [float(m["score"]) for m in day_entries if "score" in m and m["score"] is not None]
        trend.append({
            "date":        d,
            "cycles":      len(day_entries),
            "avg_score":   round(sum(scores) / len(scores), 3) if scores else None,
            "peak_score":  round(max(scores), 3) if scores else None,
        })
    return trend

# ── REPORT WRITER ────────────────────────────────────────────────────────────
def write_report(mem_stats: dict, evo_stats: dict, bb: dict, trend: list) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    mvp_board = "\n".join(
        f"  {i+1}. **{agent}** — {count} MVP cycles"
        for i, (agent, count) in enumerate(mem_stats["mvp_leaderboard"].items())
    ) or "  No MVP data yet"

    achievements = "\n".join(
        f"  - ✅ {a}" for a in mem_stats["achievements"]
    ) or "  - No high-score cycles today yet"

    challenges = "\n".join(
        f"  - ⚠️ {c}" for c in mem_stats["challenges"]
    ) or "  - No major challenges logged"

    lessons = "\n".join(
        f"  > {l}" for l in mem_stats["lessons"]
    ) or "  > No lessons extracted yet"

    improvements = "\n".join(
        f"  - {imp}" for imp in evo_stats["top_improvements"]
    ) or "  - No evolution improvements logged"

    # Trend table
    trend_rows = ""
    for t in trend:
        avg = f"{t['avg_score']:.3f}" if t["avg_score"] is not None else "—"
        peak = f"{t['peak_score']:.3f}" if t["peak_score"] is not None else "—"
        trend_rows += f"| {t['date']} | {t['cycles']} | {avg} | {peak} |\n"

    # Streak (days above 0.75)
    streak = 0
    for t in reversed(trend):
        if t["avg_score"] and t["avg_score"] >= 0.75:
            streak += 1
        else:
            break

    # Next-day brief
    vp_task = "Generate 5 specific outreach messages for VeilPiercer targeting AI developers who use Cursor/Windsurf. Include pricing anchor at $197."
    if mem_stats["avg_score"] < 0.50:
        directive = "PRIORITY: Scores are low — swarm must focus on specificity and actionable deliverables only. No generic outputs."
    elif mem_stats["avg_score"] < 0.75:
        directive = "PRIORITY: Push score above 0.75. Each agent must deliver measurable, VeilPiercer-specific output."
    else:
        directive = "PRIORITY: Maintain momentum. Push for 0.90+ by increasing insight quality and customer-specific targeting."

    report = f"""# 📊 NEXUS DAILY OPS REPORT
**Date:** {mem_stats["date"]}  
**Generated:** {now}  
**Mission:** VeilPiercer — $197 Sales · Market Dominance

---

## 🏆 TODAY'S PERFORMANCE

| Metric | Value |
|---|---|
| Swarm Cycles Completed | {mem_stats["cycle_count"]} |
| Average Score | **{mem_stats["avg_score"]}** |
| Peak Score | {mem_stats["peak_score"]} |
| Minimum Score | {mem_stats["min_score"]} |
| Evolution Generations | {evo_stats["generations_today"]} |
| Facts Added to Memory | {evo_stats["facts_added_today"]} |
| Avg Evolution Quality | {evo_stats["avg_quality"]} |
| Quality Streak (days ≥0.75) | {streak} days |

---

## 🏅 MVP LEADERBOARD — TODAY

{mvp_board}

---

## ✅ ACHIEVEMENTS

{achievements}

---

## ⚠️ CHALLENGES

{challenges}

---

## 💡 LESSONS LEARNED

{lessons}

---

## 📈 7-DAY SCORE TREND

| Date | Cycles | Avg Score | Peak Score |
|---|---|---|---|
{trend_rows}
---

## 🧠 TOP EVOLUTION IMPROVEMENTS

{improvements}

---

## 📋 NEXT-DAY BRIEF — READ THIS FIRST TOMORROW

> **Directive for all agents on {(date.today() + timedelta(days=1)).isoformat()}:**
> {directive}
>
> **VeilPiercer Objective:** {vp_task}
>
> **Context from today:** Completed {mem_stats["cycle_count"]} cycles. 
> Best lesson: {mem_stats["lessons"][-1] if mem_stats["lessons"] else 'No lessons yet — focus on specificity.'}
>
> **MVP to watch:** {list(mem_stats["mvp_leaderboard"].keys())[0] if mem_stats["mvp_leaderboard"] else 'REWARD'} — replicate this agent's approach.

---

*Auto-generated by NEXUS Daily Report System · {now}*
"""
    return report

# ── BOARD UPDATER ────────────────────────────────────────────────────────────
def update_board(mem_stats: dict, evo_stats: dict, trend: list):
    """Update the persistent improvement board JSON for the HTML dashboard."""
    board = load_json(BOARD_FILE) if BOARD_FILE.exists() else {"reports": [], "trend": []}
    if not isinstance(board, dict):
        board = {"reports": [], "trend": []}

    # Add today's entry
    today_entry = {
        "date":           mem_stats["date"],
        "cycles":         mem_stats["cycle_count"],
        "avg_score":      mem_stats["avg_score"],
        "peak_score":     mem_stats["peak_score"],
        "achievements":   len(mem_stats["achievements"]),
        "challenges":     len(mem_stats["challenges"]),
        "facts_added":    evo_stats["facts_added_today"],
        "evo_quality":    evo_stats["avg_quality"],
        "mvp_today":      list(mem_stats["mvp_leaderboard"].keys())[0] if mem_stats["mvp_leaderboard"] else "—",
        "report_file":    f"REPORT_{mem_stats['date']}.md",
    }

    # Replace existing entry for today or append
    reports = board.get("reports", [])
    existing = next((i for i, r in enumerate(reports) if r["date"] == mem_stats["date"]), None)
    if existing is not None:
        reports[existing] = today_entry
    else:
        reports.append(today_entry)
    reports = sorted(reports, key=lambda x: x["date"], reverse=True)[:30]  # keep 30 days

    board["reports"] = reports
    board["trend"]   = trend
    board["updated"] = datetime.now().isoformat()

    BOARD_FILE.write_text(json.dumps(board, indent=2, ensure_ascii=False), encoding="utf-8")
    return board

# ── SWARM INJECTION ──────────────────────────────────────────────────────────
def inject_brief_into_swarm(mem_stats: dict) -> bool:
    """Push tomorrow's brief as a high-priority task into the swarm queue."""
    bb = load_json(BLACKBOARD) if isinstance(load_json(BLACKBOARD), dict) else {}
    
    if mem_stats["avg_score"] < 0.50:
        brief = f"DAILY BRIEF: Yesterday scored {mem_stats['avg_score']:.2f}. FOCUS ON SPECIFICITY. VeilPiercer task: Draft 3 actionable outreach templates for $197 buyers. No generic AI content."
    else:
        brief = f"DAILY BRIEF: Yesterday scored {mem_stats['avg_score']:.2f} over {mem_stats['cycle_count']} cycles. MVP: {list(mem_stats['mvp_leaderboard'].keys())[0] if mem_stats['mvp_leaderboard'] else 'REWARD'}. Today: Generate VeilPiercer sales strategy with specific channels, messages, and daily actions."

    queue = bb.get("task_queue", [])
    if not isinstance(queue, list):
        queue = []

    entry = {
        "task":      brief,
        "priority":  10,
        "id":        f"daily_brief_{TODAY}",
        "timestamp": datetime.now().isoformat(),
        "source":    "DAILY_REPORT_SYSTEM"
    }
    # Don't duplicate
    if not any(t.get("id") == entry["id"] for t in queue):
        queue.insert(0, entry)
        bb["task_queue"] = queue
        BLACKBOARD.write_text(json.dumps(bb, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    return False

# ── MAIN ─────────────────────────────────────────────────────────────────────
def main(target_date: str = TODAY):
    print(f"\n⚡ NEXUS DAILY REPORT — {target_date}")
    print("=" * 60)

    memories  = load_memory()
    evo       = load_evolution()
    bb        = load_blackboard()

    print(f"  Memory entries loaded:     {len(memories)}")
    print(f"  Evolution entries loaded:  {len(evo)}")

    mem_stats = analyze_memory(memories, target_date)
    evo_stats = analyze_evolution(evo, target_date)
    trend     = build_score_trend(memories, days=7)

    print(f"\n  Today's cycles:   {mem_stats['cycle_count']}")
    print(f"  Today's avg score: {mem_stats['avg_score']}")
    print(f"  Today's peak:      {mem_stats['peak_score']}")

    report = write_report(mem_stats, evo_stats, bb, trend)
    REPORT_FILE.write_text(report, encoding="utf-8")
    print(f"\n  ✅ Report saved → {REPORT_FILE}")

    board = update_board(mem_stats, evo_stats, trend)
    print(f"  ✅ Board updated → {BOARD_FILE}")

    injected = inject_brief_into_swarm(mem_stats)
    if injected:
        print(f"  ✅ Tomorrow's brief injected into swarm queue (priority 10)")
    else:
        print(f"  ℹ️  Brief already in queue for today")

    print(f"\n{'='*60}")
    print(f"  REPORT COMPLETE. Open: reports/REPORT_{target_date}.md")
    return report

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else TODAY
    main(target)
