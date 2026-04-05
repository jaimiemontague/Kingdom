import json
import os

path = os.path.join('.cursor', 'plans', 'agent_logs', 'agent_01_ExecutiveProducer_PM.json')
with open(path, 'r', encoding='utf-8') as f:
    d = json.load(f)

sprints = d.get('sprints', {})
if not sprints:
    print("No sprints found!")
    exit(0)

sprint_key = list(sprints.keys())[-1]
sprint = sprints[sprint_key]
rounds = sprint.get('rounds', {})
if not rounds:
    print(f"No rounds in sprint {sprint_key}")
    exit(0)

round_key = list(rounds.keys())[-1]
rnd = rounds[round_key]

print(f"==================================================")
print(f"SPRINT: {sprint_key}")
print(f"ROUND:  {round_key}")
print(f"==================================================")
print(f"STATUS SUMMARY:\n{json.dumps(rnd.get('pm_status_summary', {}), indent=2)}")
print(f"\nBUG TICKETS:\n{json.dumps(rnd.get('pm_bug_tickets', []), indent=2)}")
print(f"\nFEATURE REQUESTS:\n{json.dumps(rnd.get('pm_feature_requests', []), indent=2)}")
print(f"\nNEXT ACTIONS BY AGENT:\n{json.dumps(rnd.get('pm_next_actions_by_agent', {}), indent=2)}")
print(f"\nSEND LIST MINIMAL:\n{json.dumps(rnd.get('pm_send_list_minimal', []), indent=2)}")
print(f"==================================================")
