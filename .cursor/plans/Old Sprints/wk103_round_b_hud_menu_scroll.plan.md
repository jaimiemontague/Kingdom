# WK103 Sprint Plan — Round B-20: extract hud_menu_scroll.py (mouse-wheel menu-scroll routing) — eleventh hud.py slice

**Author:** Agent 01 (PM) · **Date:** 2026-05-31 · **Goal:** all tests pass; the mouse-wheel menu-scroll routing (`is_mouse_over_menu`/`scroll_active_menu`/`handle_menu_scroll`) extracted from hud.py into a NEW `game/ui/hud_menu_scroll.py`; wheel routing behaves identically.
**Predecessors:** WK93–102 hud.py slices. **Roadmap:** Round B — hud.py (1219 LOC) split. Eleventh slice. Chosen by the WK101 grounding workflow (ranked #3).

## 0. TL;DR
WK103 extracts the **mouse-wheel menu-scroll router** — `is_mouse_over_menu` (predicate: is `pos` over a wheel-capturing menu — a visible building panel with a selected building, OR the left-column hero menu when a hero is selected and no peasant/building), `scroll_active_menu` (thin `direction`→`wheel_y=-direction` adapter that delegates to `handle_menu_scroll`), `handle_menu_scroll` (the entry point: route the wheel to `building_panel.apply_menu_scroll` or `hud._hero_panel.apply_menu_scroll`, consuming the wheel even when the panel reports no content scroll) — one cohesive input concern (~87 LOC, 3 methods) — into a NEW `game/ui/hud_menu_scroll.py` as functions taking the HUD (`hud`), behind 1-line delegating wrappers on HUD. The trio inter-calls (`scroll_active_menu`→`handle_menu_scroll`→`is_mouse_over_menu`) so all three move as a unit. ALL state stays on HUD. The only import the module needs is `pygame`. Low risk; fully covered by `tests/test_wk52_r10_menu_scroll.py` (8 assertions driving all three + the input-handler wiring). The WK67 digest (headless, AI-only) is unaffected. PM writes no code.

## 1. Scope
**IN:** create `game/ui/hud_menu_scroll.py`; move VERBATIM (replace `self.`→`hud.`) these 3 methods, keeping a 1-line delegating wrapper on HUD for each (EXACT name+signature — all 3 are PUBLIC and reached externally):

| HUD method | hud.py line | → module function | Caller(s) the wrapper preserves |
|---|---|---|---|
| `is_mouse_over_menu(self, pos, game_state, building_panel)` | 970 | `is_mouse_over_menu(hud, pos, game_state, building_panel)` | internal: `handle_menu_scroll` (hud.py:1025); `tests/test_wk52_r10_menu_scroll.py:111/112` |
| `scroll_active_menu(self, direction, pointer_pos, game_state, building_panel)` | 1000 | `scroll_active_menu(hud, direction, pointer_pos, game_state, building_panel)` | `tests/test_wk52_r10_menu_scroll.py:128/131` |
| `handle_menu_scroll(self, pos, wheel_y, game_state, building_panel)` | 1016 | `handle_menu_scroll(hud, pos, wheel_y, game_state, building_panel)` | **PUBLIC, external:** `game/input_handler.py:127`, `game/graphics/ursina_app.py:830`, `tests/test_wk52_r10_menu_scroll.py` (incl. `:151` `cmds.hud.handle_menu_scroll = MagicMock(...)`) — wrapper name MUST stay EXACT |

**Mechanical move rule — EVERY `self.<x>` becomes `hud.<x>`. Nothing else changes.** State reached via `hud.` (ALL stays on HUD): `hud._last_left_rect`, `hud._hero_menu_chat_rect`, `hud._hero_menu_hero_rect`, `hud._hero_panel`. Inter-helper calls become `hud.handle_menu_scroll(...)` (scroll_active_menu→) and `hud.is_mouse_over_menu(...)` (handle_menu_scroll→) — both via wrappers, correct + mechanical. The `getattr(self, "_hero_menu_chat_rect", None)`/`getattr(self, "_hero_menu_hero_rect", None)` become `getattr(hud, ...)`. `building_panel`/`game_state` are PARAMETERS (no `hud.` / `self.`). `pygame.Rect` stays bare. Copy docstrings verbatim.

**STAYS on HUD** (DO NOT move): all the read state (`_last_left_rect`/`_hero_menu_chat_rect`/`_hero_menu_hero_rect`/`_hero_panel`), `handle_click` (hud.py:1058 — the big central router, a DEFERRED redesign target, NOT this sprint), `render()`. **OUT.**

## 2. Pattern (WK94/100, verbatim) — new module header
`game/ui/hud_menu_scroll.py`:
```python
"""Mouse-wheel menu-scroll routing, extracted from game.ui.hud (WK103).

Decide whether a pointer position is over a wheel-capturing menu (a visible
building panel with a selected building, or the left-column hero menu) and route
the wheel to the appropriate panel's apply_menu_scroll. All HUD state
(_last_left_rect, _hero_menu_chat_rect, _hero_menu_hero_rect, _hero_panel) lives on
the HUD instance and is reached here via the ``hud`` argument; HUD keeps 1-line
delegating wrappers (exact names: is_mouse_over_menu, scroll_active_menu,
handle_menu_scroll -- input_handler.py + ursina_app.py call handle_menu_scroll).
Acyclic: hud.py imports this module lazily inside the wrappers; this module imports
only pygame + HUD under TYPE_CHECKING.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
import pygame
if TYPE_CHECKING:
    from game.ui.hud import HUD
```
**Cycle proof:** the module imports only pygame + TYPE_CHECKING HUD; hud.py imports hud_menu_scroll LAZILY in the wrappers. → no cycle. Verify BOTH fresh import orders.

### Wrapper form on HUD (replace each moved method body; keep EXACT def lines incl. the multi-line params):
```python
def is_mouse_over_menu(self, pos: tuple[int, int], game_state: dict, building_panel) -> bool:
    from game.ui import hud_menu_scroll
    return hud_menu_scroll.is_mouse_over_menu(self, pos, game_state, building_panel)

def scroll_active_menu(self, direction: int, pointer_pos: tuple[int, int], game_state: dict, building_panel) -> bool:
    from game.ui import hud_menu_scroll
    return hud_menu_scroll.scroll_active_menu(self, direction, pointer_pos, game_state, building_panel)

def handle_menu_scroll(self, pos: tuple[int, int], wheel_y: int, game_state: dict, building_panel) -> bool:
    from game.ui import hud_menu_scroll
    return hud_menu_scroll.handle_menu_scroll(self, pos, wheel_y, game_state, building_panel)
```
Move VERBATIM.

## 3. Definition of Done
- **A.** `python -m pytest -q` all pass (baseline **1188 passed / 4 skipped / 0 failed** at WK102 close; +new test → expect ~1198+).
- **B.** `python tools/determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`.
- **D.** `python tools/qa_smoke.py --quick` green.
- **E.** the 3 fns live in `game/ui/hud_menu_scroll.py`; HUD keeps the 3 wrapper names+signatures (esp. PUBLIC `handle_menu_scroll` for input_handler.py:127 + ursina_app.py:830 + the test MagicMock); call sites UNCHANGED (hud.py 1014/1025 internal; input_handler.py:127; ursina_app.py:830; test_wk52_r10_menu_scroll); state stays on HUD; hud.py smaller (~1219 → ~1132); **no import cycle** (both fresh orders); ZERO `self.` in the 3 moved fns.
- **F.** BEFORE/AFTER pygame screenshots — `base_overview` + `ui_panels` — visually identical. NOTE (document): wheel-scroll is INPUT behavior, not a static visual — the steady captures prove scene+chrome unchanged; the TARGETED guard is `tests/test_wk52_r10_menu_scroll.py` (drives both the building-panel and hero-menu wheel paths + the input-handler wiring) + the W2 behavior test. Report this caveat.
- **G.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 08 UX/UI):** create `hud_menu_scroll.py` (header + 3 fns, verbatim `self.`→`hud.`); add the 3 wrappers on HUD. Run full suite + digest + determinism + qa_smoke. Before/after pygame screenshots (base_overview + ui_panels). Verify ZERO `self.` in the 3 new fns + no top-level hud import in hud_menu_scroll + both import orders. Update own log. **DO NOT COMMIT.**
- **W2 (Agent 11 QA):** seam test `tests/test_wk103_hud_menu_scroll.py` — assert: (1) the 3 fns exist in hud_menu_scroll with the `hud`-first signature (inspect.signature). (2) the 3 HUD wrappers exist and delegate (monkeypatch each module fn to a sentinel, call the wrapper, assert fired — incl. PUBLIC `handle_menu_scroll`). (3) AST guard: hud_menu_scroll.py has no module-top `game.ui.hud` import (TYPE_CHECKING `from game.ui.hud import HUD` permitted) + fresh-subprocess both import orders returncode 0. (4) behavior (headless SDL dummy + pygame.init; mirror test_wk52_r10_menu_scroll setup): build `HUD(1920,1080)`, set `hud._last_left_rect = pygame.Rect(...)`, gs with a selected_hero (no peasant/building); assert `hud.is_mouse_over_menu((lr.centerx,lr.centery), gs, None) is True` and `((lr.right+80, lr.centery), gs, None) is False`; assert `hud.handle_menu_scroll((lr.centerx,lr.centery), 1, gs, None) is True` (hero-menu path consumes) and `((lr.right+50,lr.centery),1,gs,None) is False` (outside); assert `hud.scroll_active_menu(1, (lr.centerx,lr.centery), gs, None) is True` and `hud.scroll_active_menu(0, ...) is False` (wheel_y==0 early-out); and a building-panel path: a tiny stub building_panel (visible=True, selected_building=object(), panel_x/y/width/height, apply_menu_scroll→True) → `hud.handle_menu_scroll(mid_of_panel, 1, {}, bp) is True`. Run full DoD A–G, independently view before/after screenshots. Update own log. **DO NOT COMMIT.**

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| PUBLIC `handle_menu_scroll` wrapper name changed → input_handler.py:127 / ursina_app.py:830 wheel routing breaks (menus stop scrolling) | Med | keep EXACT name; W2 delegation + behavior test; test_wk52_r10 drives input_handler wiring + the MagicMock-replacement pattern |
| Import cycle | Very Low | module imports only pygame + TYPE_CHECKING HUD; lazy wrapper; verify both orders |
| A `self.X` missed (`_last_left_rect`/`_hero_menu_chat_rect`/`_hero_menu_hero_rect`/`_hero_panel` + the inter-helper calls) | Low | grep the 3 new fns for `self.` (MUST be ZERO); W2 drives both the building-panel and hero-menu wheel paths |
| `building_panel`/`game_state` mistakenly prefixed with `hud.` (they are PARAMETERS) | Low | they stay bare params; W2 building-panel stub path catches a wrong reference |

## 6. Success
The wheel menu-scroll router lives in `game/ui/hud_menu_scroll.py` behind 3 delegating wrappers, wheel routing behaves identically — proven by 1188+ green tests (incl. test_wk52_r10_menu_scroll driving both panel paths + a new behavior test), clean determinism guard, unchanged digest, identical before/after screenshots, and a verified no-cycle. hud.py drops ~87 LOC (eleventh slice; 2477→~1132 cumulative).

## 7. Kickoff
Roster: 08 UX/UI (W1), 11 QA (W2), 09 (consult). Order: 08 W1 → PM gate → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE VERBATIM MOVE (self.→hud.); keep the 3 wrapper names (esp. PUBLIC `handle_menu_scroll`) + ALL state on HUD; `building_panel`/`game_state` are params (NOT hud./self.); TYPE_CHECKING-only HUD import; ZERO `self.` in the 3 moved fns; before/after pygame MUST match (note input-behavior caveat); own log; DO NOT COMMIT.
Follow-ups (REMAINING roadmap, from the WK101 grounding sweep, in order): the **ursina god-files** (NEW verify model — ursina screenshots + runtime-import smoke, NOT the pygame digest): **WK104** FOG/C (`sync_dynamic_trees`+`sync_log_stacks`+`_InstancedTreeStub` → `game/graphics/ursina_terrain_growth_sync.py`, ~258 LOC) FIRST to establish the rhythm, then FOG/A+FOG/B (cohesive units), then ursina_app APP/C (env-gated debug/FPS scaffolding). DEFER: `handle_click` (hud.py:1058 — redesign, not a pure move — gate behind watch-card MiniMapProjection encapsulation), ursina_app APP/A camera + APP/B input hook (closures/monkeypatch — non-wrapper strategy). De-slop: delete dead `WATCH_MINIMAP_SIZE` (hud.py:57). NOTE: with WK103, hud.py ~1132 — the audit's #1 god-file is now well within target; remaining hud.py work is the deferred handle_click redesign. Re-run a grounding sweep before the ursina slices to confirm seams.
