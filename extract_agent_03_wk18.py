import json
import os

filepath = r"c:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\.cursor\plans\agent_logs\agent_03_TechnicalDirector_Architecture.json"
try:
    with open(filepath, 'r', encoding='utf-8') as f:
        d = json.load(f)
        wk18 = d.get('sprints', {}).get('wk18-llm-merger-and-mechanics', {})
        r2 = wk18.get('rounds', {}).get('wk18_r1_kickoff', {}) # They likely logged under r1_kickoff
        
    with open('agent_3_wk18_log.json', 'w', encoding='utf-8') as fw:
        json.dump(wk18, fw, indent=2)
except Exception as e:
    print(str(e))
