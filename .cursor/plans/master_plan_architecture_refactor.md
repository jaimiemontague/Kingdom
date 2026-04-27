# Master Plan: Architecture Refactor (Post-v1.5)

**Status:** Draft — awaiting human approval before any sprint is planned.
**Rollback commit:** `48d11f7` (Docs: update README for v1.5.0) — tag this before starting Stage 0.
**Mandatory gate (every sprint, every stage):** `python tools/qa_smoke.py --quick` PASS + `python tools/validate_assets.py --report` exit 0.

---

## Why This Refactor Exists

Over 20+ sprints, Kingdom Sim grew from a single-file prototype to a 2,000-line God Object engine with a 2,000-line tightly-coupled 3D renderer bolted onto it. That worked — the game is playable and shipped v1.5. But every new feature now requires reading and understanding two massive files simultaneously, and the renderer bypasses the intended `get_game_state()` interface to read engine internals directly. The next major feature (animated 3D units, multiplayer, or a new building system) will hit this wall immediately.

This plan decomposes the codebase in vertical slices so that:
- The 3D renderer reads a clean snapshot, not raw engine fields
- The engine is split into a simulation core and a presentation layer
- Input handling no longer requires understanding the entire engine
- New features can be added by touching 2-3 files instead of 7+

**Non-goal:** This is not a rewrite. The simulation layer (`game/systems/`, `game/entities/`, `ai/`) is in good shape from the WK8 refactor and is preserved as-is. The refactor targets only the God Object boundaries and coupling patterns.

---

## Current Architecture (Before Refactor)

```
main.py
  |
  +-- [pygame path] GameEngine(input_manager=PygameInputManager()) -> engine.run()
  |
  +-- [ursina path] UrsinaApp(ai_factory)
                      |
                      +-- GameEngine(headless_ui=True) [creates engine internally]
                      +-- UrsinaRenderer(engine)       [holds raw engine ref]
                      +-- UrsinaApp.run()              [drives tick + render loop]
```

**The three problems:**

1. **GameEngine is a God Object** (1,850 lines, 50+ methods). It owns camera, display, UI panels, audio, VFX, fog, rendering, input delegation, and simulation — all in one class with three `__init__` branches.

2. **UrsinaRenderer bypasses the snapshot interface.** It accesses `self.engine.world` (7 sites), `self.engine._fog_revision` (2 sites), `self.engine.buildings` (2 sites), `self.engine.get_game_state()` (1 site), `self.engine.vfx_system` (1 site), and `self.engine.tax_collector` (1 site) — mixing snapshot reads with direct field reads.

3. **InputHandler has a bidirectional dependency with GameEngine.** `InputHandler.__init__(self, engine)` stores the full engine reference. Its methods call back into `engine.try_select_*`, `engine.place_building`, `engine.zoom_by`, `engine.pause_menu.*`, `engine.hud.*`, `engine.building_panel.*`, etc. — over 80 unique engine attribute accesses across 633 lines.

---

## File Map: Every File That Touches the Refactor

### Files That WILL Change (ordered by risk)

| File | Lines | Owner | Risk | What Changes |
|------|-------|-------|------|-------------|
| `game/engine.py` | 1,849 | Agent 03 | HIGH | Split into SimEngine + presentation; extract camera/display/render |
| `game/graphics/ursina_renderer.py` | 2,067 | Agent 03 | HIGH | Consume SimStateSnapshot instead of raw engine ref |
| `game/graphics/ursina_app.py` | 1,010 | Agent 03 | HIGH | Wire new snapshot interface; update engine access patterns |
| `game/input_handler.py` | 633 | Agent 03 | MEDIUM | Consume command interface instead of raw engine ref |
| `game/display_manager.py` | 314 | Agent 03 | MEDIUM | Decouple from engine; receive display state explicitly |
| `game/cleanup_manager.py` | 119 | Agent 03 | LOW | Receive entity lists explicitly instead of engine ref |
| `game/building_factory.py` | 71 | Agent 03 | LOW | No structural change; just import path updates if any |
| `main.py` | 113 | Agent 03 | LOW | Update wiring to new engine split |
| `tests/test_engine.py` | 52 | Agent 11 | LOW | Expand significantly with new integration tests |
| `game/ui/pause_menu.py` | 562 | Agent 08 | LOW | Remove `self.engine` ref; receive callbacks/state instead |
| `game/ui/building_panel.py` | 445 | Agent 08 | LOW | Remove `self.engine` assignment; receive data via params |
| `game/ui/building_renderers/economic_panel.py` | 333 | Agent 08 | LOW | Remove `getattr(panel, "engine", None)` pattern |

### Files That MUST NOT Change (preserve clean contracts)

| File | Lines | Why It Is Clean |
|------|-------|----------------|
| `ai/basic_ai.py` | 487 | Operates on `game_state` dict; no engine import |
| `ai/behaviors/*.py` | ~1,400 total | Pure functions on hero + game_state; deterministic |
| `game/systems/protocol.py` | 24 | `SystemContext` + `GameSystem` Protocol — the model |
| `game/systems/combat.py` | 354 | Uses `SystemContext`; no engine dependency |
| `game/systems/economy.py` | 88 | Pure system; no engine dependency |
| `game/systems/bounty.py` | 354 | Pure system; engine orchestrates externally |
| `game/systems/buffs.py` | 69 | Protocol-compliant; no engine dependency |
| `game/systems/spawner.py` | 146 | Receives `World` in constructor; no engine dependency |
| `game/systems/lairs.py` | 131 | Receives `World` in constructor; no engine dependency |
| `game/sim/contracts.py` | 81 | Lightweight dataclasses; the foundation for snapshots |
| `game/sim/determinism.py` | 52 | RNG isolation; do not touch |
| `game/sim/timebase.py` | 51 | Sim clock; do not touch |
| `game/events.py` | 101 | EventBus; clean, deterministic, keep as-is |
| `game/entities/*.py` | ~3,200 total | Entity classes; no engine dependency |
| `config.py` | 524 | Tuning constants; no structural changes |

### Files to Consolidate or Delete (Stage 5)

| File(s) | Lines | Action |
|---------|-------|--------|
| `scratch_debug_glb.py` through `scratch_debug_glb_6.py` | ~200 total | Delete after confirming no unique utility |
| `pm_wk17_restore.py`, `pm_wk22_*.py`, `pm_check_logs.py` | ~220 total | Archive to `tools/archive/` or delete |
| `extract_*.py`, `get_agent_responses.py` | ~80 total | Archive to `tools/archive/` or delete |
| `test_llm.py` (root) | 12 | Move to `tests/` or delete |

---

## Stage 0: Regression Baseline and Test Hardening

**Goal:** Before touching any production code, establish a test safety net that covers the paths currently untested — specifically the engine integration paths, the headless smoke path, and a basic renderer instantiation test.

**Definition of Done for Stage 0:**
- All new tests pass in `python -m pytest tests/`
- `python tools/qa_smoke.py --quick` still PASS
- No production code changed
- Git commit tagged as `pre-refactor-baseline`

### Task 0-A: Expand `test_engine.py` — Headless Integration Tests

**Assigned to:** Agent 11 (QA) — MEDIUM intelligence
**Why:** The current `test_engine.py` is 52 lines with 2 tests. It only checks `get_game_state()` keys and a peasant build loop. It does not test the full tick orchestration, the three `__init__` branches, or any rendering path.

**New tests to write (add to `tests/test_engine.py`):**

**Test 1: `test_engine_headless_init_creates_all_systems`**
Verify that `GameEngine(headless=True)` successfully creates all expected systems without crashing.

```python
def test_engine_headless_init_creates_all_systems():
    engine = GameEngine(headless=True)
    try:
        assert engine.headless is True
        assert engine.world is not None
        assert engine.combat_system is not None
        assert engine.economy is not None
        assert engine.spawner is not None
        assert engine.lair_system is not None
        assert engine.bounty_system is not None
        assert engine.buff_system is not None
        assert engine.building_factory is not None
        assert engine.event_bus is not None
        assert engine.cleanup_manager is not None
        # Headless should NOT have UI/audio/VFX
        assert engine.audio_system is None
        assert engine.vfx_system is None
        assert engine.input_handler is None
        # But should have null stubs that don't crash
        engine.hud.add_message("test", (255, 255, 255))  # NullStub absorbs
    finally:
        pygame.quit()
```

**Test 2: `test_engine_headless_ui_init_creates_ui_and_systems`**
Verify that `GameEngine(headless_ui=True)` (the Ursina path) creates both systems AND UI panels.

```python
def test_engine_headless_ui_init_creates_ui_and_systems():
    engine = GameEngine(headless=False, headless_ui=True)
    try:
        assert engine.headless_ui is True
        assert engine.world is not None
        assert engine.hud is not None
        assert engine.pause_menu is not None
        assert engine.input_handler is not None
        assert engine.audio_system is not None
        assert engine.vfx_system is not None
        assert engine.window_width == 1920
        assert engine.window_height == 1080
    finally:
        pygame.quit()
```

**Test 3: `test_engine_headless_tick_simulation_advances_sim_time`**
Verify that calling `tick_simulation` in headless mode advances the sim clock without crashing.

```python
def test_engine_headless_tick_simulation_advances_sim_time():
    engine = GameEngine(headless=True)
    try:
        initial_sim_ms = engine._sim_now_ms
        # Run 60 ticks (1 second at 60 Hz)
        for _ in range(60):
            engine.update(1 / 60)
        assert engine._sim_now_ms > initial_sim_ms
    finally:
        pygame.quit()
```

**Test 4: `test_engine_get_game_state_has_all_required_keys`**
Lock down the exact keys in `get_game_state()` so the refactor can verify backward compatibility.

```python
REQUIRED_GAME_STATE_KEYS = frozenset({
    "screen_w", "screen_h", "display_mode", "window_size",
    "gold", "heroes", "peasants", "guards", "enemies",
    "buildings", "buildings_construction_progress",
    "bounties", "bounty_system", "wave",
    "selected_hero", "selected_building", "selected_peasant",
    "castle", "economy", "world",
    "placing_building_type", "debug_ui",
    "micro_view_mode", "micro_view_building",
    "micro_view_quest_hero", "micro_view_quest_data",
    "right_panel_rect", "llm_available", "ui_cursor_pos",
})

def test_engine_get_game_state_has_all_required_keys():
    engine = GameEngine(headless=True)
    try:
        gs = engine.get_game_state()
        missing = REQUIRED_GAME_STATE_KEYS - set(gs.keys())
        assert not missing, f"Missing keys from get_game_state: {missing}"
    finally:
        pygame.quit()
```

**Test 5: `test_engine_full_tick_with_enemies_no_crash`**
Run the full update loop (unpatched spawner, combat, AI) for 300 ticks to verify no crashes in the full orchestration path.

```python
def test_engine_full_tick_with_enemies_no_crash():
    engine = GameEngine(headless=True)
    try:
        from ai.basic_ai import BasicAI
        engine.ai_controller = BasicAI(llm_brain=None)
        for _ in range(300):
            engine.update(1 / 60)
        # Should have spawned some enemies and not crashed
        assert engine._sim_now_ms > 0
    finally:
        pygame.quit()
```

### Task 0-B: Add `test_ursina_renderer_mock.py` — Renderer Snapshot Contract Test

**Assigned to:** Agent 11 (QA) — MEDIUM intelligence
**Why:** There are zero tests for `UrsinaRenderer`. We cannot safely refactor the renderer-engine boundary without a test that verifies the renderer can consume a state snapshot.

**Important:** This test does NOT instantiate Ursina (which requires a GPU). Instead, it verifies the *data contract* — that the renderer's `update()` method reads exactly the keys it needs from `get_game_state()`, and that those keys contain the right types.

Create new file `tests/test_renderer_snapshot_contract.py`:

```python
"""
Verify the data contract between GameEngine.get_game_state() and the renderer.

This does NOT instantiate Ursina or any GPU resources. It only checks that
get_game_state() provides the data shapes the renderer expects to consume.
"""
import pygame
from game.engine import GameEngine

# These are the keys UrsinaRenderer.update() reads from get_game_state().
# Extracted by grep of `gs["..."]` in ursina_renderer.py lines 1693-2067.
RENDERER_CONSUMED_KEYS = frozenset({
    "buildings",
    "heroes",
    "enemies",
    "peasants",
    "guards",
    "bounties",
})


def test_game_state_provides_renderer_consumed_keys():
    engine = GameEngine(headless=True)
    try:
        gs = engine.get_game_state()
        missing = RENDERER_CONSUMED_KEYS - set(gs.keys())
        assert not missing, f"Renderer needs keys missing from get_game_state: {missing}"
    finally:
        pygame.quit()


def test_game_state_entity_lists_are_iterable():
    engine = GameEngine(headless=True)
    try:
        gs = engine.get_game_state()
        for key in ("buildings", "heroes", "enemies", "peasants", "guards"):
            assert hasattr(gs[key], "__iter__"), f"gs['{key}'] must be iterable"
    finally:
        pygame.quit()


def test_buildings_have_required_renderer_attributes():
    """Every building must have the attributes the renderer reads."""
    engine = GameEngine(headless=True)
    try:
        gs = engine.get_game_state()
        for b in gs["buildings"]:
            assert hasattr(b, "building_type"), "building missing building_type"
            assert hasattr(b, "x"), "building missing x"
            assert hasattr(b, "y"), "building missing y"
            assert hasattr(b, "width"), "building missing width"
            assert hasattr(b, "height"), "building missing height"
            assert hasattr(b, "hp"), "building missing hp"
            assert hasattr(b, "max_hp"), "building missing max_hp"
            assert hasattr(b, "is_constructed"), "building missing is_constructed"
    finally:
        pygame.quit()
```

### Task 0-C: Document the `self.engine` Access Inventory

**Assigned to:** Agent 12 (Tools) — LOW intelligence
**Why:** Before the refactor, we need a machine-readable record of every `self.engine.X` access in `ursina_renderer.py` and `ursina_app.py`. This becomes the checklist for Stage 1.

**Deliverable:** A new file `docs/refactor/engine_access_inventory.md` listing every unique `self.engine.<attribute>` access in the renderer files, grouped by category (sim data, UI state, display state, fog state).

The inventory from the exploration (to be confirmed by Agent 12):

**UrsinaRenderer `self.engine` accesses (8 total sites):**
- `self.engine.world` — 7 sites (lines 864, 966, 1096, 1150, 1221, 1728, 1887): map dimensions, tiles, visibility grid
- `self.engine._fog_revision` — 2 sites (lines 968, 1097): fog dirty-check gate
- `self.engine.buildings` — 2 sites (lines 1162, 1230): castle anchor for debug grid, scatter exclusion
- `self.engine.get_game_state()` — 1 site (line 1715): the main per-frame snapshot
- `self.engine.tax_collector` — 1 site (line 1983): fallback for tax collector rendering
- `self.engine.vfx_system` — 1 site (line 2023): fallback for projectile list

**UrsinaApp `self.engine` accesses (30+ unique sites) — representative categories:**
- Simulation: `buildings`, `heroes`, `world`, `building_factory`, `event_bus`, `neutral_building_system`, `ai_controller`, `tax_collector`
- Camera/Display: `zoom`, `default_zoom`, `camera_x`, `camera_y`, `window_width`, `window_height`
- UI: `hud`, `pause_menu`, `screen`, `paused`, `running`
- Control: `tick_simulation(dt)`, `render_pygame()`, `zoom_by(...)`, `get_game_state()`
- Flags: `_ursina_viewer`, `_ursina_skip_world_render`, `_ursina_hud_force_upload`, `_ursina_window_fps_ema`

---

## Stage 1: SimState Snapshot Interface (Renderer Decoupling)

**Goal:** Create a structured, read-only snapshot object that replaces all `self.engine.*` accesses in `UrsinaRenderer`. After this stage, the renderer has zero direct engine references — it consumes a snapshot passed to `update()`.

**Risk:** LOW — no simulation logic changes. The renderer just reads data from a different source.

**Definition of Done for Stage 1:**
- `UrsinaRenderer.__init__` no longer takes `engine` as a parameter
- `UrsinaRenderer.update(snapshot)` takes a `SimStateSnapshot` instead of reading `self.engine`
- `self.engine` does not appear anywhere in `ursina_renderer.py`
- All existing tests pass; `qa_smoke --quick` PASS
- Manual verification: `python main.py --renderer ursina --no-llm` looks identical to pre-refactor

### Architecture Options for the Snapshot

**Option A: Frozen dataclass (RECOMMENDED)**

Create a new file `game/sim/snapshot.py` with a `@dataclass(frozen=True)` that contains every field the renderer needs. The engine builds this once per frame and passes it to `renderer.update(snapshot)`.

Pros:
- Type-safe, IDE-navigable, immutable
- Easy to test (construct a snapshot in tests without an engine)
- Natural serialization boundary for future multiplayer
- The renderer cannot accidentally mutate engine state

Cons:
- Requires copying entity lists (shallow copy is fine — entities are mutable, but the list itself is frozen)
- One more allocation per frame (negligible vs the 2,000-line render pass)

**Option B: Enhanced `get_game_state()` dict**

Extend the existing `get_game_state()` dict with the additional fields the renderer needs (`world`, `fog_revision`, `tax_collector`, `vfx_projectiles`). The renderer consumes `dict` instead of engine.

Pros:
- Minimal code change — `get_game_state()` already exists and the renderer already calls it once
- No new file needed

Cons:
- Dict access is not type-checked; a typo like `gs["biuldings"]` fails at runtime
- No immutability guarantee — the renderer could accidentally mutate the dict
- Harder for agents to know what fields are available without reading engine.py

**Option C: Protocol-based interface**

Define a `RendererDataSource` Protocol that the engine implements. The renderer calls methods like `source.get_buildings()`, `source.get_fog_revision()`, etc.

Pros:
- Maximum decoupling; mockable for tests
- Clean for future multiplayer (the "source" could be a network client)

Cons:
- Over-engineered for current needs (single-player, single-threaded)
- More boilerplate than the dataclass approach
- Per-method overhead vs a single snapshot copy

**Decision: Option A (frozen dataclass).** It gives us type safety, immutability, and testability with minimal overhead. The dict option is too loose for a codebase maintained by AI agents that benefit from typed contracts.

### Task 1-A: Create `game/sim/snapshot.py`

**Assigned to:** Agent 03 (Tech Director) — HIGH intelligence
**Why:** This is the architectural centerpiece of Stage 1. Getting the fields right means the renderer can be cleanly decoupled.

**Create `game/sim/snapshot.py`:**

```python
"""
Read-only simulation state snapshot for renderers and external consumers.

Built once per frame by the engine; consumed by UrsinaRenderer.update().
Immutable so renderers cannot accidentally mutate simulation state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class SimStateSnapshot:
    """
    Everything a renderer needs to draw one frame.

    Entity lists are shallow copies of the engine's live lists.
    Individual entities are still mutable (the renderer reads but must
    not write to them), but the list membership is frozen.
    """

    # --- Core entity lists (shallow-copied from engine) ---
    buildings: tuple  # tuple of Building objects
    heroes: tuple     # tuple of Hero objects
    enemies: tuple    # tuple of Enemy objects
    peasants: tuple   # tuple of Peasant objects
    guards: tuple     # tuple of Guard objects
    bounties: tuple   # tuple of Bounty objects (unclaimed)

    # --- World / map ---
    world: Any                # game.world.World instance (read-only access to tiles, visibility, dimensions)
    fog_revision: int = 0     # Incremented when fog grid changes; renderer uses for dirty-check

    # --- Economy / game state ---
    gold: int = 0
    wave: int = 0

    # --- Construction progress (parallel to buildings tuple) ---
    buildings_construction_progress: tuple = ()  # tuple of float in [0, 1]

    # --- Selection state (for UI highlights in 3D) ---
    selected_hero: Any = None
    selected_building: Any = None

    # --- Special entities ---
    castle: Any = None
    tax_collector: Any = None

    # --- VFX / projectiles ---
    vfx_projectiles: tuple = ()  # Active projectile events for 3D rendering

    # --- Display ---
    screen_w: int = 1920
    screen_h: int = 1080

    # --- Camera (needed by UrsinaApp for coordinate mapping) ---
    camera_x: float = 0.0
    camera_y: float = 0.0
    zoom: float = 1.0
    default_zoom: float = 1.0

    # --- UI state (needed by UrsinaApp for HUD/menu gating) ---
    paused: bool = False
    running: bool = True
    pause_menu_visible: bool = False
```

### Task 1-B: Add `build_snapshot()` Method to GameEngine

**Assigned to:** Agent 03 (Tech Director) — HIGH intelligence

**Add to `game/engine.py`:**

```python
def build_snapshot(self) -> "SimStateSnapshot":
    """Build a frozen snapshot of current sim state for the renderer."""
    from game.sim.snapshot import SimStateSnapshot

    castle = next(
        (b for b in self.buildings if getattr(b, "building_type", None) == "castle"),
        None,
    )

    vfx_projectiles = ()
    if self.vfx_system is not None:
        vfx_projectiles = tuple(getattr(self.vfx_system, "active_projectiles", []))

    return SimStateSnapshot(
        buildings=tuple(self.buildings),
        heroes=tuple(self.heroes),
        enemies=tuple(self.enemies),
        peasants=tuple(self.peasants),
        guards=tuple(self.guards),
        bounties=tuple(self.bounty_system.get_unclaimed_bounties()),
        world=self.world,
        fog_revision=getattr(self, "_fog_revision", 0),
        gold=self.economy.player_gold,
        wave=self.spawner.wave_number,
        buildings_construction_progress=tuple(
            float(getattr(b, "construction_progress", 1.0)) for b in self.buildings
        ),
        selected_hero=self.selected_hero,
        selected_building=getattr(self, "selected_building", None),
        castle=castle,
        tax_collector=self.tax_collector,
        vfx_projectiles=vfx_projectiles,
        screen_w=int(self.window_width),
        screen_h=int(self.window_height),
        camera_x=self.camera_x,
        camera_y=self.camera_y,
        zoom=self.zoom if self.zoom else 1.0,
        default_zoom=getattr(self, "default_zoom", 1.0),
        paused=self.paused,
        running=self.running,
        pause_menu_visible=bool(getattr(self.pause_menu, "visible", False)),
    )
```

### Task 1-C: Migrate UrsinaRenderer to Consume Snapshot

**Assigned to:** Agent 03 (Tech Director) — HIGH intelligence
**This is the core migration.** It must be done methodically, site by site.

**Step-by-step instructions for Agent 03:**

1. **Change the constructor signature:**
   - OLD: `def __init__(self, engine):`  →  `self.engine = engine`
   - NEW: `def __init__(self, world):` → `self._world = world`
   - The `world` parameter is needed at construction time for `_setup_scene_lighting()` which reads map dimensions. Pass `engine.world` from `UrsinaApp.__init__`.

2. **Change `update()` signature:**
   - OLD: `def update(self):`
   - NEW: `def update(self, snapshot: "SimStateSnapshot"):`
   - Replace `gs = self.engine.get_game_state()` (line 1715) with `gs = snapshot` (or access snapshot fields directly).

3. **Replace every `self.engine.world` access:**
   - In `_setup_scene_lighting` (line 864): use `self._world` (already set in constructor)
   - In `_ensure_fog_overlay` (line 966): use `snapshot.world` (passed through a helper or stored as `self._world`)
   - In `_sync_visibility_gated_terrain` (line 1096): use `self._world`
   - In `_ensure_grid_debug_overlay` (line 1150): use `self._world`
   - In `_build_3d_terrain` (line 1221): use `self._world`
   - In `update` lair visibility (line 1728): use `snapshot.world`
   - In `update` enemy visibility (line 1887): use `snapshot.world`

4. **Replace `self.engine._fog_revision`:**
   - In `_ensure_fog_overlay` (line 968): use `snapshot.fog_revision`
   - In `_sync_visibility_gated_terrain` (line 1097): use `snapshot.fog_revision`
   - Store the snapshot in `self._last_snapshot` at the start of `update()` so helper methods can access it.

5. **Replace `self.engine.buildings`:**
   - In `_ensure_grid_debug_overlay` (line 1162): use `snapshot.buildings`
   - In `_building_occupied_tiles` call (line 1230): change the function to accept a buildings list instead of engine.

6. **Replace `self.engine.tax_collector` and `self.engine.vfx_system`:**
   - Line 1983: use `snapshot.tax_collector`
   - Line 2023: use `snapshot.vfx_projectiles`

7. **Delete `self.engine` from the class entirely.** Search for `self.engine` — if any remain, you missed a site. There should be zero.

8. **Update `_building_occupied_tiles` module-level function:**
   - OLD: `def _building_occupied_tiles(engine):` reads `engine.buildings`
   - NEW: `def _building_occupied_tiles(buildings):` receives a sequence of buildings directly

### Task 1-D: Update UrsinaApp to Build and Pass Snapshot

**Assigned to:** Agent 03 (Tech Director) — HIGH intelligence

In `game/graphics/ursina_app.py`, the per-frame update currently calls `self.renderer.update()`. Change it to:

```python
# In UrsinaApp's update loop (around line 967):
snapshot = self.engine.build_snapshot()
self.renderer.update(snapshot)
```

Also update the constructor:
```python
# OLD (line 121):
self.renderer = UrsinaRenderer(self.engine)
# NEW:
self.renderer = UrsinaRenderer(self.engine.world)
```

**Note:** `UrsinaApp` itself still holds `self.engine` — that is intentional. `UrsinaApp` is the *application shell* that drives the game loop, manages the Ursina window, and routes input. It needs the full engine. The goal of Stage 1 is specifically to decouple the *renderer* (the 3D scene graph), not the app shell. `UrsinaApp` decoupling is Stage 2+.

### Task 1-E: Add Snapshot Tests

**Assigned to:** Agent 11 (QA) — LOW intelligence

Add to `tests/test_renderer_snapshot_contract.py`:

```python
from game.sim.snapshot import SimStateSnapshot

def test_snapshot_is_frozen():
    snap = SimStateSnapshot(
        buildings=(), heroes=(), enemies=(), peasants=(),
        guards=(), bounties=(), world=None,
    )
    import pytest
    with pytest.raises(AttributeError):
        snap.buildings = []  # Should fail — frozen

def test_engine_build_snapshot_returns_valid_snapshot():
    engine = GameEngine(headless=True)
    try:
        snap = engine.build_snapshot()
        assert isinstance(snap, SimStateSnapshot)
        assert len(snap.buildings) >= 1  # Castle
        assert snap.world is engine.world
        assert snap.fog_revision >= 0
        assert snap.castle is not None
    finally:
        pygame.quit()
```

### Things That Will Fight Stage 1

1. **`_building_occupied_tiles(self.engine)`** is a module-level function that takes the full engine. It must be changed to accept a buildings list. This is a 2-line fix but easy to miss.

2. **`_ensure_fog_overlay` and `_sync_visibility_gated_terrain` are called from `update()` but also from `_build_3d_terrain`.** The terrain build only runs once (guarded by `self._terrain_entity`), but it also reads `self.engine.world`. Solution: store `self._world` in the constructor and use it for one-shot terrain; use `snapshot.world` (which should be the same object) for per-frame fog/visibility.

3. **The `update()` method accesses `gs["buildings"]`, `gs["heroes"]`, etc. using dict keys from the old `get_game_state()`.** The snapshot uses attributes (`snapshot.buildings`). Agent 03 must replace `gs["buildings"]` with `snapshot.buildings` throughout the 400-line `update()` method. This is mechanical but tedious — do it systematically from top to bottom.

4. **`UrsinaApp` line 776** logs `len(getattr(self.engine, 'heroes', []))`. This is in UrsinaApp, not the renderer, so it stays as-is in Stage 1. But note it for Stage 2.

---

## Stage 2: GameEngine God Object Decomposition

**Goal:** Split `GameEngine` into two classes: `SimEngine` (pure simulation, headless-safe, no pygame display dependency beyond init) and `PresentationLayer` (camera, display, UI panels, rendering, audio, VFX). The simulation can run without any presentation.

**Risk:** HIGH — this touches the central class and changes the constructor/method split. Extensive use of the Stage 0 tests as a safety net.

**Definition of Done for Stage 2:**
- `SimEngine` can be instantiated and ticked without any UI, display, or audio code
- `PresentationLayer` wraps `SimEngine` and adds camera/display/UI/render
- The old `GameEngine` name still works (as an alias or as `PresentationLayer` itself) for backward compatibility
- All Stage 0 tests pass; `qa_smoke --quick` PASS
- Manual verification: both `python main.py` and `python main.py --renderer ursina --no-llm` work

### Architecture Options for the Split

**Option A: Clean two-class split (RECOMMENDED)**

```
SimEngine (game/sim_engine.py, ~600 lines)
  - __init__: world, entity lists, systems, event_bus, bounty, economy, AI hookpoint
  - setup_initial_state()
  - update(dt): the full sim tick (AI, heroes, enemies, combat, bounties, etc.)
  - get_game_state() -> dict
  - build_snapshot() -> SimStateSnapshot
  - No pygame imports. No UI. No camera. No display. No audio. No VFX.

PresentationLayer (game/engine.py, ~1200 lines, renamed from GameEngine)
  - __init__: creates SimEngine internally, then adds camera, display, UI, audio, VFX
  - Exposes sim.buildings, sim.heroes, etc. via properties or pass-through
  - Owns render(), run(), tick_simulation(), render_pygame()
  - Owns camera methods (update_camera, zoom_by, clamp_camera, screen_to_world)
  - Owns all UI panel creation and event routing
  - Owns audio subscription and VFX
```

Pros:
- SimEngine is independently testable (no pygame display needed)
- Clean boundary: sim logic vs. presentation
- `SimEngine` becomes the natural multiplayer authority object
- Backward compatible: `PresentationLayer` or a `GameEngine = PresentationLayer` alias keeps old imports working

Cons:
- Large refactor; many methods move between files
- Need to carefully trace which methods are "sim" vs. "presentation"
- The `update()` method has interleaved sim and presentation calls that must be untangled

**Option B: Mixin / composition inside GameEngine**

Keep `GameEngine` as the single class but extract subsystems into composed objects: `CameraController`, `DisplayController`, `UIManager`, `AudioController`. GameEngine creates them in `__init__` and delegates.

Pros:
- No file split; less risk of import breakage
- Incremental: extract one concern at a time

Cons:
- GameEngine remains a God Object that just delegates more
- Not actually decoupled — it still owns everything, just through intermediaries
- Harder to test SimEngine in isolation (it's not a separate class)

**Option C: Thin GameEngine facade that composes SimEngine + PresentationLayer**

```
GameEngine (facade):
  self.sim = SimEngine(...)
  self.presentation = PresentationLayer(self.sim, ...)
  def run(self): self.presentation.run()
```

Pros:
- Three clear objects; facade provides backward compatibility
- SimEngine is independently testable
- PresentationLayer is independently swappable (pygame vs ursina)

Cons:
- Three classes where two would suffice
- The facade adds no real value over Option A's alias

**Decision: Option A (two-class split).** It's the simplest path to a testable sim engine. The facade (Option C) adds unnecessary indirection for a single-player game.

### What Moves to SimEngine vs. What Stays

**Moves to SimEngine (`game/sim_engine.py`):**

From `GameEngine.__init__` (lines 57-263):
- `headless` flag, sim seed, `_sim_now_ms`, time multiplier
- `world`, `event_bus`
- Entity lists: `buildings`, `heroes`, `enemies`, `bounties`, `peasants`, `guards`
- All systems: `combat_system`, `economy`, `spawner`, `lair_system`, `neutral_building_system`, `buff_system`, `bounty_system`, `building_factory`
- Selection state: `selected_building`, `selected_hero`, `selected_peasant`
- `ai_controller`, `tax_collector`, `peasant_spawn_timer`
- Early pacing nudge state and logic

From `GameEngine` methods:
- `setup_initial_state()` (lines 372-404)
- `_update_fog_of_war()` (lines 265-370) — fog is sim-authoritative
- `_build_system_context()` (line 821)
- `update()` and ALL its sub-methods: `_update_ai_and_heroes`, `_update_world_systems`, `_update_peasants`, `_update_enemies`, `_update_guards`, `_spawn_enemies`, `_apply_entity_separation`, `_process_combat`, `_route_combat_events`, `_cleanup_after_combat`, `_process_bounties`, `_update_neutral_systems`, `_update_buildings`
- `get_game_state()` (lines 1369-1414)
- `build_snapshot()` (from Stage 1)
- `try_hire_hero()` (lines 523-575) — this is sim logic (gold, entity creation)
- `place_building()` (lines 577-606) — sim logic
- `place_bounty()` (lines 608-638) — sim logic
- `_maybe_apply_early_pacing_nudge()` (lines 658-717) — sim logic
- `_nearest_lair_to()` (lines 640-656) — sim helper
- `send_player_message()` / `_poll_conversation_response()` — borderline; LLM is a sim-adjacent concern. Keep in SimEngine since it affects hero behavior.

**Stays in PresentationLayer (`game/engine.py`):**

- Camera state and methods: `camera_x`, `camera_y`, `zoom`, `default_zoom`, `update_camera`, `clamp_camera`, `center_on_castle`, `screen_to_world`, `set_zoom`, `zoom_by`
- Display: `display_mode`, `window_size`, `display_manager`, `screen`, `window_width`, `window_height`, `_view_surface`, `_scaled_surface`, `_pause_overlay`, `apply_display_settings`, `request_display_settings`
- UI panel creation and state: `hud`, `micro_view`, `building_menu`, `building_list_panel`, `debug_panel`, `dev_tools_panel`, `building_panel`, `pause_menu`, `build_catalog_panel`
- Input: `input_handler`, `input_manager`
- Audio: `audio_system`
- VFX: `vfx_system`
- Rendering: `render()`, `render_perf_overlay()`, `render_pygame()`, `_render_hero_minimap()`
- Perf overlay state
- `cleanup_manager` (borderline — it touches both sim entities and UI panels; stays in presentation but receives sim entities from SimEngine)
- `tick_simulation()` — orchestrates sim.update() + handle_events()
- `run()` — the main loop
- `capture_screenshot()`
- `handle_events()` — delegates to input_handler

**The key wiring in PresentationLayer.__init__:**

```python
class PresentationLayer:
    def __init__(self, early_nudge_mode=None, input_manager=None, headless=False, headless_ui=False):
        # Create the simulation core
        self.sim = SimEngine(early_nudge_mode=early_nudge_mode)

        # ... camera, display, UI setup ...

        # Expose sim properties for backward compatibility
        # (InputHandler, UI panels, etc. still read engine.buildings, engine.heroes)
    
    @property
    def buildings(self):
        return self.sim.buildings
    
    @property
    def heroes(self):
        return self.sim.heroes
    
    # ... etc. for all entity lists and systems ...
```

This property-forwarding pattern means existing code that reads `engine.buildings` keeps working without changes. The properties can be removed gradually as downstream code is migrated to use `sim` directly.

### Things That Will Fight Stage 2

1. **`_route_combat_events()` (lines 995-1048) mixes sim logic with HUD messages.** It calls `self.hud.add_message()` directly from inside what should be pure sim code. **Solution:** The SimEngine version emits events to the EventBus instead of calling HUD methods. PresentationLayer subscribes to those events and shows HUD messages. This follows the existing pattern for audio/VFX.

2. **`try_hire_hero()` calls `self.hud.add_message()`.** Same pattern: emit an event, PresentationLayer shows the message.

3. **`place_building()` calls `self.building_menu.cancel_selection()`.** The building menu is UI. **Solution:** `place_building()` in SimEngine creates the building and returns it. PresentationLayer calls `sim.place_building()` and then updates UI.

4. **`_update_render_animations()` (lines 1147-1169) is presentation, but it's called inside `update()`.** It must stay in PresentationLayer's tick, called after `sim.update()`.

5. **`_finalize_update()` (lines 1171-1211) mixes EventBus flush (sim) with HUD update and VFX update (presentation).** Split: SimEngine flushes the event bus. PresentationLayer updates HUD and VFX after.

6. **`cleanup_manager` holds an engine reference and accesses `engine.hud`, `engine.buildings`, `engine.building_panel`.** It needs to be split: sim cleanup (remove from entity lists) happens in SimEngine; UI cleanup (deselect panels, show messages) happens in PresentationLayer.

7. **The `headless_ui` code path (Ursina).** Currently, `GameEngine(headless_ui=True)` creates BOTH sim and UI in one class. After the split, `UrsinaApp` will create `SimEngine` directly and manage its own presentation. This actually simplifies `UrsinaApp` — it no longer needs the engine's render() method at all for world drawing.

### Agent Instructions for Stage 2

**Agent 03 (Tech Director) — HIGH intelligence — is the sole implementer.**

The recommended implementation order within Stage 2:

1. Create `game/sim_engine.py` with an empty `SimEngine` class that has the same `__init__` signature as `GameEngine(headless=True)`.
2. Move entity list creation and system creation from `GameEngine.__init__` to `SimEngine.__init__`, one block at a time. After each move, run `python tools/qa_smoke.py --quick`.
3. Move `setup_initial_state()` to SimEngine.
4. Move `update()` and all `_update_*` sub-methods to SimEngine. Replace `self.hud.add_message()` calls with `self.event_bus.emit()` calls using a new event type (e.g., `HUD_MESSAGE`).
5. Move `get_game_state()` and `build_snapshot()` to SimEngine.
6. In `GameEngine` (now `PresentationLayer`), create `self.sim = SimEngine(...)` and add `@property` forwarding for backward compatibility.
7. Subscribe PresentationLayer to `HUD_MESSAGE` events to restore HUD messages.
8. Run the full test suite and manual smoke.

**Do NOT attempt to do this in a single pass.** Each numbered step above is a separate commit point. If any step breaks tests, fix it before proceeding.

---

## Stage 3: Input Handler Decoupling

**Goal:** Break the `InputHandler` ↔ `GameEngine` bidirectional dependency so that `InputHandler` operates through a command/callback interface instead of holding a raw engine reference.

**Risk:** MEDIUM — input routing is complex (633 lines, ~80 engine accesses) but well-isolated in one file.

**Definition of Done for Stage 3:**
- `InputHandler.__init__` no longer takes a `GameEngine` parameter
- `InputHandler` operates through a `GameCommands` protocol or callback set
- Adding a new input action does not require reading `engine.py`
- All tests pass; `qa_smoke --quick` PASS
- Manual verification: all hotkeys, mouse actions, and panel interactions work in both renderers

### Architecture Options

**Option A: Command Protocol (RECOMMENDED)**

Define a `GameCommands` Protocol that exposes the actions `InputHandler` needs to invoke. `PresentationLayer` implements it. `InputHandler` calls `self.commands.place_bounty()` instead of `self.engine.place_bounty()`.

```python
class GameCommands(Protocol):
    def place_bounty(self) -> None: ...
    def try_hire_hero(self) -> None: ...
    def place_building(self, grid_x: int, grid_y: int) -> None: ...
    def try_select_hero(self, screen_pos: tuple) -> bool: ...
    def try_select_building(self, screen_pos: tuple) -> bool: ...
    def zoom_by(self, factor: float) -> None: ...
    def center_on_castle(self, reset_zoom: bool = False) -> None: ...
    def capture_screenshot(self) -> None: ...
    # ... etc.
```

Pros:
- Clean separation: `InputHandler` depends on an interface, not a concrete class
- Testable: mock the protocol in tests
- New input actions only need the protocol method added, not engine.py reading

Cons:
- Large protocol surface (~20-25 methods)
- Two-step: add to protocol, then implement in engine

**Option B: Callback dict**

Pass a dict of `str -> Callable` to `InputHandler`.

Pros:
- No new class/protocol file
- Very flexible

Cons:
- No type safety; misspelled key = silent failure
- Hard for agents to discover available actions

**Decision: Option A (Command Protocol).** Type safety matters for AI agents. The protocol acts as documentation.

### Implementation Notes for Agent 03

The `InputHandler` currently reads both **action methods** (e.g., `engine.place_bounty()`) and **state** (e.g., `engine.paused`, `engine.pause_menu.visible`, `engine.hud._chat_panel`). The protocol must expose both:

- **Actions:** `place_bounty`, `try_hire_hero`, `zoom_by`, etc.
- **State queries:** `is_paused() -> bool`, `is_pause_menu_visible() -> bool`, `is_chat_active() -> bool`, `get_selected_hero()`, etc.
- **UI delegation:** `handle_hud_click(pos, game_state)`, `toggle_panel(name)`, etc.

The goal is NOT to eliminate all state queries — it's to make them go through a defined interface instead of arbitrary `engine.attr` access.

---

## Stage 4: Render Method Extraction

**Goal:** Extract the 200-line `render()` method from `PresentationLayer` into a standalone `PygameRenderer` class that mirrors `UrsinaRenderer` — both consume `SimStateSnapshot` and produce visual output.

**Risk:** MEDIUM — the render method is large but self-contained. The main risk is the interleaving of world rendering with UI panel rendering.

**Definition of Done for Stage 4:**
- `PresentationLayer.render()` delegates to `PygameRenderer.render(snapshot)` for world/entity rendering
- UI panel rendering stays in PresentationLayer (it needs panel references)
- The Pygame path and Ursina path share the same `SimStateSnapshot` contract
- All tests pass; `qa_smoke --quick` PASS

### What Gets Extracted

**Moves to `PygameRenderer` (`game/graphics/pygame_renderer.py`):**
- World rendering (`self.world.render(view_surface, camera_offset)`)
- Building rendering loop (`renderer_registry.render_building`)
- Enemy rendering with fog visibility check
- Hero rendering
- Guard, peasant, tax collector rendering
- Bounty rendering
- VFX rendering
- Fog overlay rendering
- View surface scaling / zoom logic

**Stays in PresentationLayer:**
- HUD rendering (`hud.render(screen, game_state)`)
- Panel rendering (debug, dev tools, building panel, build catalog, pause menu)
- Perf overlay
- Pause overlay

This split means both renderers (Pygame and Ursina) consume `SimStateSnapshot` for world/entity rendering, while the UI layer (which is always Pygame-based) stays in the presentation layer.

---

## Stage 5: Cleanup, Consolidation, and Definition of Done

**Goal:** Clean up root directory scripts, verify the full test suite, update documentation, and declare the refactor complete.

### Task 5-A: Root Script Consolidation

Move or delete the following from the project root:
- `scratch_debug_glb*.py` (7 files) — delete after confirming no unique utility
- `pm_*.py` (5 files) — archive to `tools/archive/` or delete
- `extract_*.py` (4 files) — archive to `tools/archive/` or delete
- `test_llm.py` — move to `tests/` or delete
- `get_agent_responses.py` — archive

### Task 5-B: Update Agent Onboarding Rules

Update `.cursor/rules/02-project-layout.mdc` to reflect the new file structure (SimEngine, PresentationLayer, snapshot, GameCommands protocol).

### Task 5-C: Final Integration Test Pass

Run the complete gate stack:
1. `python tools/determinism_guard.py` — PASS
2. `python tools/qa_smoke.py --quick` — PASS (includes pytest + headless scenarios)
3. `python tools/validate_assets.py --report` — 0 errors
4. Manual smoke: `python main.py --no-llm` for 10 minutes
5. Manual smoke: `python main.py --renderer ursina --no-llm` for 10 minutes
6. Manual smoke: `python main.py --provider mock` for 5 minutes

### Global Definition of Done for the Entire Refactor

The refactor is complete when ALL of the following are true:

- [ ] `GameEngine` God Object is decomposed into `SimEngine` + `PresentationLayer`
- [ ] `UrsinaRenderer` has zero `self.engine` references — consumes `SimStateSnapshot` only
- [ ] `InputHandler` operates through `GameCommands` protocol, not raw engine reference
- [ ] `PresentationLayer.render()` world rendering is extracted to `PygameRenderer`
- [ ] Root directory has no scratch/debug scripts
- [ ] `python tools/qa_smoke.py --quick` PASS
- [ ] `python tools/validate_assets.py --report` 0 errors
- [ ] `python main.py --no-llm` runs 10 minutes without crashes
- [ ] `python main.py --renderer ursina --no-llm` runs 10 minutes without crashes
- [ ] `tests/test_engine.py` has 5+ integration tests covering headless, headless_ui, tick, and snapshot
- [ ] `tests/test_renderer_snapshot_contract.py` verifies snapshot immutability and required fields
- [ ] Agent onboarding rules updated to reflect new architecture
- [ ] CHANGELOG.md updated (version bump is Jaimie's call)

---

## Sprint Cadence Guidance for Agent 01

This plan is organized into stages, not fixed sprints. Each stage may take 1-3 sprints depending on complexity and issues discovered during implementation. The recommended cadence:

**Stage 0:** 1 sprint (test writing only, no production changes)
**Stage 1:** 1-2 sprints (snapshot + renderer migration)
**Stage 2:** 2-3 sprints (God Object decomposition — the big one)
**Stage 3:** 1 sprint (input handler decoupling)
**Stage 4:** 1 sprint (render extraction)
**Stage 5:** 1 sprint (cleanup and verification)

**Total estimated: 7-11 sprints.**

Between stages, Jaimie should playtest and confirm the game feels identical. Each stage has its own Definition of Done that can be verified independently. If a stage is taking too long, it can be split into smaller rounds. If a stage turns out to be unnecessary (e.g., Stage 4 render extraction may be deferred), it can be skipped.

---

## Agent Assignment Summary

| Stage | Primary Agent | Intelligence | Supporting Agents |
|-------|--------------|-------------|-------------------|
| 0 | Agent 11 (QA) | MEDIUM | Agent 12 (Tools, LOW) for inventory doc |
| 1 | Agent 03 (Tech) | HIGH | Agent 11 (QA, LOW) for snapshot tests |
| 2 | Agent 03 (Tech) | HIGH | Agent 11 (QA, MEDIUM) for integration tests |
| 3 | Agent 03 (Tech) | HIGH | Agent 08 (UX, LOW) for UI panel decoupling |
| 4 | Agent 03 (Tech) | MEDIUM | — |
| 5 | Agent 12 (Tools) | LOW | Agent 01 (PM) for rule updates, Agent 13 for CHANGELOG |
