# WK76 Sprint Plan — Round B-2d: engine.py selection facade

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; the GameEngine selection methods extracted out of engine.py behind delegating wrappers; behavior byte-identical (digest `b73961…` unchanged).
**Predecessors:** WK68-75 (WK75 extracted the actions facade + console). **Roadmap:** Round B-2, engine.py split (continues WK75).

## 0. TL;DR
WK75 pulled the actions facade + console out of engine.py (1678→1365). WK76 extracts the **selection** methods (`try_select_*`) into `game/engine_facades/selection.py` behind 1-line delegating wrappers (the proven WK69/WK75 pure-move pattern: facade fn takes the live `GameEngine` as `engine`, `self.`→`engine.`, original method becomes a shim so all call sites/tests are unchanged). Behavior-preserving; no screenshots-of-the-change needed beyond a sanity capture. Digest `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded` unchanged. PM writes no code.

**Deferred:** the "39× set-one-selection-null-others" idiom cleanup (the audit says ~80% is already dead no-ops via SelectionState — finish-wiring-and-delete is a separate, more-involved change). WK76 is a PURE MOVE only — do NOT change the selection logic, just relocate it.

## 1. Scope
**IN:** move the bodies of these into `game/engine_facades/selection.py` functions taking `engine`, leaving 1-line delegating wrappers on GameEngine (same names — input_handler/hud call `engine.try_select_*`):
- `try_select_hero` (engine.py:739), `try_select_hero_at_world` (766), `try_select_tax_collector` (793), `try_select_guard` (807), `try_select_peasant` (827), `try_select_enemy` (844), `try_ursina_select_unit_at_screen` (864), `try_select_building` (921).
- If there's a private `_select_only`/`_clear_*_selection` helper used only by these, move it too (else leave it).

**OUT:** the idiom cleanup / dead-no-op deletion; the lifecycle facade; the `__init__` split; any behavior change; engine_facades/{camera_display,render_coordinator,actions}.py and game/console.py (already done).

## 2. Pattern (WK75, verbatim)
```python
# game/engine_facades/selection.py
from __future__ import annotations
from typing import TYPE_CHECKING
# ... same leaf imports the methods used ...
if TYPE_CHECKING:
    from game.engine import GameEngine

def try_select_hero(engine: "GameEngine", screen_pos) -> bool:
    # EXACT body, self.->engine.
    ...
```
```python
# game/engine.py
def try_select_hero(self, screen_pos) -> bool:
    from game.engine_facades import selection
    return selection.try_select_hero(self, screen_pos)
```
TYPE_CHECKING-only engine import; no cycle; copy each method's leaf imports; preserve behavior/order exactly.

## 3. Definition of Done
- **A.** `pytest` all pass (baseline **709 passed / 4 skipped / 0 failed**).
- **B.** `determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`.
- **D.** `qa_smoke.py --quick` green.
- **E.** `selection.py` exists; the 8 `try_select_*` wrapper names still on GameEngine and delegating; engine.py smaller (~1365 → ~1180); no import cycle.
- **F.** A sanity screenshot (pygame base_overview) confirms the game renders (selection is interactive, but the capture confirms no import/crash regression).
- **G.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 03):** extract selection.py + wrappers. Verify suite + digest.
- **W2 (Agent 11):** seam test (8 wrappers delegate) + full DoD + sanity screenshot.

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| A moved method references a name only imported at engine.py top → NameError | Med | copy each method's imports; full suite catches it |
| Import cycle | Med | TYPE_CHECKING-only engine import (WK75 proved it) |
| A selection method shares a private helper with non-moved code | Low-Med | if a helper is shared, leave it on engine and call via engine; don't move shared state |
| Selection breaks but no test covers it | Low-Med | gate F sanity screenshot; if a selection test exists it's in the suite |

## 6. Success
The 8 selection methods live in `engine_facades/selection.py` behind delegating wrappers, selection behaves identically — proven by 709+ green tests, clean determinism guard, unchanged digest, and a sanity screenshot.

## 7. Kickoff
Roster: 03 (extraction W1), 11 (verify + DoD + screenshot W2), 08 (consult). Order: 03 W1 → PM gate (suite + digest) → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE MOVE, behavior-preserving, keep wrapper names, TYPE_CHECKING-only engine import; own log; DO NOT COMMIT.
Follow-ups: engine.py lifecycle facade + __init__ split + the 39× idiom cleanup; input_handler package; hud/ursina_renderer/ursina_app splits; Move 9; world.py; config package; Round D AI; zombie purge.
