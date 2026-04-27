---
name: WK35 Refactor Stage 0 Sprint
overview: "Stage 0 of the architecture refactor: write integration tests and document the engine access inventory before touching any production code. Agent 11 writes tests, Agent 12 writes the access inventory doc."
todos:
  - id: update-pm-hub
    content: Update PM hub JSON with wk35 sprint entry, agent prompts, and send list
    status: pending
  - id: tell-jaimie
    content: Give Jaimie the send list with intelligence levels and the universal prompt to paste
    status: pending
isProject: false
---

# WK35 Sprint Plan -- Refactor Stage 0: Regression Baseline

**Sprint Phase:** Architecture Refactor Stage 0
**Master plan ref:** `.cursor/plans/master_plan_architecture_refactor.md`
**Commit convention:** `Refactor Stage 0: <description>`
**Primary QA gate:** `python tools/qa_smoke.py --quick` must still pass. No production code changes this sprint.

---

## Overview

This sprint establishes the test safety net required before any production code is touched in the architecture refactor. It consists of three tasks:

1. **Task 0-A** (Agent 11): Expand `tests/test_engine.py` with 5 new headless integration tests
2. **Task 0-B** (Agent 11): Create `tests/test_renderer_snapshot_contract.py` with 3 data-contract tests
3. **Task 0-C** (Agent 12): Create `docs/refactor/engine_access_inventory.md` documenting every `self.engine` access in the renderer files

Zero production files change. Only new test files and one new doc file are created.

---

## Agent Assignments

| Agent | Role | Tasks | Intelligence |
|-------|------|-------|-------------|
| Agent 11 (QA) | Test author | 0-A + 0-B | MEDIUM |
| Agent 12 (Tools) | Inventory doc | 0-C | LOW |

**Do NOT send to:** 02, 03, 04, 05, 06, 07, 08, 09, 10, 13, 14, 15.

---

## Detailed Tasks

### AGENT 11 -- QA Test Engineering Lead

**Task 0-A: Expand `tests/test_engine.py`**

Add 5 new test functions to the existing `tests/test_engine.py`. The exact code for each test is in the master plan section "Stage 0 > Task 0-A". The tests are:

1. `test_engine_headless_init_creates_all_systems` -- verify `GameEngine(headless=True)` creates all systems and NullStub UI
2. `test_engine_headless_ui_init_creates_ui_and_systems` -- verify `GameEngine(headless_ui=True)` creates full UI + systems
3. `test_engine_headless_tick_simulation_advances_sim_time` -- verify 60 ticks advance `_sim_now_ms`
4. `test_engine_get_game_state_has_all_required_keys` -- freeze the exact `get_game_state()` key set
5. `test_engine_full_tick_with_enemies_no_crash` -- 300-tick full orchestration with AI, no crashes

**Task 0-B: Create `tests/test_renderer_snapshot_contract.py`**

Create a new test file with 3 tests. The exact code is in the master plan section "Stage 0 > Task 0-B". The tests are:

1. `test_game_state_provides_renderer_consumed_keys` -- verify `get_game_state()` has all keys the renderer needs
2. `test_game_state_entity_lists_are_iterable` -- verify entity lists are iterable
3. `test_buildings_have_required_renderer_attributes` -- verify buildings have `building_type`, `x`, `y`, `width`, `height`, `hp`, `max_hp`, `is_constructed`

**After both tasks:**
- Run `python -m pytest tests/` -- all tests must pass (new + existing)
- Run `python tools/qa_smoke.py --quick` -- must still PASS (this includes pytest)
- Update your agent log with test count, commands, and exit codes

---

### AGENT 12 -- Tools/DevEx Lead

**Task 0-C: Create engine access inventory document**

Create `docs/refactor/engine_access_inventory.md` (create the `docs/refactor/` directory if it does not exist).

This document must list every unique `self.engine.<attribute>` access in these two files:
- `game/graphics/ursina_renderer.py`
- `game/graphics/ursina_app.py`

Format: group by category (Simulation Data, UI State, Display State, Fog State, Control Methods). For each access, list the line number(s) and a one-line description of what it is used for.

The master plan section "Stage 0 > Task 0-C" has the full inventory already extracted. Your job is to verify it against the current code (grep for `self.engine` in both files) and format it as a clean markdown document.

**After task:**
- Run `python tools/qa_smoke.py --quick` -- must still PASS (you did not change code, but confirm)
- Update your agent log

---

## Definition of Done

- [ ] `tests/test_engine.py` contains 7 tests (2 existing + 5 new)
- [ ] `tests/test_renderer_snapshot_contract.py` exists with 3 tests
- [ ] `docs/refactor/engine_access_inventory.md` exists with verified access inventory
- [ ] `python -m pytest tests/` -- all pass
- [ ] `python tools/qa_smoke.py --quick` -- PASS
- [ ] No production files changed (only new files in `tests/` and `docs/refactor/`)
- [ ] Jaimie tags commit as `pre-refactor-baseline`

---

## Universal Prompt (for Jaimie to paste)

```
You are being activated for sprint **wk35-refactor-stage0-regression-baseline**.

1) Read the master plan first:
   .cursor/plans/master_plan_architecture_refactor.md
   Section: "Stage 0: Regression Baseline and Test Hardening"

2) Read your assignment in the PM hub:
   .cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json
   -> sprints["wk35-refactor-stage0-regression-baseline"]
   -> rounds["wk35_r1_execution"]
   -> pm_agent_prompts[YOUR_AGENT_NUMBER]

3) After completing your work:
   - Update your agent log
   - Run: python tools/qa_smoke.py --quick (must PASS)
   - Report status back
```

## Send List

- **Agent 11** -- QA_TestEngineering_Lead (MEDIUM intelligence) -- writes all tests
- **Agent 12** -- ToolsDevEx_Lead (LOW intelligence) -- writes inventory doc

**Do NOT send to:** 02, 03, 04, 05, 06, 07, 08, 09, 10, 13, 14, 15.