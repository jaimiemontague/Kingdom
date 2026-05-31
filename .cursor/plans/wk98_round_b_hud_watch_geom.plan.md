# WK98 Sprint Plan — Round B-15: fold watch-card geometry helpers into hud_watch_card.py + relocate HERO_LEFT_MIN_H to hud_layout.py — sixth hud.py slice

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; the 5 watch-card geometry helpers moved from hud.py into the existing `game/ui/hud_watch_card.py`; `HERO_LEFT_MIN_H` relocated to the authoritative `game/ui/hud_layout.py`; render + layout visually unchanged.
**Predecessors:** WK93 (hud_radar), WK94 (hud_toasts), WK95 (hud_summaries), WK96 (hud_watch_card — render + WATCH_CARD_* consts), WK97 (hud_panel_buttons). **Roadmap:** Round B — hud.py (1566 LOC) split. Sixth bounded slice; first slice of the left-column/layout cluster.

## 0. TL;DR
The biggest remaining hud.py region is the left-column/layout cluster (lines ~389–828). It is too interdependent and external-caller-heavy to move in one shot, so WK98 takes the **safest, most self-contained sub-slice**: the 5 **watch-card geometry helpers** that compute the pinned watch-card's heights/body-split/chat-band rect. These belong in `game/ui/hud_watch_card.py` (WK96 already moved the watch-card RENDER functions + the `WATCH_CARD_*` constants there; the render functions already call these 5 helpers via `hud.`). Folding the geometry helpers into that same module COMPLETES its cohesion. The only blocker is that `_effective_watch_card_h` reads `HERO_LEFT_MIN_H`, currently defined in hud.py — and `hud_watch_card` must NOT import `hud` (hud imports hud_watch_card at top → that would be a cycle). So we relocate `HERO_LEFT_MIN_H` to `hud_layout.py` (the authoritative layout-constants module that everyone imports acyclically), and hud.py re-imports + re-exports it. This is the WK96 constant-ownership pattern. ~75 LOC leaves hud.py (1566 → ~1490). PM writes no code.

**This is NOT the full layout extraction.** The left-column segment/split/drag cluster and the `_layout_rects_for_screen`/`_compute_layout`/`virtual_pointer_in_hud_chrome` orchestration are explicitly OUT (WK99/WK100). See §7.

## 1. Scope

### 1a. Relocate one constant (hud.py → hud_layout.py)
Move `HERO_LEFT_MIN_H = 80` OUT of hud.py (currently line 47) and INTO `game/ui/hud_layout.py` (next to `LEFT_COL_W`/`RADAR_MINIMAP_H`, with a one-line comment). Then in hud.py ADD `HERO_LEFT_MIN_H` to the existing `from game.ui.hud_layout import (...)` block (lines 13–21) so the bare name still resolves in hud.py AND `from game.ui.hud import HERO_LEFT_MIN_H` keeps working.

**Why hud_layout.py and not hud_watch_card.py:** `HERO_LEFT_MIN_H` is a LEFT-COLUMN layout constant. It is consumed by (a) the watch-card geometry being moved now, (b) the hero-menu layout that STAYS on HUD (hud.py:1060), (c) the left-column segment cluster (future WK99), and (d) three tests that import it from `game.ui.hud` (`tests/test_wk52_watch_card.py:6`, `tests/test_wk61_r10_sidebar_layout.py:11`, `tests/test_wk61_r11_sidebar_main_solo_handle.py:9`). `hud_layout.py` is the one module all of those can import without any cycle (it imports only `pygame`+`dataclasses`). Putting it in hud_watch_card would force the future left-column module to import a left-column constant from the watch-card module — wrong cohesion. `hud_layout.py` is its correct permanent home.

**Do NOT move** the other hud-local constants this sprint: `HERO_MENU_CHAT_GAP/MIN_H/PREFERRED_H/HERO_MIN_H` (used only by the staying hero-menu code 1040–1065 + test_wk61_r9), `WATCH_MINIMAP_SIZE` (line 52), and `LEFT_SPLIT_HANDLE_H`/`LEFT_SPLIT_HANDLE_HIT_H`/`LEFT_SPLIT_DEFAULT_FRAC_MAIN`/`LEFT_SPLIT_DEFAULT_FRAC_WATCH`/`LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO` (used by __init__ + the left-column cluster → WK99). They stay in hud.py.

### 1b. Move 5 methods (hud.py → hud_watch_card.py), VERBATIM (replace `self.`→`hud.`), keep a 1-line delegating wrapper on HUD for each (exact name+signature so ALL call sites are UNCHANGED):

| HUD method | hud.py line | → module function | Caller(s) the wrapper preserves |
|---|---|---|---|
| `effective_card_full_h(self)` | 389 | `effective_card_full_h(hud)` | `tests/test_wk52_watch_card.py:331/334` `hud.effective_card_full_h()` (public API) |
| `_desired_watch_card_expanded_h(self)` | 420 | `desired_watch_card_expanded_h(hud)` | internal: called by `_effective_watch_card_h` (hud.py:437) |
| `_effective_watch_card_h(self, screen_h)` | 428 | `effective_watch_card_h(hud, screen_h)` | `virtual_pointer_in_hud_chrome` (hud.py:789, stays); `hud_watch_card.py:69`; `tests/test_wk52_watch_card.py:50` |
| `_watch_card_body_split(self, ch)` | 444 | `watch_card_body_split(hud, ch)` | `virtual_pointer_in_hud_chrome` (hud.py:795, stays); `hud_watch_card.py:103` |
| `_watch_chat_band_rect(self, cx, cy, cw, ch, map_h, stats_h, chat_h, profiles, hero_id, painted_stats_bottom_override=None)` | 459 | `watch_chat_band_rect(hud, cx, cy, cw, ch, map_h, stats_h, chat_h, profiles, hero_id, painted_stats_bottom_override=None)` | `virtual_pointer_in_hud_chrome` (hud.py:798, stays); `hud_watch_card.py:189` |

**Mechanical move rule — EVERY `self.<x>` becomes `hud.<x>`. Nothing else changes.** The fields/methods these touch (all STAY on HUD, reached via `hud.`): `hud._chat_visible`, `hud._watch_card_expanded`, `hud._left_watch_rect`, `hud._pin_slot`, `hud.theme`, `hud.font_tiny`, and the inter-helper call `hud._desired_watch_card_expanded_h()` (line 437 → keep as `hud._desired_watch_card_expanded_h()`, i.e. it calls the HUD wrapper which re-delegates into this module — correct, mechanical, no recursion). The module-level constants these read (`WATCH_CARD_HEADER_H`, `WATCH_CARD_MAP_H`, `WATCH_CARD_STATS_H`, `WATCH_CARD_STATS_COMPACT_H`, `WATCH_CARD_CHAT_H`, `WATCH_CARD_FULL_H_WITH_CHAT`, `WATCH_CARD_FULL_H_NO_CHAT`) are ALREADY module-local in hud_watch_card.py — reference them bare (no `hud.`), exactly as the original hud.py code referenced them bare. `RADAR_MINIMAP_H` (used at line 435) and `HERO_LEFT_MIN_H` (used at line 440) must be IMPORTED into hud_watch_card.py from hud_layout (see §2). Reference them bare too.

**Do NOT change** the 3 existing internal call sites in hud_watch_card.py (lines 69/103/189: `hud._effective_watch_card_h(sh)`, `hud._watch_card_body_split(ch)`, `hud._watch_chat_band_rect(...)`). They keep calling via `hud.` (the wrapper re-enters this module). Leaving them untouched = zero risk. (We deliberately accept one wrapper round-trip rather than rewriting working lines.)

**STAYS on HUD** (DO NOT move): all watch-card STATE (in __init__), the hero-menu layout helpers + `HERO_MENU_*` constants, `_should_render_hero_menu_chat_popup`, the entire left-column segment/split/drag cluster (`_left_column_segments_open` … `handle_sidebar_split_pointer_up`), `_layout_rects_for_screen`, `_compute_layout`, `virtual_pointer_in_hud_chrome`. **OUT.**

## 2. Pattern (WK96, verbatim) — what to ADD to hud_watch_card.py
At the top of `hud_watch_card.py`, ADD one import line under the existing `from game.ui.widgets import HPBar, NineSlice` (line 29):
```python
from game.ui.hud_layout import HERO_LEFT_MIN_H, RADAR_MINIMAP_H
```
`hud_layout.py` imports only `pygame`+`dataclasses` (verified) → it never imports hud_watch_card or hud → **acyclic**. Then append the 5 functions (hud-first, `def fn(hud, ...)`) at the end of the module (after the existing render functions). The module already has `from __future__ import annotations`, `from typing import TYPE_CHECKING`, `import pygame`, and the `if TYPE_CHECKING: from game.ui.hud import HUD` block — reuse them; do NOT add a top-level `import game.ui.hud`.

### Wrapper form on HUD (replace each moved method body with this 1-liner; keep the EXACT def line incl. leading underscore + type hints):
```python
def effective_card_full_h(self) -> int:
    from game.ui import hud_watch_card
    return hud_watch_card.effective_card_full_h(self)

def _desired_watch_card_expanded_h(self) -> int:
    from game.ui import hud_watch_card
    return hud_watch_card.desired_watch_card_expanded_h(self)

def _effective_watch_card_h(self, screen_h: int) -> int:
    from game.ui import hud_watch_card
    return hud_watch_card.effective_watch_card_h(self, screen_h)

def _watch_card_body_split(self, ch: int) -> tuple[int, int, int]:
    from game.ui import hud_watch_card
    return hud_watch_card.watch_card_body_split(self, ch)

def _watch_chat_band_rect(
    self,
    cx: int,
    cy: int,
    cw: int,
    ch: int,
    map_h: int,
    stats_h: int,
    chat_h: int,
    profiles: dict,
    hero_id: str,
    painted_stats_bottom_override: int | None = None,
) -> pygame.Rect | None:
    from game.ui import hud_watch_card
    return hud_watch_card.watch_chat_band_rect(
        self, cx, cy, cw, ch, map_h, stats_h, chat_h, profiles, hero_id, painted_stats_bottom_override
    )
```
The wrappers import `hud_watch_card` LAZILY inside the body → no new top-level import in hud.py (hud already imports hud_watch_card at top for the constants, so even a top-level reference would be fine, but keep the lazy form for consistency with WK94–97). Move VERBATIM.

## 3. Definition of Done
- **A.** `python -m pytest -q` all pass (baseline **1037 passed / 4 skipped / 0 failed**; +new test → expect ~1043+ passed).
- **B.** `python tools/determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded` (`python -m pytest tests/test_wk67_ai_boundary.py -q`).
- **D.** `python tools/qa_smoke.py --quick` green.
- **E.** the 5 fns live in `game/ui/hud_watch_card.py`; `HERO_LEFT_MIN_H` lives in `game/ui/hud_layout.py` and is removed from hud.py's own definitions; hud.py re-imports HERO_LEFT_MIN_H from hud_layout (so `from game.ui.hud import HERO_LEFT_MIN_H` still works); HUD keeps the 5 wrapper names+signatures (esp. public `effective_card_full_h`); the call sites (hud.py 437/789/795/798; hud_watch_card.py 69/103/189; test_wk52 50/331/334) are UNCHANGED; watch-card state + hero-menu constants stay on HUD; hud.py smaller (~1566 → ~1490); **no import cycle** (both fresh import orders); ZERO `self.` in the 5 moved functions.
- **F.** BEFORE/AFTER pygame screenshots — `base_overview` + `ui_panels` — visually identical. The pinned watch card (above the minimap, bottom-left) is the affected region; capture a scenario with a pinned hero so the watch card + chat band actually render (the geometry helpers drive its height/body-split/chat-band). Report the watch-card region specifically: header, map slot, HP/XP/Lvl stats rows, chat band — heights and split must be pixel-identical before/after.
- **G.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 08 UX/UI):** (1) add `HERO_LEFT_MIN_H = 80` to hud_layout.py + remove from hud.py + add to hud.py's hud_layout import; (2) add the 2-name import to hud_watch_card.py + append the 5 fns (verbatim `self.`→`hud.`); (3) replace the 5 hud.py method bodies with wrappers. Run full suite + digest + determinism + qa_smoke. Before/after pygame screenshots (incl. a pinned-hero scenario for the watch card). Verify ZERO `self.` in the 5 new fns + no top-level hud import in hud_watch_card + both import orders. Update own log. **DO NOT COMMIT.**
- **W2 (Agent 11 QA):** seam test `tests/test_wk98_hud_watch_geom.py` — assert: (1) the 5 fns exist in hud_watch_card with the `hud`-first signature (use `inspect.signature`); (2) `HERO_LEFT_MIN_H == 80` is importable from `game.ui.hud_layout` AND re-exported by `game.ui.hud` (both `from game.ui.hud_layout import HERO_LEFT_MIN_H` and `from game.ui.hud import HERO_LEFT_MIN_H` succeed and equal 80); (3) the 5 HUD wrappers exist and delegate (monkeypatch each module fn to a sentinel, call the wrapper, assert the sentinel was hit — incl. the public `effective_card_full_h`); (4) AST guard: hud_watch_card.py has no module-top `import game.ui.hud` / `from game.ui.hud import` (TYPE_CHECKING block permitted); (5) behavior (headless: `os.environ["SDL_VIDEODRIVER"]="dummy"`, `pygame.init()`): construct `HUD(1920,1080)`, set `hud._pin_slot.hero_id="p1"` + `hud._watch_card_expanded=True` + `hud._chat_visible=True`, then call `hud._effective_watch_card_h(1080)` (assert int > WATCH_CARD_HEADER_H), `hud._watch_card_body_split(hud._effective_watch_card_h(1080))` (assert 3-tuple of ints summing ≤ ch), `hud.effective_card_full_h()` (assert == WATCH_CARD_FULL_H_WITH_CHAT when chat visible, == WATCH_CARD_FULL_H_NO_CHAT when `hud._chat_visible=False`), `hud._desired_watch_card_expanded_h()` (assert int), and `hud._watch_chat_band_rect(...)` on a real Surface's rect math (assert returns a pygame.Rect or None without raising). Run full DoD A–G, independently view before/after screenshots. Update own log. **DO NOT COMMIT.**

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Import cycle introduced by adding `from game.ui.hud_layout import …` to hud_watch_card | Very Low | hud_layout imports only pygame+dataclasses — verified no hud/hud_watch_card import; W1+W2 verify both fresh import orders |
| `HERO_LEFT_MIN_H` relocation breaks a `from game.ui.hud import HERO_LEFT_MIN_H` consumer (3 tests) | Low | hud.py re-imports it from hud_layout into its namespace → name still resolves; W2 asserts both import paths == 80; the 3 wk52/wk61 tests are the live guard |
| A `self.X` missed in the 5-method sweep (esp. `self.font_tiny`, `self._pin_slot`, the inter-helper `self._desired_watch_card_expanded_h()`) | Low | grep the 5 new fns for `self.` (MUST be ZERO); W2 behavior test exercises all 5 through the wrapper path |
| `effective_card_full_h` is PUBLIC (no underscore) — wrapper name typo would break test_wk52:331/334 | Low | keep EXACT name `effective_card_full_h`; W2 delegation test + test_wk52 catch it |
| Weak screenshot coverage (watch card only renders when a hero is pinned) | Med | DoD F mandates a pinned-hero capture; the verbatim move + behavior test rendering the card through the moved geometry is the real guard — state this caveat |

## 6. Success
The 5 watch-card geometry helpers live in `game/ui/hud_watch_card.py` (completing that module's render+geometry+constants cohesion) behind 5 delegating wrappers; `HERO_LEFT_MIN_H` lives in its correct home `hud_layout.py` (re-exported by hud) — proven by 1037+ green tests (incl. a new behavior test driving all 5 helpers through the moved path), clean determinism guard, unchanged digest, identical before/after pygame screenshots of the pinned watch card, and a verified no-cycle. hud.py drops ~75 LOC (sixth slice; 2477→~1490 cumulative).

## 7. Kickoff
Roster: 08 UX/UI (W1), 11 QA (W2), 09 (consult). Order: 08 W1 → PM gate → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE VERBATIM MOVE; relocate ONLY `HERO_LEFT_MIN_H` (to hud_layout.py, re-exported by hud) — leave HERO_MENU_*/WATCH_MINIMAP_SIZE/LEFT_SPLIT_* in hud.py; keep the 5 wrapper names (esp. public `effective_card_full_h`) + ALL state on HUD; do NOT touch the 3 existing internal calls in hud_watch_card (69/103/189); TYPE_CHECKING-only HUD import; ZERO `self.` in the 5 moved fns; before/after pygame MUST match; own log; DO NOT COMMIT.
Follow-ups (REMAINING roadmap, in order):
- **WK99** = left-column segment/split/drag cluster → NEW `game/ui/hud_left_layout.py`: `_left_column_segments_open`, `_normalized_left_split_fracs`, `_layout_left_column_segments`, `_render_left_split_handles`, `handle_sidebar_split_pointer_down/move/up` (~240 LOC); relocate `LEFT_SPLIT_HANDLE_H`/`LEFT_SPLIT_HANDLE_HIT_H`/`LEFT_SPLIT_DEFAULT_FRAC_MAIN`/`WATCH`/`MAIN_SOLO` to hud_layout.py (re-exported by hud — guarded by test_wk61_r10/r11 which import them from hud). MED risk; many external callers of handle_sidebar_split_pointer_* (ursina_app/mouse/input_handler) → keep wrappers; strong screenshot guard (left column always visible with selection/pin).
- **WK100** = layout orchestration → hud_left_layout.py: `_layout_rects_for_screen`, `_compute_layout`, `virtual_pointer_in_hud_chrome` (~120 LOC). Needs `ViewMode` from micro_view_manager (verified no hud import) + sim_now_ms + HUDLayoutManager. MED risk; MANY external callers (ursina_app.py 727/796/798/1299/1301, mouse.py 88/89/402, input_handler.py 88/89, building_panel.py 285, test_wk52/test_wk61) → keep wrappers exact.
- Then: `ursina_terrain_fog_collab`(1783)/`ursina_app`(1525) splits; messages (`add_message`/`render_messages`); input-router (`handle_click` + menu-scroll); Move 9 (SystemRunner — RISKY); world.py fog; context_builder/direct_prompt_validator; ai/vocab.py + TaskRouter; config package; clusters 3/4; Round E audit; the 21-file WK34-zombie-type purge.
