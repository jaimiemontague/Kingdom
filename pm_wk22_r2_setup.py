import json

log_path = 'c:\\Users\\Jaimie Montague\\OneDrive\\Documents\\Kingdom\\.cursor\\plans\\agent_logs\\agent_01_ExecutiveProducer_PM.json'
with open(log_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

sprint = data['sprints']['wk22-3d-refinement']
sprint['rounds']['wk22_r2_bug_hunt'] = {
    "pm_status_summary": "WK22 R1 caused several regressions: no background trees on terrain, tanked framerate upon hero spawn, and double buildings stacked visually.",
    "pm_bug_tickets": [
        {
            "id": "SPRINT-BUG-005",
            "title": "Terrain texture missing trees (solid green)",
            "severity": "major",
            "owner_agent": "09_ArtDirector_Pixel_Animation_VFX",
            "reporter": "human_playtest",
            "repro_steps": ["Launch game"],
            "expected": "Terrain has trees baked into the texture",
            "actual": "Terrain is pure solid green",
            "acceptance_test": ["Launch game and confirm trees are visible"],
            "status": "assigned"
        },
        {
            "id": "SPRINT-BUG-006",
            "title": "FPS drop to zero after hiring heroes",
            "severity": "blocker",
            "owner_agent": "10_PerformanceStability_Lead",
            "reporter": "human_playtest",
            "repro_steps": ["Launch game", "Hire heroes", "Wait 20-30 seconds"],
            "expected": "Performance remains stable",
            "actual": "Frame rate tanks significantly",
            "acceptance_test": ["Launch game, hire 4-5 heroes, ensure 60fps after 1 minute"],
            "status": "assigned"
        },
        {
            "id": "SPRINT-BUG-007",
            "title": "Buildings appear duplicated/stacked visually",
            "severity": "major",
            "owner_agent": "03_TechnicalDirector_Architecture",
            "reporter": "human_playtest",
            "repro_steps": ["Launch game", "Look at starting buildings"],
            "expected": "One sprite/model per building",
            "actual": "Two building graphics stacked on top of each other",
            "acceptance_test": ["Launch game and verify no visual duplication"],
            "status": "assigned"
        }
    ],
    "pm_feature_requests": [],
    "pm_integration_order": [
        "10_PerformanceStability_Lead (Performance blocker)",
        "03_TechnicalDirector_Architecture (Building duplication)",
        "09_ArtDirector_Pixel_Animation_VFX (Terrain)"
    ],
    "pm_next_actions_by_agent": {
        "10_PerformanceStability_Lead": "Identify and fix the massive performance regression, possibly related to shadows (Agent 03's R1 change) or entity count when heroes exist.",
        "03_TechnicalDirector_Architecture": "Investigate why the Ursina renderer is rendering two sprites for every building and fix the deduplication or spawning logic.",
        "09_ArtDirector_Pixel_Animation_VFX": "Fix the terrain texture bridging. R1 changes broke tree rendering on the terrain surface."
    },
    "pm_agent_prompts": {
        "10_PerformanceStability_Lead": "Review SPRINT-BUG-006. The addition of shadows or something else in R1 killed our framerate when heroes are out. Profile and fix the regression in ursina_renderer.py or related files.",
        "03_TechnicalDirector_Architecture": "Review SPRINT-BUG-007. Buildings have double sprites stacked vertically. Find where we are instantiating entities twice and fix it.",
        "09_ArtDirector_Pixel_Animation_VFX": "Review SPRINT-BUG-005. The terrain is back to green mush without pixel trees. Your R1 fix for upside-down trees accidentally stopped them from rendering completely. Fix it so they render right-side up."
    },
    "pm_send_list_minimal": ["03", "09", "10"]
}

with open(log_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=4)
