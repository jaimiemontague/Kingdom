import json

filepath = r"c:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\.cursor\plans\agent_logs\agent_01_ExecutiveProducer_PM.json"
with open(filepath, 'r', encoding='utf-8') as f:
    d = json.load(f)

r1 = d['sprints']['wk17-quality-logic-immersion']['rounds']['wk17_r1_kickoff_investigation']
r1['pm_bug_tickets'] = [
    {
      "id": "WK17-BUG-001",
      "title": "Memory leak / Lag after 5 minutes of play",
      "severity": "blocker",
      "owner_agent": "10_PerformanceStability_Lead",
      "reporter": "human_playtest",
      "repro_steps": [
        "Run python main.py --no-llm for a few minutes"
      ],
      "expected": "Smooth FPS and stable memory plateau.",
      "actual": "Lag and potential memory leak after 5 minutes.",
      "status": "investigated_by_agent_10"
    },
    {
      "id": "WK17-BUG-002",
      "title": "Heroes immediately turn back after leaving inn for a task",
      "severity": "major",
      "owner_agent": "06_AIBehaviorDirector_LLM",
      "reporter": "human_playtest",
      "repro_steps": [
        "Hero declares intent to buy dagger",
        "Hero exits inn",
        "Hero almost immediately re-enters inn instead of completing task"
      ],
      "expected": "Hero locks in decision to complete errand with higher priority (hysteresis).",
      "actual": "Hero re-evaluates and changes mind immediately.",
      "status": "resolved_in_round_1"
    },
    {
      "id": "WK17-BUG-003",
      "title": "Auto-spawned buildings and guards swallowed by Fog of War",
      "severity": "major",
      "owner_agent": "05_GameplaySystemsDesigner",
      "reporter": "human_playtest",
      "repro_steps": [
        "Wait for farm/house to auto-spawn, or spawn a guard",
        "Observe fog around them"
      ],
      "expected": "Player structures and guards inherently provide line of sight to push back fog.",
      "actual": "They can get covered in fog of war.",
      "status": "defined_in_round_1"
    }
]
r1['pm_feature_requests'] = [
    {
      "id": "WK17-FEAT-001",
      "title": "Clickable Peasants",
      "owner_agent": "08_UX_UI_Director",
      "specs": [
        "Every peasant must have a click hitbox",
        "Clicking peasant sets them as active selection",
        "Show a minimal flavorful UI panel with their current simple task (e.g., 'Carrying Wood')"
      ],
      "status": "implemented_in_round_1"
    }
]

with open(filepath, 'w', encoding='utf-8') as f:
    json.dump(d, f, indent=2)

print("Restored bug tickets for wk17")
