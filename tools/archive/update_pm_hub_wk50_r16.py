import json
import os

pm_hub_path = '.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json'

with open(pm_hub_path, 'r') as f:
    data = json.load(f)

sprint = data['sprints']['wk50_llm_context_direct_prompts']

# Close the previous hotfix round
if 'wk50_r15_direct_prompt_commitment_duration' in sprint['rounds']:
    sprint['rounds']['wk50_r15_direct_prompt_commitment_duration']['pm_status_summary']['status'] = 'closed_success'
    sprint['rounds']['wk50_r15_direct_prompt_commitment_duration']['pm_status_summary']['summary'] += ' (Fixed by Agent 03, verified by user)'

# Create the new hotfix round
round_id = 'wk50_r16_direct_prompt_all_commands_commitment'
sprint['rounds'][round_id] = {
    "round_meta": {
        "round_id": round_id,
        "created_utc": "2026-05-01T10:51:00Z",
        "source": "pm_kickoff",
        "closed_by": None
    },
    "pm_status_summary": {
        "status": "in_progress",
        "summary": "Applying the long-distance commitment logic to all other direct prompt commands (e.g., 'buy potions', 'retreat'). Assigning Agent 03 to wire up attach_direct_prompt_move for these actions, and Agent 11 to verify."
    },
    "pm_bug_tickets": [
        {
            "id": "WK50-BUG-007",
            "title": "Other direct prompt commands (like buy potions) get distracted on long journeys",
            "severity": "major",
            "owner_agent": "03_TechnicalDirector_Architecture",
            "reporter": "human_playtest",
            "repro_steps": [
                "Run python main.py --provider mock.",
                "Command a hero to 'buy potions' when the market is far away.",
                "Hero accepts but gets distracted by routine AI before arriving."
            ],
            "expected": "All physical direct prompt commands (buy potions, retreat, etc.) should use the same sovereign commitment logic as 'go home' so they persist until the destination is reached.",
            "actual": "Commands like 'buy_item' fall through to the standard LLM bridge without attaching a direct prompt movement commit, making them vulnerable to routine AI overrides.",
            "acceptance_test": [
                "Commands like 'buy potions' successfully attach a direct prompt movement commit.",
                "Heroes complete these journeys without being distracted by non-critical AI.",
                "python -m pytest tests/ passes.",
                "python tools/qa_smoke.py --quick passes."
            ],
            "status": "assigned"
        }
    ],
    "pm_next_actions_by_agent": {
        "03": {
            "status": "assigned",
            "next_action": "Update game/sim/direct_prompt_exec.py (or related) to ensure 'buy_item' and other physical commands use attach_direct_prompt_move."
        },
        "11": {
            "status": "assigned",
            "next_action": "Verify the fix using tests and qa_smoke."
        }
    },
    "pm_agent_prompts": {
        "03": "You are Agent 03, sprint wk50_llm_context_direct_prompts, round wk50_r16_direct_prompt_all_commands_commitment (HIGH). Human playtest feedback: the long-distance commitment fix for 'go home' works perfectly! Now we need to apply that exact same logic to the other commands. Currently, in `game/sim/direct_prompt_exec.py`, actions like `buy_item` (buy potions) or `retreat` fall through to `apply_llm_decision` without calling `attach_direct_prompt_move`, meaning they still get distracted. Wire up `attach_direct_prompt_move` for these other physical commands so they get the same sovereign lock. Run `python -m pytest tests/` and `python tools/qa_smoke.py --quick`. Update your log, validate JSON, complete.",
        "11": "You are Agent 11, sprint wk50_llm_context_direct_prompts, round wk50_r16_direct_prompt_all_commands_commitment (MEDIUM). After Agent 03 applies the commitment logic to other commands (like buy potions), verify the fix. Ensure tests cover these commands maintaining their sovereign commit. Run `python -m pytest tests/` and `python tools/qa_smoke.py --quick`. Update your log, validate JSON, complete."
    },
    "pm_send_list_minimal": {
        "order": "automation.dependencies_only",
        "then_in_order": ["03", "11"],
        "intelligence_by_agent": {
            "03": "high",
            "11": "medium"
        },
        "do_not_send": ["02", "04", "05", "06", "07", "08", "09", "10", "12", "13", "14", "15"],
        "rationale": "Agent 03 wires up the commitment logic for the remaining commands, Agent 11 verifies."
    },
    "automation": {
        "mode": "auto_until_human_gate",
        "runnable_agents": ["03", "11"],
        "dependencies": [
            {
                "id": "fix_other_commands",
                "agents": ["03"],
                "parallel": False
            },
            {
                "id": "verify_fix",
                "after": ["fix_other_commands"],
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
    "pm_universal_prompt": "You are activated for sprint wk50_llm_context_direct_prompts, round wk50_r16_direct_prompt_all_commands_commitment. We are applying the long-distance commitment logic to all other direct prompt commands (like buy potions). Update your log, run gates, validate JSON, complete."
}

with open(pm_hub_path, 'w') as f:
    json.dump(data, f, indent=2)

print("Successfully updated PM hub with wk50_r16_direct_prompt_all_commands_commitment.")