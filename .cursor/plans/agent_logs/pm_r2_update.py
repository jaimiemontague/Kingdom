import json
import os

path = os.path.join('.cursor', 'plans', 'agent_logs', 'agent_01_ExecutiveProducer_PM.json')

with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# PM decisions based on R1 questions
r2_round = {
    "pm_status_summary": {
        "overall_status": "Round 2 - Implementation Pipeline",
        "focus": "Implementing the input bridge specs from Round 1. Agent 08 maps mouse to Pygame screen, Agent 03 adds floor raycasting, Agent 12 adds the debug telemetry."
    },
    "pm_bug_tickets": [],
    "pm_feature_requests": [],
    "pm_integration_order": [
        "1. Agent 08: Implement Ursina window to Pygame screen coordinate mapping.",
        "2. Agent 03: Implement 3D floor raycast and connect it to Pygame coordinate generation.",
        "3. Agent 12: Implement the debug log line to test the inputs."
    ],
    "pm_next_actions_by_agent": {
        "08": {
            "status": "assigned_active",
            "asks": [
                "Implement `get_mouse_pos()` in `UrsinaInputManager`. Use fixed 1080p virtual screen scale strategy. Keep Pygame screen resolution fixed and map the Ursina mouse into it."
            ]
        },
        "03": {
            "status": "assigned_active",
            "asks": [
                "Build the floor raycast method. Focus default camera on the Castle + surrounding tiles. DO NOT move the 2D engine camera when panning in 3D yet."
            ]
        },
        "12": {
            "status": "assigned_active",
            "asks": [
                "Add the `KINGDOM_URSINA_DEBUG_INPUT=1` env var debug print. Simple `print()` is fine for now."
            ]
        }
    },
    "pm_agent_prompts": {
        "08": "WK20 Round 2: Implement get_mouse_pos() in UrsinaInputManager. PM Decision: Keep the fixed 1080p virtual screen and apply scaling from current Ursina window size to the 1920x1080 virtual engine screen.",
        "03": "WK20 Round 2: Implement floor raycast in Ursina (y=0) and convert into simulated screen coordinates to feed Pygame. PM Decision: Default camera should see Castle + margin. Do NOT sync 2D engine camera with 3D pans for now.",
        "12": "WK20 Round 2: Implement debug print. PM Decision: Use KINGDOM_URSINA_DEBUG_INPUT=1 env var for activation, and standard print() is fine. No logger needed."
    },
    "pm_send_list_minimal": ["03", "08", "12"]
}

data['sprints']['wk20-ui-input-bridge']['rounds']['wk20_r2_implementation'] = r2_round

with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)

print("Successfully appended R2 to agent 01 log.")
