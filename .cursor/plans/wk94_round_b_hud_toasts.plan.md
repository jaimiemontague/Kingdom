# WK94 Sprint Plan — Round B-11: extract hud_toasts.py (wave + POI toast cluster) — second hud.py slice

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; the wave-event + POI-discovery/interaction toast cluster extracted from hud.py into `game/ui/hud_toasts.py`; render visually unchanged.
**Predecessors:** WK93 (hud_radar — first hud.py slice). **Roadmap:** Round B — the audit's #1 split: hud.py (2271 LOC). This is the second bounded slice (the toast subsystem), using the proven pure-move-behind-wrappers pattern (WK69–93).

## 0. TL;DR
hud.py (2271 LOC) is the biggest god-file. WK94 extracts the **toast subsystem** — a cohesive, self-contained cluster of 9 methods (~250 LOC) — into `game/ui/hud_toasts.py` as functions taking the HUD (`hud`), behind 1-line delegating wrappers on HUD (the render pipeline + engine EventBus calls keep their exact call sites). The toast STATE stays on the HUD (`__init__`, lines 333–351). This slice is **even lower-risk than WK93's radar**: the only real import the new module needs is `pygame` — every color/size is an inline literal, no `config` import, no `world_to_grid`/DTO coupling. The WK67 digest (headless) is unaffected (toasts are pygame-render-only). PM writes no code.

## 1. Scope
**IN:** create `game/ui/hud_toasts.py`; move VERBATIM (replace `self.`→`hud.`) these 9 methods, keeping a 1-line delegating wrapper on HUD for **each** (same name + signature so all call sites are UNCHANGED):

| HUD method (current) | hud.py line | → module function | Why a wrapper is required |
|---|---|---|---|
| `on_wave_incoming(self, event)` | 357 | `on_wave_incoming(hud, event)` | **engine.py:313** calls `self.hud.on_wave_incoming(event)` (bound method) |
| `on_wave_cleared(self, event)` | 367 | `on_wave_cleared(hud, event)` | **engine.py:321** calls `self.hud.on_wave_cleared(event)` (bound method) |
| `_render_wave_toast(self, surface)` | 377 | `render_wave_toast(hud, surface)` | render() call site `self._render_wave_toast(surface)` (hud.py:1957) |
| `notify_poi_discovered(self, poi_name, interaction_type="")` | 443 | `notify_poi_discovered(hud, poi_name, interaction_type="")` | public API; called by `_check_poi_discoveries` (hud.py:467) |
| `_check_poi_discoveries(self, game_state)` | 450 | `check_poi_discoveries(hud, game_state)` | render() call site (hud.py:1953) |
| `_ensure_poi_interaction_subscription(self, game_state)` | 479 | `ensure_poi_interaction_subscription(hud, game_state)` | render() call site (hud.py:1952); subscribes `self._on_poi_interaction`/`self._on_boss_spawned_toast` to the sim EventBus as **bound methods** — those wrappers MUST stay on HUD |
| `_on_poi_interaction(self, event)` | 493 | `on_poi_interaction(hud, event)` | EventBus callback (bound method registered at hud.py:489) |
| `_on_boss_spawned_toast(self, event)` | 522 | `on_boss_spawned_toast(hud, event)` | EventBus callback (bound method registered at hud.py:490) |
| `_render_poi_toasts(self, surface)` | 530 | `render_poi_toasts(hud, surface)` | render() call site (hud.py:1954) |

Wrapper form (example — keep the leading-underscore private names exactly, since the EventBus subscriptions and render() use them):
```python
def on_wave_incoming(self, event: dict) -> None:
    from game.ui import hud_toasts
    return hud_toasts.on_wave_incoming(self, event)

def _on_poi_interaction(self, event: dict) -> None:
    from game.ui import hud_toasts
    return hud_toasts.on_poi_interaction(self, event)
# ...and the same 1-line lazy-delegate form for the other 7.
```
**State STAYS on the HUD** (set in `__init__`, lines 333–351 — DO NOT move these): `_poi_toasts`, `_POI_TOAST_DURATION_MS`, `_POI_TOAST_FADE_MS`, `_poi_toast_ids`, `_poi_last_tick_ms`, `_poi_toast_font`, `_poi_interaction_subscribed`, `_wave_toast_text`, `_wave_toast_color`, `_wave_toast_start_ms`, `_wave_toast_duration_ms`, `_wave_toast_countdown_end_ms`, `_wave_toast_font`. In the moved functions every `self.<field>` becomes `hud.<field>` and `self.top_bar_height` becomes `hud.top_bar_height`. The call `self.notify_poi_discovered(...)` inside `_check_poi_discoveries` becomes `hud.notify_poi_discovered(...)` (resolves to the HUD wrapper → module fn; correct, no recursion).

**OUT:** the rest of hud.py (watch_card / selection_panels / messages / input_router — later slices); `_render_dev_mode_label` (357…604 region but NOT a toast — LEAVE IT on HUD); `effective_card_full_h` (440 — LEAVE on HUD); any behavior/visual change. **Move VERBATIM.**

## 2. Pattern (WK87–93, verbatim)
`hud_toasts.py` header:
```python
from __future__ import annotations
from typing import TYPE_CHECKING
import pygame
if TYPE_CHECKING:
    from game.ui.hud import HUD
```
That is the ONLY import the module needs (verified: every color/size in these 9 methods is an inline literal; no `config`, no `world_to_grid`, no DTO import). The module never imports `game.ui.hud` at top level (TYPE_CHECKING only). The wrappers import `hud_toasts` lazily inside the function body → **no import cycle**. Move VERBATIM.

## 3. Definition of Done
- **A.** `pytest -q` all pass (baseline **907 passed / 4 skipped / 0 failed** at WK93 close; WK94 adds the new seam test → expect ~911+ passed).
- **B.** `python tools/determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded` (`python -m pytest tests/test_wk67_ai_boundary.py -q`).
- **D.** `python tools/qa_smoke.py --quick` green.
- **E.** the 9 fns live in `game/ui/hud_toasts.py`; HUD keeps all 9 wrapper names+signatures (incl. the `_`-prefixed private ones); the 6 call sites (engine.py:313/321; hud.py render() 1952/1953/1954/1957) are UNCHANGED; toast state stays on HUD; hud.py smaller (~2271 → ~2030); **no import cycle** (verify `import game.ui.hud_toasts` then `import game.ui.hud` AND the reverse order both succeed from a fresh interpreter).
- **F.** BEFORE/AFTER pygame screenshots — `base_overview` + `ui_panels` — visually identical. NOTE: toasts are event-driven and may not appear in a steady-state capture; the guard is (i) scene-unchanged before/after + (ii) the verbatim diff + (iii) a targeted unit test that drives a toast through the moved path and asserts it renders without error (see W2). Report this coverage caveat explicitly.
- **G.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 08 UX/UI):** create `hud_toasts.py`, move the 9 fns VERBATIM (`self.`→`hud.`), add the 9 delegating wrappers on HUD, confirm state stays in `__init__`. Run full suite + digest + determinism + qa_smoke. Capture before/after pygame screenshots (base_overview + ui_panels). Verify no import cycle (both orders). Update own log. **DO NOT COMMIT.**
- **W2 (Agent 11 QA):** seam test `tests/test_wk94_hud_toasts.py` — assert: (1) all 9 fns exist in `hud_toasts` with the `hud`-first signature; (2) all 9 HUD wrappers exist and delegate (e.g. monkeypatch a module fn, call the HUD wrapper, assert it was hit — or assert wrapper bodies reference `hud_toasts`); (3) AST guard: `hud_toasts.py` does NOT import `game.ui.hud` at module top; (4) a behavior test that constructs a HUD (headless pygame), calls `on_wave_incoming({"name":"Test","seconds":5})` then `_render_wave_toast(surface)` and `_on_poi_interaction({"interaction_type":"loot","gold":50,...})` then `_render_poi_toasts(surface)` on a real Surface and asserts no exception + the toast list mutated as expected. Run full DoD A–G, independently view before/after screenshots. Update own log. **DO NOT COMMIT.**

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| A wrapper name changed (esp. the `_`-prefixed EventBus callbacks / engine-called `on_wave_*`) → silent break of EventBus subscription or engine call | Low-Med | keep EXACT names (incl. leading `_`); W2 behavior test drives wave + poi_interaction through the bound-method path |
| Import cycle (hud_toasts ↔ hud) | Low | TYPE_CHECKING-only HUD import; lazy wrapper (proven WK87–93); W1+W2 both verify fresh import both orders |
| A `self.X` missed in the `self.`→`hud.` sweep (esp. `self.top_bar_height`, `self.notify_poi_discovered`) | Low-Med | grep the new module for `self.` after the move (must be ZERO); suite + behavior test catch a missed ref |
| Weak steady-state screenshot coverage (toasts event-driven) | Med | documented in DoD F; the verbatim move + behavior test that actually renders a toast is the real guard — state this caveat in the report, do not claim screenshot proof of the toast pixels |

## 6. Success
The toast subsystem lives in `game/ui/hud_toasts.py` behind 9 delegating wrappers, toasts render identically — proven by 907+ green tests (incl. a new behavior test that renders a wave + POI toast through the moved path), clean determinism guard, unchanged digest, identical before/after pygame screenshots, and a verified no-cycle. hud.py drops ~240 LOC (second slice; more to follow).

## 7. Kickoff
Roster: 08 UX/UI (W1), 11 QA (verify + DoD + screenshot review + behavior test, W2), 09 (consult). Order: 08 W1 → PM gate (suite + digest + screenshots + no-cycle) → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE VERBATIM MOVE, keep ALL 9 wrapper names (incl. `_`-prefixed) + state on the HUD, TYPE_CHECKING-only import, ZERO `self.` left in the new module; before/after pygame MUST match; own log; DO NOT COMMIT.
Follow-ups (REMAINING roadmap): more hud.py slices (watch_card, selection_panels/peasant+building summary, messages/add_message+render_messages, input_router/handle_click+sidebar handlers); `ursina_terrain_fog_collab`(1783) split; `ursina_app`(1525) split; Move 9 (SystemRunner ordered pipeline — RISKY); world.py fog/FogOfWar state-machine; context_builder/direct_prompt_validator restructures; ai/vocab.py + TaskRouter (Move 12); config package; clusters 3/4; Round E audit; the 21-file WK34-zombie-type purge.
