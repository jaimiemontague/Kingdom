import json
import os

pm_hub_path = '.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json'

with open(pm_hub_path, 'r') as f:
    data = json.load(f)

sprint = data['sprints']['wk50_llm_context_direct_prompts']

# Close the previous hotfix round
if 'wk50_r14_go_home_context_hotfix' in sprint['rounds']:
    sprint['rounds']['wk50_r14_go_home_context_hotfix']['pm_status_summary']['status'] = 'closed_success'
    sprint['rounds']['wk50_r14_go_home_context_hotfix']['pm_status_summary']['summary'] += ' (Fixed by Agent 06, verified by user)'

# Create the new hotfix round
round_id = 'wk50_r15_direct_prompt_commitment_duration'
sprint['rounds'][round_id] = {
    "round_meta": {
        "round_id": round_id,
        "created_utc": "2026-05-01T10:38:00Z",
        "source": "pm_kickoff",
        "closed_by": None
    },
    "pm_status_summary": {
        "status": "in_progress",
        "summary": "Starting hotfix for direct prompt commitment duration. Heroes get distracted on long journeys because the commitment window is too short. Assigning Agent 03 to make the commitment persist until the destination is reached, and Agent 11 to verify."
    },
    "pm_bug_tickets": [
        {
            "id": "WK50-BUG-006",
            "title": "Heroes get distracted on long journeys after accepting direct prompts",
            "severity": "major",
            "owner_agent": "03_TechnicalDirector_Architecture",
            "reporter": "human_playtest",
            "repro_steps": [
                "Run python main.py --provider mock.",
                "Open chat with a hero far from home.",
                "Command them to 'go home'.",
                "Hero accepts and starts moving, but gets distracted by normal AI (e.g., enemies, resting) before arriving."
            ],
            "expected": "The direct prompt commitment state should persist until the destination is reached, unless interrupted by a critical safety override.",
            "actual": "The commitment window expires too quickly, allowing routine AI to overwrite the player's command.",
            "acceptance_test": [
                "Heroes complete long-distance direct prompt movements without being distracted by non-critical AI routines.",
                "python -m pytest tests/ passes.",
                "python tools/qa_smoke.py --quick passes."
            ],
            "status": "assigned"
        }
    ],
    "pm_next_actions_by_agent": {
        "03": {
            "status": "assigned",
            "next_action": "Modify the direct prompt commitment logic so it persists until the destination is reached or a critical override occurs."
        },
        "11": {
            "status": "assigned",
            "next_action": "Verify the fix using tests and qa_smoke."
        }
    },
    "pm_agent_prompts": {
        "03": "You are Agent 03, sprint wk50_llm_context_direct_prompts, round wk50_r15_direct_prompt_commitment_duration (HIGH). Human playtest bug: heroes accept 'go home' and start moving, but get distracted if home is far. The direct prompt commitment window you implemented in wk50_r11 is too short for long-distance travel. Update the commitment logic so the hero persists until the destination is reached (or until a severe combat/safety override). Run `python -m pytest tests/` and `python tools/qa_smoke.py --quick`. Update your log, validate JSON, complete.",
        "11": "You are Agent 11, sprint wk50_llm_context_direct_prompts, round wk50_r15_direct_prompt_commitment_duration (MEDIUM). After Agent 03 fixes the direct prompt commitment duration, verify the fix. Ensure tests cover long-distance direct prompt movement without routine AI distraction. Run `python -m pytest tests/` and `python tools/qa_smoke.py --quick`. Update your log, validate JSON, complete."
    },
    "pm_send_list_minimal": {
        "order": "automation.dependencies_only",
        "then_in_order": ["03", "11"],
        "intelligence_by_agent": {
            "03": "high",
            "11": "medium"
        },
        "do_not_send": ["02", "04", "05", "06", "07", "08", "09", "10", "12", "13", "14", "15"],
        "rationale": "Agent 03 fixes the commitment duration logic, Agent 11 verifies."
    },
    "automation": {
        "mode": "auto_until_human_gate",
        "runnable_agents": ["03", "11"],
        "dependencies": [
            {
                "id": "fix_commitment_duration",
                "agents": ["03"],
                "parallel": False
            },
            {
                "id": "verify_fix",
                "after": ["fix_commitment_duration"],
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
    "pm_universal_prompt": "You are activated for sprint wk50_llm_context_direct_prompts, round wk50_r15_direct_prompt_commitment_duration. We are fixing a bug where heroes get distracted on long journeys after accepting direct prompts. Update your log, run gates, validate JSON, complete."
}

with open(pm_hub_path, 'w') as f:
    json.dump(data, f, indent=2)

print("Successfully updated PM hub with wk50_r15_direct_prompt_commitment_duration.")