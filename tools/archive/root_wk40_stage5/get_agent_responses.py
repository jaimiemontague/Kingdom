import json

agents = ['03_TechnicalDirector_Architecture', '08_UX_UI_Director', '09_ArtDirector_Pixel_Animation_VFX']
sprint_name = 'wk22-3d-refinement'
round_name = 'wk22_r1_kickoff'

print('--- AGENT RESPONSES ---')
for a in agents:
    path = f'.cursor/plans/agent_logs/agent_{a}.json'
    try:
        with open(path, 'r') as f:
            d = json.load(f)
            r = d.get('sprints', {}).get(sprint_name, {}).get('rounds', {}).get(round_name, {})
            print(f'\n=== {a} ===')
            if not r:
                print('No round data found.')
                continue
            print(f'Status: {r.get("agent_status")}')
            print(f'Done: {r.get("work_completed")}')
            print(f'Remaining: {r.get("work_remaining")}')
            print(f'Issues: {r.get("issues_encountered")}')
            if r.get('qa_results'):
                print(f'QA Results: {r.get("qa_results")}')
    except Exception as e:
        print(f'\n=== {a} === ERROR reading: {e}')
