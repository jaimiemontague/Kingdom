# WK77 Sprint Plan — Round B-2e: input_handler.py split (game/input/ package)

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; the big InputHandler method bodies extracted into a `game/input/` package behind delegating wrappers; behavior byte-identical.
**Predecessors:** WK68-76. **Roadmap:** Round B-2 (the audit's WK63-deferred input_handler split, now behind strong regression tests).

## 0. TL;DR
`game/input_handler.py` (789 LOC) is a single `InputHandler` class whose `handle_mousedown` (311 LOC: pause guard + HUD action ladder + building-panel button dispatch + world selection + placement) and `handle_keydown` (193 LOC) are the bulk. WK77 extracts these (and `select_building_for_placement`) into `game/input/` modules as functions taking the `InputHandler` as `ih`, leaving 1-line delegating wrapper methods on `InputHandler` (same names — the event loop + GameCommands callers unchanged). PURE MOVE (WK69/WK75/WK76 pattern), behavior-preserving. **Well-guarded:** the WK68 button tests + paused-click tests + `test_input_handler_gamecommands` exercise these exact routing paths; plus full suite + a sanity screenshot. Digest `b73961…` (headless sim) stays byte-identical regardless. PM writes no code.

## 1. Scope
**IN:** create a `game/input/` package and move method bodies (functions take `ih: InputHandler`):
- `game/input/mouse.py`: `handle_mousedown(ih, event)` ← `handle_mousedown` (input_handler.py:395-706); `handle_mousemove(ih, event)` ← `handle_mousemove` (707-789).
- `game/input/keyboard.py`: `handle_keydown(ih, event)` ← `handle_keydown` (187-380).
- `game/input/placement.py`: `select_building_for_placement(ih, building_type)` ← (142-186).
- `InputHandler` KEEPS: `__init__`, `process_events` (the event-poll loop — it's the router; leave it, it just dispatches to the wrappers), `_clear_hero_selection` (called by the moved mouse code via `ih._clear_hero_selection()` — keep it on InputHandler). Each extracted method becomes a 1-line delegating wrapper: `def handle_mousedown(self, event): from game.input import mouse; return mouse.handle_mousedown(self, event)`.
- Add `game/input/__init__.py`.

**OUT:** further sub-splitting handle_mousedown into hud_actions/window_drag/command_mode (the audit's finer breakdown — defer; a 311-LOC function moved verbatim is the win this sprint); the hotkey reverse-map / HUD-action-typing refactor (WK70/Round B later); any behavior change. **Do NOT restructure the class or change `process_events`'s dispatch.**

## 2. Pattern (WK75/76, verbatim)
```python
# game/input/mouse.py
from __future__ import annotations
from typing import TYPE_CHECKING
# ... same leaf imports handle_mousedown/handle_mousemove used (pygame, config, ViewMode, BUILD_HOTKEY_TO_TYPE, etc.) ...
if TYPE_CHECKING:
    from game.input_handler import InputHandler

def handle_mousedown(ih: "InputHandler", event) -> None:
    # EXACT body, self.->ih.  (self.commands stays self.commands -> ih.commands; self._clear_hero_selection() -> ih._clear_hero_selection())
    ...
```
```python
# game/input_handler.py
def handle_mousedown(self, event):
    from game.input import mouse
    return mouse.handle_mousedown(self, event)
```
TYPE_CHECKING-only InputHandler import; no cycle; copy each method's leaf imports; preserve behavior/branch-order EXACTLY (the pause guard, the HUD action ladder, the building-panel hire/enter/demolish dispatch, the WK70 hotkey reverse-map BUILD_HOTKEY_TO_TYPE in handle_keydown — all verbatim).

## 3. Definition of Done
- **A.** `pytest` all pass (baseline **720 passed / 4 skipped / 0 failed**).
- **B.** `determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`.
- **D.** `qa_smoke.py --quick` green.
- **E.** **The WK68 button + paused tests + `test_input_handler_gamecommands` pass unchanged** (they route through the moved mouse/keyboard code).
- **F.** `game/input/{mouse,keyboard,placement,__init__}.py` exist; the moved method names still on `InputHandler` as delegating wrappers; input_handler.py smaller (~789 → ~250); no import cycle.
- **G.** A sanity screenshot (pygame base_overview) confirms the game renders (no import/crash regression).
- **H.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 03):** extract the package + wrappers. Verify suite + WK68/input tests + digest.
- **W2 (Agent 11):** seam test (wrappers delegate) + full DoD + sanity screenshot.

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| handle_mousedown (311 LOC) references an engine-private name / a top-of-file import → NameError | Med-High | copy ALL leaf imports the method used; WK68 button/paused tests + full suite catch it; diff vs original |
| Import cycle (mouse/keyboard ↔ input_handler) | Med | TYPE_CHECKING-only import (proven WK75/76) |
| A pause-guard / HUD-action branch subtly altered | Med | move VERBATIM; the WK68 tests cover enter/hire/demolish/paused; manually re-read the moved block vs original |
| A selection/placement path breaks uncovered by tests | Low-Med | gate G sanity screenshot |

## 6. Success
The InputHandler's heavy mouse/keyboard/placement logic lives in `game/input/` behind delegating wrappers, input behaves identically — proven by 720+ green tests (incl. the WK68 button/paused + input tests), clean determinism guard, unchanged digest, and a sanity screenshot.

## 7. Kickoff
Roster: 03 (extraction W1), 11 (verify + DoD + screenshot W2), 08 (consult on input behavior). Order: 03 W1 → PM gate (suite + WK68/input tests + digest) → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE MOVE, behavior-preserving, keep wrapper names, TYPE_CHECKING-only import; own log; DO NOT COMMIT.
Follow-ups: finer handle_mousedown breakdown (hud_actions/window_drag/command_mode); engine.py lifecycle facade + __init__ split; hud/ursina_renderer/ursina_app splits; Move 9; world.py; config package; Round D AI; zombie purge.
