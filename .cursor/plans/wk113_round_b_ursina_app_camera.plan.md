# WK113 Round B — extract the camera-control cluster from `ursina_app.py`

**Author:** Agent 01 (Executive Producer / PM)
**Status:** PLANNED → in execution
**Sprint key (PM hub):** `wk113_round_b_ursina_app_camera`
**Version target:** patch (behavior-preserving pure-move; no feature change)
**Verification class:** URSINA RENDER SLICE → **deferred-screenshot model** (headless agents have no GPU; live before/after captures are DEFERRED to the Sovereign's end-of-marathon test — scoped exception per memory `feedback_ursina_deferred_screenshots`). Headless gates below are the in-sprint proof.
**Model for all sub-agents:** `claude-opus-4-8` (opus)

---

## 0. TL;DR

`game/graphics/ursina_app.py` is the last major render god-file (**1272 LOC**). This
sprint extracts its cohesive **camera-control cluster** (9 instance methods + 2
zone-fog class constants, ~360 LOC) into a NEW sibling module
`game/graphics/ursina_app_camera.py`, using the **WK87-92/WK104-105 owner-arg
pure-move-behind-wrappers pattern** (same as the existing `ursina_app_debug_probe.py`,
WK105). `UrsinaApp` keeps 9 one-line delegating wrappers (exact original
names+signatures), so every staying call site reaches the relocated code unchanged.
**Byte-faithful move — no behavior change.** Drops `ursina_app.py` to ~915 LOC.

**Wave order:** Wave 1 (Agent 09) does the move; Wave 2 (Agent 11) writes the seam
test (modeled VERBATIM on `tests/test_wk105_ursina_app_debug_probe.py`) + runs full
DoD. PM runs the verbatim-diff gate + final DoD + commits.

**DO NOT COMMIT. DO NOT `git add`/`commit`/`push`.** PM (Agent 01) owns the commit.

---

## 1. The move map (Agent 09 — Wave 1)

Create `game/graphics/ursina_app_camera.py`. Move these **9 instance methods**
from `UrsinaApp` (lines are in current HEAD `ursina_app.py`) into it as module
functions with **`owner` as the first parameter** (every `self.` in the body →
`owner.`). Copy each body VERBATIM — change ONLY `self`→`owner`, the two intra-cluster
call rewrites (§2), and the two moved-constant references (§3). No reordering, no
renamed literals, no "cleanup".

| Method (HEAD lines) | New module function signature |
|---|---|
| `_setup_ursina_camera_for_castle` (317–499) | `_setup_ursina_camera_for_castle(owner)` |
| `_recenter_editor_camera_to_sim_xy` (501–506) | `_recenter_editor_camera_to_sim_xy(owner, sim_x, sim_y)` |
| `_reset_camera_to_default` (514–548) | `_reset_camera_to_default(owner)` |
| `_toggle_camera_lock` (550–558) | `_toggle_camera_lock(owner)` |
| `_toggle_underground_camera` (560–579) | `_toggle_underground_camera(owner)` |
| `_sync_ursina_camera_fov_from_zoom` (581–589) | `_sync_ursina_camera_fov_from_zoom(owner)` |
| `update_zone_fog_color` (600–648) | `update_zone_fog_color(owner, camera_world_x, camera_world_z)` |
| `begin_camera_underground_transition` (659–666) | `begin_camera_underground_transition(owner, target_y)` |
| `begin_camera_surface_transition` (668–677) | `begin_camera_surface_transition(owner)` |

**DO NOT MOVE (leave on `UrsinaApp`, untouched):**
- `_is_chat_active` (508–512) — NOT camera (input-gating); sits between camera methods but stays.
- `camera_active_layer` (`@property`, 654–657) — trivial getter `return self._camera_active_layer`; stays as-is. (A property does not fit the wrapper pattern and is a 1-liner; leave it.)

**MOVE these 2 class-level constants** (currently defined on `UrsinaApp` at 592–598,
used ONLY by `update_zone_fog_color`) to `ursina_app_camera.py` as **module-level
constants**, and rewrite their reads in `update_zone_fog_color` (§3):
```python
_ZONE_FOG_COLORS: dict[str, tuple[float, float, float]] = {
    "darkwood": (0.35, 0.55, 0.35),
    "mountains": (0.60, 0.70, 0.85),
    "canyon_land": (0.75, 0.60, 0.50),
    "castle_town": (0.53, 0.72, 0.88),
}
_DEFAULT_FOG_COLOR: tuple[float, float, float] = (0.53, 0.72, 0.88)
```

---

## 2. Intra-cluster call rewrites (inside the MOVED bodies → DIRECT module calls)

These calls are between two methods that BOTH move, so they become direct
module-function calls (NOT `owner.<wrapper>` hops):

- In `_reset_camera_to_default` (HEAD L544): `self._sync_ursina_camera_fov_from_zoom()`
  → `_sync_ursina_camera_fov_from_zoom(owner)`
- In `_toggle_underground_camera` (HEAD L568): `self.begin_camera_underground_transition(target_y)`
  → `begin_camera_underground_transition(owner, target_y)`
- In `_toggle_underground_camera` (HEAD L575): `self.begin_camera_surface_transition()`
  → `begin_camera_surface_transition(owner)`

No other camera method calls another camera method.

## 3. Moved-constant reads (inside `update_zone_fog_color`)

- HEAD L631 `self._ZONE_FOG_COLORS.get(...)` → `_ZONE_FOG_COLORS.get(...)`
- HEAD L631 `self._DEFAULT_FOG_COLOR` → `_DEFAULT_FOG_COLOR` (both occurrences on that line)

Everything else in the bodies is `self.<attr>` → `owner.<attr>` (e.g. `owner._atmo_fog`,
`owner._zone_fog_current`, `owner.engine`, `owner._editor_camera`, `owner._default_cam_state`,
`owner._camera_orbit_locked`, `owner._ursina_reference_fov`, `owner._map_center_xz`,
`owner._camera_active_layer`, `owner._camera_transitioning`, `owner._camera_surface_y`,
`owner._camera_transition_target_y`, `owner._camera_transition_speed`).

---

## 4. New-module skeleton (`game/graphics/ursina_app_camera.py`)

```python
"""WK113: camera-control cluster extracted from ursina_app.py (owner-arg pure-move,
WK87-92/WK104-105 pattern). UrsinaApp keeps thin delegating wrappers; these functions
take the app instance as ``owner``. Byte-faithful move — no behavior change."""
from __future__ import annotations

import math
import os
from typing import TYPE_CHECKING

import config
from ursina import EditorCamera, Vec2, Vec3, camera

from game.graphics.ursina_renderer import SCALE, sim_px_to_world_xz

if TYPE_CHECKING:  # avoid a runtime import cycle; UrsinaApp imports THIS module (lazily)
    from game.graphics.ursina_app import UrsinaApp  # noqa: F401

_ZONE_FOG_COLORS: dict[str, tuple[float, float, float]] = { ... }   # see §1
_DEFAULT_FOG_COLOR: tuple[float, float, float] = (0.53, 0.72, 0.88)


def _setup_ursina_camera_for_castle(owner: "UrsinaApp") -> None:
    ...  # verbatim body, self->owner
# ... the other 8 functions ...
```

**Function-local imports — KEEP them function-local exactly as in the originals**
(they are inside try/except or guard config fallbacks):
- `update_zone_fog_color`: `from game.world_zones import get_zone` (inside its try/except).
- `_toggle_underground_camera`: `from config import UNDERGROUND_DEPTH`.
- `begin_camera_underground_transition` AND `begin_camera_surface_transition`:
  `from config import UNDERGROUND_CAMERA_TRANSITION_SPEED`.

The nested helper `_matches_focus` inside `_setup_ursina_camera_for_castle` moves
WITH it (stays a nested def). The `print(...)` debug lines move verbatim.

**Do NOT** add `held_keys`, `mouse`, `scene`, `time`, `window`, `Texture`, `Entity`,
`pygame`, `Image`, `pytime`, `zlib` to the new module — the camera cluster uses none
of them (only `math`, `os`, `config`, `camera`, `EditorCamera`, `Vec2`, `Vec3`,
`SCALE`, `sim_px_to_world_xz`, plus the 3 function-local config/world_zones imports).
Confirm by grepping the moved bodies; add an import ONLY if a moved body references it.

---

## 5. Wrappers on `UrsinaApp` (Agent 09 — replace each moved method body with this)

Each of the 9 wrappers keeps the **exact original name + signature** and lazily
delegates (the lazy import keeps the edge one-way/acyclic):

```python
def _setup_ursina_camera_for_castle(self) -> None:
    from game.graphics import ursina_app_camera
    return ursina_app_camera._setup_ursina_camera_for_castle(self)

def _recenter_editor_camera_to_sim_xy(self, sim_x: float, sim_y: float) -> None:
    from game.graphics import ursina_app_camera
    return ursina_app_camera._recenter_editor_camera_to_sim_xy(self, sim_x, sim_y)

def _reset_camera_to_default(self) -> None:
    from game.graphics import ursina_app_camera
    return ursina_app_camera._reset_camera_to_default(self)

def _toggle_camera_lock(self) -> None:
    from game.graphics import ursina_app_camera
    return ursina_app_camera._toggle_camera_lock(self)

def _toggle_underground_camera(self) -> None:
    from game.graphics import ursina_app_camera
    return ursina_app_camera._toggle_underground_camera(self)

def _sync_ursina_camera_fov_from_zoom(self) -> None:
    from game.graphics import ursina_app_camera
    return ursina_app_camera._sync_ursina_camera_fov_from_zoom(self)

def update_zone_fog_color(self, camera_world_x: float, camera_world_z: float) -> None:
    from game.graphics import ursina_app_camera
    return ursina_app_camera.update_zone_fog_color(self, camera_world_x, camera_world_z)

def begin_camera_underground_transition(self, target_y: float) -> None:
    from game.graphics import ursina_app_camera
    return ursina_app_camera.begin_camera_underground_transition(self, target_y)

def begin_camera_surface_transition(self) -> None:
    from game.graphics import ursina_app_camera
    return ursina_app_camera.begin_camera_surface_transition(self)
```

Leave the `_ZONE_FOG_COLORS`/`_DEFAULT_FOG_COLOR` class-const definitions DELETED from
`UrsinaApp` (they moved). Leave the `camera_active_layer` property and `_is_chat_active`
in place. The staying call sites are UNCHANGED — they already call `self.<name>(...)`:
`__init__` L194 (`self._setup_ursina_camera_for_castle()`) and L195
(`self.engine._ursina_recenter_fn = self._recenter_editor_camera_to_sim_xy` — captures
the bound WRAPPER, still valid); `run()` L1134 (`self._sync_ursina_camera_fov_from_zoom()`),
L1238/1244 (`self.begin_camera_*`), L1261 (`self.update_zone_fog_color(...)`); the input
handler L811/814/817 (`self._reset_camera_to_default()` / `_toggle_camera_lock()` /
`_toggle_underground_camera()`).

Agent 09 self-verify (paste raw output):
- `python -c "import game.graphics.ursina_app"` and `python -c "import game.graphics.ursina_app_camera"` → no error.
- `python -c "import game.graphics.ursina_app_camera as m; import inspect; print([n for n in dir(m) if not n.startswith('__')])"` → shows the 9 fns + 2 consts.
- grep the new module body for any leftover bare `self` identifier (should be ZERO `self` code-identifiers).
- `python -m pytest tests/test_wk105_ursina_app_debug_probe.py -q` → still green (the debug-probe sibling is untouched and proves the app still imports/wires).
- DO NOT COMMIT. Update the Agent 09 log. Report to PM.

---

## 6. Wave 2 — Agent 11: seam test + DoD

Create `tests/test_wk113_ursina_app_camera.py` modeled VERBATIM on
`tests/test_wk105_ursina_app_debug_probe.py` (same 6 sections), retargeted to
`ursina_app_camera` and the 9 camera functions:
- (1) existence + owner-first signature for all 9 (all are instance fns → all owner-first; NO staticmethod here, so omit the `_save_window_screenshot_sync` special case).
- (2) wrapper delegation: spy+monkeypatch each of the 9; `object.__new__(UrsinaApp)` bare instance; assert `args[0] is app` + remaining args forwarded + result returned. Per-wrapper extra-args map: `_recenter_editor_camera_to_sim_xy`→`(1.0, 2.0)`, `update_zone_fog_color`→`(3.0, 4.0)`, `begin_camera_underground_transition`→`(-7.0,)`, all others→`()`.
- (3) AST no-cycle guard: `ursina_app_camera` has no module-top runtime `import ursina_app` (TYPE_CHECKING import allowed).
- (4) fresh-subprocess BOTH import orders (`ursina_app_camera`↔`ursina_app`) → OK.
- (5) wrapper-source guard: `ursina_app.py` source references `ursina_app_camera.<fn>` for each of the 9.
- (6) best-effort behavior proof through a wrapper: e.g. set `app._camera_active_layer=0`, `app._camera_transitioning=False`, `app._camera_surface_y=None`, call `app.begin_camera_underground_transition(-7.0)`, assert `app._camera_active_layer == -1` and `app._camera_transitioning is True` (skip, not fail, if the bare-instance shape needs more attrs — note `begin_camera_underground_transition` reads `camera.y` and imports config, so it may need a try/except + skip).

Then run full DoD (paste raw output):
1. `python -m pytest -q` → 0 failed (record passed/skipped; expect ≈1367+N).
2. `python tools/determinism_guard.py` → clean PASS (it excludes `game/graphics/**`, so this proves the rest of the tree is unaffected).
3. `python -m pytest tests/test_wk67_ai_boundary.py::test_ai_decision_digest_is_stable -q` → digest byte-identical (`b73961340c…d148ded`). (Camera code is not on the AI path; this is a guard.)
4. `python tools/qa_smoke.py --quick` → DONE: PASS.
5. `python -m pytest tests/test_wk113_ursina_app_camera.py tests/test_wk105_ursina_app_debug_probe.py -q` → all green.
DO NOT COMMIT. Update the Agent 11 log. Report a PASS/FAIL table to PM.

---

## 7. PM verbatim-diff gate (Agent 01 — before commit)

For each of the 9 moved methods: AST-extract the function body from HEAD
`ursina_app.py` (`git show HEAD:game/graphics/ursina_app.py`, decode utf-8, strip a
leading `﻿` BOM if present) and from the new `ursina_app_camera.py`; canonicalize
by regex-replacing whole-word `self`/`owner` → `@`, lstrip + drop blank lines; then
`difflib.unified_diff`. The ONLY allowed diffs are:
- the 3 intra-cluster call rewrites (§2: `@.<fn>(...)` → `<fn>(@, ...)`),
- the 2 moved-constant reads (§3: `@._ZONE_FOG_COLORS`/`@._DEFAULT_FOG_COLOR` → bare).
Any other diff = STOP and bounce to Agent 09. (Read both files with `encoding="utf-8-sig"`.)
This is PM-only ad-hoc review — NOT a committed test (per memory `feedback_no_git_head_exec_in_parity_tests`, no `git show HEAD:` lives in any committed test).

---

## 8. Definition of done (PM gate)

- [ ] `game/graphics/ursina_app_camera.py` exists: 9 owner-arg fns + 2 consts; ZERO `self` code-identifiers (AST `ast.Name id=='self'` count == 0).
- [ ] `ursina_app.py`: 9 delegating wrappers (exact names/sigs); class consts + camera-method bodies removed; `camera_active_layer` property + `_is_chat_active` retained; line count ~915.
- [ ] PM verbatim-diff gate: all 9 faithful (only the §2/§3 allowed diffs).
- [ ] `tests/test_wk113_ursina_app_camera.py` green (all 6 sections).
- [ ] full `pytest -q`: 0 failed; `determinism_guard` clean; WK67 digest byte-identical; `qa_smoke --quick` DONE: PASS.
- [ ] both fresh-import orders OK (in the seam test).
- [ ] DEFERRED: live before/after Ursina camera captures (castle framing, reset, camera-lock, underground/surface transition, zone-fog tint) → Sovereign's end test.
- [ ] Agent 09 + 11 logs updated. PM commits (scoped add: `game/graphics/ursina_app.py`, `game/graphics/ursina_app_camera.py`, `tests/test_wk113_ursina_app_camera.py`, plan + PM-hub + agent logs) and pushes.

---

## 9. Grounding for the NEXT sprint (WK114 candidate)

Continue decomposing `ursina_app.py` with the next cohesive cluster:
- **Input/pointer cluster** (HEAD L679–837): `_install_ursina_input_hook`,
  `_pixel_hits_opaque_ui`, `_engine_screen_pos_for_pointer`, `_sidebar_split_drag_active`,
  `_virtual_screen_pos`, `_pointer_event_pos`, `_queue_pointer_motion_event`,
  `_handle_ursina_input` (+ `_is_chat_active` can ride along — it only gates input).
- **UI-overlay/HUD-texture cluster** (L279–317 + L837–985): `_hud_quick_fingerprint`,
  `_hud_prefers_nearest_pixel_filter`, `_sync_hud_texture_filter_mode`,
  `_refresh_ui_overlay_texture`, `_sync_headless_ui_canvas_to_window`.

Still HELD: WK34 zombie-type purge (product decision pending Sovereign's keep/purge ruling).
Deferred/riskiest: TaskRouter (Move 12), SystemRunner (Move 9).
