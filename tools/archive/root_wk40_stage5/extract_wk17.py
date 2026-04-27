import json

files = [
    r"c:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\.cursor\plans\agent_logs\agent_05_GameplaySystemsDesigner.json",
    r"c:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\.cursor\plans\agent_logs\agent_06_AIBehaviorDirector_LLM.json",
    r"c:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\.cursor\plans\agent_logs\agent_08_UX_UI_Director.json",
    r"c:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\.cursor\plans\agent_logs\agent_10_PerformanceStability_Lead.json"
]

out = {}
for fn in files:
    try:
        with open(fn, 'r', encoding='utf-8') as f:
            d = json.load(f)
            ag = d.get('agent', {}).get('id', 'unknown')
            out[ag] = d.get('sprints', {}).get('wk17-quality-logic-immersion')
    except Exception as e:
        out[fn] = str(e)

with open(r'c:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\wk17_summary.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, indent=2)

print("done")
