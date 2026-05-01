import json
import os

pm_hub_path = '.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json'

with open(pm_hub_path, 'r') as f:
    data = json.load(f)

# Revert WK50 closure
wk50 = data['sprints']['wk50_llm_context_direct_prompts']
last_round = wk50['rounds']['wk50_r12_pm_direct_prompt_fix_summary']
last_round['pm_status_summary']['status'] = 'human_retest_pending'
last_round['pm_status_summary']['summary'] = last_round['pm_status_summary']['summary'].replace(' (Skipped human retest to address urgent peasant pathing bug)', '')

# Remove WK51
if 'wk51_peasant_void_walk_hotfix' in data['sprints']:
    del data['sprints']['wk51_peasant_void_walk_hotfix']

# Add WK50 hotfix round
wk50['rounds']['wk50_r13_peasant_void_walk_hotfix'] = {
    "round_meta": {
        "round_id": "wk50_r13_peasant_void_walk_hotfix",
        "created_utc": "2026-05-01T09:56:00Z",
        "source": "pm_kickoff",
        "closed_by": None
    },
    "pm_status_summary": {
        "status": "in_progress",
        "summary": "Starting hotfix for peasant void walk bug. Assigning Agent 05 to investigate and fix peasant pathing/state logic, and Agent 11 to verify."
    },
    "pm_bug_tickets": [
        {
            "id": "WK50-BUG-004",
            "title": "Peasants run to top left of map after starting work on first building",
            "severity": "blocker",
            "owner_agent": "05_GameplaySystemsDesigner",
            "reporter": "human_playtest",
            "repro_steps": [
                "Place a building.",
                "Observe peasant spawn and start working on it.",
                "Observe peasant run off towards the top left of the map (likely 0,0)."
            ],
            "expected": "Peasants should stay at the building and finish construction, or return to the castle if done/interrupted.",
            "actual": "Peasants path to the top left of the map.",
            "acceptance_test": [
                "Peasants successfully complete building construction without running away.",
                "python tools/qa_smoke.py --quick passes."
            ],
            "status": "assigned"
        }
    ],
    "pm_next_actions_by_agent": {
        "05": {
            "status": "assigned",
            "next_action": "Investigate peasant pathing/state in game/entities/peasant.py and fix the void walk bug."
        },
        "11": {
            "status": "assigned",
            "next_action": "Verify the fix using qa_smoke and observe_sync."
        }
    },
    "pm_agent_prompts": {
        "05": "You are Agent 05, sprint wk50_llm_context_direct_prompts, round wk50_r13_peasant_void_walk_hotfix (HIGH). Human playtest bug: peasants go to start working on the first placed building, but then run off towards the top left of the map (likely 0,0). Investigate `game/entities/peasant.py` and related building/economy logic. Fix the pathing/state bug so they stay and build. Run `python tools/qa_smoke.py --quick`. Update your log, validate JSON, complete.",
        "11": "You are Agent 11, sprint wk50_llm_context_direct_prompts, round wk50_r13_peasant_void_walk_hotfix (MEDIUM). After Agent 05 fixes the peasant void walk bug, verify the fix. Run `python tools/qa_smoke.py --quick` and ensure the base scenario (which includes construction) passes without peasants running to 0,0. Update your log, validate JSON, complete."
    },
    "pm_send_list_minimal": {
        "order": "automation.dependencies_only",
        "then_in_order": ["05", "11"],
        "intelligence_by_agent": {
            "05": "high",
            "11": "medium"
        },
        "do_not_send": ["02", "03", "04", "06", "07", "08", "09", "10", "12", "13", "14", "15"],
        "rationale": "Agent 05 implements the fix, Agent 11 verifies."
    },
    "automation": {
        "mode": "auto_until_human_gate",
        "runnable_agents": ["05", "11"],
        "dependencies": [
            {
                "id": "fix_peasant_bug",
                "agents": ["05"],
                "parallel": False
            },
            {
                "id": "verify_fix",
                "after": ["fix_peasant_bug"],
                "agents": ["11"],
                "parallel": False
            }
        ],
        "human_gates": ["manual_playtest"],
        "completion_flow": "worker_completion_receipt_then_verifier_then_next_wave",
        "model_policy": {
            "required_model": "composer-2",
            "allow_overrides": False
        }
    },
    "pm_universal_prompt": "You are activated for sprint wk50_llm_context_direct_prompts, round wk50_r13_peasant_void_walk_hotfix. We are fixing a blocker bug where peasants run to the top left of the map after starting construction. Update your log, run gates, validate JSON, complete."
}

with open(pm_hub_path, 'w') as f:
    json.dump(data, f, indent=2)

print("Successfully updated PM hub with WK50 hotfix.")
