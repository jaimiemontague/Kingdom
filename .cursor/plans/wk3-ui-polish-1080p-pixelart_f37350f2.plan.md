---
name: wk3-ui-polish-1080p-pixelart
overview: A 1–2 week sprint to ship a polished Majesty-inspired UI and a 1920×1080 borderless fullscreen default, plus replace placeholder shapes/letters with pixel-art sprites for all current heroes, enemies, and buildings using CC0/open-license packs (and original art where faster/better).
todos:
  - id: wk3-round1-lock
    content: Run Round 1 to lock UI layout spec, 1080p borderless behavior, asset conventions, and attribution rules
    status: completed
  - id: wk3-buildA-ui
    content: Implement borderless 1920x1080 default + new themed UI layout skeleton (top/bottom/right/minimap) with perf-safe widgets
    status: pending
    dependencies:
      - wk3-round1-lock
  - id: wk3-buildA-quit-button
    content: Add a clear, working Quit button in the HUD (top-left or top-right) so the player can exit reliably
    status: pending
    dependencies:
      - wk3-buildA-ui
  - id: wk3-buildA-closeable-panels
    content: "Make UI panels manageable: add an 'X' close button to hero details + debug/perf panels; move/reposition FPS/perf overlay to a less intrusive area"
    status: pending
    dependencies:
      - wk3-buildA-ui
  - id: wk3-buildB-assets
    content: Ingest CC0/open-license pixel art for all current heroes/enemies/buildings into existing sprite directories; add attribution files
    status: pending
    dependencies:
      - wk3-round1-lock
  - id: wk3-validation-qa
    content: Add asset presence validation + regression coverage; keep qa_smoke green
    status: pending
    dependencies:
      - wk3-buildA-ui
      - wk3-buildB-assets
---

# WK3 Sprint Plan — UI Polish + 1080p Borderless + Pixel-Art Pass

## Sprint goal

- **Presentation jump**: the game should open in a **1920×1080 borderless fullscreen** window by default and the UI should feel **Majesty-inspired and readable**, not like debug panels.
- **Visual identity**: heroes, enemies, and buildings should render with **pixel art sprites** (no more colored circles/letters), while preserving performance and determinism.

## Non-negotiables

- **Default display**: **borderless fullscreen at 1920×1080** (your choice).
- **Assets**: **CC0/open-license packs are allowed**, with a clean attribution file. Make original art where it’s faster/better.
- **No regressions**: `python tools/qa_smoke.py --quick` stays **PASS**.

---

## Current state (what the codebase already supports)

- Window size is currently fixed via `WINDOW_WIDTH/WINDOW_HEIGHT` in [`config.py`](config.py) and created in [`game/engine.py`](game/engine.py) via `pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))`.
- Sprite pipelines already exist with PNG-overrides:
- Heroes: [`game/graphics/hero_sprites.py`](game/graphics/hero_sprites.py) loads `assets/sprites/heroes/<class>/<action>/*.png` else procedural.
- Enemies: [`game/graphics/enemy_sprites.py`](game/graphics/enemy_sprites.py) loads `assets/sprites/enemies/<type>/<action>/*.png` else procedural.
- Buildings: [`game/graphics/building_sprites.py`](game/graphics/building_sprites.py) loads `assets/sprites/buildings/<type>/<state>/*.png` else procedural.

This sprint is primarily about **(1) window/UI layout + theme**, and **(2) populating asset folders + mapping states**.---

## Cadence (recommended)

- **Build A (Midweek)**: 1080p borderless + new UI layout skeleton + theme system + minimal icons + no new art dependency.
- **Build B (Endweek)**: asset ingestion pass (CC0) for heroes/enemies/buildings + UI polish + final perf pass.

---

## Definition of done

- Default launch opens **borderless 1920×1080** and UI is readable at that resolution.
- Core UI surfaces are themed (panels, buttons, typography) and consistent.
- UI is **manageable**: player can **Quit** via a visible HUD button, and key panels can be **closed** (X buttons) so they don’t cover the playfield.
- All current hero classes, current enemy types, and all placeable buildings render with **pixel art** when assets exist (fallbacks OK for missing frames).
- `python tools/qa_smoke.py --quick` passes.

---

## Workstreams & ownership (agents)

### Active agents (required)

- **Agent 2 (GameDirector_ProductOwner)**: acceptability/feel criteria (Majesty-like clarity), cuts.
- **Agent 3 (TechnicalDirector_Architecture)**: window/config + UI scaling contracts, safe file boundaries.
- **Agent 8 (UX_UI_Director)**: UI redesign owner (layout, typography, HUD composition, tooltips).
- **Agent 9 (ArtDirector_Pixel_Animation_VFX)**: art direction + original art where convenient; ensure cohesion.
- **Agent 12 (ToolsDevEx_Lead)**: asset import pipeline, validation scripts, attribution scaffolding.
- **Agent 10 (PerformanceStability_Lead)**: perf guardrails for UI + sprite loading.
- **Agent 11 (QA_TestEngineering_Lead)**: regression coverage (fullscreen/resolution sanity + asset presence checks + no-crash).
- **Agent 13 (SteamRelease_Ops_Marketing)**: attribution compliance + patch notes formatting.

### Consult-only (ping only if needed)

- **Agent 6 (AIBehaviorDirector_LLM)**: only if UI changes require new debug surfacing of hero state.

---

## Round-based delegation (explicit)

### Round 1 (async “meeting stage”)

Goal: lock **UI layout spec + window behavior + asset conventions + licensing rules**.

- **Agent 8** posts the proposed UI layout (Majesty-inspired): panel regions, minimap placement, bottom command bar, right info panel, tooltip rules.
- **Agent 3** posts display mode + scaling plan: borderless 1080p default, fallbacks for smaller screens, UI scale strategy.
- **Agent 12 + Agent 13** post asset ingestion + attribution standard (folder conventions, where to store LICENSE files, how to cite sources).
- **Agent 10** posts perf constraints (no per-frame allocations; sprite caching; load-time constraints).
- **Agent 2** approves “Majesty-like” acceptance criteria.

### Round 2 (Build A execution)

- Implement borderless 1080p default + UI layout skeleton + theme primitives.

### Round 3 (Build B execution)

- Ingest CC0/open-license packs into the existing sprite directories and wire any missing state mappings.

### Round 4 (wrap-up)

- Silent unless blocker; finalize patch notes and attribution.

---

## Build A scope (Midweek) — UI + 1080p

### Display/Resolution

- Add config + runtime behavior in [`config.py`](config.py) and [`game/engine.py`](game/engine.py):
- Default: borderless 1920×1080
- Fallback: if display is smaller, use display’s current resolution but keep borderless.
- Add a simple settings hook (later) but keep this sprint minimal.

### UI layout (Majesty-inspired)

Target structure (high level):

- **Top bar**: gold, day/wave, alerts.
- **Bottom command bar**: build/hire/bounty actions as icon buttons; tooltips + hotkeys.
- **Right info panel**: selected entity (hero/building) with portrait + stats + actions.
- **Bottom-left**: minimap + fog-of-war overlay and pings.

Implementation approach:

- Introduce a small UI framework:
- `game/ui/theme.py` (palette, spacing, fonts)
- `game/ui/widgets.py` (panel, icon button, tooltip, 9-slice)
- Refactor [`game/ui/hud.py`](game/ui/hud.py) and [`game/ui/building_panel.py`](game/ui/building_panel.py) to use it.

### UI manageability (new P0 usability polish)

- Add a **Quit** button in the HUD (top-left or top-right) that reliably exits the game.
- Add **close (X)** buttons for:
- hero details panel (selected hero/info panel)
- debug/perf overlays/panels (FPS readout / debug windows)
- Prefer **non-invasive defaults**:
- panels open when relevant but can be dismissed
- FPS/perf overlay should not cover key HUD regions (move it to a corner that doesn’t fight the top bar/right panel)

---

## Build B scope (Endweek) — Pixel art for everything visible

### Asset ingestion (CC0/open-license)

- Populate these directories with pack-processed PNGs:
- `assets/sprites/heroes/<warrior|ranger|rogue|wizard>/{idle,walk,attack,hurt,inside}/frame_###.png`
- `assets/sprites/enemies/<goblin|wolf|skeleton|...>/{idle,walk,attack,hurt,dead}/frame_###.png`
- `assets/sprites/buildings/<building_type>/{built,construction,damaged}/frame_###.png`

### Licensing & attribution (required)

- Add:
- `assets/ATTRIBUTION.md` (human-readable)
- `assets/third_party/<pack_name>/{LICENSE,README}.txt` (verbatim)
- A short section in patch notes crediting sources.

### Validation tools (required)

- Add a tool script (owned by Tools/QA) to verify:
- required folders exist
- at least one PNG is present per required state
- naming is sortable (`frame_000.png`)

---

## Prompts to send agents (copy/paste)

- **Agent 2 (GameDirector_ProductOwner)**: “Define acceptance criteria for the new UI (Majesty-like readability). What must be visible without clicking? What’s too noisy? Approve the new layout regions and icon-first control scheme.”
- **Agent 3 (TechnicalDirector_Architecture)**: “Propose the minimal implementation for default 1920×1080 borderless fullscreen + UI scaling strategy. Identify exact files and safe boundaries.”
- **Agent 8 (UX_UI_Director)**: “Own the UI redesign: layout spec (top/bottom/right/minimap), typography, tooltip rules, and a minimal widget/theme system. Keep perf safe (cache surfaces, no per-frame churn).”
- **Agent 9 (ArtDirector_Pixel_Animation_VFX)**: “Set art direction for the new UI skin and sprites. Where convenient, create original assets; otherwise pick CC0 packs that match. Provide a style guide (palette, outlines, shading).”
- **Agent 10 (PerformanceStability_Lead)**: “Perf guardrails for UI and sprite rendering/loading. Identify hotspots and add constraints/benchmarks to avoid regressions.”
- **Agent 11 (QA_TestEngineering_Lead)**: “Add regressions for: borderless 1080p launch sanity, UI not crashing at 1080p, and asset presence validation. Keep qa_smoke green.”
- **Agent 12 (ToolsDevEx_Lead)**: “Implement asset ingestion pipeline + validation script + folder conventions (heroes/enemies/buildings). Add attribution scaffolding paths for CC0 packs.”
- **Agent 13 (SteamRelease_Ops_Marketing)**: “Define attribution/credits standard for CC0/open-license assets (where to store license files, how to cite). Draft patch notes template section for credits.”

---

## Notes / constraints

- Keep Build A shippable without any new external assets.
- Build B can land lots of PNGs, but keep sprite sizes consistent (32×32 or scaled deterministically) and avoid load-time spikes.