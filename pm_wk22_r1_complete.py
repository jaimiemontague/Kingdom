import json
import os

log_path = 'c:\\Users\\Jaimie Montague\\OneDrive\\Documents\\Kingdom\\.cursor\\plans\\agent_logs\\agent_01_ExecutiveProducer_PM.json'
with open(log_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Update wk22 r1 status
r1 = data['sprints']['wk22-3d-refinement']['rounds']['wk22_r1_kickoff']
r1['pm_status_summary'] = "WK22 Round 1 completed. Active agents (03, 08, 09) pushed their code and reported success. QA Smoke and Asset gates passed."
r1['pm_agent_status'] = {
    "03": "complete (added lit_with_shadows_shader, DirectionalLight)",
    "08": "complete (fixed hotkey bindings)",
    "09": "complete (removed inverted scale, added fog overlay quad based on visibility)"
}
r1['pm_qa_status'] = "PASS"

# We should add Round 2 (Bug Hunt & Polish or Playtest)
data['sprints']['wk22-3d-refinement']['rounds']['wk22_r2_playtest'] = {
    "pm_status_summary": "Ready for Jaimie to playtest the game and verify the 3D refinement fixes.",
    "pm_next_actions": [
        "Jaimie: Playtest the game with the ursina renderer (python main.py --renderer ursina)",
        "Jaimie: Validate that trees are upright, buildings cast shadows, fog obscures terrain, and hotkeys work.",
        "Jaimie: Report any remaining bugs or confirm completion."
    ]
}

with open(log_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=4)
