# WK102 Sprint Plan — Round B-19: extract hud_messages.py (status-message log) — tenth hud.py slice

**Author:** Agent 01 (PM) · **Date:** 2026-05-31 · **Goal:** all tests pass; the status-message subsystem (`add_message`/`update`/`render_messages`) extracted from hud.py into a NEW `game/ui/hud_messages.py`; the message log renders identically.
**Predecessors:** WK93–101 hud.py slices. **Roadmap:** Round B — hud.py (1226 LOC) split. Tenth slice. Chosen by the WK101 grounding workflow (ranked #2).

## 0. TL;DR
WK102 extracts the **status-message log** — `add_message` (append a `{text,color,time}` dict to `hud.messages`, FIFO cap 5), `update` (prune messages older than `message_duration`=3000ms), `render_messages` (draw the message stack at `top_bar_height+10`, x=10 or `left_rect.right+10`) — a tiny (~15 LOC), self-contained subsystem — into a NEW `game/ui/hud_messages.py` as functions taking the HUD (`hud`), behind 1-line delegating wrappers on HUD. ALL message STATE stays on HUD. The only real import is `pygame` + `config.COLOR_WHITE` (the `add_message` default arg). This is the same low-risk new-module pattern as hud_radar/hud_toasts/hud_summaries. The catch is HANDLING-care, not risk: (a) `add_message` has the WIDEST external blast radius of any hud.py method (~56 refs / 17 files incl. a getattr reach in pin_alert_watcher.py) — its wrapper name+signature+`COLOR_WHITE` default are load-bearing; (b) `update` is generically named but its ENTIRE body is message-pruning — its wrapper MUST keep the exact name `update` because `game/engine.py:819` calls `self.hud.update()` every frame. The WK67 digest (headless, AI-only) is unaffected. PM writes no code.

## 1. Scope
**IN:** create `game/ui/hud_messages.py`; move VERBATIM (replace `self.`→`hud.`) these 3 methods, keeping a 1-line delegating wrapper on HUD for each (EXACT name+signature):

| HUD method | hud.py line | → module function | Caller(s) the wrapper preserves |
|---|---|---|---|
| `add_message(self, text, color=COLOR_WHITE)` | 696 | `add_message(hud, text, color=COLOR_WHITE)` | **WIDE external blast radius (~56 refs/17 files):** engine.py:305, console.py (×13), engine_facades/actions.py (×9), engine_facades/camera_display.py:106/109, input/placement.py (×3), input/keyboard.py:194, cleanup_manager.py:53, graphics/ursina_app.py (×7), sim/playtest_quick_start.py:100(hasattr)/101, **ui/pin_alert_watcher.py:24(getattr)/101**, tests. Wrapper name+signature+`COLOR_WHITE` default MUST stay EXACT. |
| `update(self)` | 701 | `update_messages(hud)` | **`game/engine.py:819` calls `self.hud.update()` EVERY FRAME.** The wrapper MUST keep the exact generic name `update`. (Module fn is named `update_messages` for clarity; the HUD wrapper is named `update`.) |
| `render_messages(self, surface, left_rect=None)` | 739 | `render_messages(hud, surface, left_rect=None)` | `render()` (hud.py:~936, internal) |

**Mechanical move rule — EVERY `self.<x>` becomes `hud.<x>`. Nothing else changes.** State reached via `hud.` (ALL stays on HUD): `hud.messages` (set in __init__:254 `[]`), `hud.message_duration` (255 `=3000`), `hud.top_bar_height` (read by render_messages), `hud.font_small` (read by render_messages). `pygame.time.get_ticks()` and `pygame.Surface.blit`/`font.render` are pygame (bare). `COLOR_WHITE` is the imported default arg (bare).

**STAYS on HUD** (DO NOT move): the message STATE (`messages`/`message_duration` in __init__), `top_bar_height`, `font_small`, `render()` (calls `self.render_messages(...)`), and the unrelated `toggle_help`/`toggle_right_panel`/`on_resize` that happen to sit between these methods. **OUT.**

## 2. Pattern (WK94, verbatim) — new module header
`game/ui/hud_messages.py`:
```python
"""HUD status-message log, extracted from game.ui.hud (WK102).

Append/expire/draw the short status messages (e.g. combat-kill notices) shown at
the top of the screen. add_message FIFO-caps at 5; update() prunes entries older
than hud.message_duration (3000ms); render_messages draws the stack at
top_bar_height+10. All message STATE (hud.messages, hud.message_duration) and the
fonts (hud.font_small) live on the HUD instance and are reached here via the ``hud``
argument; HUD keeps 1-line delegating wrappers (exact names: add_message, update,
render_messages -- update() is called every frame by engine.py). Acyclic: hud.py
imports this module lazily inside the wrappers; this module imports only pygame +
config.COLOR_WHITE (config does NOT import game.ui) + HUD under TYPE_CHECKING.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
import pygame
from config import COLOR_WHITE
if TYPE_CHECKING:
    from game.ui.hud import HUD
```
**Cycle proof:** `config` imports no `game.ui` module (verified by the established hud_summaries pattern, which already imports `config.COLOR_WHITE`). The new module imports only pygame + config + TYPE_CHECKING HUD. hud.py imports hud_messages LAZILY in the wrappers. → no cycle. Verify BOTH fresh import orders.

### Wrapper form on HUD (replace each moved method body; keep EXACT def line):
```python
def add_message(self, text: str, color: tuple[int, int, int] = COLOR_WHITE) -> None:
    from game.ui import hud_messages
    return hud_messages.add_message(self, text, color)

def update(self) -> None:
    from game.ui import hud_messages
    return hud_messages.update_messages(self)

def render_messages(self, surface: pygame.Surface, left_rect: pygame.Rect | None = None) -> None:
    from game.ui import hud_messages
    return hud_messages.render_messages(self, surface, left_rect)
```
(`add_message`'s wrapper keeps `color=COLOR_WHITE` default and passes `color` through — `COLOR_WHITE` is already imported at hud.py module top, keep that import.) Move VERBATIM.

## 3. Definition of Done
- **A.** `python -m pytest -q` all pass (baseline **1165 passed / 4 skipped / 0 failed** at WK101 close; +new test → expect ~1175+).
- **B.** `python tools/determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`.
- **D.** `python tools/qa_smoke.py --quick` green.
- **E.** the 3 fns live in `game/ui/hud_messages.py`; HUD keeps the 3 wrapper names+signatures (esp. PUBLIC `add_message` with `COLOR_WHITE` default for the ~56 callers, and `update` for engine.py:819); call sites UNCHANGED (engine.py 305/819; pin_alert_watcher.py 24/101; render() internal; + all the rest); message state + fonts stay on HUD; hud.py smaller (~1226 → ~1211); **no import cycle** (both fresh orders); ZERO `self.` in the 3 moved fns.
- **F.** BEFORE/AFTER pygame screenshots — `base_overview` + `ui_panels` — visually identical. NOTE (document explicitly): messages are EVENT-DRIVEN and auto-expire after 3000ms, so a static idle capture may or may not show one (combat-kill notices like "X slew a Y!" do appear at the top when a kill happened in the last 3s of the sim window). The steady-state captures prove the scene+chrome unchanged; the TARGETED guard is the W2 behavior test that renders messages through the moved path and asserts pixels. If a message IS visible at the top of base_overview/ui_panels before/after, confirm that region matches. Report this coverage caveat.
- **G.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 08 UX/UI):** create `hud_messages.py` (header + 3 fns, verbatim `self.`→`hud.`; module fn for `update` is named `update_messages`); add the 3 wrappers on HUD (wrapper for `update` keeps name `update`). Run full suite + digest + determinism + qa_smoke. Before/after pygame screenshots (base_overview + ui_panels). ADDITIONALLY do an ad-hoc message-render proof: in a throwaway python -c (NOT committed), headless HUD, `hud.add_message("WK102 test A",(100,255,100)); hud.add_message("WK102 test B",(255,180,80))`, render to a Surface via `hud.render_messages(surf)`, save PNG — confirm two colored lines render at top_bar_height+10. Verify ZERO `self.` in the 3 new fns + no top-level hud import in hud_messages + both import orders. Update own log. **DO NOT COMMIT.**
- **W2 (Agent 11 QA):** seam test `tests/test_wk102_hud_messages.py` — assert: (1) the 3 fns exist in hud_messages with the `hud`-first signature (inspect.signature; note the module fn is `update_messages`, not `update`). (2) the 3 HUD wrappers exist and delegate (monkeypatch each module fn to a sentinel, call the wrapper, assert fired — incl. `update`→`update_messages` and the PUBLIC `add_message`). (3) AST guard: hud_messages.py has no module-top `game.ui.hud` import (TYPE_CHECKING `from game.ui.hud import HUD` permitted) + fresh-subprocess both import orders returncode 0. (4) behavior (headless SDL dummy + pygame.init): build `HUD(1920,1080)`; `hud.add_message("hello", (200,50,50))`; assert `len(hud.messages)==1` and `hud.messages[0]["text"]=="hello"` and `hud.messages[0]["color"]==(200,50,50)`; add 6 messages total, assert `len(hud.messages)==5` (FIFO cap); call `hud.add_message("default")` and assert its color == COLOR_WHITE (default arg preserved); render: `surf=pygame.Surface((1920,1080)); surf.fill((0,0,0)); hud.render_messages(surf)` then assert at least one non-black pixel exists in the message band (scan rows top_bar_height+10 .. +10+18*len, x from 10) — proves the moved render path draws; ALSO render with a left_rect (`hud.render_messages(surf, pygame.Rect(0,48,224,400))`) and assert it draws at x≈left_rect.right+10 (no exception). For `update`: set a message's `time` to `pygame.time.get_ticks()-5000` (older than 3000ms), call `hud.update()`, assert it was pruned; add a fresh one, call `hud.update()`, assert it survives. Run full DoD A–G, independently view before/after screenshots (note the event-driven caveat). Update own log. **DO NOT COMMIT.**

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| `update` wrapper renamed/dropped → engine.py:819 `self.hud.update()` breaks every frame (messages never prune; or AttributeError) | Med | keep the HUD wrapper named EXACTLY `update`; W2 delegation test patches `update_messages` + calls `hud.update()`; W2 prune behavior test; full suite (engine tests) catches it |
| `add_message` wrapper name/signature/`COLOR_WHITE` default drift → breaks 56 callers incl pin_alert_watcher getattr | Low-Med | keep exact name+signature+default; W2 asserts default color == COLOR_WHITE + FIFO cap; the 56 callers + full suite are the live guard |
| Import cycle (via config) | Very Low | config imports no game.ui (hud_summaries already imports config.COLOR_WHITE acyclically); verify both orders |
| A `self.X` missed (messages/message_duration/top_bar_height/font_small) | Low | grep new module for `self.` (MUST be ZERO); W2 add/prune/render behavior test |
| Weak steady-state screenshot coverage (messages event-driven, auto-expire) | Med | documented in DoD F; the W2 pixel-asserting render test + W1 ad-hoc PNG are the real guards; before/after base_overview proves chrome unchanged |

## 6. Success
The status-message log lives in `game/ui/hud_messages.py` behind 3 delegating wrappers, messages append/expire/render identically — proven by 1165+ green tests (incl. a new behavior test that adds, FIFO-caps, prunes, and renders messages through the moved path), clean determinism guard, unchanged digest, identical before/after screenshots, and a verified no-cycle. hud.py drops ~15 LOC (tenth slice; 2477→~1211 cumulative).

## 7. Kickoff
Roster: 08 UX/UI (W1), 11 QA (W2), 09 (consult). Order: 08 W1 → PM gate → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE VERBATIM MOVE (self.→hud.); module fn for update is `update_messages` but the HUD wrapper MUST be named `update` (engine.py:819); keep `add_message` exact (name+signature+COLOR_WHITE default — 56 callers); keep ALL message state + fonts on HUD; TYPE_CHECKING-only HUD import; ZERO `self.` in the 3 moved fns; before/after pygame MUST match (note event-driven caveat) + W1 ad-hoc message-render PNG proof; own log; DO NOT COMMIT.
Follow-ups (REMAINING roadmap, from the WK101 grounding sweep, in order): **WK103** = input-router/menu-scroll → NEW `game/ui/hud_menu_scroll.py` (`is_mouse_over_menu`/`scroll_active_menu`/`handle_menu_scroll` as ONE unit; exact names for input_handler.py:127, ursina_app.py:830, MagicMock in tests; verify hero-panel + building-panel wheel paths). Then the **ursina god-files** (NEW verify model — ursina screenshots + runtime-import smoke, NOT the pygame digest): FOG/C (`sync_dynamic_trees`+`sync_log_stacks`+`_InstancedTreeStub` → ursina_terrain_growth_sync.py, ~258 LOC) FIRST to establish the rhythm, then FOG/A+FOG/B (cohesive units), then ursina_app APP/C (env-gated debug/FPS scaffolding). DEFER: `handle_click` (redesign), ursina_app APP/A camera + APP/B input hook. De-slop: delete dead `WATCH_MINIMAP_SIZE`.
