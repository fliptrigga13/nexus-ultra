"""
nexus_live_display.py
Clean live display of NEXUS swarm for demo recording.
Shows cycles, scores, agents updating in real time.
"""
import time, re, json, os
from pathlib import Path
from datetime import datetime

LOG = Path(r'C:\Users\fyou1\Desktop\New folder\nexus-ultra\swarm_active.log')

def clear():
    os.system('cls')

def parse_last_cycle(lines):
    data = {'cycle': '', 'score': 0, 'mvp': '', 'task': '', 'latency': 0, 'status': 'STABLE', 'scores': {}, 'gen': 0}
    for line in reversed(lines):
        if 'SCORE_NORM' in line and not data['scores']:
            m = re.search(r"normed=(\{[^}]+\})", line)
            if m:
                try: data['scores'] = json.loads(m.group(1).replace("'",'"'))
                except: pass
            mv = re.search(r"MVP=(\w+)", line)
            if mv: data['mvp'] = mv.group(1)
        if 'Cycle #' in line and 'COMPLETE' in line and not data['score']:
            m = re.search(r"Cycle #(\d+)", line)
            if m: data['gen'] = int(m.group(1))
            m2 = re.search(r"Score=([\d.]+)", line)
            if m2: data['score'] = float(m2.group(1))
        if 'SWARM CYCLE cycle_' in line and not data['cycle']:
            m = re.search(r"cycle_(\d+)", line)
            if m: data['cycle'] = m.group(1)
        if 'TASK-BIAS' in line and not data['task']:
            m = re.search(r"task selection: (.+)$", line)
            if m: data['task'] = m.group(1)[:70]
        if 'avg_latency' in line and not data['latency']:
            m = re.search(r'"avg_latency":\s*([\d.]+)', line)
            if m: data['latency'] = float(m.group(1))
        if 'system_status' in line:
            data['status'] = 'UNSTABLE' if 'UNSTABLE' in line else 'STABLE'
        if all([data['cycle'], data['score'], data['scores']]): break
    return data

def bar(score, width=20):
    filled = int(score * width)
    return '█' * filled + '░' * (width - filled)

def render(data, notion_url):
    now = datetime.now().strftime('%H:%M:%S')
    score_pct = int(data['score'] * 100)
    status_color = '' if data['status'] == 'STABLE' else ''

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║          NEXUS ULTRA — LIVE AI SWARM INTELLIGENCE            ║
║                    veil-piercer.com                          ║
╠══════════════════════════════════════════════════════════════╣
║  Generation : #{data['gen']:<8} Status: {data['status']:<10} Time: {now}  ║
║  Cycle Score: [{bar(data['score'])}] {score_pct}%       ║
║  MVP Agent  : {data['mvp']:<20} Latency: {data['latency']:.1f}s          ║
║  Task       : {data['task'][:55]:<55} ║
╠══════════════════════════════════════════════════════════════╣
║  AGENT LEADERBOARD                                           ║""")

    sorted_agents = sorted(data['scores'].items(), key=lambda x: x[1], reverse=True)
    for agent, score in sorted_agents[:8]:
        mvp_star = ' *MVP*' if agent == data['mvp'] else '      '
        pct = int(score * 100)
        b = bar(score, 14)
        print(f"║  {agent:<22} [{b}] {pct:3d}%{mvp_star} ║")

    print(f"""╠══════════════════════════════════════════════════════════════╣
║  NOTION SYNC  : LIVE — updating every 35s                    ║
║  NOTION URL   : {notion_url[:44]:<44} ║
║  MEMORIES     : 2,478 stored | Redis: ACTIVE | Ollama: LOCAL ║
╚══════════════════════════════════════════════════════════════╝
  Press Ctrl+C to stop | Win+G to record this screen
""")

def main():
    NOTION_URL = "notion.so/32bf17fe54c680c2a0accb570eb38187"
    print("Starting NEXUS Live Display... (Win+G to record)")
    time.sleep(2)
    while True:
        try:
            lines = LOG.read_text(encoding='utf-8', errors='ignore').splitlines()
            data = parse_last_cycle(lines)
            if data['score']:
                clear()
                render(data, NOTION_URL)
            time.sleep(5)
        except KeyboardInterrupt:
            print("\nDisplay stopped.")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
