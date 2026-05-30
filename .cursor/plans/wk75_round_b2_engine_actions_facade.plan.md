# WK75 Sprint Plan — Round B-2c: engine.py actions facade + console

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; the GameEngine action methods + cheat console extracted out of the 1678-LOC engine.py behind delegating wrappers; behavior byte-identical.
**Predecessors:** WK68-74. **Roadmap:** Round B-2 (god-file splits). engine.py is the biggest non-UI god-file; this is its first slice.

## 0. TL;DR
`game/engine.py` (1678 LOC) is the presentation-shell god-file. WK75 extracts two self-contained concerns into modules behind delegating wrappers (the proven WK69 pattern — facade functions take the live `GameEngine` as `engine`, the original methods become 1-line `return module.fn(self, ...)` shims so all call sites + tests are unchanged):
1. **Actions** → `game/engine_facades/actions.py`: `try_hire_hero`, `place_building`, `place_bounty`, `apply_hud_pin_action`.
2. **Console** → `game/console.py`: `process_command` (the cheat/chat console).
Behavior-preserving. **The WK68 button tests are the key guard** (Hire, Enter→`apply_hud_pin_action("open_building_interior")`, demolish→`apply_hud_pin_action`, build-catalog→`place_building`, place_bounty all flow through these methods); plus the full suite + a sanity screenshot. The WK67 digest (headless sim, doesn't exercise UI actions) stays byte-identical regardless. PM writes no code.

## 1. Scope
**IN:**
- `game/engine_facades/actions.py` (new): move the bodies of `try_hire_hero` (engine.py:960), `place_building` (1032), `place_bounty` (1073), `apply_hud_pin_action` (1364) into module functions taking `engine`. Keep 1-line delegating wrapper methods on GameEngine (same names — input_handler/hud/command_bar call `engine.try_hire_hero()` etc.).
- `game/console.py` (new): move `process_command` (engine.py:333, the 111-line cheat/chat console) into a function (or a small command registry) taking `engine`; keep the `GameEngine.process_command` wrapper (ursina_app.py:1408 calls `engine.process_command('/revealmap')`).
- Apply the WK69 rules: facade modules import `GameEngine` only under TYPE_CHECKING; no import cycle; copy each method's leaf imports; preserve call order/behavior exactly.

**OUT:** the selection facade (try_select_* + the "39× set-one-null-others" cleanup — less-tested, more involved → later sprint); the lifecycle facade (update/tick_simulation); the engine.py __init__ helper split; any behavior change. **Do NOT touch the already-extracted engine_facades/{camera_display,render_coordinator}.py.**

## 2. Pattern (WK69, verbatim)
```python
# game/engine_facades/actions.py
from __future__ import annotations
from typing import TYPE_CHECKING
# ... same leaf imports the methods used ...
if TYPE_CHECKING:
    from game.engine import GameEngine

def try_hire_hero(engine: "GameEngine"):
    # EXACT body of GameEngine.try_hire_hero, self.->engine.
    ...
```
```python
# game/engine.py
def try_hire_hero(self):
    from game.engine_facades import actions
    return actions.try_hire_hero(self)
```
(Top-level `from game.engine_facades import actions` + `from game import console` is fine once verified cycle-free — these modules don't import engine at module top.)

## 3. Definition of Done
- **A.** `pytest` all pass (baseline **702 passed / 4 skipped / 0 failed**).
- **B.** `determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`.
- **D.** `qa_smoke.py --quick` green.
- **E.** **The WK68 button tests pass unchanged** (`tests/test_wk68_building_buttons.py`, `tests/test_wk68_hire_button.py`) — they exercise the extracted action paths through input_handler→engine.
- **F.** `actions.py` + `console.py` exist; the 5 method names still on GameEngine as delegating wrappers; engine.py smaller (~1678 → ~1350); no import cycle.
- **G.** A sanity screenshot (pygame base_overview + a building panel with the Hire button) confirms the UI still works.
- **H.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 03):** extract actions.py + console.py + wrappers. Verify suite + WK68 button tests + digest.
- **W2 (Agent 11):** confirm the WK68 button tests + a seam test (the 5 wrappers delegate) + full DoD gate + capture the sanity screenshot (or hand to Agent 08).

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| A moved method references a name only imported at engine.py top → NameError | Med | copy each method's imports; full suite + button tests catch it |
| Import cycle (actions/console ↔ engine) | Med | TYPE_CHECKING-only engine import; wrapper imports the module (WK69 proved this works) |
| apply_hud_pin_action has many branches (demolish, interior, pin) — a missed branch | Med | move verbatim; WK68 button tests cover demolish/interior; manually check the pin/recall branches |
| A UI action subtly breaks (not caught by tests) | Low-Med | gate G sanity screenshot; the WK68 tests cover the main button actions |

## 6. Success
The GameEngine action methods + cheat console live in their own modules behind delegating wrappers, every UI action behaves identically — proven by 702+ green tests (incl. the WK68 button tests), clean determinism guard, unchanged digest, and a sanity screenshot.

## 7. Kickoff
Roster: 03 (extraction W1), 11 (verify + DoD + screenshot W2), 08 (consult on UI actions). Order: 03 W1 → PM gate (suite + button tests + digest) → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; behavior-preserving; keep wrapper names; TYPE_CHECKING-only engine import; own log; DO NOT COMMIT.
Follow-ups: engine.py selection facade + lifecycle facade + __init__ split; input_handler package; hud/ursina_renderer/ursina_app/ursina_terrain_fog_collab splits; Move 9; world.py; config package; Round D AI router/splits; zombie purge.
