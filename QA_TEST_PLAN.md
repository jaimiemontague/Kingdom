# QA Test Plan (Prototype)

## Goals
- Prevent **crashes**, softlocks, and obvious economy/combat regressions.
- Make bugs **reproducible** (seeded, scripted where possible).
- Keep checks **cheap** to run locally before changes merge.

## Test Layers
- **Automated smoke (headless)**: `tools/qa_smoke.py` (wraps `tools/observe_sync.py`)
- **Manual smoke (interactive)**: short in-game checklist
- **Regression scenarios**: targeted “known fragile” behaviors that frequently break

## High-Risk Areas (focus)
- **Combat targeting**: retarget-on-hit, lair interactions, multi-attacker accounting
- **Economy**: taxes, hero shopping loops, potion research, building costs/prereqs
- **AI + LLM**: cooldown gating, decision application, graceful fallback when provider fails
- **Construction / peasants**: new building build/repair priorities (esp. castle repair)
- **Performance**: entity count scaling, pathfinding spikes

## Automated Smoke (recommended)
Run:
- `python tools/qa_smoke.py --quick`

What it covers (via `observe_sync`):
- Headless boot and N-second sim tick
- Basic AI loop + movement updates
- Combat system execution
- Peasant construction/repair exercise
- Optional mock-LLM decision path
- **QA assertions** (nonzero exit on failure):
  - At least one bounty exists (in bounty-enabled profiles)
  - At least one bounty responder appears after warmup
  - If/when `hero.intent` is implemented, it must become non-empty after warmup
- **wk12 Chronos**: `--speed-multiplier` headless runs at 0.1x, 0.25x, 0.5x, 1.0x (sim-time equivalent); occupancy assertions when Building has `occupants`/`get_occupant_count()` or Inn `heroes_resting`
- **wk13 Living Interiors**: `interior_view` scenario — MicroViewManager `enter_interior()`/`exit_interior()` no-crash in headless; building-destroyed path (`exit_interior(reason="destroyed")`); occupancy assertions still run

## Manual Smoke (5–10 minutes)
Run one of:
- `python main.py --provider mock`
- `python main.py --no-llm`

Checklist:
- **Boot**: game starts without exceptions, no frozen black screen.
- **Input**:
  - Build selection hotkeys (at least `1`, `2`) highlight/enter placement mode.
  - Cancel selection and pause works (`Esc`).
  - Debug panel toggle works (`F1`).
- **Core loop**:
  - Place a building and verify it starts unconstructed (low HP) and peasants respond.
  - Hire a hero and verify they roam/engage enemies.
  - Place a bounty and verify at least one hero responds over time.
- **UI sanity**: HUD renders, no massive text overlap, no rapid spam messages.

## Regression Scenarios (add as we find bugs)
Keep a short list of “always re-check” items here. Suggested starters:
- **Peasants prioritize castle repair over construction** after castle takes damage.
- **Goblin retarget-on-hit** works (attacker shifts off a building when a hero hits it).
- **No duplicate hero names** in a single run (or if duplicates exist, confirm it’s harmless).
- **Bounty responders update**: after placing a bounty, responders count should go from 0 to >0 within ~30s in typical conditions.
- **Hero intent display** (when implemented): selected hero shows a non-empty “Current intent” and updates as behavior changes.

## Reporting
Use `BUG_REPORT_TEMPLATE.md` for consistent, actionable bug reports.


