import json

pm_hub_path = '.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json'

with open(pm_hub_path, 'r') as f:
    data = json.load(f)

sprint = data['sprints']['wk50_llm_context_direct_prompts']

# Close the previous hotfix round
if 'wk50_r16_direct_prompt_all_commands_commitment' in sprint['rounds']:
    sprint['rounds']['wk50_r16_direct_prompt_all_commands_commitment']['pm_status_summary']['status'] = 'closed_success'
    sprint['rounds']['wk50_r16_direct_prompt_all_commands_commitment']['pm_status_summary']['summary'] += ' (Fixed by Agent 03, verified by user)'

# Create the new round
round_id = 'wk50_r17_direct_prompt_integration_tests'
sprint['rounds'][round_id] = {
    "round_meta": {
        "round_id": round_id,
        "created_utc": "2026-05-01T11:15:00Z",
        "source": "pm_kickoff",
        "closed_by": None
    },
    "pm_status_summary": {
        "status": "in_progress",
        "summary": "Creating integration tests for all direct prompt commands to catch false refusals (e.g. market too far, can't afford). Agent 11 writes the tests, Agent 06 fixes the validator/context, Agent 11 verifies."
    },
    "pm_bug_tickets": [
        {
            "id": "WK50-BUG-008",
            "title": "Heroes falsely refuse commands due to broken context evaluation",
            "severity": "major",
            "owner_agent": "06_AIBehaviorDirector_LLM",
            "reporter": "human_playtest",
            "repro_steps": [
                "Run python main.py --provider mock.",
                "Ensure a hero has 20+ gold and has discovered the market.",
                "Command the hero to 'buy potions'.",
                "Hero refuses, claiming they can't afford it, haven't discovered the market, or it's too far."
            ],
            "expected": "Hero should correctly evaluate their gold against potion cost (15g), recognize the market in their memory, and commit to moving there to buy.",
            "actual": "Validator or context builder provides incorrect info or misinterprets state, causing false refusal.",
            "acceptance_test": [
                "Comprehensive integration tests exist for all direct commands (go home, buy potions, explore east, etc.).",
                "All tests pass, confirming no false refusals for valid states.",
                "python tools/qa_smoke.py --quick passes."
            ],
            "status": "assigned"
        }
    ],
    "pm_next_actions_by_agent": {
        "11": {
            "status": "assigned",
            "next_action": "Write comprehensive integration tests for every direct prompt command (e.g., tests/test_direct_prompt_integration.py) first, then later verify they pass."
        },
        "06": {
            "status": "assigned",
            "next_action": "Fix ai/direct_prompt_validator.py and ai/context_builder.py so the new tests pass."
        }
    },
    "pm_agent_prompts": {
        "11": "You are Agent 11, sprint wk50_llm_context_direct_prompts, round wk50_r17_direct_prompt_integration_tests (HIGH). Human playtest feedback: heroes falsely refuse 'buy potions' (claiming they can't afford it when they have 20+ gold, or market not discovered when it is). We need comprehensive integration tests. Create `tests/test_direct_prompt_integration.py`. Write a test for EVERY command (buy potions, go home, explore east, status report, etc.). Set up the exact scenario (e.g., spawn a Ranger, give 20+ gold, add market to memory). Send the prompt through the mock provider/validator and assert it commits the correct action without a false refusal. The tests WILL fail initially. Run `python -m pytest tests/test_direct_prompt_integration.py` to see them fail. Update your log, validate JSON, complete.",
        "06": "You are Agent 06, sprint wk50_llm_context_direct_prompts, round wk50_r17_direct_prompt_integration_tests (HIGH). Agent 11 just wrote failing integration tests in `tests/test_direct_prompt_integration.py` because heroes falsely refuse commands like 'buy potions' (claiming they can't afford it or don't know the market). Fix the `ai/direct_prompt_validator.py` and `ai/context_builder.py` logic so all of Agent 11's tests pass. Make sure affordability checks and place memory lookups work even when the hero is far from the shop. Run `python -m pytest tests/test_direct_prompt_integration.py` until it passes. Update your log, validate JSON, complete.",
        "11_verify": "You are Agent 11, sprint wk50_llm_context_direct_prompts, round wk50_r17_direct_prompt_integration_tests (MEDIUM). Agent 06 has fixed the bugs. Run `python -m pytest tests/` and `python tools/qa_smoke.py --quick` to verify everything is green. Update your log, validate JSON, complete."
    },
    "pm_send_list_minimal": {
        "order": "automation.dependencies_only",
        "then_in_order": ["11", "06", "11_verify"],
        "intelligence_by_agent": {
            "11": "high",
            "06": "high",
            "11_verify": "medium"
        },
        "do_not_send": ["02", "03", "04", "05", "07", "08", "09", "10", "12", "13", "14", "15"],
        "rationale": "Agent 11 writes failing tests -> Agent 06 fixes bugs -> Agent 11 verifies."
    },
    "automation": {
        "mode": "auto_until_human_gate",
        "runnable_agents": ["11", "06", "11_verify"],
        "dependencies": [
            {
                "id": "write_tests",
                "agents": ["11"],
                "parallel": False
            },
            {
                "id": "fix_bugs",
                "after": ["write_tests"],
                "agents": ["06"],
                "parallel": False
            },
            {
                "id": "verify_tests",
                "after": ["fix_bugs"],
                "agents": ["11_verify"],
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
    "pm_universal_prompt": "You are activated for sprint wk50_llm_context_direct_prompts, round wk50_r17_direct_prompt_integration_tests. We are creating integration tests for every command and fixing false refusals. Follow your agent prompt. Update your log, run gates, validate JSON, complete."
}

with open(pm_hub_path, 'w') as f:
    json.dump(data, f, indent=2)

print("Successfully updated PM hub with wk50_r17_direct_prompt_integration_tests.")