# WK118 Round B — extract the `run()` frame-loop into `ursina_app_frame.py`

**Author:** Agent 01 (Executive Producer / PM)
**Status:** PLANNED → in execution
**Sprint key (PM hub):** `wk118_round_b_ursina_app_frame`
**Version target:** patch (behavior-preserving owner-arg pure-move)
**Verification class:** URSINA RENDER SLICE → **deferred-screenshot model** (headless, no GPU). NOTE: the per-frame `update()` loop is NOT exercised by the headless WK67 digest, determinism_guard, or qa_smoke (those drive the pygame/sim path, not the live Ursina frame loop). Therefore the **PM AST verbatim-diff gate is the PRIMARY faithfulness proof** this sprint — it must show the moved body is byte-identical to the original `update()` modulo the documented structural diffs. Live frame-loop behavior is deferred to the Sovereign's end test.
**Model for all sub-agents:** `claude-opus-4-8` (opus)

---

## 0. TL;DR

Finish decomposing `game/graphics/ursina_app.py` (**669 LOC**). Its `run()` method
(L415–669) is dominated by a single ~245-line per-frame `update()` closure (L418–663).
Extract that closure body into a new module `game/graphics/ursina_app_frame.py` as
`run_frame(owner, dt)` (owner-arg pure-move). `run()` collapses to a ~7-line Ursina
bootstrap whose `update()` shim calls `run_frame(self, time.dt)`. **Byte-faithful — no
behavior change.** Drops `ursina_app.py` to ~430 LOC (mostly `__init__`), completing
the render-god-file decomposition (1272 → ~430 across WK105/113/116/117/118).

This is the largest single move of the series and the hot path, so faithfulness is
proven by the **verbatim-diff gate** (§6), not just delegation. Waves: Agent 09 moves →
PM verbatim gate → Agent 11 seam test + full DoD → PM commit. **DO NOT COMMIT** — PM owns it.

---

## 1. The move (Agent 09 — Wave 1)

Create `game/graphics/ursina_app_frame.py`. Move the body of the `update()` closure
(HEAD `ursina_app.py` L418–663) into a module function `run_frame(owner, dt)`. Copy
VERBATIM with EXACTLY these changes — nothing else:

1. **Drop the first line** `dt = time.dt` (HEAD L419) — `dt` is now the function PARAMETER.
2. **Add `pan_speed = 55.0`** as the FIRST line of `run_frame` (it was a `run()` local at
   HEAD L416 that the closure captured; it must travel with the body). Keep the exact
   value/spelling.
3. **`self.` → `owner.`** everywhere (every `self` identifier in the body).
4. The nested `_chat_captures_keyboard()` closure (HEAD L423–428) STAYS nested inside
   `run_frame` verbatim (it captures the local `eng`; after the move `eng = owner.engine`
   is still a local at the top of `run_frame`, so the closure is unchanged except via the
   self→owner rule which does not touch it).
5. Every method the body calls on the app (`self._sync_headless_ui_canvas_to_window()`,
   `self._queue_pointer_motion_event()`, `self._virtual_screen_pos()`,
   `self._pointer_event_pos()`, `self._sidebar_split_drag_active()`,
   `self._engine_screen_pos_for_pointer()`, `self._record_fps_probe_stage_ms(...)`,
   `self._install_worker_scale_comparison_shot()`, `self._record_fps_probe_sample(...)`,
   `self._maybe_auto_screenshot_then_quit()`, `self._sync_ursina_camera_fov_from_zoom()`,
   `self.begin_camera_underground_transition(...)`, `self.begin_camera_surface_transition()`,
   `self.update_zone_fog_color(...)`) becomes `owner.<same method>(...)` — i.e. these stay
   as `owner.<wrapper>` hops (they are wrappers on UrsinaApp delegating to the WK113/116/117
   sibling modules; do NOT rewrite them to direct module-fn calls).

KEEP all function-local imports function-local exactly as in the original:
`from config import TILE_SIZE` (HEAD L451), `from ursina import application` (L494),
`import sys` (L498), `from game.graphics.terrain_height import get_terrain_height,
is_initialized as _terrain_ok` (L609), `from config import UNDERGROUND_DEPTH` (L634).

---

## 2. New-module skeleton (`game/graphics/ursina_app_frame.py`)

```python
"""WK118: the per-frame update() loop extracted from ursina_app.py's run() (owner-arg
pure-move). UrsinaApp.run() keeps a thin update() shim that calls run_frame(self, time.dt).
Byte-faithful move — no behavior change."""
from __future__ import annotations

import time as pytime
from typing import TYPE_CHECKING

import config
from ursina import Vec3, camera, held_keys, mouse

from game.graphics.ursina_input_debug import is_ursina_debug_input_enabled, print_wk20_input_line
from game.input_manager import InputEvent

if TYPE_CHECKING:  # one-way edge: ursina_app imports THIS module (lazily in the shim)
    from game.graphics.ursina_app import UrsinaApp  # noqa: F401


def run_frame(owner: "UrsinaApp", dt) -> None:
    pan_speed = 55.0
    eng = owner.engine

    def _chat_captures_keyboard() -> bool:
        ...  # verbatim nested closure

    ...  # the rest of the update() body, self->owner, function-local imports kept local
```

**Import-set rule:** add a module-top import ONLY if the moved body references the name.
Grep the body to confirm the set above is exactly right — confirm it uses `pytime`
(`perf_counter`), `config` (`ZOOM_STEP`), `Vec3`/`camera`/`held_keys`/`mouse` (ursina),
`InputEvent`, `is_ursina_debug_input_enabled`/`print_wk20_input_line`. Do NOT import
`time` (the `time.dt` read stays in the `run()` shim, NOT in `run_frame`). Do NOT import
`pygame`/`Texture`/etc. unless a body line uses it.

**Acyclic:** `ursina_input_debug` and `input_manager` must not import `ursina_app` at
module top (confirm). The seam test's fresh-subprocess both-orders check (§5) is the guard.

---

## 3. The thin `run()` shim (Agent 09 — replace L415–669 with this)

```python
def run(self):
    def update():
        from game.graphics import ursina_app_frame
        ursina_app_frame.run_frame(self, time.dt)

    import __main__

    __main__.update = update
    self.app.run()
```
`time` is already imported at the top of `ursina_app.py` (`from ursina import ... time ...`),
so `time.dt` resolves in the shim. Leave `__main__.update = update` and `self.app.run()`
exactly as before.

Agent 09 self-verify (paste raw output; DO NOT COMMIT):
- `python -c "import game.graphics.ursina_app"` and `python -c "import game.graphics.ursina_app_frame"` → no error.
- `python -c "import ast,io; t=ast.parse(io.open('game/graphics/ursina_app_frame.py',encoding='utf-8-sig').read()); print('self count =', sum(1 for n in ast.walk(t) if isinstance(n,ast.Name) and n.id=='self'))"` → `self count = 0`.
- `python -c "import game.graphics.ursina_app_frame as m; import inspect; print(list(inspect.signature(m.run_frame).parameters))"` → `['owner', 'dt']`.
- `python -m pytest tests/test_wk105_ursina_app_debug_probe.py tests/test_wk113_ursina_app_camera.py tests/test_wk116_ursina_app_input.py tests/test_wk117_ursina_app_ui_overlay.py -q` → still green.
- Report new `ursina_app.py` line count (expect ~430) and confirm `run()` is now the ~7-line shim.
- Update the Agent 09 log; report to PM.

---

## 4. (no test contract changes) — only NEW seam test in Wave 2

No existing test pins the `update()` closure internals (it is a live-loop closure). So
there is no contract to rewrite; Wave 2 only ADDS the seam test.

---

## 5. Wave 2 — Agent 11: seam test + DoD

Create `tests/test_wk118_ursina_app_frame.py`:
- **Existence + signature:** `ursina_app_frame.run_frame` exists, is callable, signature
  `(owner, dt)` (first param `owner`).
- **Shim delegation:** `UrsinaApp.run` source (read `inspect.getsource`, utf-8-sig
  tolerant) contains `ursina_app_frame.run_frame(self, time.dt)` and defines a nested
  `update`; assert `run()`'s body no longer contains the old loop markers (e.g.
  `_chat_captures_keyboard`, `pan_speed = 55.0`, `tick_simulation`) — they moved out.
- **Source guard:** `ursina_app.py` source references `ursina_app_frame.run_frame`.
- **AST no-cycle:** `ursina_app_frame` has no module-top runtime `import ...ursina_app`
  (TYPE_CHECKING UrsinaApp allowed).
- **fresh-subprocess BOTH import orders** (`ursina_app_frame` ↔ `ursina_app`) → OK.
- **Best-effort drive (skip-friendly):** build a stub `owner = types.SimpleNamespace(...)`
  with the attrs `run_frame` reads early (`engine` with `tick_simulation`/`get_game_state`/
  `paused`/`pause_menu`/`zoom_by`/`_last_frame_dt_ms`/`running=True`, `input_manager`,
  `_pending_lmb=False`, the fps-probe + camera-state flags, the owner methods as no-op
  lambdas) and monkeypatch the module globals (`camera`, `held_keys`, `mouse`) with
  stubs; call `run_frame(owner, 0.016)` and assert `owner.engine.tick_simulation` was
  invoked once. Wrap in try/except + `pytest.skip(...)` on shape mismatch — this is a
  best-effort smoke; the verbatim-diff gate + the structural pins are the core proof.
  (Document in the test docstring that the live loop is deferred-screenshot-verified.)

Then full DoD (paste raw output; DO NOT COMMIT):
1. `python -m pytest -q` → 0 failed (record counts).
2. `python tools/determinism_guard.py` → clean PASS.
3. `python -m pytest tests/test_wk67_ai_boundary.py::test_ai_decision_digest_is_stable -q` → digest byte-identical `b73961340c…d148ded`.
4. `python tools/qa_smoke.py --quick` → DONE: PASS.
5. `python -m pytest tests/test_wk118_ursina_app_frame.py tests/test_wk117_ursina_app_ui_overlay.py tests/test_wk116_ursina_app_input.py tests/test_wk113_ursina_app_camera.py tests/test_wk105_ursina_app_debug_probe.py -q` → all green.
Update the Agent 11 log; report a PASS/FAIL table.

---

## 6. PM verbatim-diff gate (Agent 01 — PRIMARY proof, before commit)

AST-extract the original `update()` closure body from HEAD `ursina_app.py` (it is the
inner `FunctionDef` named `update` inside `run`) and the `run_frame` body from
`ursina_app_frame.py`. Canonicalize whole-word `self`/`owner`→`@`, line-diff. The ONLY
allowed diffs:
- HEAD-only line `dt = time.dt` (removed — `dt` is now the param).
- NEW-only line `pan_speed = 55.0` (hoisted into `run_frame`; it was the captured `run()`
  local). On the HEAD side `pan_speed` is referenced but not defined in `update()`; on
  the NEW side it is defined at the top — so this single added line is allowed.
Every OTHER line must be IDENTICAL after canonicalization (including the nested
`_chat_captures_keyboard` and all `owner.<wrapper>(...)` calls). Any other diff = STOP,
bounce to Agent 09. Read files `encoding="utf-8-sig"`; strip a leading BOM before parse.
This gate is load-bearing this sprint (the loop has no headless runtime coverage).

## 7. Definition of done (PM gate)

- [ ] `ursina_app_frame.py`: `run_frame(owner, dt)`; ZERO `self` code-identifiers (AST).
- [ ] `ursina_app.py`: `run()` is the ~7-line shim; `update()` body gone; ~430 LOC.
- [ ] PM verbatim-diff gate: run_frame body == original update() body modulo ONLY the two
      documented structural diffs (dt-param drop, pan_speed hoist).
- [ ] `tests/test_wk118_ursina_app_frame.py` green.
- [ ] full `pytest -q` 0 failed; determinism clean; WK67 digest byte-identical; qa_smoke PASS.
- [ ] both fresh-import orders OK.
- [ ] DEFERRED: live frame-loop (pan/zoom, camera transitions, terrain clamp, hero-follow,
      zone fog, auto-exit, HUD upload) → Sovereign end test. Flag this prominently in the
      closeout since the loop has no headless runtime coverage.
- [ ] Agent 09 + 11 logs updated. PM commits (scoped add: `ursina_app.py`,
      `ursina_app_frame.py`, `tests/test_wk118_ursina_app_frame.py`, plan + PM hub + agent logs) + pushes.

## 8. Grounding for NEXT sprint (WK119)

`ursina_app.py` (~430 LOC) is now essentially `__init__` (scene/entity/camera
construction, HEAD L58–266) + the thin `run()` shim. Candidate WK119: split `__init__`'s
scene-construction into `game/graphics/ursina_app_scene.py::build_scene(owner)` (owner-arg;
the env-read/state-init prologue stays in `__init__`, the entity/light/sky/terrain/overlay
construction moves out). This is an init-split (sets `owner.*` attrs) rather than a method
move — ground the attr-assignment boundary carefully; verbatim-diff still applies.
ALTERNATIVELY pivot off ursina_app to the digest-guarded sim refactors now that the render
god-file is essentially done: TaskRouter (`ai/basic_ai.py update_hero` → `ai/task_router.py`,
Move 12) and SystemRunner (sim_engine update ordering, Move 9) — both are HEADLESS-verifiable
via the WK67 digest (must stay byte-identical) + determinism + full suite, which is STRONGER
coverage than the deferred render slices. PM may prefer these next for higher-confidence wins.
