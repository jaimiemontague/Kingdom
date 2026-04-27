# Engine Access Inventory (Ursina bridge)

This doc records every direct engine field/method access from the Ursina bridge files, as a checklist for refactor stages that remove `self.engine` coupling.

Scope:
- `game/graphics/ursina_renderer.py`
- `game/graphics/ursina_app.py`

Legend:
- **direct**: `self.engine.<attr>` / `engine.<attr>`
- **guarded**: `getattr(self.engine, ...)` / `hasattr(self.engine, ...)`

---

## `UrsinaRenderer` (`game/graphics/ursina_renderer.py`)

### World / map data
- **direct**: `self.engine.world` (many sites)

### Fog dirty-check state
- **guarded**: `getattr(self.engine, "_fog_revision", 0)`

### Entities / lists
- **guarded**: `getattr(self.engine, "buildings", [])`

### Snapshot interface
- **direct**: `self.engine.get_game_state()`

### Special entities
- **guarded**: `getattr(self.engine, "tax_collector", None)`

### VFX
- **guarded**: `getattr(self.engine, "vfx_system", None)`

---

## `UrsinaApp` (`game/graphics/ursina_app.py`)

### One-time bridge/control flags (Ursina path)
- **direct**: `self.engine._ursina_viewer = True`
- **direct**: `self.engine._ursina_skip_world_render = True`

### AI wiring
- **direct**: `self.engine.ai_controller = ai_controller_factory()`

### Entities / lists / systems (editor/debug helpers)
These appear in helper functions that take a local `engine` parameter.

- **direct**: `engine.buildings` (iterate/append)
- **direct**: `engine.heroes` (append; `len(engine.heroes)`)
- **direct**: `engine.world`
- **direct**: `engine.event_bus` (passed into `set_event_bus`)
- **direct**: `engine.building_factory`
- **direct**: `engine._fog_revision = int(getattr(engine, "_fog_revision", 0)) + 1` (fog bump)
- **guarded**: `getattr(self.engine, "buildings", [])`
- **guarded**: `getattr(self.engine, "heroes", [])` (logged length)

### Rendering / surface upload (HUD blit path)
- **direct**: `self.engine.screen` (read surface)
- **direct**: `self.engine.render_pygame()` (draw HUD + panels into `engine.screen`)
- **guarded**: `getattr(self.engine, "_ursina_hud_force_upload", False)` (force upload)

### HUD / UI messaging
- **guarded**: `hasattr(self.engine, "hud")` and `self.engine.hud`
- **direct**: `self.engine.hud.add_message(...)`

### Simulation loop integration
- **direct**: `self.engine.tick_simulation(dt)`
- **guarded**: `getattr(self.engine, "running", True)` (quit handling / loop exit)

---

## `InputHandler` + `GameCommands` (WK38 Stage 3)

`game/input_handler.py` no longer references `GameEngine` at runtime. It holds `self.commands: GameCommands` and uses a local `c` handle to the same object for all event handling.

- **Protocol + default implementation:** `game/game_commands.py` — `GameCommands` (Protocol) and `EngineBackedGameCommands` (delegates to the real `GameEngine` in `engine.py` when wiring the default path).
- **Wiring:** `GameEngine` constructs `InputHandler(EngineBackedGameCommands(self))` in `game/engine.py`.
- **DoD / grep (sprint R3):** `self.engine` and `engine = self.engine` must not appear in `game/input_handler.py` (use your search tool of choice; `rg` in the plan is the same check).
- **Tests:** `tests/test_input_handler_gamecommands.py` — mock `GameCommands` / `SimpleNamespace` to assert QUIT, affordance, and `H` hotkey call the command surface only.

Other code (Ursina, etc.) may still use `engine` as a local or `self.engine` on their own types; this section is only the **input** decoupling story.

---

## `PygameRenderer` + `GameEngine.render` (WK39 Stage 4)

- **Contract:** Each frame, `GameEngine.build_snapshot()` produces a read-only `SimStateSnapshot`; `PygameRenderer.render_world(screen, snapshot, ...)` draws terrain → entities → fog → bounty pipeline into the zoom/view surface (or bounty-metrics-only when `skip_pygame_world` for Ursina HUD composite).
- **Non-snapshot refs:** `PygameWorldRenderContext` holds `renderer_registry`, `bounty_system`, `vfx_system`, `building_menu`, `building_list_panel`, `economy`.
- **Stays on `GameEngine`:** HUD, building panel, build catalog, pause menu, perf overlay, pause tint; hero-focus minimap still orchestrates rect/blit from `render()`, map pixels shared via `PygameRenderer.render_minimap_contents`.
- **Tests:** `tests/test_pygame_renderer_wk39.py` — imports, snapshot wiring, `skip_pygame_world` smoke (full-frame pygame raster stays covered by `qa_smoke --quick`).

---

## `BuildingPanel` (post–REFACTOR-TECH-001)

- `game/ui/building_panel.py` does **not** store `self.engine`. Ursina HUD re-upload is requested via optional `on_request_ursina_hud_upload: Callable[[], None] | None` (wired from `GameEngine._request_ursina_hud_upload` in `engine.py`).
- `game/ui/building_renderers/economic_panel.py` calls that callback via `_request_live_hud_upload_for_ursina(panel)` (no `getattr(panel, "engine", ...)`).

---

## WK41 mechanical splits (readability; no API contract change)

- **`game/engine_facades/camera_display.py`** — `EngineCameraDisplay`: camera/zoom, display apply, screenshot (`GameEngine` delegates one-liners).
- **`game/engine_facades/render_coordinator.py`** — `EngineRenderCoordinator`: pygame composite `render`, hero-focus minimap, perf overlay (`GameEngine` delegates).
- **`game/engine_facades/__init__.py`** — re-exports the two facades.
- **`game/graphics/ursina_coords.py`**, **`ursina_environment.py`**, **`ursina_prefabs.py`**, **`ursina_units_anim.py`** — leaf helpers split out of `ursina_renderer.py` (Track A1).
- **`game/graphics/ursina_terrain_fog_collab.py`** — `UrsinaTerrainFogCollab`: terrain root, fog, visibility-gated props, grid debug (when wired on branch using collaborators).
- **`game/graphics/ursina_entity_render_collab.py`** — `UrsinaEntityRenderCollab`: billboard/prefab/3D building entity sync helpers (same).
- **`game/graphics/ursina_renderer.py`** — `UrsinaRenderer.update()` delegates snapshot sync to `_sync_snapshot_*` helpers + `_update_debug_status_text` / `_destroy_removed_entities` (Track A3 / R4); renderer owns `_entities` / `_unit_anim_state` / lighting fields as before.
