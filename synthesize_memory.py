import json

with open(r'nexus_session_facts.json', encoding='utf-8') as f:
    d = json.load(f)

facts = d.get('facts', [])
seen = set()
unique = []
for fct in sorted(facts, key=lambda x: x.get('importance', 0), reverse=True):
    c = fct.get('content', '')[:60]
    if c not in seen:
        seen.add(c)
        unique.append(fct)

print(f'TOTAL: {len(facts)} facts | {len(unique)} unique')
print()
print('=== TOP 3 STRATEGIC INSIGHTS (importance, deduplicated) ===')
for i, fct in enumerate(unique[:3]):
    imp = fct.get('importance', 0)
    content = fct.get('content', '')
    tags = fct.get('tags', [])
    print(f'  {i+1}. [{imp:.2f}] {content}')
    print(f'       tags={tags}')

print()
print('=== ALL HIGH-VALUE FACTS (importance >= 0.85) ===')
high = [fct for fct in unique if fct.get('importance', 0) >= 0.85]
for fct in high:
    imp = fct.get('importance', 0)
    content = fct.get('content', '')
    print(f'  [{imp:.2f}] {content}')
print(f'  Total: {len(high)} high-value facts')

print()
print('=== AGENT RANKED IMPROVEMENT PLAN (from real evolution data) ===')
evo_facts = [fct for fct in facts if fct.get('type') == 'evolution']
print(f'  Evolution facts: {len(evo_facts)}')
mem_facts = [fct for fct in facts if fct.get('type') == 'memory_flag']
print(f'  Memory flags: {len(mem_facts)}')
