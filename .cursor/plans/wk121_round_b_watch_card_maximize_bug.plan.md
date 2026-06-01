# WK121 Round B — fix: hero (watch) card top-bar click maximizes over the whole left sidebar

**Author:** Agent 01 (Executive Producer / PM)
**Status:** PLANNED → in execution
**Sprint key (PM hub):** `wk121_round_b_watch_card_maximize_bug`
**Version target:** patch (UI bug fix)
**Verification class:** PYGAME HUD — **SCREENSHOT-VERIFIED** (reproduce the click, before/after captures, visual verdict; NOT the ursina deferred exception). Alignment/layering checked first.
**Model for all sub-agents:** `claude-opus-4-8` (opus)

---

## 0. The bug (Sovereign-reported, while testing WK115)

> "clicking the top bar of the hero card maximizes it across the entire left sidebar,
> getting rid of any other menus (building/hero) that were there. It either shouldn't do
> this (preferred) or go back to a smaller window once the top bar is clicked again."

**Desired outcome (in priority order):**
1. **PREFERRED:** clicking the hero/watch card's top bar should NOT maximize it over the
   whole sidebar / should NOT hide the building/hero menu that was open.
2. Acceptable fallback: a second click reliably restores the smaller window.

So the FIX must guarantee: **clicking the watch-card header never evicts or hides the
main building/hero menu, and the card never takes over the entire left sidebar when
another menu is present.** A reliable collapse-toggle is the minimum; not maximizing over
the other menu is the goal.

---

## 1. PM grounding (what's known — start here, then REPRODUCE)

- The watch card's header has a small 14×14 "X"-glyph control drawn by
  `game/ui/info_card.py::draw_shell` (L95–102, `header_close_x=True`) and returned as the
  `control_hit` rect → stored as `hud._watch_card_chevron_rect`.
- Clicking it routes through `HUD.handle_click` (`game/ui/hud.py:1144–1148`) which does
  `self._watch_card_expanded = not self._watch_card_expanded; return "watch_card_chevron_toggle"`.
- The action handler `game/input/mouse.py:119–120` is a no-op (`return`) — it does NOT
  deselect the hero/building, so the toggle itself is clean.
- The left-column layout is `game/ui/hud_left_layout.py::layout_left_column_segments`.
  In the `main_open and watch_open` branch the split uses `_left_split_fracs` (main/watch);
  WK115 added a chat-grow that bumps `watch_h` to `_desired_watch_card_expanded_h()` ONLY
  when `_chat_visible and _watch_card_expanded`.
- The X glyph LOOKS like a close button but actually TOGGLES expand/maximize — a likely
  UX confusion contributing to the report.

**This is a CLICK-DRIVEN layout effect that static screenshot scenarios do not reproduce
(they set `_watch_card_expanded` programmatically). Agent 08 MUST reproduce the actual
click first** (see §2) to pin the exact mechanism before fixing.

---

## 2. Wave 1 — Agent 08 (UX/UI): REPRODUCE → DIAGNOSE → FIX → VERIFY

### 2a. Reproduce (headless) — capture BEFORE/AFTER the click
Write a throwaway repro (or a temporary test) that builds the real HUD state the Sovereign
hit: a **building OR hero selected (main menu open)** AND **a hero pinned (watch card
present, collapsed)**, at 1920×1080. Model the setup on `tools/screenshot_scenarios.py`'s
`_apply_sidebar_pin_split` / `_apply_select_hero` hooks (they already construct an engine +
HUD + heroes + pin slot). Then:
1. Render once; record `hud._left_main_rect`, `hud._left_watch_rect`, `_watch_card_expanded`,
   and the selected_* state; capture `before.png`.
2. Get `hud._watch_card_chevron_rect` (the X); call `hud.handle_click(chevron.center, game_state)`;
   render again; record the same fields; capture `after.png`.
3. Report the DELTA: did `_left_main_rect` shrink/vanish? did the watch card become
   full-column? did anything get deselected? Read both PNGs and describe what visibly changed.

This pins the EXACT mechanism. Likely candidates (confirm which): (a) the expanded watch
segment grows to (near) full column, squeezing `main` to `HERO_LEFT_MIN_H` or hiding it;
(b) a layout path makes `main_open` effectively lose its space; (c) the WK115 chat-grow or
a solo-watch path triggers unexpectedly.

### 2b. Fix (per the diagnosis; satisfy §0's preferred outcome)
Implement the fix the diagnosis points to, choosing the option that best matches "clicking
the top bar should NOT maximize over / hide the other menu." Guidance:
- **If** expanding the watch card squeezes/hides the main menu: bound the watch segment so
  that when `main_open and watch_open`, the main (building/hero) menu ALWAYS keeps at least
  its content height (or a sane minimum well above `HERO_LEFT_MIN_H`), and the watch card
  expands only within its own segment — never full-column while a main menu is present.
  The two must visibly coexist (like the existing `ui_panels_sidebar_split` shot).
- **If** the toggle does not reliably collapse back (e.g. the X rect isn't hittable when
  expanded, or its position shifts): ensure `_watch_card_chevron_rect` is re-derived each
  frame at the expanded header position and a second click on it reliably sets
  `_watch_card_expanded = False`.
- Prefer the minimal change that makes clicking the header **non-destructive to the other
  menu**. Do NOT remove the ability to view the pinned hero; do NOT change unrelated layout.
- Keep the WK115 fixes intact (solo card content-sizing; chat-grow only on `_chat_visible`).

### 2c. Verify (MANDATORY screenshot loop)
- Re-run the §2a repro AFTER the fix: clicking the X must NOT hide the main menu; capture
  `after_fixed.png`; clicking again must restore the prior size; capture `toggled_back.png`.
  Read all PNGs; give a per-image verdict (alignment/layering first: main menu still
  present + correctly placed; watch card bounded; no overlap).
- Capture the standard HUD scenarios to confirm no regression:
  `python tools/capture_screenshots.py --scenario ui_panels --out docs/screenshots/wk121_after --seed 3 --size 1920x1080`
  `python tools/capture_screenshots.py --scenario wk52_pin_alerts --out docs/screenshots/wk121_after --seed 3 --size 1920x1080`
  Read `ui_panels_hero`, `ui_panels_sidebar_split`, `ui_panels_pinned_chat`,
  `wk52_watch_card_expanded`, `wk52_watch_card_minimized` and verdict each.
- Add a regression test `tests/test_wk121_watch_card_no_evict.py` that drives the click
  headlessly (the §2a repro, hardened) and asserts: after the chevron toggle with a main
  selection open, `hud._left_main_rect is not None and hud._left_main_rect.height >=`
  the main panel's minimum (it is NOT hidden), and a second toggle returns
  `_watch_card_expanded` to its prior value. (Use the scenario setup helpers; skip-guard
  any piece that needs assets, but the core layout assertion must run.)
- DO NOT COMMIT. Update the Agent 08 log with the diagnosis + per-image verdicts + test.

---

## 3. Wave 2 — Agent 11 (QA): full DoD + independent screenshot review

1. `python -m pytest -q` → 0 failed (record counts).
2. `python tools/determinism_guard.py` → clean PASS.
3. `python -m pytest tests/test_wk67_ai_boundary.py::test_ai_decision_digest_is_stable -q` → digest byte-identical `b73961340c…d148ded` (presentation-only change).
4. `python tools/qa_smoke.py --quick` → DONE: PASS.
5. `python -m pytest tests/test_wk121_watch_card_no_evict.py tests/test_wk115_left_menu_polish.py tests/test_wk52_watch_card.py tests/test_wk96_hud_watch_card.py tests/test_wk98_hud_watch_geom.py tests/test_wk99_hud_left_layout.py tests/test_wk100_hud_layout_orchestration.py tests/test_wk101_hud_hero_menu_layout.py -q` → all green (the watch/left-layout suite must not regress).
6. Independent broad screenshot review: re-capture the §2c scenarios, Read each, verdict alignment/layering first; confirm the main menu coexists with the watch card and nothing is hidden. DO NOT COMMIT.

---

## 4. Definition of done (PM gate)

- [ ] Reproduction confirmed the mechanism (before/after captures + field deltas in the Agent 08 log).
- [ ] Clicking the watch-card header no longer hides/evicts the building/hero menu; the card never takes the full sidebar while a main menu is present; a second click restores the prior size.
- [ ] `tests/test_wk121_watch_card_no_evict.py` green; the watch/left-layout suite (WK52/96/98/99/100/101 + WK115) green.
- [ ] full `pytest -q` 0 failed; determinism clean; WK67 digest byte-identical; qa_smoke PASS.
- [ ] PM has Read the before/after/toggled-back PNGs and confirmed the fix visually.
- [ ] Agent 08 + 11 logs updated. PM commits (scoped add of touched `game/ui/*` [+ `info_card.py`/`hud.py`/`hud_left_layout.py` as needed], the new test, plan + PM hub + agent logs) + pushes. Screenshot PNGs stay gitignored.

## 5. Note
This is a follow-up to the WK115 left-menu polish (Sovereign found it while testing). It is
NOT a roadmap item — it is live user-reported UX feedback, prioritized ahead of the
remaining optional/deferred items. After WK121, the deferred Move-12 propose() re-arch +
the two tiny optional items remain (see `project_audit_roadmap_complete_wk120` memory).
