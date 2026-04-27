import json
import os

log_path = 'c:\\Users\\Jaimie Montague\\OneDrive\\Documents\\Kingdom\\.cursor\\plans\\agent_logs\\agent_01_ExecutiveProducer_PM.json'
with open(log_path, 'r') as f:
    data = json.load(f)

# Add wk22
data['sprints']['wk22-3d-refinement'] = {
    "rounds": {
        "wk22_r1_kickoff": {
            "pm_status_summary": "WK21 completed visual mapping. Now addressing gameplay-breaking visual and input issues: inverted terrain, missing shadows, translucent fog of war, and broken hotkeys.",
            "pm_bug_tickets": [
                {
                    "id": "SPRINT-BUG-001",
                    "title": "Trees/Terrain textures are upside down",
                    "severity": "major",
                    "owner_agent": "09_ArtDirector_Pixel_Animation_VFX",
                    "reporter": "human_playtest",
                    "repro_steps": ["Launch game", "Observe trees randomly generated on map"],
                    "expected": "Trees face right side up",
                    "actual": "Trees are upside down",
                    "acceptance_test": ["Launch game and visually confirm tree orientation"],
                    "status": "assigned"
                },
                {
                    "id": "SPRINT-BUG-002",
                    "title": "Shadows not casting",
                    "severity": "polish",
                    "owner_agent": "03_TechnicalDirector_Architecture",
                    "reporter": "human_playtest",
                    "repro_steps": ["Launch game", "Observe buildings and entities"],
                    "expected": "Directional light casts shadows from 3D objects",
                    "actual": "No shadows visible",
                    "acceptance_test": ["Launch game and visually confirm shadow casting from buildings/entities"],
                    "status": "assigned"
                },
                {
                    "id": "SPRINT-BUG-003",
                    "title": "Fog of War visible everywhere",
                    "severity": "major",
                    "owner_agent": "09_ArtDirector_Pixel_Animation_VFX",
                    "reporter": "human_playtest",
                    "repro_steps": ["Launch game"],
                    "expected": "Unexplored areas are black/grey or visually obscured",
                    "actual": "Terrain is visible everywhere, monsters just pop in",
                    "acceptance_test": ["Unexplored areas must visually block the terrain"],
                    "status": "assigned"
                },
                {
                    "id": "SPRINT-BUG-004",
                    "title": "Hotkeys are completely broken",
                    "severity": "blocker",
                    "owner_agent": "08_UX_UI_Director",
                    "reporter": "human_playtest",
                    "repro_steps": ["Launch game", "Press hotkeys for build/menu/etc"],
                    "expected": "Hotkeys trigger corresponding UI/game actions",
                    "actual": "Hotkeys do not respond",
                    "acceptance_test": ["Press standard hotkeys and confirm they function"],
                    "status": "assigned"
                }
            ],
            "pm_feature_requests": [],
            "pm_integration_order": [
                "03_TechnicalDirector_Architecture (Shadows)",
                "09_ArtDirector_Pixel_Animation_VFX (Terrain orientation, Fog of War visuals)",
                "08_UX_UI_Director (Hotkeys)"
            ],
            "pm_next_actions_by_agent": {
                "03_TechnicalDirector_Architecture": "Implement directional light shadow casting in Ursina renderer.",
                "09_ArtDirector_Pixel_Animation_VFX": "Fix the texture coordinate mapping or rotation for trees/terrain so they are upright. Adjust the fog of war visual overlay so unexplored tiles are visibly dark.",
                "08_UX_UI_Director": "Diagnose and repair the hotkey event delegation from Ursina through to the Pygame/simulation layer."
            },
            "pm_agent_prompts": {
                "03_TechnicalDirector_Architecture": "Review Bug Ticket SPRINT-BUG-002. Enable shadow casting for our 3D entities in the Ursina renderer. Ensure it doesn't catastrophically tank performance.",
                "09_ArtDirector_Pixel_Animation_VFX": "Review Bug Tickets SPRINT-BUG-001 and SPRINT-BUG-003. Fix the upside-down trees by correcting UVs or entity rotation. Also, adjust the visual presentation of Fog of War in the 3D renderer so it actually obscures the terrain like a traditional RTS, instead of just hiding entities.",
                "08_UX_UI_Director": "Review Bug Ticket SPRINT-BUG-004. Hotkeys are dead. Figure out where the input events are being swallowed or failing to map in the new 3D integration and fix them."
            },
            "pm_send_list_minimal": ["03", "08", "09"]
        }
    }
}

with open(log_path, 'w') as f:
    json.dump(data, f, indent=4)
