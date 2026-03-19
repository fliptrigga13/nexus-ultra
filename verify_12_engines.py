import socket
import subprocess

ports_to_check = {
    "1. Ollama LLM Engine": 11434,
    "2. COSMOS Orchestration": 9100,
    "3. PSO SWARM BRAIN (Julia/GPU)": 7700,
    "6. EH API": 7701,
    "11. Permanent Hub Server": 7702
}

processes_to_check = {
    "4. Tier-2 Memory Core": "nexus_memory_core.py",
    "5. NEXUS SWARM LOOP": "nexus_swarm_loop.py",
    "7. ANT COLONY ANTENNAE": "nexus_antennae.py",
    "8. INFINITE EVOLUTION ENGINE": "nexus_evolution.py",
    "9. ROGUE SQUAD": "nexus_rogue_agents.py",
    "10. MYCORRHIZAL THOUGHT WEB": "nexus_mycelium.py",
    "12. FEED INGESTOR": "nexus_feed_ingestor.py"
}

def check_port(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

print("\n" + "="*50)
print("NEXUS 12-ENGINE HEALTH CHECK")
print("="*50)

all_good = True

# Check ports
for name, port in ports_to_check.items():
    if check_port(port):
        print(f"[OK] {name} is listening on Port {port}")
    else:
        print(f"[OFFLINE] {name} (Port {port})")
        all_good = False

# Check processes
cmd = 'wmic process get commandline'
try:
    output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
except Exception as e:
    output = ""
    print("Could not verify processes via wmic.")

for name, proc_str in processes_to_check.items():
    if proc_str in output:
        print(f"[OK] {name} is running ({proc_str})")
    else:
        print(f"[OFFLINE] {name} ({proc_str} not found)")
        all_good = False

print("="*50)
if all_good:
    print("ALL 12 ENGINES ARE FULLY OPERATIONAL.")
else:
    print("WARNING: Some engines are offline. Run START_ULTIMATE_GOD_MODE.bat to launch them.")
print("="*50 + "\n")
