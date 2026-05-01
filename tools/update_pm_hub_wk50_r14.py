import json
import os

pm_hub_path = '.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json'

with open(pm_hub_path, 'r') as f:
    data = json.load(f)

sprint = data['sprints']['wk50_llm_context_direct_prompts']

# Close the previous hotfix round
if 'wk50_r13_peasant_void_walk_hotfix' in sprint['rounds']:
    sprint['rounds']['wk50_r13_peasant_void_walk_hotfix']['pm_status_summary']['status'] = 'closed_success'
    sprint['rounds']['wk50_r13_peasant_void_walk_hotfix']['pm_status_summary']['summary'] += ' (Fixed by Agent 05, verified by user)'

# Create the new hotfix round
round_id = 'wk50_r14_go_home_context_hotfix'
sprint['rounds'][round_id] = {
    "round_meta": {
        "round_id": round_id,
        "created_utc": "2026-05-01T10:22:00Z",
        "source": "pm_kickoff",
        "closed_by": None
    },
    "pm_status_summary": {
        "status": "in_progress",
        "summary": "Starting hotfix for 'go home' direct prompt. Rangers are refusing the command claiming they don't know a safe home, despite spawning from a guild. Assigning Agent 06 to fix the LLM context/validator, and Agent 11 to verify."
    },
    "pm_bug_tickets": [
        {
            "id": "WK50-BUG-005",
            "title": "Heroes refuse 'go home' command claiming no safe home known",
            "severity": "major",
            "owner_agent": "06_AIBehaviorDirector_LLM",
            "reporter": "human_playtest",
            "repro_steps": [
                "Run python main.py --provider mock.",
                "Open chat with a Ranger (or other hero).",
                "Command them to 'go home'.",
                "Hero refuses, stating they do not know of a safe home."
            ],
            "expected": "Heroes should recognize their spawn guild (or the castle) as a valid 'home' and accept the command to return there.",
            "actual": "Heroes fail to resolve 'home' in the direct prompt context/validator and refuse the command.",
            "acceptance_test": [
                "Direct prompt validator successfully resolves 'home' to the hero's guild or a safe location.",
                "Mock provider accepts 'go home' and hero commits to moving there.",
                "python -m pytest tests/ passes.",
                "python tools/qa_smoke.py --quick passes."
            ],
            "status": "assigned"
        }
    ],
    "pm_next_actions_by_agent": {
        "06": {
            "status": "assigned",
            "next_action": "Investigate LLM context injection and direct prompt validator to ensure hero's guild is recognized as 'home'."
        },
        "11": {
            "status": "assigned",
            "next_action": "Verify the fix using tests and qa_smoke."
        }
    },
    "pm_agent_prompts": {
        "06": "You are Agent 06, sprint wk50_llm_context_direct_prompts, round wk50_r14_go_home_context_hotfix (HIGH). Human playtest bug: Rangers (and possibly other heroes) refuse the 'go home' direct prompt, claiming they don't know a safe home, even though they spawn from a guild. Investigate the LLM context injection, memory, and direct prompt validator. Ensure a hero's home guild is always recognized as a valid 'home' or 'safe' location for the 'go home' command. Fix the logic, run `python -m pytest tests/` and `python tools/qa_smoke.py --quick`. Update your log, validate JSON, complete.",
        "11": "You are Agent 11, sprint wk50_llm_context_direct_prompts, round wk50_r14_go_home_context_hotfix (MEDIUM). After Agent 06 fixes the 'go home' context bug, verify the fix. Ensure tests cover a hero successfully resolving 'go home' to their guild. Run `python -m pytest tests/` and `python tools/qa_smoke.py --quick`. Update your log, validate JSON, complete."
    },
    "pm_send_list_minimal": {
        "order": "automation.dependencies_only",
        "then_in_order": ["06", "11"],
        "intelligence_by_agent": {
            "06": "high",
            "11": "medium"
        },
        "do_not_send": ["02", "03", "04", "05", "07", "08", "09", "10", "12", "13", "14", "15"],
        "rationale": "Agent 06 fixes the context/validator logic, Agent 11 verifies."
    },
    "automation": {
        "mode": "auto_until_human_gate",
        "runnable_agents": ["06", "11"],
        "dependencies": [
            {
                "id": "fix_go_home",
                "agents": ["06"],
                "parallel": False
            },
            {
                "id": "verify_fix",
                "after": ["fix_go_home"],
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
    "pm_universal_prompt": "You are activated for sprint wk50_llm_context_direct_prompts, round wk50_r14_go_home_context_hotfix. We are fixing a bug where heroes refuse the 'go home' command because they claim not to know a safe home. Update your log, run gates, validate JSON, complete."
}

with open(pm_hub_path, 'w') as f:
    json.dump(data, f, indent=2)

print("Successfully updated PM hub with wk50_r14_go_home_context_hotfix.")