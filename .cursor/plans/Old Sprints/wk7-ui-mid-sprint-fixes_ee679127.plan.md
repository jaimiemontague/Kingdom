---
name: wk7-ui-mid-sprint-fixes
overview: Mid-sprint plan to fix UI click hitbox offsets, make display mode switching actually work (and feel obvious), and overhaul the UI look using a cohesive CC0 UI art pack with a toggleable right panel.
todos:
  - id: wk7m_click_hitboxes
    content: Fix click offset bugs + add resize propagation for modal panels
    status: completed
  - id: wk7m_display_modes
    content: Make display mode switching obvious; set windowed default size; sync UI on resize
    status: completed
    dependencies:
      - wk7m_click_hitboxes
  - id: wk7m_ui_art_pack
    content: Select + import CC0 UI pack; add attribution + license proofs
    status: completed
  - id: wk7m_ui_skin_layout
    content: Implement 9-slice skin + Tab-toggle right panel + reduce wasted space
    status: completed
    dependencies:
      - wk7m_ui_art_pack
      - wk7m_click_hitboxes
  - id: wk7m_qa_proof
    content: QA verification + before/after screenshots + bug tickets if needed
    status: completed
    dependencies:
      - wk7m_ui_skin_layout
      - wk7m_display_modes
---

# WK7 Mid-Sprint Plan — UI Bugs + Display Modes + Visual Overhaul

## Goals (this mid-sprint)

- Fix **misaligned click hitboxes** ("must click 100–200px above") for build-related UI.
- Make **Graphics → display mode switching** actually change modes in an obvious way (fullscreen, borderless fullscreen-windowed, windowed).
- Upgrade the UI from grey/black to a **Majesty-quality look** using a **cohesive CC0 UI art pack** (9-slice panels/buttons + icons).
- Change the massive right-side panel to be **toggleable (Tab)** (your choice).

## Primary issues observed (root causes)

- **Click offset** likely comes from **coordinate-space mismatches**:
- `BuildingPanel.render_castle()` sets `build_catalog_button_rect` in mixed coordinates (screen X but panel-local Y) and draws using that rect onto an offscreen panel surface.
- UI modal panels (`PauseMenu` / `BuildCatalogPanel`) cache `screen_width/height` and may not be updated after mode changes → wrong `ModalPanel.get_panel_rect()` and hitboxes.
- **Display mode “tries but stays fullscreen”** likely because:
- `windowed` defaults to the same size as the display (1920×1080), which can *look* fullscreen; and/or
- after `pygame.display.set_mode` the UI subsystems aren’t fully re-synced to the new size.

## Workstreams + owners

### Workstream A — Fix click hitbox alignment (Owner: Agent 08; Consult: Agent 03)

- **Fix `BuildingPanel` button rect math** so render coords and hit-test coords match:
- `build_catalog_button_rect` must be stored in **screen coords** and the draw call on panel surface must use **panel-local coords**.
- Verify all other buttons in `BuildingPanel` follow the same rule.
- **Fix modal panel sizing sync**:
- When window size changes, update `PauseMenu.modal.screen_width/height` and `BuildCatalogPanel.modal.screen_width/height`.
- Add explicit `on_resize(w,h)` methods to:
- [`game/ui/pause_menu.py`](game/ui/pause_menu.py)
- [`game/ui/build_catalog_panel.py`](game/ui/build_catalog_panel.py)
- [`game/ui/hud.py`](game/ui/hud.py) (if needed)
- Call them from [`game/engine.py`](game/engine.py) inside `apply_display_settings()` after the new window is applied.
- **Acceptance criteria**:
- Clicking the visible button hits correctly (no offset) in all 3 display modes.
- `python tools/qa_smoke.py --quick` PASS.

### Workstream B — Display mode switching that’s obvious (Owner: Agent 03)

- **Change default windowed size** to something visibly windowed (e.g. 1280×720) while keeping borderless default.
- Store last-used windowed size in memory (BuildA); optional file persistence can be BuildB.
- **Harden mode switching on Windows**:
- Ensure switching to `windowed` clears borderless assumptions (position, flags).
- Ensure UI gets re-synced (via Workstream A resize hooks).
- **Acceptance criteria**:
- Switching to **windowed** shows a decorated, resizable window (obvious).
- Switching to **borderless** is true fullscreen-windowed.
- Switching to **fullscreen** is exclusive fullscreen.

### Workstream C — CC0 UI art pack integration (Owner: Agent 09; Consult: Agent 13, Agent 12)

- **Pick ONE cohesive CC0 UI pack** (panels, buttons, icons) and import a minimal curated subset:
- Add to `assets/ui/<pack_name>/...` plus `assets/third_party/<pack_name>/{LICENSE,README}`.
- Update [`assets/ATTRIBUTION.md`](assets/ATTRIBUTION.md) with exact sources + license proof.
- **Define a small UI texture contract**:
- 9-slice panel texture(s) for: top bar, bottom bar, right panel, modal window.
- Button textures: normal/hover/pressed.
- Optional icons for: Build/Hire/Bounty, tabs (Graphics/Audio/Controls).
- **Acceptance criteria**:
- No missing attribution; assets load with nearest-neighbor scaling.

### Workstream D — UI skin + layout refactor (Owner: Agent 08)

- **Implement 9-slice rendering** in [`game/ui/widgets.py`](game/ui/widgets.py):
- `NineSlice` helper + cached surfaces per (texture, size, state).
- Update `Panel`/`ModalPanel` to optionally render using textures (fallback to current code-drawn frames if assets absent).
- **Make right-side panel toggleable**:
- Hotkey: **Tab** toggles right panel.
- Default: hidden until toggled OR selection (choose simple rule: Tab-only).
- When hidden, world area should reclaim the space (HUD layout recompute).
- Add a small hint in top bar (e.g. `Tab: Panel`).
- **Reduce “wasted space”**:
- Tighten modal sizes and layout density (avoid giant empty margins).
- Ensure Build Catalog grid uses consistent padding and doesn’t overgrow.
- **Acceptance criteria**:
- New UI is visibly less grey/black and closer to Majesty quality.
- Right panel is not always present; Tab toggles it.
- `python tools/qa_smoke.py --quick` PASS.

### Workstream E — QA + visual proof (Owner: Agent 11)

- Add/refresh a focused checklist:
- Click-hitbox correctness (Build Buildings button + catalog grid)
- Display mode switching in Graphics menu
- Tab toggles right panel; no input bleed
- No crashes on startup
- Evidence:
- `python tools/qa_smoke.py --quick` PASS
- Screenshots: before/after UI comparables (use `.cursor/human_provided/week6-7 UI.JPG` + new captures)

## Files likely to change

- [`game/engine.py`](game/engine.py) (apply_display_settings, resize propagation, Tab toggle wiring)
- [`game/ui/hud.py`](game/ui/hud.py) (layout: right panel optional, top bar hint)
- [`game/ui/building_panel.py`](game/ui/building_panel.py) (Build Buildings button rect/coords)
- [`game/ui/build_catalog_panel.py`](game/ui/build_catalog_panel.py) (modal sizing + on_resize)
- [`game/ui/pause_menu.py`](game/ui/pause_menu.py) (modal sizing + on_resize)
- [`game/ui/widgets.py`](game/ui/widgets.py) (9-slice support)
- [`assets/ATTRIBUTION.md`](assets/ATTRIBUTION.md) + `assets/third_party/...` (UI pack licensing)

## Definition of Done (mid-sprint)

- **Bug fixes**: click hitboxes align; display mode switching is obvious.
- **UX**: right panel toggle via Tab; layout wastes less space.
- **Visuals**: CC0 UI art pack integrated and used for core panels/buttons.
- **Gates**: `python tools/qa_smoke.py --quick` PASS; manual 10-minute smoke in `--no-llm` and `--provider mock`.