import json
import os

path = os.path.join('.cursor', 'plans', 'agent_logs', 'agent_01_ExecutiveProducer_PM.json')

with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

sprint_data = {
    "rounds": {
        "wk21_r1_kickoff": {
            "pm_status_summary": {
                "overall_status": "Round 1 - Specs & Conventions",
                "focus": "Defining how to map the existing 2D pixel art onto the 3D Ursina viewport."
            },
            "pm_bug_tickets": [],
            "pm_feature_requests": [
                {
                    "title": "3D Visual Polish Pipeline",
                    "specs": "Replace the basic primitives in the 3D renderer with textured 3D elements or 2D billboards based on art direction."
                }
            ],
            "pm_integration_order": [
                "1. Agent 09: Spec out the approach for billboards vs 3D models."
            ],
            "pm_next_actions_by_agent": {
                "09": {
                    "status": "assigned_active",
                    "asks": [
                        "Define the visual mapping conventions for Ursina. How will we transition the cubes in ursina_renderer.py into something beautiful?"
                    ]
                }
            },
            "pm_agent_prompts": {
                "09": "WK21 Round 1: Spec the transition from basic cubes to polished art. Do we use textured 3D primitives, or 2D billboards that always face the camera? How will we map our existing pixel art from game/graphics/tile_sprites.py into the Ursina renderer?"
            },
            "pm_send_list_minimal": ["09"]
        }
    }
}

data['sprints']['wk21-3d-visual-polish'] = sprint_data

with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)

print("Added WK21 to PM Log.")
