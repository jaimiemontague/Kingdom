import json

agents = ['03_TechnicalDirector_Architecture', '08_UX_UI_Director', '09_ArtDirector_Pixel_Animation_VFX']

print('--- AGENT RESPONSES ---')
for a in agents:
    path = f'.cursor/plans/agent_logs/agent_{a}.json'
    try:
        with open(path, 'r', encoding='utf-8') as f:
            d = json.load(f)
            sprints = d.get('sprints', {})
            if not sprints:
                continue
            last_sprint_key = list(sprints.keys())[-1]
            last_round_key = list(sprints[last_sprint_key]['rounds'].keys())[-1]
            r = sprints[last_sprint_key]['rounds'][last_round_key]
            print(f'\n=== {a} | {last_sprint_key} | {last_round_key} ===')
            if 'response' in r:
                resp = r['response']
                print(f'Status: {resp.get("status")}')
                print('Summary:', resp.get('summary_bullets', []))
                print('QA Results:', r.get('qa_results', resp.get('qa_results')))
            else:
                for k in r:
                    if k not in ['prompt_text', 'pm_agent_prompt']:
                        print(f'{k}: {r[k]}')
    except Exception as e:
        print(f'\n=== {a} === ERROR reading: {e}')
