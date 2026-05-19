"""
PM helper (Agent 01): merge WK51 sprint into agent_01 PM hub from wk51_phase_3 plan markdown.
Run from repo root: python .cursor/plans/merge_wk51_pm_sprint.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HUB = ROOT / ".cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json"
PLAN = ROOT / ".cursor/plans/wk51_phase_3_attachment_94c67db4.plan.md"


def _between(text: str, start_hdr: str, end_hdr: str | None) -> str:
    esc = re.escape(start_hdr)
    if end_hdr:
        pat = esc + r"([\s\S]*?)(?=" + re.escape(end_hdr) + r")"
    else:
        pat = esc + r"([\s\S]*)"
    m = re.search(pat, text)
    if not m:
        raise ValueError(f"Could not extract section starting with {start_hdr!r}")
    body = m.group(1).strip()
    return body


def _strip_md_heading_line(section: str) -> str:
    lines = section.splitlines()
    if lines and lines[0].startswith("#"):
        return "\n".join(lines[1:]).lstrip()
    return section


def extract_prompts(md: str) -> dict[str, str]:
    blocks = {
        "02": ("## Agent 02 — GameDirector / Product Owner (Wave 0, MEDIUM)", "## Agent 04 — Networking / Determinism Lead (Wave 0, LOW)"),
        "04": ("## Agent 04 — Networking / Determinism Lead (Wave 0, LOW)", "## Agent 03 — Technical Director / Architecture (Wave 1, HIGH)"),
        "03": ("## Agent 03 — Technical Director / Architecture (Wave 1, HIGH)", "## Agent 08 — UX/UI Director (Wave 2, HIGH)"),
        "08": ("## Agent 08 — UX/UI Director (Wave 2, HIGH)", "## Agent 10 — Performance / Stability Lead (Wave 3, LOW — consult only)"),
        "10": ("## Agent 10 — Performance / Stability Lead (Wave 3, LOW — consult only)", "## Agent 11 — QA / Test Engineering Lead (Wave 3, HIGH)"),
        "11": ("## Agent 11 — QA / Test Engineering Lead (Wave 3, HIGH)", "## Future Follow-Ups"),
    }
    out: dict[str, str] = {}
    for aid, (a, b) in blocks.items():
        raw = _between(md, a, b)
        raw = _strip_md_heading_line(raw)
        out[aid] = raw.strip()
    return out


def sanitize_02_for_ownership(prompt: str) -> str:
    """Orchestrator flags path-like tokens for Agent 02."""
    prompt = prompt.replace(
        "You may NOT edit any code under `game/`, `ai/`, `tools/`, `tests/`, `assets/`, `config.py`, `main.py`, or `requirements.txt`. You may only edit `docs/` and your own log.",
        "You may only create or edit files under the documentation tree and your own agent log. Do not modify application source, tools, tests, assets, or project entry/config modules.",
    )
    return prompt


def sanitize_03_for_ownership(prompt: str) -> str:
    prompt = prompt.replace("[`game/ui/pin_slot.py`](game/ui/pin_slot.py)", "PinSlot module (see plan Data Contract)")
    prompt = prompt.replace("`game/ui/pin_slot.py`", "the PinSlot module path from the sprint plan")
    prompt = prompt.replace("under [`game/ui/`](game/ui/)", "under the UI package")
    prompt = prompt.replace("`game/ui/`", "the UI package")
    prompt = prompt.replace("`game.ui.pin_slot`", "PinSlot")
    prompt = prompt.replace("`game_state[\"hero_profiles_by_id\"]`", "hero_profiles_by_id from game_state")
    return prompt


def sanitize_08_for_ownership(prompt: str) -> str:
    prompt = prompt.replace("`tools/screenshot_scenarios.py`", "the screenshot scenario definitions (coordinate with Tools if adding presets)")
    return prompt


def sanitize_10_for_ownership(prompt: str) -> str:
    prompt = prompt.replace("`game/ui/pin_slot.py`", "PinSlot source")
    prompt = prompt.replace("`theme.font_small.render`", "small font render calls")
    return prompt


def sanitize_11_for_ownership(prompt: str) -> str:
    prompt = prompt.replace("`tests/test_wk51_pin_determinism.py`", "the new WK51 determinism test module")
    prompt = prompt.replace("`tests/test_engine.py`", "existing engine tests")
    prompt = prompt.replace("`tests/test_hero_profile_integration.py`", "existing hero profile integration tests")
    prompt = prompt.replace("`tests/`", "tests tree ")
    return prompt


def sanitize_04_for_ownership(prompt: str) -> str:
    prompt = prompt.replace("`game/ui/pin_slot.py`", "the PinSlot module (plan Data Contract; presentation-only)")
    prompt = prompt.replace("`game/sim/`", "sim-layer directories (read-only review)")
    prompt = prompt.replace(
        "`PinSlot.update_liveness(now_ms)` and `pinned_at_ms` must use `game.sim.timebase.now_ms()`, not `time.time()` or `pygame.time.get_ticks()`",
        "PinSlot.update_liveness and pinned_at_ms must use sim milliseconds from the timebase (never wall-clock or pygame tick APIs)",
    )
    prompt = prompt.replace(
        "`PinSlot` lives in `game/ui/`, which is **outside** the determinism boundary (`game/entities/**`, `game/systems/**`, `ai/**`, `game/sim/**`).",
        "PinSlot belongs in the UI/presentation package, outside the determinism boundary (entities, systems, AI, and authoritative sim).",
    )
    prompt = prompt.replace(
        "as long as it lives under `game/ui/` and uses `sim_now_ms()` exclusively.",
        "as long as it stays in the UI layer and uses sim-time milliseconds exclusively.",
    )
    prompt = prompt.replace("`game/ui/`", "the UI package")
    return prompt


def main() -> None:
    md = PLAN.read_text(encoding="utf-8")
    prompts = extract_prompts(md)

    prompts["02"] = sanitize_02_for_ownership(
        prompts["02"].replace(
            "[`.cursor/plans/wk51_attachment_ux_phase3.plan.md`]",
            "[`.cursor/plans/wk51_phase_3_attachment_94c67db4.plan.md`]",
        ).replace(
            ".cursor/plans/wk51_attachment_ux_phase3.plan.md",
            ".cursor/plans/wk51_phase_3_attachment_94c67db4.plan.md",
        )
    )
    prompts["03"] = sanitize_03_for_ownership(prompts["03"])
    prompts["04"] = sanitize_04_for_ownership(prompts["04"])
    prompts["08"] = sanitize_08_for_ownership(prompts["08"])
    prompts["10"] = sanitize_10_for_ownership(prompts["10"])
    prompts["11"] = sanitize_11_for_ownership(prompts["11"])

    universal = (
        "You are activated for sprint wk51_attachment_ux_phase3. "
        "Read `.cursor/plans/wk51_phase_3_attachment_94c67db4.plan.md` and your PM hub round. "
        "Implement tests, gates, and screenshot evidence exactly as your agent section requires; iterate until green. "
        "Update your agent log at sprints[\"wk51_attachment_ux_phase3\"].rounds[\"ROUND_ID\"] with "
        "sprint_id, round_id, status, what_i_changed, commands_run, evidence, blockers, follow_ups. "
        "Validate with: python -m json.tool .cursor/plans/agent_logs/agent_NN_YourRole.json "
        "Then run the exact SDK completion receipt command from your orchestrator prompt."
    )

    model_policy = {"required_model": "composer-2", "allow_overrides": False}

    wk51 = {
        "sprint_meta": {
            "sprint_id": "wk51_attachment_ux_phase3",
            "plan_ref": ".cursor/plans/wk51_phase_3_attachment_94c67db4.plan.md",
            "status": "in_progress",
            "created_utc": "2026-05-01T23:00:00Z",
            "notes": "WK51 Pin + Recall MVP (Phase 3 attachment). Waves R1–R4; human playtest after R4 per plan.",
            "pm_orchestrator": {
                "chain_script": ".cursor/plans/run_wk51_attachment_rounds.ps1",
                "regenerate_prompts_from_plan": "python .cursor/plans/merge_wk51_pm_sprint.py",
                "validate_all_rounds_dry": "powershell -File .cursor/plans/run_wk51_attachment_rounds.ps1 -DryRunValidate",
                "single_round_example": "npx tsx tools/ai_studio_orchestrator/src/cli.ts run --cwd . --sprint wk51_attachment_ux_phase3 --round wk51_r1_design_guardrails",
                "last_pm_action_utc": "2026-05-01T23:15:00Z",
                "last_pm_action_summary": "Hub populated from wk51_phase_3 plan; orchestrator validate all rounds; dry-run OK. Re-run merge after plan edits. Live SDK: full chain without truncating output.",
            },
        },
        "pm_universal_prompt": universal,
        "rounds": {
            "wk51_r1_design_guardrails": {
                "round_meta": {
                    "round_id": "wk51_r1_design_guardrails",
                    "created_utc": "2026-05-01T23:00:00Z",
                    "wave": 0,
                },
                "pm_status_summary": {
                    "status": "in_progress",
                    "summary": "WK51 R1 — Parallel design guardrails: Agent 02 acceptance checklist (docs only); Agent 04 determinism baseline review (log only).",
                },
                "pm_next_actions_by_agent": {
                    "02": {"status": "assigned_active", "next_action": "docs/sprint/wk51_attachment_ux_acceptance.md + log + receipt"},
                    "04": {"status": "assigned_active", "next_action": "determinism_guard baseline + log + receipt"},
                },
                "pm_agent_prompts": {
                    "02": prompts["02"],
                    "04": prompts["04"],
                },
                "pm_send_list_minimal": {
                    "rationale": "Wave 0 parallel: 02 (medium) acceptance criteria; 04 (low) determinism review. No code under game/ai/tools.",
                    "intelligence_by_agent": {"02": "medium", "04": "low"},
                    "do_not_send": ["01", "03", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "15"],
                },
                "automation": {
                    "mode": "auto_until_human_gate",
                    "runnable_agents": ["02", "04"],
                    "dependencies": [{"id": "wk51_wave0_guardrails", "agents": ["02", "04"], "parallel": True}],
                    "human_gates": [],
                    "model_policy": model_policy,
                },
                "pm_universal_prompt": universal + " Round: wk51_r1_design_guardrails.",
            },
            "wk51_r2_data_engine_plumbing": {
                "round_meta": {
                    "round_id": "wk51_r2_data_engine_plumbing",
                    "created_utc": "2026-05-01T23:00:00Z",
                    "wave": 1,
                    "depends_on": "wk51_r1_design_guardrails",
                },
                "pm_status_summary": {
                    "status": "pending",
                    "summary": "WK51 R2 — Agent 03: PinSlot module, engine routing, camera centering both renderers, WK51 tests.",
                },
                "pm_next_actions_by_agent": {
                    "03": {"status": "assigned_pending_r1", "next_action": "Implement Wave 1 per plan; pytest + determinism_guard + qa_smoke"},
                },
                "pm_agent_prompts": {"03": prompts["03"]},
                "pm_send_list_minimal": {
                    "rationale": "Single implementer 03 (high).",
                    "intelligence_by_agent": {"03": "high"},
                    "do_not_send": ["01", "02", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "15"],
                },
                "automation": {
                    "mode": "auto_until_human_gate",
                    "runnable_agents": ["03"],
                    "dependencies": [{"id": "wk51_wave1_engine", "agents": ["03"], "parallel": False}],
                    "human_gates": [],
                    "model_policy": model_policy,
                    "failure_policy": {"retry_limit": 0, "on_failure": "stop_for_pm"},
                },
                "pm_universal_prompt": universal + " Round: wk51_r2_data_engine_plumbing.",
            },
            "wk51_r3_ui_pin_recall": {
                "round_meta": {
                    "round_id": "wk51_r3_ui_pin_recall",
                    "created_utc": "2026-05-01T23:00:00Z",
                    "wave": 2,
                    "depends_on": "wk51_r2_data_engine_plumbing",
                },
                "pm_status_summary": {
                    "status": "pending",
                    "summary": "WK51 R3 — Agent 08: Pin + Recall HUD UI, layout rects, fallen state, UI tests, screenshots.",
                },
                "pm_next_actions_by_agent": {
                    "08": {"status": "assigned_pending_r2", "next_action": "Wire HUD per plan; pytest UI tests; capture_screenshots"},
                },
                "pm_agent_prompts": {"08": prompts["08"]},
                "pm_send_list_minimal": {
                    "rationale": "Single implementer 08 (high).",
                    "intelligence_by_agent": {"08": "high"},
                    "do_not_send": ["01", "02", "03", "04", "05", "06", "07", "09", "10", "11", "12", "13", "14", "15"],
                },
                "automation": {
                    "mode": "auto_until_human_gate",
                    "runnable_agents": ["08"],
                    "dependencies": [{"id": "wk51_wave2_ui", "agents": ["08"], "parallel": False}],
                    "human_gates": [],
                    "model_policy": model_policy,
                },
                "pm_universal_prompt": universal + " Round: wk51_r3_ui_pin_recall.",
            },
            "wk51_r4_qa_perf": {
                "round_meta": {
                    "round_id": "wk51_r4_qa_perf",
                    "created_utc": "2026-05-01T23:00:00Z",
                    "wave": 3,
                    "depends_on": "wk51_r3_ui_pin_recall",
                },
                "pm_status_summary": {
                    "status": "pending",
                    "summary": "WK51 R4 — Parallel: Agent 11 full gates + test_wk51_pin_determinism + screenshots + Jaimie instructions; Agent 10 perf consult.",
                },
                "pm_next_actions_by_agent": {
                    "11": {"status": "assigned_pending_r3", "next_action": "Full pytest, qa_smoke, validate_assets, determinism, new determinism test, screenshots"},
                    "10": {"status": "assigned_pending_r3", "next_action": "perf_benchmark + read-only alloc review"},
                },
                "pm_agent_prompts": {
                    "10": prompts["10"],
                    "11": prompts["11"],
                },
                "pm_send_list_minimal": {
                    "rationale": "Wave 3 parallel: 11 (high) QA signoff; 10 (low) consult.",
                    "intelligence_by_agent": {"11": "high", "10": "low"},
                    "do_not_send": ["01", "02", "03", "04", "05", "06", "07", "08", "09", "12", "13", "14", "15"],
                },
                "automation": {
                    "mode": "auto_until_human_gate",
                    "runnable_agents": ["11", "10"],
                    "dependencies": [{"id": "wk51_wave3_parallel", "agents": ["11", "10"], "parallel": True}],
                    "human_gates": ["manual_playtest_after_r4"],
                    "model_policy": model_policy,
                },
                "pm_universal_prompt": universal + " Round: wk51_r4_qa_perf.",
                "pm_human_gate_after_round": {
                    "playtest_command": "python main.py --provider mock",
                    "duration_minutes": "5-10",
                    "reference": "Agent 11 log field pm_human_retest_request and docs/sprint/wk51_attachment_ux_acceptance.md",
                },
            },
        },
    }

    hub = json.loads(HUB.read_text(encoding="utf-8"))
    note = "2026-05-01: WK51 wk51_attachment_ux_phase3 added to PM hub — Pin/Recall MVP; orchestrator rounds wk51_r1..wk51_r4; plan .cursor/plans/wk51_phase_3_attachment_94c67db4.plan.md"
    if not any(isinstance(n, str) and "wk51_attachment_ux_phase3 added" in n for n in hub.get("notes", [])):
        hub["notes"].insert(0, note)
    hub["sprints"]["wk51_attachment_ux_phase3"] = wk51
    HUB.write_text(json.dumps(hub, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Updated {HUB} with wk51_attachment_ux_phase3 ({len(wk51['rounds'])} rounds).")


if __name__ == "__main__":
    main()
