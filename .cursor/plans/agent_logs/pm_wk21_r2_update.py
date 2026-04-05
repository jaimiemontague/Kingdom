import json
import os

path = os.path.join('.cursor', 'plans', 'agent_logs', 'agent_01_ExecutiveProducer_PM.json')

with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

r2_round = {
    "pm_status_summary": {
        "overall_status": "Round 2 - Implementation Pipeline",
        "focus": "Replacing basic 3D cubes with textured primitives and billboards using our existing pixel art."
    },
    "pm_bug_tickets": [],
    "pm_feature_requests": [],
    "pm_integration_order": [
        "1. Agent 09: Write the TerrainTextureBridge utility to pull Pygame surfaces into Ursina Textures.",
        "2. Agent 03: Implement the terrain caching and rendering loop in ursina_renderer.py using the new bridge."
    ],
    "pm_next_actions_by_agent": {
        "09": {
            "status": "assigned_active",
            "asks": [
                "Implement the texture bridge utility. Building UV art IS in scope for this milestone. Convert the existing pixel art into cached Ursina textures."
            ]
        },
        "03": {
            "status": "assigned_active",
            "asks": [
                "Implement the rendering logic. Use a startup bake for the terrain textures to avoid in-game lag spikes. We are targeting mainstream PC specs (4GB VRAM), so don't over-engineer memory constraints right now unless it crashes."
            ]
        }
    },
    "pm_agent_prompts": {
        "09": "WK21 Round 2: Implement the Texture Bridge logic. PM Decision: Building UV art and Unit billboards ARE in scope for this sprint. We want it fully visibly mapped.",
        "03": "WK21 Round 2: Implement the Ursina rendering updates. PM Decision: Target standard PC hardware (4GB VRAM). Feel free to use a startup bake for the terrain to avoid frame drops. Map the terrain, buildings, and billboard units using the new textures."
    },
    "pm_send_list_minimal": ["03", "09"]
}

data['sprints']['wk21-3d-visual-polish']['rounds']['wk21_r2_implementation'] = r2_round

with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)

print("Appended WK21 R2 to PM Log.")
