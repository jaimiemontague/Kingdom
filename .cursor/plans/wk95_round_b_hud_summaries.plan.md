# WK95 Sprint Plan — Round B-12: extract hud_summaries.py (entity info-card renderers) — third hud.py slice

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; the peasant/building/hero-focus info-card renderers extracted from hud.py into `game/ui/hud_summaries.py`; render visually unchanged.
**Predecessors:** WK93 (hud_radar), WK94 (hud_toasts). **Roadmap:** Round B — the audit's #1 split: hud.py (2085 LOC). Third bounded slice (entity-summary renderers), proven pure-move-behind-wrappers pattern (WK69–94).

## 0. TL;DR
hud.py (2085 LOC) is the biggest god-file. WK95 extracts the **entity info-card render cluster** — `_peasant_action_label` (:852), `_render_peasant_summary` (:879), `_render_building_summary` (:1400), `_render_hero_focus_profile` (:1578) — ~200 LOC of leaf render helpers that draw an entity's summary into a panel rect — into `game/ui/hud_summaries.py` as functions taking the HUD (`hud`), behind 1-line delegating wrappers on HUD (the render() call sites + the external `micro_view_manager` caller keep their exact names). These are LEAF renderers (lower coupling than the watch-card cluster, which is WK96): they only read HUD theme/frame state and call shared helpers that STAY on HUD. The new module's only real imports are `pygame`, `TextLabel`, `HPBar`, `COLOR_WHITE`. The WK67 digest (headless) is unaffected. PM writes no code.

## 1. Scope
**IN:** create `game/ui/hud_summaries.py`; move VERBATIM (replace `self.`→`hud.`) these 4 methods, keeping a 1-line delegating wrapper on HUD for **each** (same name + signature so all call sites are UNCHANGED):

| HUD method (current) | hud.py line | → module function | Caller(s) the wrapper preserves |
|---|---|---|---|
| `_peasant_action_label(self, peasant)` | 852 | `peasant_action_label(hud, peasant)` | called at hud.py:914 inside `_render_peasant_summary` |
| `_render_peasant_summary(self, surface, peasant, left_rect)` | 879 | `render_peasant_summary(hud, surface, peasant, left_rect)` | render() at hud.py:1712 |
| `_render_building_summary(self, surface, building, rect)` | 1400 | `render_building_summary(hud, surface, building, rect)` | `_render_right_panel_overview` at hud.py:981 |
| `_render_hero_focus_profile(self, surface, rect, game_state)` | 1578 | `render_hero_focus_profile(hud, surface, rect, game_state)` | **EXTERNAL: `game/ui/micro_view_manager.py:119` `hasattr(hud, "_render_hero_focus_profile")` + :126 `hud._render_hero_focus_profile(...)`** — wrapper name MUST stay exactly |

Wrapper form (example):
```python
def _render_peasant_summary(self, surface: pygame.Surface, peasant, left_rect: pygame.Rect) -> None:
    from game.ui import hud_summaries
    return hud_summaries.render_peasant_summary(self, surface, peasant, left_rect)
def _peasant_action_label(self, peasant) -> str:
    from game.ui import hud_summaries
    return hud_summaries.peasant_action_label(self, peasant)
# ...and the same 1-line lazy-delegate form for _render_building_summary and _render_hero_focus_profile.
```
Inside the moved functions, replace EVERY `self.<x>` with `hud.<x>`, including: `hud.theme` (margin, font_title, font_small, font_body), `hud._frame_inner`, `hud._frame_highlight`, `hud._draw_section_divider(...)`, `hud._peasant_action_label(...)` (the peasant-summary calls the helper — leave it as `hud._peasant_action_label` so it resolves to the HUD wrapper → module fn; correct), `hud._right_panel_top_pad(...)`, `hud._micro_view`, `hud._hero_panel`.

**STAYS on HUD** (DO NOT move — shared/generic helpers + state): `_draw_section_divider` (:846 — used by many renderers), `_right_panel_top_pad` (:992), `_frame_inner`/`_frame_highlight` (set in __init__ :96/97), `_micro_view` (:251), `_hero_panel` (:219), `theme`. The moved functions reach them via `hud.`.

**OUT:** the watch-card cluster (`_render_hero_watch_card_infocard`/`_render_card_slot`/`_render_watch_card_chrome` — WK96, has the test_wk52_watch_card.py guard); `messages`/`render_messages` (later); `_render_right_panel_overview` (:975 — orchestrator, stays); any behavior/visual change. **Move VERBATIM.**

## 2. Pattern (WK87–94, verbatim)
`hud_summaries.py` header:
```python
from __future__ import annotations
from typing import TYPE_CHECKING
import pygame
from config import COLOR_WHITE
from game.ui.widgets import HPBar, TextLabel
if TYPE_CHECKING:
    from game.ui.hud import HUD
```
(verified: these 4 methods use only `pygame`, `TextLabel`, `HPBar`, `COLOR_WHITE` as module-level deps; everything else is reached via `hud.`). The module never imports `game.ui.hud` at top (TYPE_CHECKING only). Wrappers import `hud_summaries` lazily inside the body → **no import cycle** (note: `widgets` does not import `hud`, so no cycle there either — verify). Move VERBATIM.

## 3. Definition of Done
- **A.** `pytest -q` all pass (baseline **943 passed / 4 skipped / 0 failed** at WK94 close; WK95 adds the new seam/behavior test → expect ~950+ passed).
- **B.** `python tools/determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded` (`python -m pytest tests/test_wk67_ai_boundary.py -q`).
- **D.** `python tools/qa_smoke.py --quick` green.
- **E.** the 4 fns live in `game/ui/hud_summaries.py`; HUD keeps all 4 wrapper names+signatures (esp. `_render_hero_focus_profile` for the micro_view_manager hasattr-caller); the call sites (hud.py 914/981/1712; micro_view_manager.py 119/126) are UNCHANGED; shared helpers + state stay on HUD; hud.py smaller (~2085 → ~1890); **no import cycle** (verify both import orders from a fresh interpreter); ZERO `self.` in the new module.
- **F.** BEFORE/AFTER pygame screenshots — `base_overview` + `ui_panels` — visually identical. NOTE: a summary only renders when its entity kind is selected; the steady-state captures prove scene+chrome unchanged. The targeted guard is the W2 behavior test (renders each summary onto a Surface with a mock peasant/building/hero and asserts no error). Report this coverage caveat explicitly.
- **G.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 08 UX/UI):** create `hud_summaries.py`, move the 4 fns VERBATIM (`self.`→`hud.`), add the 4 delegating wrappers on HUD. Run full suite + digest + determinism + qa_smoke. Capture before/after pygame screenshots (base_overview + ui_panels). Verify ZERO `self.` in new module + no import cycle (both orders). Update own log. **DO NOT COMMIT.**
- **W2 (Agent 11 QA):** seam test `tests/test_wk95_hud_summaries.py` — assert: (1) the 4 fns exist in `hud_summaries` with the `hud`-first signature; (2) all 4 HUD wrappers exist and delegate (monkeypatch a module fn + assert the wrapper hits it; include `_render_hero_focus_profile` since an external module calls it via hasattr); (3) AST guard: `hud_summaries.py` does NOT import `game.ui.hud` at module top (TYPE_CHECKING-only allowed); (4) behavior: construct a headless HUD, build a tiny mock peasant (state/hp/max_hp), a mock building (building_type/hp/max_hp), and a mock hero+game_state, then call `hud._render_peasant_summary(surface, peasant, rect)`, `hud._render_building_summary(surface, building, rect)`, `hud._peasant_action_label(peasant)` (assert a str), and `hud._render_hero_focus_profile(surface, rect, game_state)` — each on a real Surface, asserting no exception. Run full DoD A–G, independently view before/after screenshots. Update own log. **DO NOT COMMIT.**

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| `_render_hero_focus_profile` wrapper name changed → micro_view_manager `hasattr` silently returns False (hero-focus top panel stops rendering) | Low-Med | keep EXACT name; W2 behavior test calls it + asserts render; note the external caller explicitly |
| A `self.X` missed in the sweep (theme/_frame_*/_draw_section_divider/_peasant_action_label/_right_panel_top_pad/_micro_view/_hero_panel) | Low-Med | grep new module for `self.` (must be ZERO); suite + behavior test catch a missed ref |
| Import cycle (hud_summaries ↔ hud, or via widgets) | Low | TYPE_CHECKING-only HUD import; lazy wrapper (proven WK87–94); widgets doesn't import hud — verify both orders |
| Weak steady-state screenshot coverage (summaries only show when an entity is selected) | Med | documented in DoD F; the verbatim move + behavior test rendering each summary is the real guard — state this caveat, don't claim screenshot proof of the summary pixels |

## 6. Success
The entity info-card renderers live in `game/ui/hud_summaries.py` behind 4 delegating wrappers, summaries render identically — proven by 943+ green tests (incl. a new behavior test that renders each summary through the moved path), clean determinism guard, unchanged digest, identical before/after pygame screenshots, and a verified no-cycle. hud.py drops ~195 LOC (third slice).

## 7. Kickoff
Roster: 08 UX/UI (W1), 11 QA (verify + DoD + screenshot review + behavior test, W2), 09 (consult). Order: 08 W1 → PM gate (suite + digest + screenshots + no-cycle) → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE VERBATIM MOVE, keep ALL 4 wrapper names (esp. `_render_hero_focus_profile`) + shared helpers/state on the HUD, TYPE_CHECKING-only import, ZERO `self.` left in the new module; before/after pygame MUST match; own log; DO NOT COMMIT.
Follow-ups (REMAINING roadmap): WK96 watch-card cluster (`_render_hero_watch_card_infocard`/`_render_card_slot`/`_render_watch_card_chrome` + height helpers — guarded by test_wk52_watch_card.py + always-visible ui_panels_hero screenshot); messages (`add_message`/`render_messages`); input_router (`handle_click` + sidebar split handlers + menu-scroll); `ursina_terrain_fog_collab`(1783)/`ursina_app`(1525) splits; Move 9 (SystemRunner — RISKY); world.py fog; context_builder/direct_prompt_validator; ai/vocab.py + TaskRouter (Move 12); config package; clusters 3/4; Round E audit; the 21-file WK34-zombie-type purge.
