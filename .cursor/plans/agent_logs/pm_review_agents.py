import json
import os

agents = {
    "03": "agent_03_TechnicalDirector_Architecture.json",
    "08": "agent_08_UX_UI_Director.json",
    "12": "agent_12_ToolsDevEx_Lead.json"
}

sprint_key = "wk20-ui-input-bridge"
round_key = "wk20_r1_kickoff"

for agent_id, filename in agents.items():
    path = os.path.join('.cursor', 'plans', 'agent_logs', filename)
    print(f"--- AGENT {agent_id} ---")
    if not os.path.exists(path):
        print(f"File not found: {path}")
        continue
    with open(path, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
            sprint_data = data.get('sprints', {}).get(sprint_key, {})
            round_data = sprint_data.get('rounds', {}).get(round_key, {})
            print(json.dumps(round_data, indent=2))
        except Exception as e:
            print(f"Error parsing {filename}: {e}")
    print()
