# WK96 Sprint Plan — Round B-13: extract hud_watch_card.py (pinned-hero watch card) — fourth hud.py slice

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; the pinned-hero watch-card render cluster (+ its layout constants) extracted from hud.py into `game/ui/hud_watch_card.py`; render visually unchanged.
**Predecessors:** WK93 (hud_radar), WK94 (hud_toasts), WK95 (hud_summaries). **Roadmap:** Round B — hud.py (1901 LOC) split. Fourth bounded slice — the watch-card cluster, the meatiest renderer left.

## 0. TL;DR
hud.py (1901 LOC) is the biggest god-file. WK96 extracts the **pinned-hero watch-card render cluster** — `_render_hero_watch_card_infocard` (:1008, ~160 LOC), `_render_card_slot` (:1168), `_render_watch_card_chrome` (:1186) — into `game/ui/hud_watch_card.py` as functions taking the HUD (`hud`), behind 1-line delegating wrappers on HUD (render() keeps calling `self._render_watch_card_chrome(...)`). The new module also becomes the **owner of the WATCH_CARD_* layout constants** (hud.py lines 35–45) — these must move because the render cluster uses `WATCH_CARD_HEADER_H`, and keeping them in hud.py would force the new module to import hud (a back-dependency). hud.py then **re-imports + re-exports** those constants so `from game.ui.hud import WATCH_CARD_*` keeps working for `tests/test_wk52_watch_card.py` AND for the watch-card LAYOUT HELPERS that STAY on HUD (`_effective_watch_card_h`/`_watch_card_body_split`/`_desired_watch_card_expanded_h`/`effective_card_full_h`/`_watch_chat_band_rect`). This is the riskiest slice so far (heavy HUD-state coupling, ~25 instance fields, the constant re-export), but strongly guarded: `test_wk52_watch_card.py` pins the layout/radar math, the **watch card is VISIBLE in the `ui_panels_hero` screenshot** (a hero is pinned), and a new W2 behavior test renders the card through the moved path. The WK67 digest (headless) is unaffected. PM writes no code.

## 1. Scope
**IN:** create `game/ui/hud_watch_card.py` containing:
1. The WATCH_CARD_* constant block moved VERBATIM from hud.py lines 35–45 (incl. the line-38 comment):
   `WATCH_CARD_HEADER_H=18`, `WATCH_CARD_MAP_H=160`, `WATCH_CARD_STATS_H=78`, `WATCH_CARD_STATS_COMPACT_H=58`, `WATCH_CARD_CHAT_H=150`, `WATCH_CARD_FULL_H_WITH_CHAT`, `WATCH_CARD_FULL_H_NO_CHAT`, `WATCH_CARD_FULL_H`. **DO NOT move lines 46+** (`HERO_LEFT_MIN_H`, `HERO_MENU_*`, `WATCH_MINIMAP_SIZE`, `LEFT_SPLIT_*` — those stay in hud.py).
2. The 3 render methods moved VERBATIM (`self.`→`hud.`):

| HUD method | hud.py line | → module function | Wrapper preserves |
|---|---|---|---|
| `_render_hero_watch_card_infocard(self, surface, minimap_rect, game_state)` | 1008 | `render_hero_watch_card_infocard(hud, surface, minimap_rect, game_state)` | called by `_render_card_slot` (now inside the module — call `render_hero_watch_card_infocard(hud, ...)` directly there) |
| `_render_card_slot(self, surface, minimap_rect, game_state)` | 1168 | `render_card_slot(hud, surface, minimap_rect, game_state)` | called by `_render_watch_card_chrome` (call `render_card_slot(hud, ...)` directly) |
| `_render_watch_card_chrome(self, surface, minimap_rect, game_state)` | 1186 | `render_watch_card_chrome(hud, surface, minimap_rect, game_state)` | render() at hud.py:1534 |

Inside the moved functions, replace EVERY `self.<x>` with `hud.<x>`: instance state (`hud._card_slot_kind`, `hud._pin_slot`, `hud._left_watch_rect`, `hud._watch_name_sig`, `hud._watch_name_surf`, `hud._info_card`, `hud._watch_card_chevron_rect`, `hud._watch_card_rect`, `hud._watch_card_expanded`, `hud.watch_card_map_rect`, `hud._chat_open_rect`, `hud._watch_stats_sig`, `hud._watch_hp_label_surf`, `hud._watch_xp_label_surf`, `hud._watch_lv_label_surf`, `hud._watch_mana_label_surf`, `hud._chat_visible`, `hud._button_tex_normal`, `hud._button_slice_border`, `hud._watch_card_chat_rect`, `hud._chat_panel`, `hud._chat_close_rect`, `hud.font_tiny`) AND helper-method calls that STAY on HUD (`hud._effective_watch_card_h(...)`, `hud._watch_card_body_split(...)`, `hud._watch_chat_band_rect(...)`). The internal cross-calls between the 3 moved methods become direct module calls: in `render_card_slot` call `render_hero_watch_card_infocard(hud, ...)`; in `render_watch_card_chrome` call `render_card_slot(hud, ...)`. `WATCH_CARD_HEADER_H` is now a module-local constant (no `hud.` prefix).

3. In hud.py, REPLACE the constant block (35–45) with a re-import from the new module (so the names remain module attributes of hud — preserving `from game.ui.hud import WATCH_CARD_*` and the bare-name references in the staying layout helpers):
```python
from game.ui.hud_watch_card import (
    WATCH_CARD_HEADER_H,
    WATCH_CARD_MAP_H,
    WATCH_CARD_STATS_H,
    WATCH_CARD_STATS_COMPACT_H,
    WATCH_CARD_CHAT_H,
    WATCH_CARD_FULL_H_WITH_CHAT,
    WATCH_CARD_FULL_H_NO_CHAT,
    WATCH_CARD_FULL_H,
)
```
4. In hud.py, REPLACE the 3 render-method bodies with delegating wrappers (keep EXACT names+signatures), e.g.:
```python
def _render_watch_card_chrome(self, surface: pygame.Surface, minimap_rect: pygame.Rect, game_state: dict) -> None:
    from game.ui import hud_watch_card
    return hud_watch_card.render_watch_card_chrome(self, surface, minimap_rect, game_state)
```
(`_render_card_slot` and `_render_hero_watch_card_infocard` get the analogous wrappers — they keep working for any internal/legacy reference, though the module now cross-calls directly.)

**STAYS on HUD** (DO NOT move): all the watch-card STATE (set in __init__ — `_pin_slot` :256, `_info_card` :317, `_chat_panel` :239, the `_watch_*` caches, `_button_*` :121/125, fonts), and the LAYOUT HELPERS `_desired_watch_card_expanded_h` (:419), `_effective_watch_card_h` (:427), `_watch_card_body_split` (:443), `_watch_chat_band_rect` (:458), `effective_card_full_h` (:388) — they reference the WATCH_CARD_* names via hud's globals (the re-import keeps them defined). DO NOT touch the constants at lines 46+.

**OUT:** the layout helpers (stay); messages/input_router (later); any behavior/visual change. **Move VERBATIM.**

## 2. Pattern (WK87–95, verbatim — with one refinement)
`hud_watch_card.py` header:
```python
from __future__ import annotations
from typing import TYPE_CHECKING
import pygame
from game.ui.widgets import HPBar, NineSlice
if TYPE_CHECKING:
    from game.ui.hud import HUD
# ...then the WATCH_CARD_* constants, then the 3 functions.
```
**Refinement vs WK93–95:** here hud.py imports the new module AT TOP LEVEL (for the constant re-export) — that's the normal/acyclic direction (hud → hud_watch_card). The new module must STILL have NO top-level import of `game.ui.hud` (it reaches HUD only via the `hud` param + TYPE_CHECKING). So the dependency is one-directional and acyclic. Verify fresh import BOTH orders. (verified: the 3 methods use only `pygame`, `HPBar`, `NineSlice`, `WATCH_CARD_HEADER_H` as non-`hud.` deps; collaborators like `_info_card`/`_chat_panel` are reached as `hud._info_card` etc. — no class import needed.)

## 3. Definition of Done
- **A.** `pytest -q` all pass (baseline **966 passed / 4 skipped / 0 failed** at WK95 close; WK96 adds the new seam/behavior test → expect ~975+ passed). **`tests/test_wk52_watch_card.py` MUST still pass** (it imports the WATCH_CARD_* constants from hud + calls `hud._effective_watch_card_h`).
- **B.** `python tools/determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`.
- **D.** `python tools/qa_smoke.py --quick` green.
- **E.** the 3 fns + the WATCH_CARD_* constants live in `game/ui/hud_watch_card.py`; HUD keeps the 3 wrapper names+signatures; hud.py re-imports+re-exports the constants (so `from game.ui.hud import WATCH_CARD_HEADER_H` etc. still resolve); render() call site (hud.py:1534) unchanged; watch-card state + layout helpers stay on HUD; hud.py smaller (~1901 → ~1715); **no import cycle** (new module has NO top-level `game.ui.hud` import; both fresh-interpreter import orders succeed); ZERO `self.` in the new module.
- **F.** BEFORE/AFTER pygame screenshots — `base_overview` + `ui_panels` — visually identical. **The `ui_panels_hero` variant SHOWS the watch card (pinned hero) — its before/after MUST match** (header, map slot, HP/XP/Lvl rows + bars, Chat button, chat band). Report the watch-card region specifically.
- **G.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 08 UX/UI):** create `hud_watch_card.py` (constants + 3 fns), re-import constants into hud.py, add 3 wrappers. Run full suite (confirm test_wk52 green) + digest + determinism + qa_smoke. Before/after pygame screenshots (base_overview + ui_panels; call out ui_panels_hero). Verify ZERO `self.` in new module + new module has no top-level hud import + both import orders. Update own log. **DO NOT COMMIT.**
- **W2 (Agent 11 QA):** seam test `tests/test_wk96_hud_watch_card.py` — assert: (1) 3 fns exist in `hud_watch_card` with `hud`-first signature + the 8 WATCH_CARD_* constants exist there with the expected int values; (2) 3 HUD wrappers exist and delegate (monkeypatch + assert); (3) `from game.ui.hud import WATCH_CARD_HEADER_H` (and the others) still works AND equals `hud_watch_card.WATCH_CARD_HEADER_H` (re-export integrity); (4) AST guard: `hud_watch_card.py` has NO module-top `import game.ui.hud`; (5) behavior: construct a headless HUD, set `_pin_slot.hero_id` + a `hero_profiles_by_id` entry with a duck-typed profile (`vitals` w/ hp/max_hp, `progression` w/ xp/xp_to_level, `identity` w/ level), set `_watch_card_expanded=True`, then call `hud._render_watch_card_chrome(surface, minimap_rect, game_state)` on a real Surface — assert no exception AND `hud._watch_card_rect` got set (the card drew). Also test the `hero_id is None` early-out path. Run full DoD A–G, independently view before/after (esp. ui_panels_hero). Update own log. **DO NOT COMMIT.**

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Constant re-export breaks `test_wk52_watch_card.py` import or the staying layout helpers' bare-name refs | Med | hud.py re-imports all 8 WATCH_CARD_* from the new module at top; W2 asserts `from game.ui.hud import WATCH_CARD_HEADER_H` works + equals the new module's value; full suite includes test_wk52 |
| A `self.X` missed in the sweep (~25 state fields + 3 helper calls) → AttributeError or wrong render | Med | grep new module for `self.` (MUST be ZERO); W2 behavior test renders the full card with a pinned hero+profile (exercises stats + chat-button + chat-band paths) |
| Watch card renders wrong/missing (visual regression) | Med | move VERBATIM; ui_panels_hero before/after MUST match the watch-card region (header/map/HP-XP-Lvl/bars/Chat button) |
| Import cycle / wrong direction | Low-Med | new module has NO top-level hud import (reaches HUD via param); hud→hud_watch_card top-level is acyclic; verify BOTH fresh import orders |

## 6. Success
The pinned-hero watch card + its layout constants live in `game/ui/hud_watch_card.py` behind 3 delegating wrappers with the constants re-exported from hud, the card renders identically — proven by 966+ green tests (incl. test_wk52 + a new behavior test rendering the card through the moved path), clean determinism guard, unchanged digest, identical before/after `ui_panels_hero` screenshots, and a verified no-cycle. hud.py drops ~185 LOC (fourth slice; 2477→~1715 cumulative).

## 7. Kickoff
Roster: 08 UX/UI (W1), 11 QA (verify + DoD + screenshot review + behavior test, W2), 09 (consult). Order: 08 W1 → PM gate (suite incl test_wk52 + digest + ui_panels_hero screenshots + re-export check + no-cycle) → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE VERBATIM MOVE; the new module OWNS the WATCH_CARD_* constants + hud RE-EXPORTS them; keep the 3 wrapper names + ALL state + the layout helpers on HUD; new module has NO top-level hud import; ZERO `self.` in the new module; ui_panels_hero before/after MUST match; own log; DO NOT COMMIT.
Follow-ups (REMAINING roadmap): WK97 messages (`add_message`/`render_messages`); input_router (`handle_click` + sidebar split pointer handlers + menu-scroll) — likely the last big hud.py clusters; then `ursina_terrain_fog_collab`(1783)/`ursina_app`(1525) splits; Move 9 (SystemRunner — RISKY); world.py fog; context_builder/direct_prompt_validator; ai/vocab.py + TaskRouter (Move 12); config package; clusters 3/4; Round E audit; the 21-file WK34-zombie-type purge.
