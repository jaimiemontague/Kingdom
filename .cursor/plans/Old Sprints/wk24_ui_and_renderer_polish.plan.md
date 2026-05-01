# WK24 Sprint: UI & Renderer Polish

This sprint tackles 8 specific user-reported bugs across the UI, AI logic, and Ursina 3D renderer. The goal is to provide maximum reasoning for all agents so no guesswork is required.

## Proposed Changes

---

### Bug Set A: UI & UX (Agent 08 — UX/UI Director)

#### [MODIFY] `game/ui/hud.py`
- **End Conversation Bug:** The "End Conversation" action is caught by `input_handler.py`, which incorrectly fails to clear the selected hero. However, ensuring the macro UI state exits the hero focus should be done robustly. In `game/input_handler.py` around line 351, update `handle_mousedown` logic for `"end_conversation"` to properly exit hero focus and clear `selected_hero`. 
  **Code Example:**
  ```python
                    if action == "end_conversation":
                        chat_panel = getattr(engine.hud, "_chat_panel", None)
                        if chat_panel is not None:
                            chat_panel.end_conversation()
                        # Exit the hero focus so the panel successfully transitions out
                        if getattr(engine, "micro_view", None) is not None:
                            engine.micro_view.exit_hero_focus()
                        engine.selected_hero = None
                        return
  ```
- **"X" Buttons:** Ensure the right-side panels (Interior, Chat, Quest) and the left-side (Hero/Peasant) explicitly draw a global `.right_close_rect` or local close buttons and handle closing securely. Draw an X button globally in `hud.py` when ANY selection is active, or locally inside `chat_panel.py`, `hero_panel.py`, etc. 

#### [MODIFY] `game/ui/pause_menu.py`
- **Controls Menu Text Wrap:** Wrap the descriptions ("1-8", etc.) in the Controls menu so that text does not run off the screen.
- **Audio Sliders / Graphics Toggles:** Verify `request_display_settings` behaves safely in Ursina. If not, add a fallback or disable toggles when running Ursina. Broaden the hit box width for audio sliders if they are too small to easily grab.

---

### Bug Set B: Graphics & Rendering (Agent 09 - Art / Agent 03 - Arch)

#### [MODIFY] `game/graphics/ursina_renderer.py`
- **Bug 1: Enemies visible in greyed Fog:** Enemies should strictly fade out if they are not actively visible. Inside the `gs["enemies"]` loop, verify if `world.visibility` tile is exactly `Visibility.VISIBLE`.
  ```python
            world = self.engine.world
            tx, ty = int(e.x / 32.0), int(e.y / 32.0)
            is_visible = True
            if 0 <= ty < world.height and 0 <= tx < world.width:
                is_visible = (world.visibility[ty][tx] == Visibility.VISIBLE)
            
            if not getattr(e, "is_alive", True) or not is_visible:
                continue
  ```
- **Bug 4: Peasants are too small:** Currently `PEASANT_SCALE = 0.3`. Our hero scale is `0.62`. Change `PEASANT_SCALE` to `0.465` (which is 75% of the hero size).
- **Bug 5: Tax Collector missing:** Scroll down to the peasant/guard billboard loops. Add a new loop for `gs["tax_collectors"]`. Use identical logic to `gs["guards"]` but use:  
  `ptex = TerrainTextureBridge.surface_to_texture(_worker_idle_surface("tax_collector"), ...)`

---

### Bug Set C: Architecture & AI tuning (Agent 03 — engine; Agent 06 — AI behaviors)

#### [MODIFY] `game/engine.py`
- **'H' Hotkey Issue:** The `try_hire_hero()` only fires properly if a guild is already selected. Rewrite `try_hire_hero` to auto-locate an applicable valid guild if `engine.selected_building` is `None` (mimicking the HUD CommandBar's backend logic that iterates through buildings looking for a valid guild).

#### [MODIFY] `ai/behaviors/task_durations.py`
- **Heroes stuck in market:** Heroes buying potions wait too long idle. Tighten `"shopping"` and `"buy_potion"` entries in `TASK_DURATION_RANGES` (keep other keys unchanged unless playtest shows a regression).
- **Target ranges (starting point):** `buy_potion` → `(3, 6)` seconds; `shopping` → `(4, 8)` seconds. Tune slightly if headless or manual play shows heroes leaving shops unrealistically fast.

---

## Agent routing (studio roles)

Per `.cursor/rules/08-role-boundaries.mdc` and `01-studio-onboarding.mdc`:

| Bug set | Primary agent | Rationale |
|--------|----------------|-----------|
| **A** — UI / input / pause menu | **08** (UX/UI Director) | Owns `game/ui/`; coordinates with **03** if `game/engine.py` or `game/input_handler.py` contracts need changes |
| **B** — Ursina billboards / fog | **09** (Art / 3D presentation) | Owns `game/graphics/` |
| **C** — `try_hire_hero` | **03** (Technical Director) | Owns `game/engine.py` |
| **C** — task durations | **06** (AI Behavior) | Owns `ai/` including `ai/behaviors/` |

**Agent 11 (QA)** does not implement features; they run `python tools/qa_smoke.py --quick` after R1 merges and may extend scenarios if new assertions are needed.

---

## Acceptance criteria (Round 1)

### Bug Set A (Agent 08)
- [ ] **End Conversation:** After clicking End Conversation, hero chat closes, hero focus / micro-view exits, and `selected_hero` is cleared; no stuck panel state.
- [ ] **X close:** User can dismiss the active selection panel (interior / chat / quest / hero / peasant flows as applicable) via a visible close control without leaving orphan UI state.
- [ ] **Pause (ESC) menu:** Controls text fits the panel (wrapped); audio sliders are grabbable at 1080p virtual resolution; if a setting cannot apply under `--renderer ursina`, it fails safe (disabled or no-op with clear behavior — no crash).

### Bug Set B (Agent 09)
- [ ] Enemies in **grey fog / not fully visible** tiles do not draw (or are hidden consistently with sim visibility).
- [ ] Peasant billboards read at a similar visual weight to heroes (target: `PEASANT_SCALE = 0.465`).
- [ ] Tax collectors appear in Ursina using the same billboard pattern as guards/peasants where appropriate.

### Bug Set C — Engine (Agent 03)
- [ ] **H** hires from a valid guild when no building is selected, matching the intent of the HUD hire affordance (auto-pick a legal guild).

### Bug Set C — AI tuning (Agent 06)
- [ ] Potion shopping loops feel shorter; no obvious “standing in market for 20+ seconds” idle while the sim is running at 1× speed.

---

## Verification (every implementer)

From repo root:

```bash
python tools/qa_smoke.py --quick
```

Manual Ursina spot-check (after automated PASS):

```bash
python main.py --renderer ursina --provider mock
```

Confirm: fog hides off-vision enemies, panels close cleanly, H hires without pre-selecting a guild, ESC menu usable.

---

## Round structure

| Round | Goal |
|-------|------|
| **R1** | Implement fixes above; keep gates green |
| **R2** (if needed) | Polish edge cases from playtest, screenshot pass, any Ursina-specific display-settings follow-ups |

---

## Dependencies / sequencing

- **03** (`try_hire_hero`) and **08** (`input_handler` / HUD) may touch adjacent code — prefer small PRs or coordinate in agent logs if merge conflicts appear.
- **09** Ursina changes should not alter simulation state — render-only.
- **06** duration changes affect pacing — if `qa_smoke` timing assumptions break, adjust tests only with Agent 11 / Agent 12 coordination.

---

## Out of scope for WK24 R1

- New gameplay systems, new buildings, or multiplayer work
- Asset pipeline / `assets/` attribution changes unless required for a new texture path
- Version bump / `CHANGELOG.md` (human release decision)
