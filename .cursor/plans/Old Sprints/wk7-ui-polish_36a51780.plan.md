---
name: wk7-ui-polish
overview: UI overhaul sprint focused on window/display modes, an in-game ESC menu, a castle-driven build catalog, and a UI quality pass benchmarked against Majesty.
todos: []
---

# WK7 Sprint Plan — UI Overhaul + WK6 Finish

## Goals (WK7)

- **Window/display modes**: support **fullscreen**, **fullscreen windowed (borderless)**, and **windowed**; expose in **ESC menu → Graphics**.
- **ESC menu**: pressing **Esc** always opens a centered **pause/settings menu**; game is paused while it’s open.
- **Castle-driven build catalog**: selecting the **castle** provides a **Build buildings** action that opens a centered building catalog (with pixel-art thumbnails, name, cost, hotkey/shortcut), and selecting an item closes the menu and enters placement mode.
- **UI quality pass**: bring overall UI composition closer to Majesty’s standard (not a clone)—consistent framing, spacing, hierarchy, and readability.

## Non-goals (WK7)

- Major gameplay/system refactors outside UI contracts.
- Multiplayer/network determinism changes.

## Must-have requirements (from you)

- **Window modes UI**:
- Settings live in **ESC menu → Graphics**.
- In **fullscreen windowed**, click+hold+drag on the **top bar** switches to **windowed** and **live-drags with cursor**.
- **ESC** opens a centered menu with options (audio volume, key bindings, etc.).
- **Castle → Build buildings** opens a centered building picker with pixel art thumbnails and click-to-place.
- **Agent 08** compares current UI vs Majesty reference screenshot and proposes additional UI changes.

## Current state (baseline)

- Window init currently supports **borderless (NOFRAME)** default via `DEFAULT_BORDERLESS` and display-size fallback in [`game/engine.py`](game/engine.py).
- ESC currently toggles pause/cancel selection, but there is **no** centered pause/settings menu.
- Build list exists as [`game/ui/building_list_panel.py`](game/ui/building_list_panel.py) and is toggled via HUD Build button (`build_menu_toggle`) in [`game/ui/hud.py`](game/ui/hud.py).
- Audio system exists and supports per-sound volume; ambient starts at engine init; there is no user-facing audio UI.

## Design decisions (locked for WK7)

- **Keep a slim bottom bar** for core actions; move **settings/options** into the ESC menu.
- **Best-effort live drag**: implement live window drag on Windows using `pygame._sdl2` window access when available; if not available, degrade to “switch to windowed at drag start” + show a brief HUD message.

## Implementation plan (PM assignments)

### Workstream A — Window modes + Graphics menu (Owner: Agent 03; Consult: Agent 10, Agent 11)

- **Add a user settings model** (UI-only, non-sim):
- `display_mode`: `fullscreen` | `borderless` | `windowed`
- `window_size`: `(w,h)` for windowed
- `vsync` (optional future)
- **Implement runtime mode switching** in [`game/engine.py`](game/engine.py):
- Centralize display creation in a single method, e.g. `apply_display_settings()`.
- Modes:
- `fullscreen`: `pygame.FULLSCREEN`
- `borderless`: `pygame.NOFRAME` at desktop resolution
- `windowed`: `pygame.RESIZABLE` at saved window_size
- **Top-bar drag behavior** (when in borderless):
- Add an input hook that detects click+drag starting in the HUD top bar region.
- On drag start: switch to windowed + begin **live drag** if supported.
- Use `pygame._sdl2.Window.from_display_module()` to set window position during drag (Windows).
- **Expose these options in ESC menu → Graphics** (see Workstream B).
- **QA gates**:
- `python tools/qa_smoke.py --quick` must remain PASS.
- Manual: verify all three display modes + drag-to-windowed on Windows.

### Workstream B — ESC pause/settings menu framework (Owner: Agent 08; Consult: Agent 03, Agent 14)

- Add a centered modal menu panel shown when `engine.pause_menu.visible == True`.
- Menu structure (Build A for WK7):
- **Resume** (close menu)
- **Graphics** (dropdown/radio for display_mode; apply button)
- **Audio** (master volume slider; ambient/music volume optional)
- **Controls** (show keybindings list; WK7: read-only list + placeholders for rebinding UI unless time permits)
- **Quit to desktop**
- Input rules:
- `Esc` toggles menu open/close.
- While menu open, world input is blocked and game is paused.
- Files likely touched:
- [`game/ui/widgets.py`](game/ui/widgets.py) (add `Slider`, `RadioGroup`, `ModalPanel` helpers)
- [`game/ui/hud.py`](game/ui/hud.py) (top-level “is menu open” awareness for input gating/top-bar drag region)
- [`game/engine.py`](game/engine.py) (route Esc to menu, not only pause)

### Workstream C — Castle-driven build catalog (Owner: Agent 08; Consult: Agent 09)

- Add a **Build buildings** button in the castle UI.
- Likely in [`game/ui/building_panel.py`](game/ui/building_panel.py) (if it is the interactive building UI), otherwise in HUD right-panel building summary.
- Replace/augment `BuildingListPanel` with a centered **BuildCatalogPanel**:
- Grid or list with:
- Pixel-art thumbnail (from `assets/sprites/buildings/<type>/...` if available; fallback to colored swatch)
- Building name, cost, hotkey
- Disabled state messaging (affordability/prereq/constraints)
- Click selects and closes the catalog; engine enters placement via existing `select_building_for_placement()`.
- Keep current HUD Build button behavior for now (optional shortcut): it can open the same BuildCatalogPanel.

### Workstream D — UI quality benchmark vs Majesty (Owner: Agent 08)

- Use `.cursor/human_provided/Original Majesty UI Example.JPG` as the reference.
- Deliverables:
- Screenshot set of current Kingdom Sim UI in a comparable state (same resolution if possible).
- A “delta list” of improvements: panel framing, typography scale, iconography consistency, spacing grid, minimap treatment, command bar density.
- Concrete proposals mapped to files/widgets (no code by PM).

### Workstream E — WK6 follow-ups that still feel incomplete (Owners: Agent 14 + Agent 12; Consult: Agent 11)

- **Audio settings UI** (hooked into Workstream B): master volume slider (and optionally SFX vs ambient split).
- **SFX coverage gaps**:
- Add/confirm remaining optional keys (ui_confirm/ui_error/hero_hired/purchase) if assets exist.
- Ensure validator stays green: `python tools/validate_assets.py --report` shows 0 warns.

## Coordination and logging (PM-owned)

- PM will post all assignments and acceptance criteria in the hub:
- [`.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json`](.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json) under `wk7-...` sprint id.
- Active agents update their own logs under [`.cursor/plans/agent_logs/`](.cursor/plans/agent_logs/).

## Definition of Done (WK7)

- **Functional**:
- ESC menu works; game pauses; resume works.
- Graphics menu switches between fullscreen/borderless/windowed.
- Borderless top-bar drag switches to windowed and live-drags on Windows (best-effort).
- Castle opens build catalog; selecting a building enters placement.
- **Quality**:
- UI composition passes Agent 08’s Majesty benchmark checklist.
- **QA**:
- `python tools/qa_smoke.py --quick` PASS.
- Manual 10-minute smoke in `python main.py --no-llm` and `python main.py --provider mock`.

## Implementation todos

- wk7_pm_hub: Write WK7 sprint entry + agent prompts into Agent 01 hub log
- wk7_window_modes: Window mode switching + drag-to-windowed behavior
- wk7_pause_menu: ESC menu modal framework + audio/graphics pages
- wk7_build_catalog: Castle-driven build catalog panel with thumbnails
- wk7_ui_benchmark: Screenshot comparison + delta proposals vs Majesty