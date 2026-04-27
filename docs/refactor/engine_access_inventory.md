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

