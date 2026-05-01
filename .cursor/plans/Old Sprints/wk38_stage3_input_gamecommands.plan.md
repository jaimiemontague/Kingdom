# WK38 — Stage 3: InputHandler + `GameCommands` protocol

## Source of truth

- **Stage 3 (scope, DoD, Option A Protocol):** [.cursor/plans/master_plan_architecture_refactor.md](master_plan_architecture_refactor.md) — *Stage 3: Input Handler Decoupling* (~L794–858).
- **Stage owner matrix:** same file — Agent 03 (HIGH), Agent 11 (LOW), Agent 08 consult (LOW).
- **Prior sprint pattern:** multi-round, gates per round — [.cursor/plans/wk37_stage2_simengine_split_1bc48a29.plan.md](wk37_stage2_simengine_split_1bc48a29.plan.md).

## Current code reality

- [game/input_handler.py](../../game/input_handler.py): **~630 lines**; `InputHandler(engine)` constructed from [game/engine.py](../../game/engine.py). **~160+** `engine.` access sites (actions, panels, `economy`, `world`, private engine fields, etc.).
- Ursina: input construction is centralized in `GameEngine` (Ursina references InputHandler in comments only).

## Definition of Done (sprint exit)

- `InputHandler.__init__` takes **`GameCommands`**, not `GameEngine`.
- [game/input_handler.py](../../game/input_handler.py) uses **`self.commands` only** — no runtime import of `GameEngine` except `TYPE_CHECKING` if needed.
- **Gates:** `python -m pytest tests/` PASS; `python tools/qa_smoke.py --quick` PASS; `python tools/validate_assets.py --report` exit 0 (warns OK).
- **Manual:** default Ursina + `python main.py --renderer pygame --no-llm` (2D) + spot `python main.py --provider mock` as needed.

## Architecture (Option A — locked)

- New [game/game_commands.py](../../game/game_commands.py): **`GameCommands` Protocol** (actions + state queries + explicit bridges for private engine hooks / panels as needed).
- Concrete **EngineBackedGameCommands** (same file or engine): delegates 1:1 to today’s `GameEngine` — behavior-preserving decouple, not a UI rewrite.

## Rounds

| Round | Goal |
|--------|------|
| **WK38-R1** | Inventory of distinct capabilities; `GameCommands` + `EngineBackedGameCommands`; `InputHandler(commands)`; migrate first vertical slice (enough to run) or wire constructor and begin migration. |
| **WK38-R2** | Mechanical migration: `handle_keydown`, `handle_mousedown`, `handle_mousemove`, helpers. Extend protocol. No intended behavior change. |
| **WK38-R3** | Tests (mock `GameCommands`), grep cleanup, optional [docs/refactor/engine_access_inventory.md](../../docs/refactor/engine_access_inventory.md) subsection; **Agent 08** UX consult checklist. |

**Closeout:** `rg "self\\.engine|engine = self\\.engine" game/input_handler.py` should be **empty** before calling Stage 3 done.

## Out of scope

- Stage 4 (PygameRenderer extraction).
- Bumping version / CHANGELOG (Jaimie’s call).

## Gates (each round, minimum)

```powershell
python -m pytest tests/
if ($LASTEXITCODE -ne 0) { exit 1 }
python tools/qa_smoke.py --quick
if ($LASTEXITCODE -ne 0) { exit 1 }
python tools/validate_assets.py --report
```

R3 manual (from repo root):

```powershell
python main.py --no-llm
```

```powershell
python main.py --renderer ursina --no-llm
```
