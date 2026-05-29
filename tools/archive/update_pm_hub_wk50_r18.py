import json

pm_hub_path = '.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json'

with open(pm_hub_path, 'r') as f:
    data = json.load(f)

sprint = data['sprints']['wk50_llm_context_direct_prompts']

# Close the previous integration tests round
if 'wk50_r17_direct_prompt_integration_tests' in sprint['rounds']:
    sprint['rounds']['wk50_r17_direct_prompt_integration_tests']['pm_status_summary']['status'] = 'closed_success'
    sprint['rounds']['wk50_r17_direct_prompt_integration_tests']['pm_status_summary']['summary'] += ' (Fixed false refusals, verified by Agent 11 tests)'

# Create the new round
round_id = 'wk50_r18_direct_prompt_arrival_handlers'
sprint['rounds'][round_id] = {
    "round_meta": {
        "round_id": round_id,
        "created_utc": "2026-05-01T11:45:00Z",
        "source": "pm_kickoff",
        "closed_by": None
    },
    "pm_status_summary": {
        "status": "in_progress",
        "summary": "Fixing arrival handlers for direct prompt commands. Currently, heroes arrive at the Inn but don't enter it, 'explore east' gets dropped too quickly, and 'rest until healed' doesn't route properly if they are outdoors. Assigning Agent 03 to fix the arrival and execution logic, and Agent 11 to verify."
    },
    "pm_bug_tickets": [
        {
            "id": "WK50-BUG-009",
            "title": "Heroes fail to execute arrival actions for direct prompts (Inn, Rest, Explore)",
            "severity": "major",
            "owner_agent": "03_TechnicalDirector_Architecture",
            "reporter": "human_playtest",
            "repro_steps": [
                "Run python main.py --provider mock.",
                "Command hero to 'go to inn': they walk there but don't enter.",
                "Command hero to 'rest until healed' while outdoors: they often refuse or fail to route.",
                "Command hero to 'explore east': they take a few steps and immediately drop the sovereign commit."
            ],
            "expected": "Heroes should enter the inn upon arrival (`enter_building_briefly` or `start_resting_at_building`). 'rest until healed' should route to safety the same as 'go home'. 'explore east' should maintain the commit for the full journey length.",
            "actual": "Missing arrival handlers in `ai/behaviors/bounty_pursuit.py:handle_moving` for these sub_intents, and missing mapping in `direct_prompt_validator.py`/`direct_prompt_exec.py`.",
            "acceptance_test": [
                "Hero enters the inn when 'go to inn' is commanded and reached.",
                "'rest until healed' properly routes home or to the inn.",
                "'explore east' completes the journey without dropping early.",
                "python tools/qa_smoke.py --quick passes."
            ],
            "status": "assigned"
        }
    ],
    "pm_next_actions_by_agent": {
        "03": {
            "status": "assigned",
            "next_action": "Fix `ai/behaviors/bounty_pursuit.py:handle_moving` to properly handle arrivals for `go_to_known_place` (Inn) and `rest_until_healed`/`seek_healing`. Fix explore commitment duration."
        },
        "11": {
            "status": "assigned",
            "next_action": "Verify the arrival fixes using qa_smoke."
        }
    },
    "pm_agent_prompts": {
        "03": "You are Agent 03, sprint wk50_llm_context_direct_prompts, round wk50_r18_direct_prompt_arrival_handlers (HIGH). Human playtest feedback: when commanded to 'go to the inn', heroes walk to the inn but don't actually enter it. 'rest until healed' is also failing to trigger proper resting, and 'explore east' drops its commit too quickly. Fix `ai/behaviors/bounty_pursuit.py:handle_moving()` so that when `hero.target` has `sub_intent` like 'go_to_known_place' (inn) or 'rest_until_healed'/'seek_healing', they actually call `enter_building_briefly` or `start_resting_at_building` upon arrival. Also ensure the explore commit lasts longer. Run `python tools/qa_smoke.py --quick`. Update your log, validate JSON, complete.",
        "11": "You are Agent 11, sprint wk50_llm_context_direct_prompts, round wk50_r18_direct_prompt_arrival_handlers (MEDIUM). After Agent 03 fixes the arrival handlers, verify the fixes. Ensure tests pass and the logic correctly handles inn entry and resting. Run `python tools/qa_smoke.py --quick`. Update your log, validate JSON, complete."
    },
    "pm_send_list_minimal": {
        "order": "automation.dependencies_only",
        "then_in_order": ["03", "11"],
        "intelligence_by_agent": {
            "03": "high",
            "11": "medium"
        },
        "do_not_send": ["02", "04", "05", "06", "07", "08", "09", "10", "12", "13", "14", "15"],
        "rationale": "Agent 03 fixes the arrival execution logic, Agent 11 verifies."
    },
    "automation": {
        "mode": "auto_until_human_gate",
        "runnable_agents": ["03", "11"],
        "dependencies": [
            {
                "id": "fix_arrivals",
                "agents": ["03"],
                "parallel": False
            },
            {
                "id": "verify_fixes",
                "after": ["fix_arrivals"],
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
    "pm_universal_prompt": "You are activated for sprint wk50_llm_context_direct_prompts, round wk50_r18_direct_prompt_arrival_handlers. We are fixing arrival handlers so heroes actually enter the inn when told to go there, properly rest when told, and don't drop explore commands early. Update your log, run gates, validate JSON, complete."
}

with open(pm_hub_path, 'w') as f:
    json.dump(data, f, indent=2)

print("Successfully updated PM hub with wk50_r18_direct_prompt_arrival_handlers.")