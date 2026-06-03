# WK97 Sprint Plan — Round B-14: extract hud_panel_buttons.py (panel-chrome button renderers) — fifth hud.py slice

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; the panel-chrome button renderers extracted from hud.py into `game/ui/hud_panel_buttons.py`; render visually unchanged.
**Predecessors:** WK93 (hud_radar), WK94 (hud_toasts), WK95 (hud_summaries), WK96 (hud_watch_card). **Roadmap:** Round B — hud.py (1744 LOC) split. Fifth bounded slice.

## 0. TL;DR
WK97 extracts the **panel-chrome button render cluster** — `_render_right_close_button` (:886), `_render_left_close_button` (:914), `_render_pin_button` (:949), `trigger_recall_flash` (:1007), `_render_memorial_button` (:1051), `_render_recall_button` (:1073) — ~200 LOC of leaf button renderers (each draws a button + stores a hit-rect that `handle_click` reads) — into `game/ui/hud_panel_buttons.py` as functions taking the HUD (`hud`), behind 1-line delegating wrappers on HUD. The `COLOR_PIN_GOLD` constant (hud.py:34, used ONLY by `_render_pin_button`, no external consumers) moves into the new module too (clean — no re-export needed). All hit-rect/flash STATE stays on HUD. Same low-risk leaf-renderer shape as WK95. The WK67 digest (headless) is unaffected. PM writes no code.

## 1. Scope
**IN:** create `game/ui/hud_panel_buttons.py`; move VERBATIM (replace `self.`→`hud.`) these 6 methods + 1 constant, keeping a 1-line delegating wrapper on HUD for each method (same name+signature):

| HUD method | hud.py line | → module function | Caller(s) the wrapper preserves |
|---|---|---|---|
| `_render_right_close_button(self, surface, right_rect)` | 886 | `render_right_close_button(hud, surface, right_rect)` | render() internal |
| `_render_left_close_button(self, surface, left_rect)` | 914 | `render_left_close_button(hud, surface, left_rect)` | render() (1363/1367/1370/1466) |
| `_render_pin_button(self, surface, left_rect, game_state)` | 949 | `render_pin_button(hud, surface, left_rect, game_state)` | render() (1362/1465) |
| `trigger_recall_flash(self)` | 1007 | `trigger_recall_flash(hud)` | **EXTERNAL: `game/ui/pin_alert_watcher.py:102` `self._hud.trigger_recall_flash()`** — wrapper name MUST stay |
| `_render_memorial_button(self, surface, memorial_rect, game_state)` | 1051 | `render_memorial_button(hud, surface, memorial_rect, game_state)` | render() (1384) |
| `_render_recall_button(self, surface, recall_rect, game_state)` | 1073 | `render_recall_button(hud, surface, recall_rect, game_state)` | render() (1383) |

Also MOVE the constant `COLOR_PIN_GOLD = (220, 180, 50)` from hud.py:34 into the new module (it's used only at the moved line 986; verified NO other use in hud.py and NO external consumer — so just move it, delete from hud.py, NO re-export).

Inside the moved functions, every `self.<x>`→`hud.<x>`: state (`hud._right_close_button`, `hud._left_close_button`, `hud._button_tex_normal/_hover/_pressed`, `hud._button_slice_border`, `hud._frame_outer/_inner/_highlight`, `hud.right_close_rect`, `hud.left_close_rect`, `hud.pin_button_rect`, `hud._pin_slot`, `hud._pin_emoji_font`, `hud._pin_emoji_font_size`, `hud._recall_flash_end_ms`, `hud.memorial_btn_rect`, `hud._pending_memorial`, `hud.memorial_card`, `hud.recall_rect`, `hud._recall_label_sig`, `hud._recall_label_surf`, `hud._recall_overlay_size`, `hud._recall_fallen_overlay`, `hud._recall_flash_overlay`, `hud.theme`). The `Button(...)` lazy-init in `_render_left_close_button` (915-921) stays verbatim (sets `hud._left_close_button`). The `hasattr(self, "_pin_emoji_font")`/`getattr(self, ...)` in `_render_pin_button` become `hasattr(hud, ...)`/`getattr(hud, ...)`.

**STAYS on HUD** (DO NOT move): all the hit-rect + flash STATE (set in __init__: `right_close_rect` :251, `left_close_rect` :252, `pin_button_rect` :260, `memorial_btn_rect` :275, `memorial_card` :291, `_pending_memorial` :292, `_recall_flash_*` :274/286, etc.), `_right_panel_top_pad` (:880, reads `self.right_close_rect`), `handle_click` (reads the hit-rects). These are reached via `hud.`.

**OUT:** messages/input-router/layout (later); any behavior/visual change. **Move VERBATIM.**

## 2. Pattern (WK87–96, verbatim)
`hud_panel_buttons.py` header:
```python
from __future__ import annotations
from typing import TYPE_CHECKING
import pygame
from config import COLOR_WHITE  # only if used; otherwise omit
from game.sim.timebase import now_ms as sim_now_ms
from game.ui.hero_panel import truncate_panel_line
from game.ui.widgets import Button, NineSlice, TextLabel
if TYPE_CHECKING:
    from game.ui.hud import HUD

COLOR_PIN_GOLD = (220, 180, 50)
# ...then the 6 functions.
```
(verified deps: `pygame`, `Button`/`NineSlice`/`TextLabel` (widgets), `sim_now_ms` (game.sim.timebase — leaf), `truncate_panel_line` (game.ui.hero_panel — leaf, imported by hud at top so it does NOT import hud → no cycle), and `COLOR_PIN_GOLD` (now module-local). Drop `COLOR_WHITE` if grep shows it's unused in these 6 methods.) The module never imports `game.ui.hud` at top (TYPE_CHECKING only). Wrappers import `hud_panel_buttons` lazily → **no cycle**. Move VERBATIM.

## 3. Definition of Done
- **A.** `pytest -q` all pass (baseline **1001 passed / 4 skipped / 0 failed** at WK96 close; +new test → expect ~1010+).
- **B.** `python tools/determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`.
- **D.** `python tools/qa_smoke.py --quick` green.
- **E.** the 6 fns + `COLOR_PIN_GOLD` live in `game/ui/hud_panel_buttons.py`; HUD keeps the 6 wrapper names+signatures (esp. `trigger_recall_flash` for pin_alert_watcher); the render() call sites + pin_alert_watcher.py:102 unchanged; hit-rect/flash state stays on HUD; `COLOR_PIN_GOLD` removed from hud.py (no re-export — no consumers); hud.py smaller (~1744 → ~1555); **no import cycle** (both fresh import orders); ZERO `self.` in the new module.
- **F.** BEFORE/AFTER pygame screenshots — `base_overview` + `ui_panels` — visually identical. The `ui_panels_hero` variant shows the close/pin/recall buttons; the close button shows whenever a panel is open. Report the button regions specifically (close X, pin, recall, memorial when present).
- **G.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 08 UX/UI):** create `hud_panel_buttons.py` (constant + 6 fns), add 6 wrappers, delete COLOR_PIN_GOLD from hud.py. Run full suite + digest + determinism + qa_smoke. Before/after pygame screenshots. Verify ZERO `self.` in new module + no top-level hud import + both import orders. Update own log. **DO NOT COMMIT.**
- **W2 (Agent 11 QA):** seam test `tests/test_wk97_hud_panel_buttons.py` — assert: (1) 6 fns exist (hud-first) + `COLOR_PIN_GOLD == (220,180,50)` in the new module; (2) 6 HUD wrappers exist and delegate (monkeypatch, incl. `trigger_recall_flash` since pin_alert_watcher calls it); (3) AST guard: no module-top `game.ui.hud` import; (4) behavior: headless HUD + a real Surface + Rects, call each render fn (with a `selected_hero` game_state for pin; a pinned `_pin_slot.hero_id` + profiles for recall; `_pending_memorial` set + `memorial_card.visible=False` for memorial) — assert no exception AND the hit-rects got set (`right_close_rect`/`left_close_rect`/`pin_button_rect`/`recall_rect`/`memorial_btn_rect`); and assert `trigger_recall_flash()` sets `_recall_flash_end_ms > 0`. Run full DoD A–G, independently view before/after screenshots. Update own log. **DO NOT COMMIT.**

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| `trigger_recall_flash` wrapper name changed → pin_alert_watcher silently no-ops the recall flash | Low-Med | keep EXACT name; W2 behavior test calls it + asserts `_recall_flash_end_ms` set |
| `COLOR_PIN_GOLD` move misses a consumer | Low | grep confirmed only hud.py:34 (def) + :986 (use, moving); no external/import consumers — safe to move outright |
| A `self.X` missed in the sweep (~22 state fields, the Button lazy-init, hasattr/getattr) | Low-Med | grep new module for `self.` (MUST be ZERO); W2 behavior test renders all 5 buttons + asserts hit-rects |
| Import cycle (via hero_panel/widgets/timebase) | Low | all three are leaves hud already imports at top; TYPE_CHECKING-only HUD import; verify both orders |

## 6. Success
The panel-chrome button renderers + `COLOR_PIN_GOLD` live in `game/ui/hud_panel_buttons.py` behind 6 delegating wrappers, the buttons render identically — proven by 1001+ green tests (incl. a new behavior test rendering all 5 buttons + the recall-flash trigger through the moved path), clean determinism guard, unchanged digest, identical before/after pygame screenshots, and a verified no-cycle. hud.py drops ~190 LOC (fifth slice; 2477→~1555 cumulative).

## 7. Kickoff
Roster: 08 UX/UI (W1), 11 QA (W2), 09 (consult). Order: 08 W1 → PM gate → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE VERBATIM MOVE; move COLOR_PIN_GOLD into the new module (delete from hud.py, no re-export); keep the 6 wrapper names (esp. `trigger_recall_flash`) + all hit-rect/flash state on HUD; TYPE_CHECKING-only import; ZERO `self.` in the new module; before/after pygame MUST match; own log; DO NOT COMMIT.
Follow-ups (REMAINING roadmap): WK98 = messages (`add_message`/`render_messages`) and/or the input-router (`handle_click` + sidebar split handlers + menu-scroll, MEDIUM risk) and/or the left-column layout cluster; then `ursina_terrain_fog_collab`(1783)/`ursina_app`(1525) splits; Move 9 (SystemRunner — RISKY); world.py fog; context_builder/direct_prompt_validator; ai/vocab.py + TaskRouter; config package; clusters 3/4; Round E audit; the 21-file WK34-zombie-type purge.
