import json
from datetime import datetime
file_path = 'C:\\Users\\fyou1\\Desktop\\New folder\\nexus-ultra\\nexus_blackboard.json'
with open(file_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Fix the last element if it's a string
if data.get('task_queue') and isinstance(data['task_queue'][-1], str):
    data['task_queue'][-1] = {
        'task': data['task_queue'][-1],
        'priority': 1,
        'id': 'task_fixed_123'
    }

# Insert custom test task
test_task = {
    'task': 'TEST PROTOCOL ALPHA: The user has requested to see the swarm test its execution capabilities. Write a short, highly enthusiastic 3-sentence summary of VeilPiercer. Output just the summary.',
    'priority': 100,
    'id': 'task_user_test_' + str(datetime.now().timestamp()),
    'timestamp': datetime.now().isoformat()
}

data['task_queue'].insert(0, test_task)

with open(file_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)
print('Test task injected successfully into blackboard!')
