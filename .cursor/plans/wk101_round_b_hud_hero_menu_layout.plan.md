# WK101 Sprint Plan — Round B-18: fold hero-menu-chat-popup layout into hud_left_layout.py + relocate HERO_MENU_* to hud_layout.py — ninth hud.py slice

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; the 3 hero-menu-chat-popup layout helpers moved from hud.py into the existing `game/ui/hud_left_layout.py`; the 4 `HERO_MENU_*` constants relocated to `hud_layout.py`; the in-column hero+chat split renders identically.
**Predecessors:** WK93–97 (hud.py slices), WK98 (watch-card geometry → hud_watch_card), WK99 (left-column split → hud_left_layout), WK100 (layout orchestration → hud_left_layout). **Roadmap:** Round B — hud.py (1258 LOC) split. Ninth slice. Chosen by the WK101 parallel grounding sweep (ranked #1: most cohesive, lowest-risk, coupling-reducing).

## 0. TL;DR
WK101 folds the **hero-menu-chat-popup layout** — `_should_render_hero_menu_chat_popup` (when a hero is selected with an active chat that is NOT the pinned watch-card chat, show an in-column chat band), `_hero_menu_chat_desired_h` (the chat band's reserved height), and `_hero_menu_chat_split_rects` (split the left column into a shrunk hero sheet + a readable chat band) — into the existing `game/ui/hud_left_layout.py`. This is the natural home: `layout_left_column_segments` (already in hud_left_layout) ALREADY calls `hud._should_render_hero_menu_chat_popup` across the module boundary (hud_left_layout.py:92), so the fold turns a cross-module wrapper hop into a same-module call and consolidates ALL left-column layout in one module — **coupling decreases**. The 4 `HERO_MENU_*` constants relocate to `hud_layout.py` (same WK98/99 pattern), hud.py re-imports + re-exports them. ~45 LOC leaves hud.py (1258 → ~1213). The WK67 digest (headless, AI-only) is unaffected. PM writes no code.

## 1. Scope

### 1a. Relocate 4 constants (hud.py → hud_layout.py)
Move OUT of hud.py (lines 53–56) and INTO `game/ui/hud_layout.py` (next to `HERO_LEFT_MIN_H`/`LEFT_SPLIT_*`, with a one-line comment):
```python
HERO_MENU_CHAT_GAP = 4
HERO_MENU_CHAT_MIN_H = 152
HERO_MENU_CHAT_PREFERRED_H = 220
HERO_MENU_HERO_MIN_H = 120
```
Then in hud.py ADD all 4 to the existing `from game.ui.hud_layout import (...)` block so `from game.ui.hud import HERO_MENU_CHAT_MIN_H` / `HERO_MENU_HERO_MIN_H` keep resolving for **`tests/test_wk61_r9_hero_chat_readable_layout.py:10-11`** (the two load-bearing re-exports). Re-import all 4 (GAP/PREFERRED_H have no external importer today, but re-import them so hud.py stays self-consistent and future-proof).
**Do NOT touch `WATCH_MINIMAP_SIZE` (hud.py:57)** — grounding confirmed it is DEAD (zero consumers repo-wide). Leaving it untouched keeps this a clean verbatim move; flag it for a separate de-slop deletion sprint.

### 1b. Move 3 methods (hud.py → hud_left_layout.py), VERBATIM (replace `self.`→`hud.`), keep a 1-line delegating wrapper on HUD for each (EXACT name+signature):

| HUD method | hud.py line | → module function | Caller(s) the wrapper preserves |
|---|---|---|---|
| `_should_render_hero_menu_chat_popup(self, game_state)` | 717 | `should_render_hero_menu_chat_popup(hud, game_state)` | `hud_left_layout.layout_left_column_segments` (hud_left_layout.py:92, **already cross-module** — stays `hud._should_...`, now same-module via wrapper); `render()` (hud.py:851, 985); `tests/test_wk61_r4_ui_regressions.py:145` |
| `_hero_menu_chat_desired_h(self, left_h)` | 730 | `hero_menu_chat_desired_h(hud, left_h)` | internal: called by `_hero_menu_chat_split_rects` (hud.py:747) |
| `_hero_menu_chat_split_rects(self, left)` | 741 | `hero_menu_chat_split_rects(hud, left)` | `render()` (hud.py:852); `tests/test_wk61_r4:146`; `tests/test_wk61_r9:36` |

**Mechanical move rule — EVERY `self.<x>` becomes `hud.<x>`. Nothing else changes.** State/methods reached via `hud.`: `hud._chat_panel` (ChatPanel instance — accessed via attr, NOT imported), `hud._uses_pinned_watch_card_chat(hid)` (STAYS on HUD — see below), and the inter-helper call `hud._hero_menu_chat_desired_h(left.height)` (→ wrapper → same module; correct + mechanical, matches how layout_left_column_segments already calls `hud._should_render_hero_menu_chat_popup`). Constants referenced BARE: `HERO_MENU_CHAT_GAP`, `HERO_MENU_CHAT_MIN_H`, `HERO_MENU_CHAT_PREFERRED_H`, `HERO_MENU_HERO_MIN_H`, `HERO_LEFT_MIN_H` — all imported at module top (see §2). Copy docstrings verbatim.

**STAYS on HUD** (DO NOT move):
- **`_uses_pinned_watch_card_chat` (hud.py:712)** — a watch-card/pin concern (reads `_pin_slot`/`_chat_visible`/`_watch_card_expanded`), NOT menu layout. The moved popup predicate calls it as `hud._uses_pinned_watch_card_chat(hid)`.
- **The `_hero_menu_hero_rect`/`_hero_menu_chat_rect` STATE ASSIGNMENTS** — `_hero_menu_chat_split_rects` only RETURNS `(hero_rect, chat_rect)`; the assignment to `self._hero_menu_hero_rect`/`self._hero_menu_chat_rect` happens in `render()` (hud.py:848/849/855/856) and STAYS there. Downstream readers (hud.py:866/867/969/985/1087/1090/1139 incl. getattr reads) + the wk61_r9 height asserts depend on render() doing the assignment. The moved method must NOT assign state.
- `render()`, `__init__` state (`_hero_menu_chat_rect`/`_hero_menu_hero_rect` at :316/317), the `_chat_panel`. **OUT.**

## 2. Pattern (WK99/100, verbatim) — what to ADD to hud_left_layout.py
hud_left_layout.py already imports from hud_layout (currently `HERO_LEFT_MIN_H, LEFT_COL_W, LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO, LEFT_SPLIT_HANDLE_H, LEFT_SPLIT_HANDLE_HIT_H, RADAR_MINIMAP_H`). ADD the 4 `HERO_MENU_*` names to that SAME import block:
```python
from game.ui.hud_layout import (
    HERO_LEFT_MIN_H,
    HERO_MENU_CHAT_GAP,
    HERO_MENU_CHAT_MIN_H,
    HERO_MENU_CHAT_PREFERRED_H,
    HERO_MENU_HERO_MIN_H,
    LEFT_COL_W,
    LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO,
    LEFT_SPLIT_HANDLE_H,
    LEFT_SPLIT_HANDLE_HIT_H,
    RADAR_MINIMAP_H,
)
```
No other new imports (the 3 methods use only pygame [already imported] + hud state + those constants). Then append the 3 functions at the END of the module. The module already has `from __future__ import annotations`, `if TYPE_CHECKING: from game.ui.hud import HUD`, and NO top-level `import game.ui.hud` — keep it that way.
**Cycle proof:** hud_layout is a leaf (pygame+dataclasses only); adding 4 constant defs there changes nothing. hud_left_layout still imports only leaves + TYPE_CHECKING HUD. hud.py imports hud_left_layout LAZILY in the wrappers. → no cycle. Verify BOTH fresh import orders + the WK99/WK100 AST no-cycle guards stay green.

### Wrapper form on HUD (replace each moved method body; keep EXACT def line):
```python
def _should_render_hero_menu_chat_popup(self, game_state: dict) -> bool:
    from game.ui import hud_left_layout
    return hud_left_layout.should_render_hero_menu_chat_popup(self, game_state)

def _hero_menu_chat_desired_h(self, left_h: int) -> int:
    from game.ui import hud_left_layout
    return hud_left_layout.hero_menu_chat_desired_h(self, left_h)

def _hero_menu_chat_split_rects(self, left: pygame.Rect) -> tuple[pygame.Rect, pygame.Rect] | None:
    from game.ui import hud_left_layout
    return hud_left_layout.hero_menu_chat_split_rects(self, left)
```
The cross-module call at `hud_left_layout.py:92` (`hud._should_render_hero_menu_chat_popup(game_state or {})`) is UNCHANGED — it now calls the HUD wrapper which re-enters this same module (one harmless hop; keep it wrapper-uniform). Move VERBATIM.

## 3. Definition of Done
- **A.** `python -m pytest -q` all pass (baseline **1135 passed / 4 skipped / 0 failed** at WK100 close; +new test → expect ~1145+).
- **B.** `python tools/determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`.
- **D.** `python tools/qa_smoke.py --quick` green.
- **E.** the 3 fns live in `game/ui/hud_left_layout.py`; the 4 `HERO_MENU_*` live in `hud_layout.py` + removed from hud.py's own defs + re-imported by hud (so `from game.ui.hud import HERO_MENU_CHAT_MIN_H`/`HERO_MENU_HERO_MIN_H` work); HUD keeps the 3 wrapper names+signatures; `_uses_pinned_watch_card_chat` + the rect-state ASSIGNMENTS stay on HUD; call sites (hud.py 747/851/852/985; hud_left_layout.py:92; test_wk61_r4 145/146; test_wk61_r9:36) UNCHANGED; `WATCH_MINIMAP_SIZE` untouched at hud.py:57; hud.py smaller (~1258 → ~1213); **no import cycle** (both fresh orders); ZERO `self.` in the 3 moved fns.
- **F.** BEFORE/AFTER pygame screenshots — scenario **`wk61_hero_menu_chat`** at BOTH **1920x1080 AND 1024x576** (the split clamps depend on left-column height; one resolution can hide a clamp-path regression). The in-column split (upper hero sheet + lower readable chat band, with the divider) MUST be pixel-identical. Apply the alignment-first check: hero/chat split not overlapping, left edges flush, divider at the same y. Report the split region specifically.
- **G.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 08 UX/UI):** (1) relocate the 4 `HERO_MENU_*` to hud_layout.py + remove from hud.py + add all 4 to hud.py's hud_layout import. (2) add the 4 names to hud_left_layout.py's hud_layout import block + append the 3 fns (verbatim `self.`→`hud.`). (3) replace the 3 hud.py method bodies with wrappers. Run full suite + digest + determinism + qa_smoke. Before/after pygame screenshots (`wk61_hero_menu_chat` at BOTH resolutions). Verify ZERO `self.` in the 3 new fns + no top-level hud import in hud_left_layout + both import orders + the 2 re-exports resolve. Update own log. **DO NOT COMMIT.**
- **W2 (Agent 11 QA):** seam test `tests/test_wk101_hud_hero_menu_layout.py` — assert: (1) the 3 fns exist in hud_left_layout with the `hud`-first signature (inspect.signature). (2) `HERO_MENU_CHAT_GAP==4`, `HERO_MENU_CHAT_MIN_H==152`, `HERO_MENU_CHAT_PREFERRED_H==220`, `HERO_MENU_HERO_MIN_H==120` importable from BOTH `game.ui.hud_layout` AND `game.ui.hud` (re-export); read hud_layout.py source: all 4 defined col-0; read hud.py source: NO col-0 `HERO_MENU_*=` def (only import); assert `WATCH_MINIMAP_SIZE` still defined in hud.py (untouched). (3) the 3 HUD wrappers exist and delegate (monkeypatch each module fn to a sentinel, call wrapper, assert fired). (4) AST guard: hud_left_layout.py has no module-top `game.ui.hud` import (TYPE_CHECKING `from game.ui.hud import HUD` permitted) + fresh-subprocess both import orders returncode 0. (5) behavior (headless SDL dummy + pygame.init): build `HUD(1920,1080)`; (a) with `game_state={}` assert `hud._should_render_hero_menu_chat_popup({})` is False (no selected_hero/active chat) [no exception]; (b) `assert isinstance(hud._hero_menu_chat_desired_h(600), int)` and `hud._hero_menu_chat_desired_h(0)==0`; (c) `r = hud._hero_menu_chat_split_rects(pygame.Rect(0,48,224,700))` → assert `r is None or (len(r)==2 and all isinstance Rect)`, and the returned hero_rect.height >= HERO_MENU_HERO_MIN_H + chat_rect.height >= HERO_MENU_CHAT_MIN_H when not None (mirror test_wk61_r9). Run full DoD A–G, independently view before/after screenshots at BOTH resolutions. Update own log. **DO NOT COMMIT.**

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Re-export dropped → `from game.ui.hud import HERO_MENU_CHAT_MIN_H/HERO_MENU_HERO_MIN_H` breaks test_wk61_r9 at import time | Low-Med | hud.py re-imports all 4 from hud_layout; W2 asserts both import paths == literals; test_wk61_r9 is the live guard |
| Accidentally moving the rect-state ASSIGNMENT (split_rects starts assigning `_hero_menu_*_rect`) → downstream readers + wk61_r9 height asserts diverge | Med | the moved method ONLY returns; assignments stay in render() (848-856); W1 verbatim move + W2 split_rects behavior test + test_wk61_r9 catch it |
| `_uses_pinned_watch_card_chat` moved by mistake | Low | plan says STAYS on HUD; the popup predicate calls it as `hud._uses_pinned_watch_card_chat`; grep confirms it's a watch-card concern |
| Import cycle | Very Low | hud_layout leaf; hud_left_layout imports only leaves + TYPE_CHECKING HUD; WK99/WK100 AST guards already enforce this; verify both orders |
| Clamp-path regression hidden at one resolution | Low-Med | DoD F mandates BOTH 1920x1080 + 1024x576 captures (split clamps depend on left_h) |
| Touching dead `WATCH_MINIMAP_SIZE` | Low | plan: DO NOT touch line 57; W2 asserts it's still present |

## 6. Success
The hero-menu-chat-popup layout lives in `game/ui/hud_left_layout.py` (consolidating ALL left-column layout in one module — coupling reduced) behind 3 delegating wrappers, the 4 `HERO_MENU_*` live in `hud_layout.py` (re-exported by hud) — proven by 1135+ green tests (incl. test_wk61_r4 + test_wk61_r9 driving the popup predicate + split through the wrappers + a new behavior test), clean determinism guard, unchanged digest, identical before/after `wk61_hero_menu_chat` screenshots at two resolutions, and a verified no-cycle. hud.py drops ~45 LOC (ninth slice; 2477→~1213 cumulative).

## 7. Kickoff
Roster: 08 UX/UI (W1), 11 QA (W2), 09 (consult). Order: 08 W1 → PM gate → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE VERBATIM MOVE (self.→hud.); relocate the 4 `HERO_MENU_*` to hud_layout.py (re-exported by hud) — do NOT touch dead `WATCH_MINIMAP_SIZE`; keep the 3 wrapper names + `_uses_pinned_watch_card_chat` + the rect-state ASSIGNMENTS on HUD (split_rects only RETURNS); TYPE_CHECKING-only HUD import; ZERO `self.` in the 3 moved fns; before/after pygame `wk61_hero_menu_chat` at BOTH resolutions MUST match; own log; DO NOT COMMIT.
Follow-ups (REMAINING roadmap, from the WK101 grounding sweep, in order): **WK102** = messages → NEW `game/ui/hud_messages.py` (`add_message`/`update`/`render_messages`; preserve `add_message` exactly — widest blast radius, 56 refs/17 files + getattr in pin_alert_watcher; keep `update` name verbatim for engine.py:819; event-driven capture harness). **WK103** = input-router/menu-scroll → NEW `game/ui/hud_menu_scroll.py` (`is_mouse_over_menu`/`scroll_active_menu`/`handle_menu_scroll` as ONE unit; exact names for input_handler.py:127, ursina_app.py:830). Then the **ursina god-files** (NEW verification model — ursina screenshots + runtime-import smoke, NOT the pygame digest): FOG/C (`sync_dynamic_trees`+`sync_log_stacks`+`_InstancedTreeStub` → ursina_terrain_growth_sync.py, ~258 LOC) first to establish the rhythm, then FOG/A+FOG/B (move as cohesive units), then ursina_app APP/C (env-gated debug/FPS scaffolding). DEFER: `handle_click` (redesign, not a pure move — gate behind watch-card MiniMapProjection encapsulation) and ursina_app APP/A camera + APP/B input hook (closures/bound-method/monkeypatch — needs a non-wrapper strategy). De-slop: delete dead `WATCH_MINIMAP_SIZE`.
