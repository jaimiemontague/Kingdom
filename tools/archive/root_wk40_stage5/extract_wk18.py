import json
import os

agents = [
    "05_GameplaySystemsDesigner",
    "06_AIBehaviorDirector_LLM",
    "08_UX_UI_Director",
    "12_ToolsDevEx_Lead"
]

base_dir = r"c:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\.cursor\plans\agent_logs"

results = {}

for agent in agents:
    filepath = os.path.join(base_dir, f"agent_{agent}.json")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            d = json.load(f)
            # Find wk18 sprint
            wk18 = d.get("sprints", {}).get("wk18-llm-merger-and-mechanics", {})
            r1 = wk18.get("rounds", {}).get("wk18_r1_kickoff", {})
            results[agent[:2]] = r1.get("response", "NO RESPONSE YET")
    except Exception as e:
        results[agent[:2]] = f"Error reading: {e}"

with open("wk18_r1_summary.json", 'w', encoding='utf-8') as out:
    json.dump(results, out, indent=2)

print("Extraction complete.")
