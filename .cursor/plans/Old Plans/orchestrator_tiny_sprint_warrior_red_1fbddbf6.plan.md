---
name: orchestrator_tiny_sprint_warrior_red
overview: A tiny, safe sprint to validate the Cursor SDK orchestrator end-to-end with one implementer (Agent 09) and post-implementation QA (Agent 11), stopping only for final human visual approval.
todos:
  - id: pmhub-round
    content: Add sprint orch_tiny_warrior_red + round orch_r0_impl_then_qa to PM hub with pm_send_list_minimal, pm_agent_prompts, and automation block.
    status: pending
  - id: run-orchestrator
    content: Run orchestrator validate → dry-run → live run for that sprint/round; ensure only Agents 09 then 11 are launched and model policy is enforced.
    status: pending
  - id: human-visual-gate
    content: After QA PASS and orchestrator stop, manually verify warrior shirts are dark red in both Ursina and pygame renderers (no version bump, no commit/push).
    status: pending
isProject: false
---

## Goal
Validate `tools/ai_studio_orchestrator` can:
- read a new PM hub sprint/round
- launch exactly one implementer agent, then Agent 11
- enforce **Composer 2 only**
- record a ledger + dashboard
- stop at an explicit **visual approval** human gate (no auto version bump / commit / push)

## Tiny change (low risk)
Change **warrior shirt color** from blue to **dark red** in the procedural hero sprite palette:
- Primary source: `game/graphics/hero_sprites.py` → `HeroSpriteSpec.warrior`
- Because you selected **both renderers**, ensure Ursina billboards don’t re-tint the sprite back toward blue:
  - `game/graphics/ursina_renderer.py` currently sets `COLOR_HERO = color.azure` and uses that as `tint_col` for warriors while still applying a texture.
  - Implementer should set warrior tint to **white** (or otherwise neutral) when a hero texture is present so the shirt’s base color reads as authored.

## PM hub changes (Agent 01 only)
Add a new sprint + single round in:
- `.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json`

Suggested IDs:
- **sprint**: `orch_tiny_warrior_red`
- **round**: `orch_r0_impl_then_qa`

Round fields to include:
- `pm_status_summary`: status = `active`
- `pm_next_actions_by_agent`:
  - `09`: `assigned_active`
  - `11`: `blocked_until_09_done`
  - `01`: `active` (notes/next_action)
- `pm_send_list_minimal`:
  - `order`: `then_in_order`
  - `then_in_order`: `["09","11"]`
  - `intelligence_by_agent`: `{ "09": "medium", "11": "low" }`
  - `do_not_send`: everyone else
  - `rationale`: “One implementer + QA to validate orchestrator DAG + gate stops.”
- `pm_agent_prompts`:
  - `09` implementer prompt (see below)
  - `11` QA prompt (see below)
- `pm_universal_prompt`: point to this sprint/round and remind **Composer 2 only**, **no visual approval until end**, **no version bump**, **no commit/push**.

### Add an explicit `automation` block (recommended)
Add `automation` to the round to make the DAG unambiguous (per `.cursor/plans/ai_studio_automation_contract.md`):

- `mode`: `auto_until_human_gate`
- `runnable_agents`: `["09","11"]`
- `dependencies`:
  - `{ "id": "wave1", "agents": ["09"], "parallel": false }`
  - `{ "id": "qa", "after": ["wave1"], "agents": ["11"] }`
- `human_gates`: `["visual_approval", "manual_playtest", "version_bump", "commit", "push"]`
- `success_signals`:
  - `required_log_entries`: true
  - `required_exit_codes`: `[0]`
  - `required_gates`: `["python tools/qa_smoke.py --quick"]`
- `failure_policy`:
  - `retry_limit`: 0
  - `on_failure`: `stop_for_pm`
- `model_policy`:
  - `required_model`: `composer-2`
  - `allow_overrides`: false

## Prompts (copy into PM hub)
### `pm_agent_prompts["09"]` (Implementer — MEDIUM)
Task: Make the warrior shirt red.

Scope:
- In scope:
  - Change `HeroSpriteSpec.warrior` to **(180, 45, 45)** in `game/graphics/hero_sprites.py`.
  - Ensure the change is visible in **both** render paths:
    - Pygame procedural hero frames (shirt uses `base_color`).
    - Ursina hero billboards: avoid tinting textured heroes with `COLOR_HERO = color.azure` (make warrior neutral/white when a texture is present).
- Out of scope:
  - No new assets, no new systems, no refactors.
  - No version bump, no changelog edits.

Files you MAY edit:
- `game/graphics/hero_sprites.py`
- `game/graphics/ursina_renderer.py` (only if required to prevent blue tint overriding the new red shirt)

Acceptance:
- Warriors read as **red-shirted** in both renderers.
- `python tools/qa_smoke.py --quick` will be run by Agent 11 after you finish; you do not need to run it.

Report back with:
- Files touched
- Any notes about tinting logic

### `pm_agent_prompts["11"]` (QA — LOW)
After Agent 09 reports done, run gates from repo root (PowerShell):

- `python tools/qa_smoke.py --quick`

Record:
- exit code
- any failures (paste last ~50 lines)

Stop condition:
- If gates PASS, report PASS and note that the remaining human gate is **visual approval** only.

## Orchestrator run commands (Jaimie, PowerShell)
From repo root:

1) Validate the PM hub round is runnable:
- `cd tools/ai_studio_orchestrator`
- `npm run studio -- validate --sprint orch_tiny_warrior_red --round orch_r0_impl_then_qa`

2) Dry-run the DAG:
- `npm run studio -- run --sprint orch_tiny_warrior_red --round orch_r0_impl_then_qa --dry-run`

3) Run for real (auto until human gate):
- `npm run studio -- run --sprint orch_tiny_warrior_red --round orch_r0_impl_then_qa --mode auto_until_human_gate`

4) Write dashboard:
- `npm run studio -- status --write-dashboard`

## End-of-sprint (human visual approval only)
After QA PASS and the orchestrator stops for the visual gate, do a quick manual check:
- `python main.py --no-llm` (2 minutes)
- `python main.py --renderer pygame --no-llm` (2 minutes)

Verify:
- Warrior shirts look dark red, not purple/blue.
- No obvious tint regression on other hero classes.

Constraints explicitly enforced
- No version bump
- No commit/push
- No human visual approval until the end (orchestrator must pause at `visual_approval`)
- Composer 2 only (`automation.model_policy.required_model = composer-2`)