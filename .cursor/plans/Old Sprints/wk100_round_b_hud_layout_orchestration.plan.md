# WK100 Sprint Plan — Round B-17: move layout orchestration trio into hud_left_layout.py — eighth hud.py slice (completes the left-column/layout cluster)

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; the 3 layout-orchestration methods (`_layout_rects_for_screen`, `_compute_layout`, `virtual_pointer_in_hud_chrome`) moved from hud.py into the existing `game/ui/hud_left_layout.py`; layout computation + pointer hit-testing behave identically.
**Predecessors:** WK93–97 (hud.py slices), WK98 (watch-card geometry → hud_watch_card), WK99 (left-column split → hud_left_layout). **Roadmap:** Round B — hud.py (1373 LOC) split. Eighth slice; THIRD and FINAL of the left-column/layout cluster.

## 0. TL;DR
WK100 moves the 3 **layout-orchestration** methods that sit on top of the WK99 segment cluster — `_layout_rects_for_screen` (delegates core rects to `HUDLayoutManager` then overlays the left-column segments), `_compute_layout` (sets screen_w/h + returns the rect tuple for render()), and `virtual_pointer_in_hud_chrome` (the pointer hit-test that decides if a screen coord lies over HUD chrome vs the world) — into the existing `game/ui/hud_left_layout.py` (WK99's module), behind 1-line delegating wrappers on HUD. They naturally belong next to `layout_left_column_segments` (which `_layout_rects_for_screen` calls) and the watch-card-geometry helpers (which `virtual_pointer` calls). This completes the left-column/layout extraction: after WK100 the new module owns the full left-column layout + pointer-chrome subsystem and hud.py keeps only thin wrappers. The 2 NEW module-level deps are `ViewMode` (from `game.ui.micro_view_manager` — verified NO hud import) and `sim_now_ms` (from `game.sim.timebase` — leaf). ~150 LOC leaves hud.py (1373 → ~1230). The WK67 digest (headless, AI-only) is unaffected. PM writes no code.

## 1. Scope
**IN:** move VERBATIM (replace `self.`→`hud.`) these 3 methods into `game/ui/hud_left_layout.py` as functions taking `hud` first, keeping a 1-line delegating wrapper on HUD for each (EXACT name+signature):

| HUD method | hud.py line | → module function | Caller(s) the wrapper preserves |
|---|---|---|---|
| `_layout_rects_for_screen(self, w, h, *, show_right_panel, game_state=None)` | 484 | `layout_rects_for_screen(hud, w, h, *, show_right_panel, game_state=None)` | `_compute_layout` (hud.py:554), `virtual_pointer_in_hud_chrome` (hud.py:574), `test_wk52_watch_card.py:172`, `test_wk61_r10:21`, `test_wk61_r11:18` |
| `_compute_layout(self, surface, game_state=None)` | 536 | `compute_layout(hud, surface, game_state=None)` | `render()` (hud.py:942), `test_wk52_r10_menu_scroll.py:90` |
| `virtual_pointer_in_hud_chrome(self, pos, surface, game_state)` | 560 | `virtual_pointer_in_hud_chrome(hud, pos, surface, game_state)` | **PUBLIC, external:** `game/graphics/ursina_app.py:727` (pointer routing), `test_wk52_r10_menu_scroll.py:92/96` — wrapper name MUST stay EXACT |

**Mechanical move rule — EVERY `self.<x>` becomes `hud.<x>`. Nothing else changes.** STATE/instances reached via `hud.` (ALL stay on HUD): `hud.theme`, `hud._layout_mgr` (HUDLayoutManager instance — accessed via attribute, NOT imported), `hud._watch_card_chat_rect`, `hud.screen_width`, `hud.screen_height`, `hud._show_right_panel`, `hud.right_panel_visible`, `hud.side_panel_width`, `hud._micro_view`, `hud._pin_slot`, `hud.memorial_card`, `hud.building_interior_overlay`, `hud.demolish_confirm_overlay`, `hud._left_watch_rect`, `hud._chat_visible`, `hud._left_split_handle_rects`, `hud.show_help`. Method calls become `hud.` wrappers: `hud._layout_left_column_segments(...)` (WK99 wrapper), `hud._layout_rects_for_screen(...)` (this sprint's own wrapper — `_compute_layout`/`virtual_pointer` call it via `hud.`, correct + mechanical), `hud._effective_watch_card_h(...)`, `hud._watch_card_body_split(...)`, `hud._watch_chat_band_rect(...)` (WK98 wrappers → hud_watch_card). The `getattr(self, "memorial_card", None)` etc. become `getattr(hud, "memorial_card", None)`. Copy docstrings verbatim.

**STAYS on HUD** (DO NOT move): everything else — `render()`, `handle_click`, all state, the hero-menu code, etc. They reach the moved code via `hud.` wrappers. **OUT.**

## 2. Pattern (WK99, verbatim) — what to ADD to hud_left_layout.py
At the top of `hud_left_layout.py`, ADD two imports (after `import pygame`):
```python
from game.sim.timebase import now_ms as sim_now_ms
from game.ui.micro_view_manager import ViewMode
```
**Cycle proof:** `game.sim.timebase` is a leaf. `game.ui.micro_view_manager` imports only enum/typing/pygame/config/timebase (verified — NO `game.ui.hud` and NO `game.ui.hud_left_layout` import). So `hud_left_layout` → {hud_layout, hud_watch_card, timebase, micro_view_manager} are all acyclic w.r.t. hud / hud_left_layout. hud.py imports hud_left_layout LAZILY in the wrappers. → no cycle. Verify BOTH fresh import orders. Then append the 3 functions at the END of the module.

### Wrapper form on HUD (replace each moved method body; keep EXACT def line incl. the full 9-tuple return annotations + the keyword-only `*, show_right_panel`):
```python
def _layout_rects_for_screen(self, w: int, h: int, *, show_right_panel: bool, game_state: dict | None = None) -> tuple[pygame.Rect, pygame.Rect, pygame.Rect, pygame.Rect, pygame.Rect, pygame.Rect, pygame.Rect, pygame.Rect, pygame.Rect]:
    from game.ui import hud_left_layout
    return hud_left_layout.layout_rects_for_screen(self, w, h, show_right_panel=show_right_panel, game_state=game_state)

def _compute_layout(self, surface: pygame.Surface, game_state: dict | None = None) -> tuple[pygame.Rect, pygame.Rect, pygame.Rect, pygame.Rect, pygame.Rect, pygame.Rect, pygame.Rect, pygame.Rect, pygame.Rect]:
    from game.ui import hud_left_layout
    return hud_left_layout.compute_layout(self, surface, game_state)

def virtual_pointer_in_hud_chrome(self, pos: tuple[int, int], surface: pygame.Surface, game_state: dict) -> bool:
    from game.ui import hud_left_layout
    return hud_left_layout.virtual_pointer_in_hud_chrome(self, pos, surface, game_state)
```
(Copy the EXACT multi-line return-tuple annotations from hud.py:486-496 / 538-548 onto the two layout wrappers — you may keep them multi-line or collapse to one line; the runtime behavior is identical, but keep `*, show_right_panel` keyword-only on `_layout_rects_for_screen`.) Move VERBATIM.

## 3. Definition of Done
- **A.** `python -m pytest -q` all pass (baseline **1115 passed / 4 skipped / 0 failed** at WK99 close; +new test → expect ~1125+).
- **B.** `python tools/determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`.
- **D.** `python tools/qa_smoke.py --quick` green.
- **E.** the 3 fns live in `game/ui/hud_left_layout.py`; HUD keeps the 3 wrapper names+signatures (esp. PUBLIC `virtual_pointer_in_hud_chrome` for ursina_app pointer routing; keyword-only `show_right_panel` on `_layout_rects_for_screen`); call sites (hud.py 554/574/942; ursina_app.py:727; test_wk52:172, test_wk52_r10:90/92/96, test_wk61_r10:21, test_wk61_r11:18) UNCHANGED; all state + `_layout_mgr` stay on HUD; hud.py smaller (~1373 → ~1230); **no import cycle** (both fresh orders); ZERO `self.` in the 3 moved fns.
- **F.** BEFORE/AFTER pygame screenshots — `base_overview` + `ui_panels` (esp. `ui_panels_hero` + `ui_panels_sidebar_split`) — visually identical. `_compute_layout` drives ALL HUD rect placement every frame, so ANY layout regression shows everywhere: report top-bar, bottom-bar button row (recall/memorial/command/speed), minimap, and the left column are all in identical positions. (Pointer hit-testing isn't visible — its guard is test_wk52_r10 + the W2 behavior test.)
- **G.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 08 UX/UI):** add the 2 imports (sim_now_ms, ViewMode) to hud_left_layout.py + append the 3 fns (verbatim `self.`→`hud.`); replace the 3 hud.py method bodies with wrappers. Run full suite + digest + determinism + qa_smoke. Before/after pygame screenshots (base_overview + ui_panels). Verify ZERO `self.` in the 3 new fns + no top-level hud import in hud_left_layout + both import orders. Update own log. **DO NOT COMMIT.**
- **W2 (Agent 11 QA):** seam test `tests/test_wk100_hud_layout_orchestration.py` — assert: (1) the 3 fns exist in hud_left_layout with the `hud`-first signature (inspect.signature); for `layout_rects_for_screen` assert `show_right_panel` is KEYWORD-ONLY (inspect: in `kwonlyargs`/`KEYWORD_ONLY`). (2) the 3 HUD wrappers exist and delegate (monkeypatch each module fn to a sentinel, call the wrapper, assert fired — incl. the PUBLIC `virtual_pointer_in_hud_chrome`). (3) AST guard: hud_left_layout.py has no module-top `game.ui.hud` import (TYPE_CHECKING `from game.ui.hud import HUD` permitted) + fresh-subprocess both import orders returncode 0. (4) behavior (headless SDL dummy + pygame.init): build `HUD(1920,1080)`, surface = pygame.Surface((1920,1080)); call `top,bottom,left,right,minimap,command,speed,recall,memorial = hud._compute_layout(surface, gs)` with a hero-selected+pinned gs → assert all 9 are pygame.Rect, `hud.screen_width==1920`/`hud.screen_height==1080`, top.y==0, bottom.bottom==1080; call `hud._layout_rects_for_screen(1920,1080, show_right_panel=False, game_state=gs)` → same 9-tuple; call `hud.virtual_pointer_in_hud_chrome((left.x+4, left.y+4), surface, gs)` → True (a point inside the left panel when a hero is selected) and `hud.virtual_pointer_in_hud_chrome((1900, 540), surface, {})` → False (a world point, empty gs) — mirror `tests/test_wk52_r10_menu_scroll.py`. Run full DoD A–G, independently view before/after screenshots. Update own log. **DO NOT COMMIT.**

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| PUBLIC `virtual_pointer_in_hud_chrome` wrapper name changed → ursina_app pointer routing breaks (clicks fall through to world / blocked) | Med | keep EXACT name; W2 delegation + behavior test; test_wk52_r10 asserts True/False hits |
| `show_right_panel` loses keyword-only status → callers that pass it positionally break (none do, but signature drift) | Low | wrapper keeps `*, show_right_panel`; W2 asserts kwonly via inspect |
| Import cycle via micro_view_manager | Low | micro_view_manager verified NO hud import (imports enum/typing/pygame/config/timebase); verify both orders |
| A `self.X` missed (esp. the many overlay getattrs + `_layout_mgr` + the wrapper calls) | Med | grep the 3 new fns for `self.` (MUST be ZERO); W2 behavior test drives compute_layout + both pointer cases + test_wk52_r10/test_wk61 are live guards |
| Layout math drift breaks EVERY frame's rect placement | Low | PURE verbatim move; _compute_layout feeds render() so a regression is obvious in BOTH screenshots; bottom-bar/minimap/left positions reported |

## 6. Success
The layout-orchestration trio lives in `game/ui/hud_left_layout.py` behind 3 delegating wrappers — completing the left-column/layout cluster extraction (segments + split + drag + watch-card geometry [hud_watch_card] + orchestration). Proven by 1115+ green tests (incl. test_wk52_r10 pointer hits + test_wk61_r10/r11 layout + a new behavior test), clean determinism guard, unchanged digest, identical before/after `ui_panels` screenshots (compute_layout drives every rect), and a verified no-cycle. hud.py drops ~145 LOC (eighth slice; 2477→~1230 cumulative).

## 7. Kickoff
Roster: 08 UX/UI (W1), 11 QA (W2), 09 (consult). Order: 08 W1 → PM gate → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE VERBATIM MOVE (self.→hud.); add ONLY the 2 imports (sim_now_ms, ViewMode); keep the 3 wrapper names (esp. PUBLIC `virtual_pointer_in_hud_chrome`) + `*, show_right_panel` keyword-only + ALL state/`_layout_mgr` on HUD; TYPE_CHECKING-only HUD import; ZERO `self.` in the 3 moved fns; before/after pygame layout MUST match; own log; DO NOT COMMIT.
Follow-ups (REMAINING roadmap, in order): hud.py now ~1230 — the left-column/layout cluster is DONE. Next hud.py targets: messages (`add_message`/`render_messages`); the input-router (`handle_click` + menu-scroll `is_mouse_over_menu`/`scroll_active_menu`/`handle_menu_scroll`); the hero-menu-chat-popup layout (`_should_render_hero_menu_chat_popup` + `_compute_hero_menu_layout` + HERO_MENU_* + WATCH_MINIMAP_SIZE). Then OTHER god-files: `ursina_terrain_fog_collab`(1783)/`ursina_app`(1525) splits; Move 9 (SystemRunner — RISKY); world.py fog; context_builder/direct_prompt_validator; ai/vocab.py + TaskRouter; config package; clusters 3/4; Round E audit; the 21-file WK34-zombie-type purge.
