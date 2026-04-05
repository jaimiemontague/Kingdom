import json
import os

path = os.path.join('.cursor', 'plans', 'agent_logs', 'agent_01_ExecutiveProducer_PM.json')

with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

r3_round = {
    "pm_status_summary": {
        "overall_status": "Round 3 - Visual Bug Hunt & Tools Expansion",
        "focus": "Fixing the missing grass, noisy road tiles, and black background on stick figures. Also adding a screenshot tool for future automated QA."
    },
    "pm_bug_tickets": [
        "SPRINT-BUG-WK21-01 (Missing Grass)",
        "SPRINT-BUG-WK21-02 (Noisy Road Pixels)",
        "SPRINT-BUG-WK21-03 (Black Stick Figures)"
    ],
    "pm_feature_requests": [
        {
            "title": "Automated Screenshot QA",
            "specs": "Bind F12 to take a screenshot and save it to the docs/screenshots/ directory with a timestamp so the PM can visually inspect the Ursina renderer output without manual human uploads."
        }
    ],
    "pm_integration_order": [
        "1. Agent 12: Add F12 screenshot binding.",
        "2. Agent 09 / Agent 03: Fix the transparency on unit billboards (black boxes).",
        "3. Agent 09 / Agent 03: Fix the missing grass texture and force Nearest-Neighbor filtering on the road tiles so they aren't noisy scattered pixels."
    ],
    "pm_next_actions_by_agent": {
        "12": {
            "status": "assigned_active",
            "asks": [
                "Implement a screenshot tool (F12) that saves PNG files to the docs/screenshots/ folder. Make sure it grabs the Ursina window."
            ]
        },
        "09": {
            "status": "assigned_active",
            "asks": [
                "Diagnose why the road tiles are noisy/scattered pixels and the grass is entirely missing. Also confirm unit billboards need their alpha/transparency flag fixed so they don't render as black stick figures."
            ]
        },
        "03": {
            "status": "assigned_active",
            "asks": [
                "Implement Agent 09's fixes. Ensure Ursina Entity or Texture uses `filtering=None` and `transparency=True` where needed."
            ]
        }
    },
    "pm_agent_prompts": {
        "12": "WK21 Round 3: Implement an F12 screenshot hotkey in the Ursina wrapper that saves PNGs into `docs/screenshots/`.",
        "09": "WK21 Round 3: Visual bugs reported! Grass is missing, road tiles are a noisy line of scattered pixels (filtering issue?), and units are black stick figures (alpha/transparency issue). Prescribe exact fixes.",
        "03": "WK21 Round 3: Coordinate with Agent 09 to apply the transparency/filtering fixes to the Ursina rendering objects."
    },
    "pm_send_list_minimal": ["03", "09", "12"]
}

data['sprints']['wk21-3d-visual-polish']['rounds']['wk21_r3_bug_hunt'] = r3_round

with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)

print("Appended WK21 R3 to PM Log.")
