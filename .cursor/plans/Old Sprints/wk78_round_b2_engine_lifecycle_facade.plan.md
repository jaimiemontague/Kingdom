# WK78 Sprint Plan — Round B-2f: engine.py lifecycle facade

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; the GameEngine per-frame lifecycle methods extracted out of engine.py behind delegating wrappers; behavior byte-identical (digest `b73961…` unchanged).
**Predecessors:** WK75 (actions+console), WK76 (selection). **Roadmap:** Round B-2 engine.py split (third/final core slice).

## 0. TL;DR
WK75/76 pulled actions+console+selection out of engine.py (1678→1184). WK78 extracts the **per-frame lifecycle** methods into `game/engine_facades/lifecycle.py` behind 1-line delegating wrappers (the proven pure-move pattern: facade fn takes the live `GameEngine` as `engine`, `self.`→`engine.`, original becomes a shim). These are the frame-step orchestration; moving them is a pure relocation. **Well-guarded:** `qa_smoke --quick` runs the sim, the sanity screenshot runs the full engine to render a frame, the WK67 digest exercises the sim tick, plus the 732-test suite. Digest `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded` unchanged. PM writes no code.

## 1. Scope
**IN:** move the bodies of these into `game/engine_facades/lifecycle.py` functions taking `engine`, leaving 1-line delegating wrappers on GameEngine (same names — `run()` calls `self.update()`, ursina_app/pygame loop call `self.tick_simulation()`):
- `update` (engine.py:692), `_prepare_sim_and_camera` (784), `_update_render_animations` (818), `tick_simulation` (1083).

**OUT (leave on GameEngine):** `build_snapshot` (1007) + `build_presentation_frame` (1028) — recently rewritten in WK67/68 (DTOs), keep stable; `update_camera` (966) — camera, a different facade; `run` (1156) — the top-level loop; the `__init__`; everything else. No behavior change. **Do NOT touch engine_facades/{camera_display,render_coordinator,actions,selection}.py or game/console.py.**

## 2. Pattern (WK75/76, verbatim)
```python
# game/engine_facades/lifecycle.py
from __future__ import annotations
from typing import TYPE_CHECKING
# ... same leaf imports the methods used ...
if TYPE_CHECKING:
    from game.engine import GameEngine

def update(engine: "GameEngine", dt: float) -> None:
    # EXACT body, self.->engine.   (calls to other moved methods become engine._prepare_sim_and_camera(dt) etc. via the wrapper, OR call the lifecycle fn directly — keep it simple: go through engine.<name> so the wrappers stay the single seam)
    ...
```
```python
# game/engine.py
def update(self, dt: float):
    from game.engine_facades import lifecycle
    return lifecycle.update(self, dt)
```
TYPE_CHECKING-only engine import; no cycle; copy each method's leaf imports; preserve behavior/order EXACTLY. When a moved method calls another moved method, route through `engine.<name>(...)` (the wrapper) so behavior + the seam are unchanged.

## 3. Definition of Done
- **A.** `pytest` all pass (baseline **732 passed / 4 skipped / 0 failed**).
- **B.** `determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`.
- **D.** `qa_smoke.py --quick` green (runs the sim — exercises tick_simulation/update).
- **E.** `lifecycle.py` exists; the 4 wrapper names still on GameEngine and delegating; engine.py smaller (~1184 → ~900); no import cycle.
- **F.** A sanity screenshot (pygame base_overview — runs the full engine update/tick/render pipeline) confirms a normal frame.
- **G.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 03):** extract lifecycle.py + wrappers. Verify suite + digest + qa_smoke.
- **W2 (Agent 11):** seam test (4 wrappers delegate) + full DoD + sanity screenshot.

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Central frame methods — a missed import/branch breaks the loop | Med | qa_smoke runs the sim + sanity screenshot runs the engine — a broken loop fails both; full suite + digest catch sim drift |
| A moved method calls another moved method and the seam changes | Low-Med | route inter-method calls through engine.<wrapper> (§2); move verbatim |
| Import cycle | Med | TYPE_CHECKING-only import (proven WK75/76) |
| Frame-timing/order subtly altered | Low | move verbatim; digest (sim tick) + qa_smoke guard it |

## 6. Success
The GameEngine per-frame lifecycle lives in `engine_facades/lifecycle.py` behind delegating wrappers, the game updates/ticks/renders identically — proven by 732+ green tests, clean determinism guard, unchanged digest, green qa_smoke, and a sanity screenshot.

## 7. Kickoff
Roster: 03 (extraction W1), 11 (verify + DoD + screenshot W2), 10 (consult on frame/perf). Order: 03 W1 → PM gate (suite + digest + qa_smoke) → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE MOVE, behavior-preserving, keep wrapper names, route inter-method calls through engine.<wrapper>, TYPE_CHECKING-only import; own log; DO NOT COMMIT.
Follow-ups: engine.py __init__ split + 39× idiom cleanup; the BIG presentation splits (hud.py 2477 / ursina_renderer.py 1985 / ursina_terrain_fog_collab.py 1783 / ursina_app.py 1525 — screenshot-heavy); Move 9; world.py; config package; audio split; clusters 3/4/5; Round D AI router/splits; Round E audit; zombie purge.
