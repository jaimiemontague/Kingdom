# WK117 Round B — extract the UI-overlay / HUD-texture cluster from `ursina_app.py`

**Author:** Agent 01 (Executive Producer / PM)
**Status:** PLANNED → in execution
**Sprint key (PM hub):** `wk117_round_b_ursina_app_ui_overlay`
**Version target:** patch (behavior-preserving owner-arg pure-move)
**Verification class:** URSINA RENDER SLICE → **deferred-screenshot model** (headless, no GPU; the HUD→GPU texture upload + dirty-row blit are display artifacts; live captures deferred to the Sovereign end test). Headless gates below are the in-sprint proof.
**Model for all sub-agents:** `claude-opus-4-8` (opus)

---

## 0. TL;DR

Continue decomposing `game/graphics/ursina_app.py` (**833 LOC**). Extract its
**UI-overlay / HUD-texture cluster** — **3 `@staticmethod`s + 2 instance methods**
(~165 LOC) — into a NEW sibling `game/graphics/ursina_app_ui_overlay.py` using the
WK105 MIXED static+instance owner-arg pure-move pattern (WK105 moved `_save_window_screenshot_sync`
as a plain static + 7 instance fns — same shape). `UrsinaApp` keeps 5 one-line
delegating wrappers (3 stay `@staticmethod`, 2 owner-first). **Byte-faithful — no
behavior change.** Drops `ursina_app.py` to ~670 LOC.

Same waves as WK113/116: Agent 09 moves → PM AST verbatim-diff gate → Agent 11 seam
test (WK105-style mixed) + full DoD → PM commit. **DO NOT COMMIT** — PM owns it.

---

## 1. The move map (Agent 09 — Wave 1)

Create `game/graphics/ursina_app_ui_overlay.py`. Move these 5 members (current HEAD
`ursina_app.py` lines) into it. Copy each body VERBATIM; change ONLY `self`→`owner`
(instance fns) and the intra-cluster call rewrites (§2).

**3 `@staticmethod`s → PLAIN module functions (NO `owner` arg, signatures unchanged):**
| Method (HEAD lines) | New module function |
|---|---|
| `_hud_quick_fingerprint` (278–296) | `_hud_quick_fingerprint(surf)` |
| `_hud_prefers_nearest_pixel_filter` (298–301) | `_hud_prefers_nearest_pixel_filter()` |
| `_sync_hud_texture_filter_mode` (303–315) | `_sync_hud_texture_filter_mode(tex)` |

**2 instance methods → owner-first module functions:**
| Method (HEAD lines) | New module function |
|---|---|
| `_refresh_ui_overlay_texture` (398–525) | `_refresh_ui_overlay_texture(owner)` |
| `_sync_headless_ui_canvas_to_window` (527–544) | `_sync_headless_ui_canvas_to_window(owner)` |

Leave `_read_int_env` (267–276, generic env helper) where it is — NOT part of this cluster.

---

## 2. Call rewrites inside the MOVED bodies

All these calls are between members that BOTH move → DIRECT module-fn calls:
- In `_sync_hud_texture_filter_mode` (HEAD L307): `UrsinaApp._hud_prefers_nearest_pixel_filter()`
  → `_hud_prefers_nearest_pixel_filter()`.
- In `_refresh_ui_overlay_texture`:
  - L415 + L436 `self._hud_quick_fingerprint(surf)` → `_hud_quick_fingerprint(surf)`
    (static — pass `surf`, NO owner).
  - L457 + L471 `self._sync_hud_texture_filter_mode(self._hud_composite_texture)` →
    `_sync_hud_texture_filter_mode(owner._hud_composite_texture)` (static — pass the tex).
- `_sync_headless_ui_canvas_to_window` has NO intra-cluster calls.

All other `self.<attr>` in the 2 instance bodies → `owner.<attr>` (e.g. `owner.engine`,
`owner.ui_overlay`, `owner._hud_composite_texture`, `owner._hud_composite_size`,
`owner._hud_quick_sig`, `owner._hud_prev_raw`, `owner._last_ui_overlay_scale`,
`owner.input_manager`).

---

## 3. New-module skeleton (`game/graphics/ursina_app_ui_overlay.py`)

```python
"""WK117: UI-overlay / HUD-texture cluster extracted from ursina_app.py (mixed
static+instance owner-arg pure-move, WK105 pattern). UrsinaApp keeps thin delegating
wrappers (3 @staticmethod, 2 owner-first). Byte-faithful move — no behavior change."""
from __future__ import annotations

import zlib
from typing import TYPE_CHECKING

import pygame
from ursina import Texture, camera, window

from game.display_manager import DisplayManager

if TYPE_CHECKING:  # one-way edge: ursina_app imports THIS module (lazily in wrappers)
    from game.graphics.ursina_app import UrsinaApp  # noqa: F401


def _hud_quick_fingerprint(surf: "pygame.Surface") -> int:
    ...  # verbatim body (uses pygame, zlib)


def _hud_prefers_nearest_pixel_filter() -> bool:
    ...


def _sync_hud_texture_filter_mode(tex: "Texture | None") -> None:
    ...  # calls _hud_prefers_nearest_pixel_filter() directly


def _refresh_ui_overlay_texture(owner: "UrsinaApp") -> None:
    ...  # verbatim body, self->owner; keep the two function-local panda3d imports


def _sync_headless_ui_canvas_to_window(owner: "UrsinaApp") -> None:
    ...  # verbatim body, self->owner
```

**KEEP function-local (in `_refresh_ui_overlay_texture`):**
`from panda3d.core import Texture as PandaTexture` (HEAD L443) and
`from panda3d.core import PNMImage as _PNMImage` (HEAD L501) — both stay function-local.

**Import-set rule:** add a module-top import ONLY if a moved body references the name.
Grep the moved bodies to confirm the §3 set is exactly right — `pygame` (tobytes/image),
`zlib` (crc32), `Texture`/`camera` (refresh), `window`+`DisplayManager` (canvas-sync).
Do NOT add `Entity`/`Vec3`/`os`/`Image`/etc. unless a body uses it.

**Acyclic:** `game.display_manager` must NOT import `ursina_app` at module top (it is a
lower-level util — confirm). The seam test's fresh-subprocess both-import-orders check
(§5) is the guard.

---

## 4. Wrappers on `UrsinaApp` (Agent 09 — replace each moved body with this shape)

3 stay `@staticmethod` (signatures unchanged), 2 owner-first. All lazily delegate:
```python
@staticmethod
def _hud_quick_fingerprint(surf: pygame.Surface) -> int:
    from game.graphics import ursina_app_ui_overlay
    return ursina_app_ui_overlay._hud_quick_fingerprint(surf)

@staticmethod
def _hud_prefers_nearest_pixel_filter() -> bool:
    from game.graphics import ursina_app_ui_overlay
    return ursina_app_ui_overlay._hud_prefers_nearest_pixel_filter()

@staticmethod
def _sync_hud_texture_filter_mode(tex: Texture | None) -> None:
    from game.graphics import ursina_app_ui_overlay
    return ursina_app_ui_overlay._sync_hud_texture_filter_mode(tex)

def _refresh_ui_overlay_texture(self) -> None:
    from game.graphics import ursina_app_ui_overlay
    return ursina_app_ui_overlay._refresh_ui_overlay_texture(self)

def _sync_headless_ui_canvas_to_window(self) -> None:
    from game.graphics import ursina_app_ui_overlay
    return ursina_app_ui_overlay._sync_headless_ui_canvas_to_window(self)
```
Staying call sites are UNCHANGED — `run()` L595 (`self._sync_headless_ui_canvas_to_window()`),
L722 (`self._refresh_ui_overlay_texture()`), L725 (`self._sync_hud_texture_filter_mode(...)`).

Agent 09 self-verify (paste raw output; DO NOT COMMIT):
- `python -c "import game.graphics.ursina_app"` and `python -c "import game.graphics.ursina_app_ui_overlay"` → no error.
- `python -c "import ast,io; t=ast.parse(io.open('game/graphics/ursina_app_ui_overlay.py',encoding='utf-8-sig').read()); print('self count =', sum(1 for n in ast.walk(t) if isinstance(n,ast.Name) and n.id=='self'))"` → `self count = 0`.
- `python -c "import game.graphics.ursina_app_ui_overlay as m; print(sorted(n for n in dir(m) if n.startswith('_') and not n.startswith('__')))"` → the 5 fn names.
- `python -m pytest tests/test_wk105_ursina_app_debug_probe.py tests/test_wk113_ursina_app_camera.py tests/test_wk116_ursina_app_input.py -q` → still green.
- Report new `ursina_app.py` line count (expect ~670).
- Update the Agent 09 log; report to PM.

---

## 5. Wave 2 — Agent 11: seam test + DoD

Create `tests/test_wk117_ursina_app_ui_overlay.py` modeled on `tests/test_wk105_ursina_app_debug_probe.py`
(it is the MIXED static+instance template). Retarget to `ursina_app_ui_overlay`:
- INSTANCE fns (owner-first): `_refresh_ui_overlay_texture`, `_sync_headless_ui_canvas_to_window`
  — existence + `params[0] == "owner"` + wrapper delegates with the bare app as owner.
- STATIC fns (NOT owner-first): `_hud_quick_fingerprint` (params start `["surf"]`),
  `_hud_prefers_nearest_pixel_filter` (no params), `_sync_hud_texture_filter_mode`
  (params start `["tex"]`) — existence + first param != "owner" + the `@staticmethod`
  wrapper delegates with the passthrough args (mirror WK105's
  `test_save_window_screenshot_sync_wrapper_delegates`).
- AST no-cycle guard (no module-top `import ursina_app`; TYPE_CHECKING UrsinaApp allowed).
- fresh-subprocess BOTH import orders (`ursina_app_ui_overlay` ↔ `ursina_app`) → OK.
- wrapper-source guard: `ursina_app.py` references `ursina_app_ui_overlay.<fn>` for all 5.
- behavior (best-effort): `_hud_prefers_nearest_pixel_filter()` returns `True` (cheap pure
  proof through the static wrapper); optionally `_hud_quick_fingerprint(pygame.Surface((8,8)))`
  returns an int (build a tiny surface; skip on shape mismatch).

Then full DoD (paste raw output; DO NOT COMMIT):
1. `python -m pytest -q` → 0 failed (record counts; expect ≈1463+N).
2. `python tools/determinism_guard.py` → clean PASS.
3. `python -m pytest tests/test_wk67_ai_boundary.py::test_ai_decision_digest_is_stable -q` → digest byte-identical `b73961340c…d148ded`.
4. `python tools/qa_smoke.py --quick` → DONE: PASS.
5. `python -m pytest tests/test_wk117_ursina_app_ui_overlay.py tests/test_wk116_ursina_app_input.py tests/test_wk113_ursina_app_camera.py tests/test_wk105_ursina_app_debug_probe.py -q` → all green.
Update the Agent 11 log; report a PASS/FAIL table.

---

## 6. PM verbatim-diff gate (Agent 01 — before commit)

AST-extract each of the 5 moved bodies from HEAD `ursina_app.py` and from
`ursina_app_ui_overlay.py`, canonicalize whole-word `self`/`owner`→`@`, line-diff. The
ONLY allowed diffs: the §2 intra-cluster call rewrites (`@.<fn>(...)`/`UrsinaApp.<fn>(...)`
→ `<fn>(...)` with the static-passthrough args; `@._sync_hud_texture_filter_mode(@._hud_composite_texture)`
→ `_sync_hud_texture_filter_mode(@._hud_composite_texture)`). Any other diff = STOP,
bounce to Agent 09. Read files `encoding="utf-8-sig"`; strip a leading BOM before parse.
(Static fns have no `self`/`owner` so they should be near-IDENTICAL except the call rewrite.)

## 7. Definition of done (PM gate)

- [ ] `ursina_app_ui_overlay.py`: 3 static + 2 owner-arg fns; ZERO `self` code-identifiers (AST).
- [ ] `ursina_app.py`: 5 delegating wrappers (3 `@staticmethod`, 2 instance; exact names/sigs); bodies removed; ~670 LOC.
- [ ] PM verbatim-diff gate: all 5 faithful (only the §2 allowed rewrites).
- [ ] `tests/test_wk117_ursina_app_ui_overlay.py` green.
- [ ] full `pytest -q` 0 failed; determinism clean; WK67 digest byte-identical; qa_smoke PASS.
- [ ] both fresh-import orders OK.
- [ ] DEFERRED: live HUD→GPU upload / dirty-row blit / window-resize-canvas captures → Sovereign end test.
- [ ] Agent 09 + 11 logs updated. PM commits (scoped add: `ursina_app.py`,
      `ursina_app_ui_overlay.py`, `tests/test_wk117_ursina_app_ui_overlay.py`, plan + PM hub + agent logs) + pushes.

## 8. Grounding for NEXT sprint (WK118)

`ursina_app.py` (~670 LOC) is now mostly `__init__` (267 LOC of scene/entity/camera
construction) + `run()` (the frame-loop `update()` + `app.run()`). Candidate WK118: the
`run()` frame-loop body is a large closure — consider extracting its per-frame stages
(input/sim-tick/fps-ema/auto-exit/render-upload orchestration) into
`game/graphics/ursina_app_frame.py` as `run_frame(owner, dt)` (owner-arg), leaving `run()`
as the Ursina bootstrap + `update` shim. This is more involved (closure → owner-arg fn);
ground it carefully. Alternatively split `__init__`'s scene-construction into a helper
module. Deferred/riskiest (sim-reorder, digest-fragile): TaskRouter (Move 12),
SystemRunner (Move 9) — land last.
