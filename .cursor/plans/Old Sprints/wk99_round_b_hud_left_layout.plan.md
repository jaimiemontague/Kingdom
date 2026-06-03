# WK99 Sprint Plan — Round B-16: extract hud_left_layout.py (left-column segment + split + drag cluster) + relocate LEFT_SPLIT_* to hud_layout.py — seventh hud.py slice

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; the left-column segment-allocation + split-handle render + sidebar-drag cluster extracted from hud.py into a NEW `game/ui/hud_left_layout.py`; the 5 `LEFT_SPLIT_*` constants relocated to `hud_layout.py`; left-column layout + drag-resize behave + render identically.
**Predecessors:** WK93 (hud_radar), WK94 (hud_toasts), WK95 (hud_summaries), WK96 (hud_watch_card render+consts), WK97 (hud_panel_buttons), WK98 (watch-card geometry → hud_watch_card + HERO_LEFT_MIN_H → hud_layout). **Roadmap:** Round B — hud.py (1523 LOC) split. Seventh slice; second of three for the left-column/layout cluster (WK98 done; WK100 = layout orchestration).

## 0. TL;DR
WK99 extracts the **left-column split cluster** — 7 methods (~165 LOC) that (a) decide which left segments are open, (b) normalize the user's saved split fractions, (c) allocate the main-panel + watch-card rects above the minimap and stash the resize-handle rects, (d) draw the resize handles, and (e) handle the pointer down/move/up drag that resizes the split — into a NEW `game/ui/hud_left_layout.py` as functions taking the HUD (`hud`), behind 1-line delegating wrappers on HUD. ALL drag/layout STATE stays on HUD (set in __init__). The 5 `LEFT_SPLIT_*` constants relocate to `hud_layout.py` (the authoritative layout-constants module; same WK98 pattern as HERO_LEFT_MIN_H) and hud.py re-imports + re-exports them. This is MED risk (state mutation + a render fn + pointer hit-region + external callers in ursina_app/mouse/input_handler), but it is well-guarded: `tests/test_wk61_r10_sidebar_layout.py` and `tests/test_wk61_r11_sidebar_main_solo_handle.py` directly drive the layout + all three drag handlers, and the left column is ALWAYS visible (with a selection/pin) so the `ui_panels` screenshots are a strong pixel guard. The WK67 digest (headless, AI-only) is unaffected. PM writes no code.

## 1. Scope

### 1a. Relocate 5 constants (hud.py → hud_layout.py)
Move OUT of hud.py (currently lines 53–57) and INTO `game/ui/hud_layout.py` (next to `HERO_LEFT_MIN_H`, with a one-line comment):
```python
LEFT_SPLIT_HANDLE_H = 4
LEFT_SPLIT_HANDLE_HIT_H = 8
LEFT_SPLIT_DEFAULT_FRAC_MAIN = 0.55
LEFT_SPLIT_DEFAULT_FRAC_WATCH = 0.45
LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO = 0.72
```
Then in hud.py ADD all 5 names to the existing `from game.ui.hud_layout import (...)` block so the bare names still resolve in hud.py's __init__ (lines 322–324 set `self._left_split_fracs` defaults from `LEFT_SPLIT_DEFAULT_FRAC_MAIN/WATCH/MAIN_SOLO`) AND so `from game.ui.hud import LEFT_SPLIT_*` keeps working for `tests/test_wk61_r10_sidebar_layout.py` (imports `LEFT_SPLIT_HANDLE_H`) and `tests/test_wk61_r11_sidebar_main_solo_handle.py` (imports `LEFT_SPLIT_HANDLE_HIT_H`, `LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO`).
**Do NOT touch** `HERO_MENU_*` (lines 48–51) or `WATCH_MINIMAP_SIZE` (52) — they stay in hud.py (hero-menu code + test_wk61_r9).

### 1b. Move 7 methods (hud.py → hud_left_layout.py), VERBATIM (replace `self.`→`hud.`), keep a 1-line delegating wrapper on HUD for each (EXACT name+signature):

| HUD method | hud.py line | → module function | Caller(s) the wrapper preserves |
|---|---|---|---|
| `_left_column_segments_open(self, game_state)` | 451 | `left_column_segments_open(hud, game_state)` | internal: `_layout_left_column_segments` (hud.py:494) |
| `_normalized_left_split_fracs(self, main_open, watch_open)` | 463 | `normalized_left_split_fracs(hud, main_open, watch_open)` | internal: `_layout_left_column_segments` (hud.py:504) |
| `_layout_left_column_segments(self, top_h, minimap, game_state)` | 486 | `layout_left_column_segments(hud, top_h, minimap, game_state)` | `_layout_rects_for_screen` (hud.py:670, STAYS — WK100) |
| `_render_left_split_handles(self, surface)` | 562 | `render_left_split_handles(hud, surface)` | `render()` (hud.py:1152, STAYS) |
| `handle_sidebar_split_pointer_down(self, pos, game_state)` | 579 | `handle_sidebar_split_pointer_down(hud, pos, game_state)` | **PUBLIC, external:** `handle_click` (hud.py:1399), `game/input/mouse.py:88/89`, `game/graphics/ursina_app.py:796/798/1299/1301` (via hasattr/getattr), `test_wk61_r10:59`, `test_wk61_r11:52` — wrapper name MUST stay EXACT |
| `handle_sidebar_split_pointer_move(self, pos, game_state)` | 593 | `handle_sidebar_split_pointer_move(hud, pos, game_state)` | **PUBLIC, external:** `game/input/mouse.py:402` (getattr), `test_wk61_r10:60`, `test_wk61_r11:53` — EXACT |
| `handle_sidebar_split_pointer_up(self)` | 627 | `handle_sidebar_split_pointer_up(hud)` | **PUBLIC, external:** `game/input_handler.py:88/89` (hasattr), `test_wk61_r10:61`, `test_wk61_r11:54` — EXACT |

**Mechanical move rule — EVERY `self.<x>` becomes `hud.<x>`. Nothing else changes.** STATE reached via `hud.` (ALL stays on HUD, set in __init__): `hud._pin_slot`, `hud._left_split_fracs`, `hud._left_main_rect`, `hud._left_watch_rect`, `hud._left_split_handle_rects`, `hud._last_left_rect`, `hud._left_split_drag_kind`, `hud._left_split_drag_start_y`, `hud._left_split_drag_main_h0`, `hud._left_split_drag_watch_h0`, `hud.screen_height`, `hud.theme`. Inter-helper calls become `hud._left_column_segments_open(...)`, `hud._normalized_left_split_fracs(...)` (→ wrapper → this module; correct + mechanical) and `hud._should_render_hero_menu_chat_popup(...)` (STAYS on HUD — leave as `hud._should_render_hero_menu_chat_popup`). Constants are referenced BARE (no `hud.`): `LEFT_COL_W`, `HERO_LEFT_MIN_H`, `WATCH_CARD_HEADER_H`, `LEFT_SPLIT_HANDLE_H`, `LEFT_SPLIT_HANDLE_HIT_H`, `LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO`, `RADAR_MINIMAP_H` — all imported at module top (see §2). Copy docstrings verbatim.

**STAYS on HUD** (DO NOT move): all the `_left_*` STATE in __init__; `_should_render_hero_menu_chat_popup` (982) + the `HERO_MENU_*` hero-menu code; `_layout_rects_for_screen` (634) + `_compute_layout` + `virtual_pointer_in_hud_chrome` (WK100); `render()`; `handle_click`. They reach the moved code via `hud.` wrappers. **OUT.**

## 2. Pattern (WK96/98, verbatim) — new module header
`game/ui/hud_left_layout.py`:
```python
"""Left-column segment/split layout + sidebar-resize drag, extracted from game.ui.hud (WK99).

Allocates the main-panel + pinned-watch-card rectangles above the fixed minimap from
the user's saved split fractions, draws the resize handles, and handles the pointer
down/move/up that resizes the split. All layout/drag STATE lives on the HUD instance
and is reached here via the ``hud`` argument; HUD keeps 1-line delegating wrappers
(exact names, incl. the public handle_sidebar_split_pointer_* the input layer calls
via hasattr/getattr). Acyclic: hud.py imports this module lazily inside the wrappers;
this module imports only leaf modules (hud_layout, hud_watch_card) + reaches HUD via
the ``hud`` param + TYPE_CHECKING (NO top-level ``import game.ui.hud``).
"""
from __future__ import annotations
from typing import TYPE_CHECKING
import pygame
from game.ui.hud_layout import (
    HERO_LEFT_MIN_H,
    LEFT_COL_W,
    LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO,
    LEFT_SPLIT_HANDLE_H,
    LEFT_SPLIT_HANDLE_HIT_H,
    RADAR_MINIMAP_H,
)
from game.ui.hud_watch_card import WATCH_CARD_HEADER_H
if TYPE_CHECKING:
    from game.ui.hud import HUD
```
**Cycle proof:** `hud_layout` imports only pygame/dataclasses (leaf). `hud_watch_card` imports pygame/widgets/hud_layout (no hud, no hud_left_layout). `hud_left_layout` imports those two leaves only (no hud at top). hud.py imports hud_watch_card + hud_layout at top and hud_left_layout LAZILY in the wrappers. → no cycle. Verify BOTH fresh import orders.

### Wrapper form on HUD (replace each moved method body; keep EXACT def line):
```python
def handle_sidebar_split_pointer_down(self, pos: tuple[int, int], game_state: dict) -> bool:
    from game.ui import hud_left_layout
    return hud_left_layout.handle_sidebar_split_pointer_down(self, pos, game_state)
```
…and the analogous 1-line lazy-delegate for the other 6 (incl. the `_`-prefixed `_left_column_segments_open`, `_normalized_left_split_fracs`, `_layout_left_column_segments`, `_render_left_split_handles`, and the public `handle_sidebar_split_pointer_move`/`handle_sidebar_split_pointer_up`). Move VERBATIM.

## 3. Definition of Done
- **A.** `python -m pytest -q` all pass (baseline **1071 passed / 4 skipped / 0 failed** at WK98 close; +new test → expect ~1080+).
- **B.** `python tools/determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`.
- **D.** `python tools/qa_smoke.py --quick` green.
- **E.** the 7 fns live in `game/ui/hud_left_layout.py`; the 5 `LEFT_SPLIT_*` live in `hud_layout.py` + removed from hud.py's own defs + re-imported by hud (so `from game.ui.hud import LEFT_SPLIT_*` works + __init__ 322–324 resolves); HUD keeps the 7 wrapper names+signatures (esp. the 3 public `handle_sidebar_split_pointer_*`); call sites (hud.py 494/504/670/1152/1399; mouse.py 88/89/402; input_handler.py 88/89; ursina_app.py 796/798/1299/1301; test_wk61_r10/r11) UNCHANGED; ALL `_left_*` state stays on HUD; hud.py smaller (~1523 → ~1370); **no import cycle** (both fresh orders); ZERO `self.` in the 7 moved fns.
- **F.** BEFORE/AFTER pygame screenshots — `base_overview` + `ui_panels` — visually identical. The affected region is the LEFT COLUMN: with a hero selected + pinned, `ui_panels_sidebar_split.png` shows the main panel + watch card split by a resize handle (the moved code computes those rects + draws the handle). Report the left-column split specifically: main-panel rect, watch-card rect, the divider/handle bar position, and that the column is flush-left + non-overlapping — MUST be pixel-identical.
- **G.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 08 UX/UI):** (1) relocate the 5 `LEFT_SPLIT_*` to hud_layout.py + remove from hud.py + add to hud.py's hud_layout import. (2) create `hud_left_layout.py` (header above + 7 fns, verbatim `self.`→`hud.`). (3) replace the 7 hud.py method bodies with wrappers. Run full suite + digest + determinism + qa_smoke. Before/after pygame screenshots (base_overview + ui_panels; focus ui_panels_sidebar_split). Verify ZERO `self.` in the 7 new fns + no top-level hud import in hud_left_layout + both import orders + LEFT_SPLIT_* re-export. Update own log. **DO NOT COMMIT.**
- **W2 (Agent 11 QA):** seam test `tests/test_wk99_hud_left_layout.py` — assert: (1) the 7 fns exist in hud_left_layout with the `hud`-first signature (inspect.signature); (2) the 5 `LEFT_SPLIT_*` are importable from `game.ui.hud_layout` AND re-exported by `game.ui.hud` (both equal the literals 4/8/0.55/0.45/0.72); assert hud_layout source defines them + hud.py source no longer has its own column-0 `LEFT_SPLIT_*=` defs; (3) the 7 HUD wrappers exist and delegate (monkeypatch each module fn to a sentinel, call wrapper, assert fired — incl. all 3 public `handle_sidebar_split_pointer_*` since the input layer calls them); (4) AST guard: hud_left_layout.py has no module-top `game.ui.hud` import (TYPE_CHECKING `from game.ui.hud import HUD` permitted) + fresh-subprocess both import orders returncode 0; (5) behavior (headless SDL dummy + pygame.init): build `HUD(1920,1080)`, select a hero + pin one (mirror test_wk61_r10/r11 setup), call `hud._layout_left_column_segments(top_h, minimap_rect, gs)` → assert it returns (left, main, watch) Rects + sets `hud._left_main_rect`/`hud._left_watch_rect`/`hud._left_split_handle_rects`; then drive a drag: `hud.handle_sidebar_split_pointer_down(handle.center, gs)` is True, `hud.handle_sidebar_split_pointer_move((x,y+40), gs)` is True (and `hud._left_split_fracs` changed), `hud.handle_sidebar_split_pointer_up()` is True; and `hud._render_left_split_handles(surface)` raises nothing. Run full DoD A–G, independently view before/after screenshots. Update own log. **DO NOT COMMIT.**

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| A public `handle_sidebar_split_pointer_*` wrapper name changed → input layer's hasattr/getattr silently no-ops sidebar drag (ursina_app/mouse/input_handler) | Med | keep EXACT names; W2 delegation test patches all 3 + asserts fired; test_wk61_r10/r11 drive the full down/move/up through HUD |
| Import cycle via hud_watch_card or hud_layout | Low | both are leaves (verified, no hud import); hud_left_layout imports only them at top; lazy wrapper; verify both orders |
| A `self.X` missed in the 7-method sweep (esp. the 9 drag-state fields + the inter-helper calls + `_should_render_hero_menu_chat_popup`) | Med | grep the 7 new fns for `self.` (MUST be ZERO); W2 behavior test drives layout + full drag + handle render |
| `LEFT_SPLIT_*` relocation breaks __init__ (322–324) or a test import | Low | hud.py re-imports all 5 into its namespace; W2 asserts both import paths == literals; test_wk61_r10/r11 are the live guard |
| Layout math drifts (rounding / handle rect) | Low | PURE verbatim move (no expression edits); test_wk61_r10 asserts `main_bottom` handle height == LEFT_SPLIT_HANDLE_H + main_h >= HERO_LEFT_MIN_H; r11 asserts solo handle + frac update |

## 6. Success
The left-column split cluster lives in `game/ui/hud_left_layout.py` behind 7 delegating wrappers, the 5 `LEFT_SPLIT_*` live in `hud_layout.py` (re-exported by hud) — proven by 1071+ green tests (incl. test_wk61_r10/r11 driving the drag through the wrappers + a new behavior test), clean determinism guard, unchanged digest, identical before/after `ui_panels_sidebar_split` screenshots, and a verified no-cycle. hud.py drops ~155 LOC (seventh slice; 2477→~1370 cumulative).

## 7. Kickoff
Roster: 08 UX/UI (W1), 11 QA (W2), 09 (consult). Order: 08 W1 → PM gate → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE VERBATIM MOVE (self.→hud.); relocate the 5 `LEFT_SPLIT_*` to hud_layout.py (re-exported by hud) — leave HERO_MENU_*/WATCH_MINIMAP_SIZE in hud.py; keep the 7 wrapper names (esp. the 3 public `handle_sidebar_split_pointer_*`) + ALL `_left_*` state on HUD; `_should_render_hero_menu_chat_popup` stays on HUD (call via hud.); TYPE_CHECKING-only HUD import; ZERO `self.` in the 7 moved fns; before/after pygame left-column split MUST match; own log; DO NOT COMMIT.
Follow-ups (REMAINING roadmap, in order): **WK100** = layout orchestration (`_layout_rects_for_screen`, `_compute_layout`, `virtual_pointer_in_hud_chrome`) → hud_left_layout.py (needs ViewMode from micro_view_manager [verified no hud import] + HUDLayoutManager + sim_now_ms; MANY external callers ursina_app/mouse/input_handler/building_panel/tests → keep wrappers). Then: `ursina_terrain_fog_collab`(1783)/`ursina_app`(1525) splits; messages (`add_message`/`render_messages`); input-router (`handle_click` + menu-scroll); Move 9 (SystemRunner — RISKY); world.py fog; context_builder/direct_prompt_validator; ai/vocab.py + TaskRouter; config package; clusters 3/4; Round E audit; the 21-file WK34-zombie-type purge.
