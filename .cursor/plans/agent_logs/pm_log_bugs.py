import json
import os
import time

path = os.path.join('.cursor', 'plans', 'agent_logs', 'agent_01_ExecutiveProducer_PM.json')

with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Ensure the bugs list exists
if 'pm_bug_tickets' not in data['sprints']['wk21-3d-visual-polish']['rounds']['wk21_r2_implementation']:
    data['sprints']['wk21-3d-visual-polish']['rounds']['wk21_r2_implementation']['pm_bug_tickets'] = []

bugs = data['sprints']['wk21-3d-visual-polish']['rounds']['wk21_r2_implementation']['pm_bug_tickets']

bugs.extend([
    {
        "id": "SPRINT-BUG-WK21-01",
        "title": "Grass texture missing in Ursina renderer",
        "severity": "major",
        "owner_agent": "03_TechnicalDirector_Architecture",
        "reporter": "human_playtest",
        "repro_steps": ["Launch game with --renderer ursina", "Observe grass tiles on the map"],
        "expected": "Grass should have a texture.",
        "actual": "Grass texture is missing/broken.",
        "status": "open"
    },
    {
        "id": "SPRINT-BUG-WK21-02",
        "title": "Road tiles appear as random pixels",
        "severity": "major",
        "owner_agent": "09_ArtDirector_Pixel_Animation_VFX",
        "reporter": "human_playtest",
        "repro_steps": ["Launch game with --renderer ursina", "Observe road tiles"],
        "expected": "Road should look like cobblestones/dirt.",
        "actual": "Road looks like random scattered pixels.",
        "status": "open"
    },
    {
        "id": "SPRINT-BUG-WK21-03",
        "title": "Worker billboards are black stick figures",
        "severity": "major",
        "owner_agent": "09_ArtDirector_Pixel_Animation_VFX",
        "reporter": "human_playtest",
        "repro_steps": ["Launch game with --renderer ursina", "Observe workers (peasants/tax collectors)"],
        "expected": "Workers should render with proper colors/sprites and transparency.",
        "actual": "Workers render as black stick figures (likely an alpha channel transparency bug).",
        "status": "open"
    }
])

with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)

print("Added visual bugs to PM log.")
