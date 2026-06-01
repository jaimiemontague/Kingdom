# WK116 Round B — extract the input/pointer cluster from `ursina_app.py`

**Author:** Agent 01 (Executive Producer / PM)
**Status:** PLANNED → in execution
**Sprint key (PM hub):** `wk116_round_b_ursina_app_input`
**Version target:** patch (behavior-preserving owner-arg pure-move)
**Verification class:** URSINA RENDER/INPUT SLICE → **deferred-screenshot model** (headless, no GPU; live input/pointer captures deferred to the Sovereign's end test — memory `feedback_ursina_deferred_screenshots`). Headless gates below are the in-sprint proof.
**Model for all sub-agents:** `claude-opus-4-8` (opus)

---

## 0. TL;DR

Continue decomposing `game/graphics/ursina_app.py` (**961 LOC**). Extract its
**input/pointer cluster** — 9 instance methods (~158 LOC) — into a NEW sibling module
`game/graphics/ursina_app_input.py` using the SAME owner-arg pure-move-behind-wrappers
pattern as WK113 (`ursina_app_camera.py`) and WK105 (`ursina_app_debug_probe.py`).
`UrsinaApp` keeps 9 one-line delegating wrappers (exact original names+signatures).
**Byte-faithful move — no behavior change.** Drops `ursina_app.py` to ~810 LOC.

Same wave structure as WK113: Agent 09 moves (Wave 1) → PM AST verbatim-diff gate →
Agent 11 seam test (WK113-style) + full DoD (Wave 2) → PM commit.

**DO NOT COMMIT / add / push.** PM (Agent 01) owns the commit.

---

## 1. The move map (Agent 09 — Wave 1)

Create `game/graphics/ursina_app_input.py`. Move these **9 instance methods** from
`UrsinaApp` (current HEAD `ursina_app.py` lines) into it as module functions with
`owner` first (`self.`→`owner.`). Copy each body VERBATIM; change ONLY `self`→`owner`,
the intra-cluster call rewrites (§2), and keep cross-cluster + external calls per §2.

| Method (HEAD lines) | New module function signature |
|---|---|
| `_is_chat_active` (325–329) | `_is_chat_active(owner)` |
| `_install_ursina_input_hook` (368–376) | `_install_ursina_input_hook(owner)` |
| `_pixel_hits_opaque_ui` (378–387) | `_pixel_hits_opaque_ui(owner, px, py)` |
| `_engine_screen_pos_for_pointer` (389–436) | `_engine_screen_pos_for_pointer(owner)` |
| `_sidebar_split_drag_active` (438–440) | `_sidebar_split_drag_active(owner)` |
| `_virtual_screen_pos` (442–444) | `_virtual_screen_pos(owner)` |
| `_pointer_event_pos` (446–451) | `_pointer_event_pos(owner)` |
| `_queue_pointer_motion_event` (453–465) | `_queue_pointer_motion_event(owner)` |
| `_handle_ursina_input` (467–524) | `_handle_ursina_input(owner, key)` |

`_is_chat_active` (currently sandwiched among the WK113 camera methods at L325) moves
here — it only gates input. Leave `_recenter_editor_camera_to_sim_xy`, the camera
methods, and the `camera_active_layer` property exactly where they are.

---

## 2. Call rewrites inside the MOVED bodies

**Intra-cluster (both ends move) → DIRECT module-fn calls:**
- `_install_ursina_input_hook` closure: `app._handle_ursina_input(key)` →
  `_handle_ursina_input(app, key)` (the closure keeps `app = owner`, then calls the
  module fn with `app`).
- `_engine_screen_pos_for_pointer`: `self._pixel_hits_opaque_ui(px, py)` →
  `_pixel_hits_opaque_ui(owner, px, py)`.
- `_pointer_event_pos`: `self._sidebar_split_drag_active()` →
  `_sidebar_split_drag_active(owner)`; `self._virtual_screen_pos()` →
  `_virtual_screen_pos(owner)`; `self._engine_screen_pos_for_pointer()` →
  `_engine_screen_pos_for_pointer(owner)`.
- `_queue_pointer_motion_event`: `self._pointer_event_pos()` → `_pointer_event_pos(owner)`.
- `_handle_ursina_input`: `self._virtual_screen_pos()` → `_virtual_screen_pos(owner)`;
  `self._sidebar_split_drag_active()` → `_sidebar_split_drag_active(owner)`;
  `self._is_chat_active()` → `_is_chat_active(owner)`.

**Cross-cluster (target is a WK113 camera wrapper that STAYS on UrsinaApp) → keep as
`owner.<wrapper>` hops** (do NOT rewrite to direct calls — those fns live in
`ursina_app_camera` and are reached via the owner's wrappers):
- In `_handle_ursina_input`: `self._reset_camera_to_default()` → `owner._reset_camera_to_default()`;
  `self._toggle_camera_lock()` → `owner._toggle_camera_lock()`;
  `self._toggle_underground_camera()` → `owner._toggle_underground_camera()`.

All other `self.<attr>` → `owner.<attr>` (e.g. `owner.engine`, `owner.input_manager`,
`owner._pending_lmb`, `owner._last_engine_screen_pos`).

---

## 3. New-module skeleton (`game/graphics/ursina_app_input.py`)

```python
"""WK116: input/pointer cluster extracted from ursina_app.py (owner-arg pure-move,
WK105/WK113 pattern). UrsinaApp keeps thin delegating wrappers; these functions take
the app instance as ``owner``. Byte-faithful move — no behavior change."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ursina import mouse

from game.graphics.ursina_pick import pick_world_xz_on_floor_y0
from game.graphics.ursina_renderer import SCALE
from game.graphics.ursina_screenshot import save_ursina_window_screenshot
from game.input_manager import InputEvent
from game.ursina_input_manager import ursina_key_to_input_event

if TYPE_CHECKING:  # one-way edge: ursina_app imports THIS module (lazily in wrappers)
    from game.graphics.ursina_app import UrsinaApp  # noqa: F401


def _is_chat_active(owner: "UrsinaApp") -> bool:
    ...
# ... the other 8 functions ...
```

**KEEP function-local imports function-local** exactly as in the originals:
- `_install_ursina_input_hook`: `import __main__`.
- `_handle_ursina_input`: `from ursina import application` (in the F12 branch) and
  `import os as _os` (in the F12 branch). Move them verbatim, still function-local.

**Import-set rule:** add a module-top import ONLY if a moved body references the name.
Grep the moved bodies to confirm the §3 set is exactly right (e.g. confirm `mouse`,
`SCALE`, `pick_world_xz_on_floor_y0`, `InputEvent`, `ursina_key_to_input_event`,
`save_ursina_window_screenshot` are all used; do NOT add `pygame`/`Vec3`/`camera`/etc.
unless a body uses them — `_pixel_hits_opaque_ui` uses `owner.engine.screen.get_at`,
no import needed).

**Acyclic check:** `ursina_pick`, `ursina_renderer`, `ursina_screenshot`,
`input_manager`, `ursina_input_manager` must NOT import `ursina_app` at module top
(WK113 already proved `ursina_renderer` is safe). The seam test's fresh-subprocess
both-import-orders check (§5) is the guard.

---

## 4. Wrappers on `UrsinaApp` (Agent 09 — replace each moved body with this shape)

Each of the 9 wrappers keeps the EXACT original name + signature and lazily delegates:
```python
def _is_chat_active(self) -> bool:
    from game.graphics import ursina_app_input
    return ursina_app_input._is_chat_active(self)

def _install_ursina_input_hook(self) -> None:
    from game.graphics import ursina_app_input
    return ursina_app_input._install_ursina_input_hook(self)

def _pixel_hits_opaque_ui(self, px: int, py: int) -> bool:
    from game.graphics import ursina_app_input
    return ursina_app_input._pixel_hits_opaque_ui(self, px, py)

def _engine_screen_pos_for_pointer(self):
    from game.graphics import ursina_app_input
    return ursina_app_input._engine_screen_pos_for_pointer(self)

def _sidebar_split_drag_active(self) -> bool:
    from game.graphics import ursina_app_input
    return ursina_app_input._sidebar_split_drag_active(self)

def _virtual_screen_pos(self) -> tuple[int, int]:
    from game.graphics import ursina_app_input
    return ursina_app_input._virtual_screen_pos(self)

def _pointer_event_pos(self) -> tuple[int, int]:
    from game.graphics import ursina_app_input
    return ursina_app_input._pointer_event_pos(self)

def _queue_pointer_motion_event(self) -> None:
    from game.graphics import ursina_app_input
    return ursina_app_input._queue_pointer_motion_event(self)

def _handle_ursina_input(self, key: str) -> None:
    from game.graphics import ursina_app_input
    return ursina_app_input._handle_ursina_input(self, key)
```
Preserve `_engine_screen_pos_for_pointer`'s original return annotation on the wrapper
(`tuple[tuple[int, int], str, tuple[float, float] | None, float, float]`).

The staying call sites are UNCHANGED — they already call `self.<name>(...)`:
`__init__` L207 (`self._install_ursina_input_hook()`); `run()` L726
(`self._queue_pointer_motion_event()`), L730/737/738/745 (pointer helpers). No external
caller changes.

Agent 09 self-verify (paste raw output; DO NOT COMMIT):
- `python -c "import game.graphics.ursina_app"` and `python -c "import game.graphics.ursina_app_input"` → no error.
- `python -c "import ast,io; t=ast.parse(io.open('game/graphics/ursina_app_input.py',encoding='utf-8-sig').read()); print('self count =', sum(1 for n in ast.walk(t) if isinstance(n,ast.Name) and n.id=='self'))"` → `self count = 0`.
- `python -c "import game.graphics.ursina_app_input as m; print(sorted(n for n in dir(m) if n.startswith('_') and not n.startswith('__')))"` → the 9 fn names.
- `python -m pytest tests/test_wk105_ursina_app_debug_probe.py tests/test_wk113_ursina_app_camera.py -q` → still green (siblings untouched; app still imports/wires).
- Report new `ursina_app.py` line count (expect ~810).
- Update the Agent 09 log; report to PM.

---

## 5. Wave 2 — Agent 11: seam test + DoD

Create `tests/test_wk116_ursina_app_input.py` modeled VERBATIM on
`tests/test_wk113_ursina_app_camera.py` (6 sections), retargeted to
`ursina_app_input` and the 9 input functions (ALL owner-first; no staticmethod). Per-
wrapper extra-args for the delegation test: `_pixel_hits_opaque_ui`→`(10, 10)`,
`_handle_ursina_input`→`("escape",)`, all others→`()`. For section (6)
behavior-through-wrapper, use a cheap pure one: on a bare app set
`owner._left_split_drag_kind=None` and a stub `engine`/`hud`, assert
`_sidebar_split_drag_active(app)` returns the expected bool (skip on shape mismatch —
delegation tests are the core proof).

Then full DoD (paste raw output; DO NOT COMMIT):
1. `python -m pytest -q` → 0 failed (record counts; expect ≈1430+N).
2. `python tools/determinism_guard.py` → clean PASS.
3. `python -m pytest tests/test_wk67_ai_boundary.py::test_ai_decision_digest_is_stable -q` → digest byte-identical `b73961340c…d148ded`.
4. `python tools/qa_smoke.py --quick` → DONE: PASS.
5. `python -m pytest tests/test_wk116_ursina_app_input.py tests/test_wk113_ursina_app_camera.py tests/test_wk105_ursina_app_debug_probe.py -q` → all green.
Update the Agent 11 log; report a PASS/FAIL table.

---

## 6. PM verbatim-diff gate (Agent 01 — before commit)

AST-extract each of the 9 moved bodies from HEAD `ursina_app.py` and from
`ursina_app_input.py`, canonicalize whole-word `self`/`owner`→`@`, line-diff. The ONLY
allowed diffs: the §2 intra-cluster call rewrites (`@.<fn>(...)` → `<fn>(@, ...)`). The
cross-cluster camera calls stay `@.<wrapper>(...)` on BOTH sides (identical). Any other
diff = STOP, bounce to Agent 09. Read files `encoding="utf-8-sig"`; strip a leading BOM
before `ast.parse`.

## 7. Definition of done (PM gate)

- [ ] `ursina_app_input.py`: 9 owner-arg fns; ZERO `self` code-identifiers (AST).
- [ ] `ursina_app.py`: 9 delegating wrappers (exact names/sigs); bodies removed; ~810 LOC.
- [ ] PM verbatim-diff gate: all 9 faithful (only the §2 allowed rewrites).
- [ ] `tests/test_wk116_ursina_app_input.py` green (6 sections).
- [ ] full `pytest -q` 0 failed; determinism clean; WK67 digest byte-identical; qa_smoke PASS.
- [ ] both fresh-import orders OK (in the seam test).
- [ ] DEFERRED: live pointer/input + F12-screenshot + camera-hotkey (Home/L/U) captures → Sovereign end test.
- [ ] Agent 09 + 11 logs updated. PM commits (scoped add: `ursina_app.py`,
      `ursina_app_input.py`, `tests/test_wk116_ursina_app_input.py`, plan + PM hub + agent logs) + pushes.

## 8. Grounding for NEXT sprint (WK117)

`ursina_app.py` (~810 LOC) — the **UI-overlay / HUD-texture cluster**:
`_hud_quick_fingerprint`, `_hud_prefers_nearest_pixel_filter`,
`_sync_hud_texture_filter_mode` (the 3 `@staticmethod`s at L278–315 — move as plain
module fns, NO owner arg, like WK105's `_save_window_screenshot_sync`),
`_refresh_ui_overlay_texture` (L526), `_sync_headless_ui_canvas_to_window` (L655) →
new `game/graphics/ursina_app_ui_overlay.py`, owner-arg pure-move (mixed static+instance
like WK105). Then the remaining `run()` loop is the last big block. Deferred/riskiest:
TaskRouter (Move 12), SystemRunner (Move 9).
