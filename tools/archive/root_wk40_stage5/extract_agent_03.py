import json

fn = r"c:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\.cursor\plans\agent_logs\agent_03_TechnicalDirector_Architecture.json"
try:
    with open(fn, 'r', encoding='utf-8') as f:
        d = json.load(f)
        wk17 = d.get('sprints', {}).get('wk17-quality-logic-immersion', {})
    with open('agent_3_wk17_log.json', 'w', encoding='utf-8') as fw:
        json.dump(wk17, fw, indent=2)
except Exception as e:
    print(str(e))
