# WK115 Round B — left-menu UI polish (slider / hero-card / chat-expand)

**Author:** Agent 01 (Executive Producer / PM)
**Status:** PLANNED → in execution
**Sprint key (PM hub):** `wk115_round_b_left_menu_ui_polish`
**Version target:** patch (UI polish; 3 user-reported bugs)
**Verification class:** PYGAME HUD — **headless SCREENSHOT-VERIFIED** (this is NOT an ursina slice; the deferred-screenshot exception does NOT apply — capture + visual verdict is MANDATORY, broad coverage, alignment/layering checked first).
**Model for all sub-agents:** `claude-opus-4-8` (opus)

---

## 0. The three bugs (Sovereign-reported)

> "the left menu sliders are a little odd — the slider bar sometimes shows up even
> when nothing is there, and there's weird effects on some things like the hero card,
> pressing chat on that doesn't automatically expand to fit the new chatbox."

PM has root-caused all three (grounding sweep + baseline captures) and confirmed them
visually. Fixes are localized to `game/ui/`. The WK67 AI digest is unaffected (pure
presentation). **DO NOT COMMIT** — PM owns the commit.

---

## 1. BUG 1 — solo resize "slider" floats in a blank panel

**Root cause** (`game/ui/hud_left_layout.py::layout_left_column_segments`): in the
solo case (a hero/building is selected, watch card closed, chat popup not active),
`main_h = round(LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO(0.72) * available)` — sized by a
fraction, NOT by content. The hero/building card content is much shorter (~300px on a
1080 screen where `main_h≈600px`), so `Panel.render` fills ~600px of solid panel and
the `main_solo` resize handle (registered at L118–124, drawn by
`render_left_split_handles`) sits at the very bottom — floating ~300px below the last
line of content. That is "the slider bar shows up even when nothing is there."

**Fix** — make the solo panel size to its content and drop the solo handle entirely
(the genuine two-panel dividers `main_bottom`/`watch_top`/`watch_bottom` stay; only the
SOLO handle, which resizes against empty space, is removed):

### 1a. Persist each panel's natural content height (Agent 08)
Both panels already compute their content extent during render but don't keep it:
- `game/ui/hero_panel.py` ~L894 (`content_h = int(y) - body_start`; the panel's natural
  FULL height is from the panel top to the bottom of the last drawn element). At the
  same spot, store the natural full height (header + body + a small bottom pad, e.g.
  `+ 8`) as `self.last_content_height = max(HERO_LEFT_MIN_H, <natural full height>)`.
  Initialize `self.last_content_height = 0` in `__init__`. Use the value that
  represents "how tall the card needs to be to show everything", NOT the body-only
  `content_h` and NOT clamped to the viewport.
- `game/ui/building_panel.py` ~L335 (`content_h = min(scratch_h, y + bottom_padding)`).
  Store `self.last_content_height = max(HERO_LEFT_MIN_H, int(content_h))` (init `0`).

### 1b. Size solo `main_h` to content + remove the solo handle (Agent 08)
In `layout_left_column_segments`, the `elif main_open:` block (currently L95–101). Keep
the chat-popup branch FIRST and unchanged (it must still win — chat active ⇒ full
height):
```python
elif main_open:
    if hud._should_render_hero_menu_chat_popup(game_state or {}):
        main_h = available
    else:
        natural = hud._left_main_natural_h()  # cached content height, 0 if unknown
        if natural > 0:
            main_h = max(HERO_LEFT_MIN_H, min(natural, available))
        else:
            # first frame after selection (panel not yet rendered): fall back to the
            # legacy fraction so we never collapse the card before we know its content.
            solo_frac = fracs.get("main_solo", LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO)
            main_h = max(HERO_LEFT_MIN_H, min(int(round(float(solo_frac) * available)), available))
```
Then in the rect-allocation block (currently L117–124, the `else:` that registers
`main_solo`): **delete the `main_solo` handle registration entirely** — register NO
handle in the solo case. (Leave the `main_open and watch_open` divider at L113–116 and
the `watch_bottom` handle at L131–134 untouched.)

Add the helper on HUD (delegating to the active panel), e.g. in `game/ui/hud.py` near
the other left-column helpers:
```python
def _left_main_natural_h(self) -> int:
    """Last-rendered natural content height of the active left-column panel (0 if unknown).
    Used to size the solo hero/building card to its content (WK115 BUG 1)."""
    gs = getattr(self, "_last_game_state", None) or {}
    if gs.get("selected_building") is not None:
        return int(getattr(self._building_panel, "last_content_height", 0) or 0)
    if gs.get("selected_hero") is not None:
        return int(getattr(self._hero_panel, "last_content_height", 0) or 0)
    return 0
```
If `_last_game_state` is not already stored each frame, instead pass the panel choice
another way the implementer prefers — but the SIMPLEST correct approach: have
`layout_left_column_segments` already receives `game_state`; thread the active panel's
`last_content_height` from there. (Implementer's discretion; the contract is: solo
`main_h` = clamp(content_height, HERO_LEFT_MIN_H, available) once content is known.)

**Net effect:** the hero/building card becomes a compact card sized to its content; no
resize bar floats below it. When content exceeds `available`, `main_h = available` and
the existing mouse-wheel scroll (`apply_menu_scroll`) handles overflow — no handle
needed.

---

## 2. BUG 3 — pressing "Chat" doesn't grow the card to fit the chatbox

**Two chat surfaces:**
- **Un-pinned hero** (in-column popup): already works — `should_render_hero_menu_chat_popup`
  returns True ⇒ `main_h = available` ⇒ `hero_menu_chat_split_rects` carves a chat band.
  VERIFY this still looks right on 1920 after BUG 1 (the popup branch must remain first).
- **Pinned watch hero** (watch-card chat band): BROKEN. `effective_watch_card_h` returns
  `_left_watch_rect.height` (set by the split fraction), ignoring `_chat_visible`, so the
  band is whatever the fraction gave — often too small for the chatbox, so the card does
  not grow.

**Fix** (`game/ui/hud_left_layout.py::layout_left_column_segments`, the
`main_open and watch_open` branch, currently L86–94): when the pinned watch hero has
chat open, bias the watch segment up to its chat-inclusive desired height. After the
existing `main_h`/`watch_h` computation in that branch, add:
```python
        if hud._chat_visible and hud._watch_card_expanded:
            want_watch = int(hud._desired_watch_card_expanded_h())  # already includes WATCH_CARD_CHAT_H
            max_watch = max(WATCH_CARD_HEADER_H, available - HERO_LEFT_MIN_H)
            grown = min(want_watch, max_watch)
            if grown > watch_h:
                watch_h = grown
                main_h = max(HERO_LEFT_MIN_H, available - watch_h)
```
`_desired_watch_card_expanded_h` (hud_watch_card.py ~L243–249) already adds
`WATCH_CARD_CHAT_H` when `_chat_visible`, so no change is needed there;
`effective_watch_card_h` returns the now-grown `_left_watch_rect.height` automatically.
(The watch-solo branch `else: watch_h = available` already gives full height — fine.)

Also confirm the click path: `game/input/mouse.py` ~L148–150 already sets
`_watch_card_expanded=True` + `_chat_visible=True` when the chat target is the pinned
hero. No change needed there unless the screenshot shows the flag isn't set — if so,
ensure pressing Chat sets `_chat_visible=True` for the pinned hero.

---

## 3. BUG 2 — "weird effects on the hero card"

Largely a CONSEQUENCE of #1 (blank padded panel + floating bar) and #3 (cramped chat).
Once the card is content-sized and chat fits, most of it resolves. Remaining targeted
fixes (Agent 08 — CAPTURE FIRST, identify the actual visible artifact, then fix):
- **Scroll-clip edge artifacts** (`game/ui/hero_panel.py` ~L560–567): the body is drawn
  inside a `set_clip(viewport)`. When `_menu_max_scroll <= 0` (content fits — the common
  case after BUG 1), there is nothing to scroll, so SKIP setting the clip (draw without
  it) to avoid partial-line clipping at the viewport top/bottom edges. Only clip when
  `_menu_max_scroll > 0`. Restore `prev_clip` exactly as today.
- **Draw ordering** (`game/ui/hud.py` ~L825–846): the in-column chat divider line and
  `_render_left_split_handles` are painted last. After BUG 1 the solo handle is gone, so
  no bar paints over solo content. Keep the divider line ONLY when `_hero_menu_chat_rect`
  is not None (already the case). Verify no 1px stray line remains in the no-chat shot.
- If the after-capture still shows an artifact, diagnose from the image and fix the
  specific cause; do NOT paper over it. Re-capture to confirm.

---

## 4. Tests to update / add (contract changes are deliberate, Sovereign-driven)

The BUG-1 fix intentionally changes the solo-handle contract. Update in lockstep:
- **`tests/test_wk61_r11_sidebar_main_solo_handle.py`** — currently asserts the
  `main_solo` handle ALWAYS exists for an unpinned hero + that the panel height equals
  the fraction. REWRITE to the new contract:
  - With content known and fitting: `"main_solo" not in hud._left_split_handle_rects`
    and `hud._left_main_rect.height <= available` and the card is sized to content
    (height ≈ panel `last_content_height`, clamped ≥ HERO_LEFT_MIN_H). (Render once to
    populate `last_content_height`, then layout, then assert.)
  - Keep/repurpose the click test: clicking where the old solo handle was now returns no
    `sidebar_split_drag` (it routes normally) — assert the solo drag no longer fires.
  - Preserve coverage that the genuine `main_bottom`/`watch_bottom` dividers still exist
    in the watch+main and watch-solo cases (add or keep such asserts).
  Keep the file's intent (left-column split behavior) — just encode the new, fixed UX.
- **`tests/test_wk61_r10_sidebar_layout.py`** — asserts `main_bottom` divider in the
  watch+main case (L43–56, 109). That case is UNCHANGED — keep it green; only adjust if
  a shared helper shifts. Do not weaken it.
- **NEW `tests/test_wk115_left_menu_polish.py`** — pin the three fixes headlessly:
  - BUG 1: select a hero (unpinned, 1920×1080), render once, layout; assert NO
    `main_solo` handle and `_left_main_rect.height` is content-sized (< the old
    `0.72*available`, ≥ HERO_LEFT_MIN_H).
  - BUG 3: pin a hero, `_watch_card_expanded=True`, `_chat_visible=True`, small `watch`
    split frac (e.g. `{"main":0.7,"watch":0.3}`), layout; assert
    `_left_watch_rect.height >= min(_desired_watch_card_expanded_h(), available-HERO_LEFT_MIN_H)`
    and that `_watch_card_body_split(_effective_watch_card_h(1080))` yields `chat_h >=`
    a readable minimum (> 0, and ≥ the chat band can show ≥1 line).
  - BUG 2: after BUG 1, `hero_panel._menu_max_scroll == 0` for a normal hero on 1080
    (content fits) ⇒ no clip path taken (assert the panel renders without raising and the
    card background is filled at the card rect but NOT far below it).

The WK98/WK99/WK100/WK101/WK52/WK96 layout tests must stay green (they cover the
unchanged watch-card geometry + orchestration). Run them explicitly.

---

## 5. Screenshot scenarios (capture + verify — MANDATORY)

Existing scenarios cover the bugs; ADD one for the pinned-chat-visible state (BUG 3's
failing case) so it is regression-pinned:
- In `tools/screenshot_scenarios.py`, add a Shot to `scenario_ui_panels` (or a sibling)
  that pins a hero, sets `engine2.hud._watch_card_expanded = True`,
  `engine2.hud._chat_visible = True`, a small watch split frac, seeds 2–3 chat lines on
  the pinned hero, and labels it `ui_panels_pinned_chat`. Model it on the existing
  `_apply_sidebar_pin_split` hook (~L526–536).

Capture command (run from repo root; headless defaults are set by the tool):
```
python tools/capture_screenshots.py --scenario ui_panels --out docs/screenshots/wk115_after --seed 3 --size 1920x1080
python tools/capture_screenshots.py --scenario wk61_hero_menu_chat --out docs/screenshots/wk115_after --seed 3
python tools/capture_screenshots.py --scenario wk52_pin_alerts --out docs/screenshots/wk115_after --seed 3 --size 1920x1080
```
Agent 08 MUST capture BEFORE (current `main`) and AFTER (its fix) for each scenario,
then `Read` every AFTER PNG and give a per-image visual verdict: BUG 1 — no floating
bar below the hero/building card; BUG 2 — no clipping/stray-line/overlap artifacts on
the card; BUG 3 — the pinned chat band is tall enough to show the chatbox + at least one
message. Check ALIGNMENT and LAYERING first (card left edge flush, no panel overlap, no
bar over content), THEN text/styling. Cover EVERY affected path
(`ui_panels_hero`, `ui_panels_building`, `ui_panels_sidebar_split`, `ui_panels_tax_collector`,
`wk61_hero_menu_chat_1024`, `wk61_hero_menu_chat_1920`, `ui_panels_pinned_chat`,
`wk52_watch_card_expanded`). Do not rubber-stamp one scenario.

---

## 6. Waves

- **Wave 1 — Agent 08 (UX/UI):** implement §1a/§1b, §2, §3 in `game/ui/*`; add the
  `ui_panels_pinned_chat` scenario (§5); update `tests/test_wk61_r11…` to the new
  contract (§4) and add `tests/test_wk115_left_menu_polish.py`. Capture BEFORE/AFTER for
  all §5 scenarios, Read every AFTER PNG, give per-image verdicts (alignment/layering
  first). Self-verify: `python -m pytest tests/test_wk115_left_menu_polish.py
  tests/test_wk61_r11_sidebar_main_solo_handle.py tests/test_wk61_r10_sidebar_layout.py
  tests/test_wk99_hud_left_layout.py tests/test_wk100_hud_layout_orchestration.py
  tests/test_wk101_hud_hero_menu_layout.py tests/test_wk52_watch_card.py
  tests/test_wk96_hud_watch_card.py tests/test_wk98_hud_watch_geom.py -q` → all green.
  DO NOT COMMIT.
- **Wave 2 — Agent 11 (QA):** full DoD + INDEPENDENT broad screenshot review (Read every
  §5 AFTER PNG, verdict alignment/layering first; confirm unaffected panels —
  `ui_panels_building`, pause menu, building menu — are unchanged/clean):
  1. `python -m pytest -q` → 0 failed (record counts).
  2. `python tools/determinism_guard.py` → clean PASS.
  3. `python -m pytest tests/test_wk67_ai_boundary.py::test_ai_decision_digest_is_stable -q`
     → digest byte-identical `b73961340c…d148ded` (presentation-only change ⇒ must hold).
  4. `python tools/qa_smoke.py --quick` → DONE: PASS.
  5. Re-capture the §5 scenarios and Read them; report a per-image PASS/FAIL.
  DO NOT COMMIT.

## 7. Definition of done (PM gate)

- [ ] BUG 1: solo hero/building card sized to content; NO floating resize bar; verified
      in `ui_panels_hero`, `ui_panels_building`, `ui_panels_tax_collector` AFTER shots.
- [ ] BUG 2: no clip/stray-line/overlap artifacts on the hero card (AFTER shots).
- [ ] BUG 3: pressing Chat grows the card; pinned `ui_panels_pinned_chat` shows a usable
      chat band; un-pinned `wk61_hero_menu_chat_1920` chat is readable.
- [ ] `tests/test_wk115_left_menu_polish.py` green; `test_wk61_r11…` updated to the new
      contract + green; WK52/96/98/99/100/101 + r10 layout tests green.
- [ ] full `pytest -q` 0 failed; determinism clean; WK67 digest byte-identical; qa_smoke PASS.
- [ ] PM has Read the key BEFORE/AFTER PNGs and confirmed the three fixes visually.
- [ ] Agent 08 + 11 logs updated. PM commits (scoped add of touched `game/ui/*`,
      `tools/screenshot_scenarios.py`, the 2 test files, plan + PM hub + agent logs) +
      pushes. Do NOT commit the `docs/screenshots/wk115_*` PNGs unless they're small and
      intended as fixtures — default: leave them untracked / git-ignored, they are
      verification artifacts, not source.

## 8. Grounding for NEXT sprint (WK116)

Resume `ursina_app.py` decomposition (961 LOC): the **input/pointer cluster**
(`_install_ursina_input_hook`, `_pixel_hits_opaque_ui`, `_engine_screen_pos_for_pointer`,
`_sidebar_split_drag_active`, `_virtual_screen_pos`, `_pointer_event_pos`,
`_queue_pointer_motion_event`, `_handle_ursina_input`, +`_is_chat_active`) → new
`game/graphics/ursina_app_input.py`, owner-arg pure-move (WK113 pattern; deferred
screenshots). Mind the intra-cluster call chain, the `_install_ursina_input_hook`
closure, and cross-cluster calls into the WK113 camera wrappers (`owner._reset_camera_to_default()`
etc. stay as `owner.<wrapper>` hops). Then the UI-overlay/HUD-texture cluster.
Still HELD: nothing (zombie purge done WK114). Deferred/riskiest: TaskRouter, SystemRunner.
