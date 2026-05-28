# WK63 Sprint Plan — Engine Boundary Cleanup

**Created:** 2026-05-28 | **PM:** Agent 01 | **Current version:** Prototype v1.5.9 (pre-close)
**Sprint ID:** `wk63_engine_boundary_cleanup`
**Source:** `.cursor/plans/GPT 5.5 Codebase Improvements Recommendations.md` items 3, 5, 7
**Execution model:** Claude Code parent Agent 1 coordinates role-based subagents. No orchestrator.
**Depends on:** Sprint `wk62_architecture_cleanup_baseline` (committed `6ea09b0`)

---

## Goals

1. **Replace wall-clock pathfinding budget with deterministic expansion-count budget** (audit item 3)
2. **Split `GameCommands` into narrow Protocol-based command ports** (audit item 5)
3. **Move selection state out of `SimEngine` into presentation-owned `SelectionState`, converting to entity IDs** (audit item 7)

## Non-Goals

- Do not rewrite InputHandler's UI subsystem access pattern (the `c.hud.*`, `c.pause_menu.*` passthroughs stay for now)
- Do not split InputHandler into multiple files
- Do not add 3D selection highlighting to the Ursina renderer
- Do not touch AI, graphics rendering, or audio systems

## Definition of Done

- `python -m pytest tests/ -x -q` PASS (all tests pass)
- `python tools/determinism_guard.py` PASS
- `python tools/qa_smoke.py --quick` PASS
- Pathfinding decisions use deterministic expansion counts, not wall-clock time
- Selection state lives in `game/presentation/selection_state.py`, not in SimEngine
- All entity types have stable string IDs
- `GameCommands` is replaced by 4+ narrow Protocol interfaces
- InputHandler no longer accesses `commands._engine` directly

---

## Architecture Context

### Current State (post-WK62)

```
InputHandler --[GameCommands Protocol (43 members, 30 Any)]--> EngineBackedGameCommands --> GameEngine
                                                                                            |
                                                                  GameEngine.selected_hero = self.sim.selected_hero  (forwarding)
                                                                                            |
                                                                  SimEngine.selected_hero/building/enemy/peasant (object references)
```

### Target State (post-WK63)

```
InputHandler --[CameraCommands]--> GameEngine
             --[SelectionCommands]--> SelectionState (presentation-owned, stores entity IDs)
             --[PlacementCommands]--> GameEngine
             --[MenuCommands]--> GameEngine (still broad, but typed)
             --[GameStateCommands]--> GameEngine

PathfindingBudget: counts A* expansions per frame (deterministic), not wall-clock ms
```

---

## Wave Structure

```
Wave 0: Baseline Tests (Agent 11)
    |
    v
Wave 1 (parallel, no file overlap):
    Agent 03: Entity IDs + SelectionState
    Agent 04: Deterministic pathfinding budget
    |
    v
Gate 1: Agent 11 verifies both
    |
    v
Wave 2: GameCommands Protocol Split (Agent 03)
    |
    v
Gate 2: Agent 11 + Agent 04 verify
```

---

## Wave 0 — Baseline Characterization Tests

**Owner:** Agent 11 (QA_TestEngineering_Lead)
**Intelligence:** HIGH (writing novel characterization tests)

### Task: Add tests that prove current behavior before changes

Create `tests/test_wk63_engine_boundary.py` with the following tests. Each test documents current behavior so Wave 1/2 agents have a regression net.

**Files you may edit:** `tests/test_wk63_engine_boundary.py` (new)
**Files you must not edit:** `game/**`, `ai/**`, `config.py`, `tools/**`

#### Test 1: Pathfinding budget enforcement

```python
def test_pathfinding_budget_exhaustion_returns_empty_path():
    """When budget is exhausted, compute_path_worldpoints returns []."""
    from game.systems.navigation import (
        get_pathfinding_budget, compute_path_worldpoints
    )
    from game.engine import GameEngine
    import pygame

    engine = GameEngine(headless=True)
    try:
        budget = get_pathfinding_budget()
        budget.begin_frame()

        # Exhaust the budget by setting _frame_ms_used above MAX_MS_PER_FRAME
        budget._frame_ms_used = budget.MAX_MS_PER_FRAME + 1.0

        result = compute_path_worldpoints(
            engine.sim.world, engine.sim.buildings,
            100.0, 100.0,  # start
            500.0, 500.0,  # goal
        )
        assert result == [], f"Expected empty path when budget exhausted, got {result}"
    finally:
        pygame.quit()
```

#### Test 2: Pathfinding budget resets each frame

```python
def test_pathfinding_budget_resets_each_frame():
    """begin_frame() resets the per-frame budget counters."""
    from game.systems.navigation import get_pathfinding_budget

    budget = get_pathfinding_budget()
    budget._frame_ms_used = 999.0
    budget._frame_plans = 999

    budget.begin_frame()

    assert budget._frame_ms_used == 0.0
    assert budget._frame_plans == 0
```

#### Test 3: Selection mutual exclusivity

```python
def test_selection_is_mutually_exclusive():
    """Selecting one entity type clears the others."""
    from game.engine import GameEngine
    import pygame

    engine = GameEngine(headless=True)
    try:
        hero = engine.sim.heroes[0] if engine.sim.heroes else None
        if hero is None:
            pytest.skip("No heroes in headless engine")

        engine.selected_hero = hero
        assert engine.selected_hero is hero

        # Selecting a building should clear hero (if buildings exist)
        buildings = [b for b in engine.sim.buildings
                     if getattr(b, "building_type", "") != "castle"]
        if buildings:
            b = buildings[0]
            engine.selected_building = b
            engine.selected_peasant = None
            engine.selected_enemy = None
            # Note: the engine does NOT automatically clear selected_hero
            # when you set selected_building -- that's done by try_select_building().
            # This test documents the current manual clearing pattern.
    finally:
        pygame.quit()
```

#### Test 4: GameCommands interface completeness

```python
def test_game_commands_has_all_expected_members():
    """GameCommands protocol exposes the expected interface."""
    from game.game_commands import GameCommands
    import inspect

    members = {name for name, _ in inspect.getmembers(GameCommands)
               if not name.startswith("__")}

    # These are the members that must exist for InputHandler to work
    required = {
        "zoom_by", "center_on_castle", "camera_x", "camera_y", "zoom",
        "selected_hero", "selected_building", "selected_peasant", "selected_enemy",
        "try_select_hero", "try_select_building", "try_select_peasant",
        "try_select_enemy", "try_select_hero_at_world",
        "try_select_tax_collector", "try_select_guard",
        "place_building", "get_game_state",
        "running", "paused", "display_mode",
        "hud", "pause_menu", "building_menu",
    }
    missing = required - members
    assert not missing, f"GameCommands missing: {missing}"
```

#### Test 5: Entity ID existence check (documents current state)

```python
def test_hero_has_stable_id():
    """Heroes have a hero_id string attribute."""
    from game.engine import GameEngine
    import pygame

    engine = GameEngine(headless=True)
    try:
        for hero in engine.sim.heroes:
            assert hasattr(hero, "hero_id"), "Hero missing hero_id"
            assert isinstance(hero.hero_id, str), f"hero_id should be str, got {type(hero.hero_id)}"
            assert len(hero.hero_id) > 0, "hero_id should not be empty"
    finally:
        pygame.quit()


def test_buildings_lack_stable_id():
    """Buildings currently lack entity_id — this test documents the gap.
    When Wave 1 adds entity_id, change this test to assert it exists.
    """
    from game.engine import GameEngine
    import pygame

    engine = GameEngine(headless=True)
    try:
        for b in engine.sim.buildings:
            has_id = hasattr(b, "entity_id") and b.entity_id is not None
            if has_id:
                # Wave 1 has landed — update this test
                assert isinstance(b.entity_id, str)
            # else: expected gap, no assertion failure
    finally:
        pygame.quit()
```

**Verification:**

```powershell
python -m pytest tests/test_wk63_engine_boundary.py -x -v
python -m pytest tests/ -x -q
python tools/qa_smoke.py --quick
```

---

## Wave 1A — Entity IDs + Selection State Migration

**Owner:** Agent 03 (TechnicalDirector_Architecture)
**Intelligence:** HIGH (novel architecture, cross-system design)

### Overview

Add stable string IDs to all entity types, then move selection state from SimEngine into a presentation-owned SelectionState that stores IDs instead of object references.

**Files you may edit:**
- `game/entities/buildings/base.py` (add entity_id)
- `game/entities/enemy.py` (add entity_id)
- `game/entities/peasant.py` (add entity_id)
- `game/entities/guard.py` (add entity_id)
- `game/presentation/selection_state.py` (new)
- `game/sim_engine.py` (remove selected_* fields)
- `game/engine.py` (own SelectionState, update get_game_state/build_snapshot)
- `game/cleanup_manager.py` (update selection clearing)
- `game/sim/snapshot.py` (update selected fields to use IDs)
- `tests/test_engine_sim_boundary.py` (if needed)
- `tests/test_wk63_engine_boundary.py` (update entity ID tests)

**Files you must not edit:**
- `game/graphics/**` (except snapshot consumption if needed)
- `game/ui/**`
- `ai/**`
- `config.py`
- `game/game_commands.py` (that's Wave 2)
- `game/input_handler.py` (that's Wave 2)

### Task 1: Add entity_id to Building, Enemy, Peasant, Guard

Each entity type needs a stable string ID assigned at construction time. Follow the existing hero pattern.

**Building base class** — read `game/entities/buildings/base.py` and find the `Building.__init__` method. Add:

```python
# At the top of the file, add a module-level counter:
_next_building_id = 0

def _allocate_building_id() -> str:
    global _next_building_id
    _next_building_id += 1
    return f"b{_next_building_id:08d}"

# In Building.__init__, add near the top:
    self.entity_id: str = _allocate_building_id()
```

**Enemy** — read `game/entities/enemy.py` and find `Enemy.__init__`. Add:

```python
_next_enemy_id = 0

def _allocate_enemy_id() -> str:
    global _next_enemy_id
    _next_enemy_id += 1
    return f"e{_next_enemy_id:08d}"

# In Enemy.__init__:
    self.entity_id: str = _allocate_enemy_id()
```

**Peasant** — read `game/entities/peasant.py` and find `Peasant.__init__`. Add:

```python
_next_peasant_id = 0

def _allocate_peasant_id() -> str:
    global _next_peasant_id
    _next_peasant_id += 1
    return f"p{_next_peasant_id:08d}"

# In Peasant.__init__:
    self.entity_id: str = _allocate_peasant_id()
```

**Guard** — read `game/entities/guard.py` and find `Guard.__init__`. Add:

```python
_next_guard_id = 0

def _allocate_guard_id() -> str:
    global _next_guard_id
    _next_guard_id += 1
    return f"g{_next_guard_id:08d}"

# In Guard.__init__:
    self.entity_id: str = _allocate_guard_id()
```

**Important:** Heroes already have `hero_id` (format `"h00000001"`). Do NOT add a separate `entity_id` to heroes — use `hero_id` as their entity ID. The SelectionState will use `hero_id` for heroes and `entity_id` for everything else.

### Task 2: Create SelectionState

Create `game/presentation/selection_state.py`:

```python
"""Presentation-owned selection state. Stores entity IDs, not live object references.

The sim never reads or writes this. GameEngine owns the instance and populates
get_game_state() / build_snapshot() from it. InputHandler writes to it through
GameCommands (or directly after Wave 2).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass(slots=True)
class SelectionState:
    """Tracks which entity the player has selected.

    Selection is mutually exclusive across entity types:
    setting one clears the others. The exception is that
    selected_building_id can coexist with selected_hero_id
    (the HUD shows building in right panel and hero in left).
    """

    selected_hero_id: Optional[str] = None
    selected_building_id: Optional[str] = None
    selected_enemy_id: Optional[str] = None
    selected_peasant_id: Optional[str] = None

    def select_hero(self, hero_id: str) -> None:
        """Select a hero. Clears enemy and peasant selection."""
        self.selected_hero_id = hero_id
        self.selected_enemy_id = None
        self.selected_peasant_id = None

    def select_building(self, building_id: str) -> None:
        """Select a building. Clears enemy and peasant selection."""
        self.selected_building_id = building_id
        self.selected_enemy_id = None
        self.selected_peasant_id = None

    def select_enemy(self, enemy_id: str) -> None:
        """Select an enemy. Clears hero and peasant selection."""
        self.selected_hero_id = None
        self.selected_enemy_id = enemy_id
        self.selected_peasant_id = None

    def select_peasant(self, peasant_id: str) -> None:
        """Select a peasant. Clears hero and enemy selection."""
        self.selected_hero_id = None
        self.selected_peasant_id = peasant_id
        self.selected_enemy_id = None

    def clear_hero(self) -> None:
        self.selected_hero_id = None

    def clear_building(self) -> None:
        self.selected_building_id = None

    def clear_enemy(self) -> None:
        self.selected_enemy_id = None

    def clear_peasant(self) -> None:
        self.selected_peasant_id = None

    def clear_all(self) -> None:
        self.selected_hero_id = None
        self.selected_building_id = None
        self.selected_enemy_id = None
        self.selected_peasant_id = None

    def on_entity_destroyed(self, entity_id: str) -> None:
        """Clear selection if the destroyed entity was selected."""
        if self.selected_hero_id == entity_id:
            self.selected_hero_id = None
        if self.selected_building_id == entity_id:
            self.selected_building_id = None
        if self.selected_enemy_id == entity_id:
            self.selected_enemy_id = None
        if self.selected_peasant_id == entity_id:
            self.selected_peasant_id = None
```

### Task 3: Migrate GameEngine to use SelectionState

**In `game/engine.py`:**

1. Import SelectionState at the top:
   ```python
   from game.presentation.selection_state import SelectionState
   ```

2. In `GameEngine.__init__`, create the SelectionState instance:
   ```python
   self.selection = SelectionState()
   ```

3. Replace the property forwarding block (currently around lines 540-569 that forward to `self.sim.selected_*`) with properties that use SelectionState + lookup:

   ```python
   @property
   def selected_hero(self):
       if self.selection.selected_hero_id is None:
           return None
       for h in self.sim.heroes:
           if h.hero_id == self.selection.selected_hero_id:
               return h
       self.selection.selected_hero_id = None  # stale reference
       return None

   @selected_hero.setter
   def selected_hero(self, v):
       if v is None:
           self.selection.clear_hero()
       else:
           self.selection.select_hero(v.hero_id)

   @property
   def selected_building(self):
       if self.selection.selected_building_id is None:
           return None
       for b in self.sim.buildings:
           if getattr(b, "entity_id", None) == self.selection.selected_building_id:
               return b
       self.selection.selected_building_id = None
       return None

   @selected_building.setter
   def selected_building(self, v):
       if v is None:
           self.selection.clear_building()
       else:
           self.selection.select_building(v.entity_id)

   @property
   def selected_enemy(self):
       if self.selection.selected_enemy_id is None:
           return None
       for e in self.sim.enemies:
           if getattr(e, "entity_id", None) == self.selection.selected_enemy_id:
               return e
       self.selection.selected_enemy_id = None
       return None

   @selected_enemy.setter
   def selected_enemy(self, v):
       if v is None:
           self.selection.clear_enemy()
       else:
           self.selection.select_enemy(v.entity_id)

   @property
   def selected_peasant(self):
       if self.selection.selected_peasant_id is None:
           return None
       for p in self.sim.peasants:
           if getattr(p, "entity_id", None) == self.selection.selected_peasant_id:
               return p
       self.selection.selected_peasant_id = None
       return None

   @selected_peasant.setter
   def selected_peasant(self, v):
       if v is None:
           self.selection.clear_peasant()
       else:
           self.selection.select_peasant(v.entity_id)
   ```

   **IMPORTANT:** These property getters do a linear scan of the entity lists. This is acceptable because selection lookup happens a few times per frame (not per entity). Do NOT optimize with a dict cache in this sprint — keep it simple.

4. Remove `selected_hero`, `selected_building`, `selected_peasant`, `selected_enemy` from `SimEngine.__init__` (lines 123-127 of sim_engine.py).

5. In `SimEngine.get_game_state()` (around line 400): Remove the lines that read `self.selected_hero`, `self.selected_building`, `self.selected_peasant` from SimEngine. The caller (GameEngine.get_game_state()) will populate these from its own `self.selected_*` properties.

6. In `GameEngine.get_game_state()` (around line 1498-1523): Make sure the dict is populated from `self.selected_hero`, `self.selected_building`, `self.selected_peasant`, `self.selected_enemy` (which now use SelectionState lookups). This should largely already work since GameEngine was forwarding to SimEngine before — just verify the patching at line 1520 for `selected_enemy` still works.

7. In `SimEngine.build_snapshot()` (around line 457): Remove the `selected_hero` and `selected_building` parameters or populate them from GameEngine instead. If the snapshot is only built by GameEngine, have GameEngine set these fields after snapshot construction:
   ```python
   snap = self.sim.build_snapshot(...)
   snap.selected_hero = self.selected_hero
   snap.selected_building = self.selected_building
   ```

8. In `SimEngine._cleanup_destroyed_buildings()` (around line 898): Remove the selection clearing lines (`if self.selected_building is building: self.selected_building = None`). Instead, use the event bus — the BUILDING_DESTROYED event already fires, and GameEngine can listen for it and call `self.selection.on_entity_destroyed(building.entity_id)`.

9. In `game/cleanup_manager.py` (around line 62): Same — replace `engine.selected_building = None` with `engine.selection.on_entity_destroyed(building.entity_id)` or just remove it since the sim-side cleanup now handles this.

### Task 4: Update Wave 0 tests

After entity IDs are added, update the `test_buildings_lack_stable_id` test in `tests/test_wk63_engine_boundary.py` to assert that `entity_id` exists and is a string.

Add a new test:

```python
def test_selection_state_stores_ids_not_objects():
    """SelectionState stores string IDs, not entity references."""
    from game.presentation.selection_state import SelectionState

    sel = SelectionState()
    sel.select_hero("h00000001")
    assert sel.selected_hero_id == "h00000001"
    assert isinstance(sel.selected_hero_id, str)

    sel.select_building("b00000001")
    assert sel.selected_building_id == "b00000001"
    assert sel.selected_enemy_id is None  # cleared by select_building

    sel.on_entity_destroyed("b00000001")
    assert sel.selected_building_id is None  # cleared
```

### Verification

```powershell
python -m pytest tests/test_engine_sim_boundary.py tests/test_wk63_engine_boundary.py tests/test_engine.py -x -v
python -m pytest tests/ -x -q
python tools/determinism_guard.py
python tools/qa_smoke.py --quick
```

The key acceptance criteria:
- All 4 boundary tests from WK62 still PASS
- All new WK63 tests PASS
- Selection works end-to-end (qa_smoke observe_sync scenarios exercise hero selection)
- Entity IDs are stable strings on all entity types

---

## Wave 1B — Deterministic Pathfinding Budget

**Owner:** Agent 04 (NetworkingDeterminism_Lead)
**Intelligence:** HIGH (determinism reasoning)

### Overview

Replace the wall-clock `time.perf_counter()` pathfinding budget in `game/systems/navigation.py` with a deterministic expansion-count budget. Keep `perf_counter()` for metrics/observability only — it must not gate gameplay decisions.

**Files you may edit:**
- `game/systems/navigation.py`
- `game/systems/pathfinding.py`
- `game/systems/perf_stats.py`
- `game/sim_engine.py` (only the `begin_frame()` call)
- `tests/test_wk63_engine_boundary.py` (update pathfinding tests)
- New: `tests/test_pathfinding_budget.py`

**Files you must not edit:**
- `game/engine.py` (Agent 03 owns this in Wave 1A)
- `game/entities/**`
- `game/graphics/**`
- `game/ui/**`
- `ai/**`
- `config.py`

### Task 1: Create deterministic PathfindingBudget

Open `game/systems/navigation.py`. Find the `PathfindingBudget` class (starts around line 21). Currently it looks like:

```python
class PathfindingBudget:
    MAX_MS_PER_FRAME = 3.0

    def __init__(self):
        self._frame_start = 0.0
        self._frame_ms_used = 0.0
        self._frame_plans = 0
        self._pending = []

    def begin_frame(self):
        self._frame_start = _time.perf_counter()
        self._frame_ms_used = 0.0
        self._frame_plans = 0

    def budget_available(self):
        return self._frame_ms_used < self.MAX_MS_PER_FRAME

    def record_time(self, ms):
        self._frame_ms_used += ms
        self._frame_plans += 1
```

Replace with this deterministic version:

```python
class PathfindingBudget:
    """Deterministic per-frame pathfinding budget.

    Budget is measured in A* node expansions, not wall-clock time.
    This ensures identical gameplay regardless of hardware speed.
    Wall-clock timing is still collected for perf metrics but does
    not gate whether a path request is served.
    """

    MAX_PLANS_PER_FRAME: int = 12
    MAX_EXPANSIONS_PER_FRAME: int = 24_000

    def __init__(self) -> None:
        self._frame_plans: int = 0
        self._frame_expansions: int = 0
        # Metrics only (not used for budget decisions):
        self._frame_ms_used: float = 0.0

    def begin_frame(self) -> None:
        self._frame_plans = 0
        self._frame_expansions = 0
        self._frame_ms_used = 0.0

    def budget_available(self) -> bool:
        return (
            self._frame_plans < self.MAX_PLANS_PER_FRAME
            and self._frame_expansions < self.MAX_EXPANSIONS_PER_FRAME
        )

    def record_plan(self, expansions: int, wall_ms: float = 0.0) -> None:
        """Record one completed path plan.

        Args:
            expansions: Number of A* nodes expanded (from find_path return).
            wall_ms: Wall-clock time for metrics only.
        """
        self._frame_plans += 1
        self._frame_expansions += expansions
        self._frame_ms_used += wall_ms
```

**Key constants:**
- `MAX_PLANS_PER_FRAME = 12` — limits per-frame plan count. Current game has ~8 heroes + ~10 enemies + ~5 guards + ~2 tax collectors = ~25 entities, but most don't replan every frame (heroes have 400ms replan cooldown). 12 plans per frame is generous.
- `MAX_EXPANSIONS_PER_FRAME = 24_000` — limits total A* work. Each plan expands up to `max_expansions` nodes (default 8000, dynamically scaled). 24,000 allows 3 max-length plans or many short ones.

### Task 2: Make find_path return expansion count

Open `game/systems/pathfinding.py`. Find the `find_path()` function. Currently it returns `list` (the path). It internally tracks an `expansions` counter that is checked against `max_expansions`.

Change the return type to include the expansion count. The cleanest way is to return a tuple:

```python
def find_path(
    world,
    start: tuple,
    goal: tuple,
    buildings: list = None,
    *,
    max_expansions: int = 8000,
) -> tuple[list, int]:
    """Returns (path, expansions_used).

    path: list of (grid_x, grid_y) tuples, or [] if no path found.
    expansions_used: number of A* nodes expanded (for budget tracking).
    """
```

Find every `return` statement in `find_path()` and change it:
- Where it returns `[]` (no path found), change to `return [], expansions` (or `return [], 0` if the counter hasn't started yet)
- Where it returns the reconstructed path, change to `return path, expansions`
- Find the variable name used for the expansion counter — it may be called `expansions` or `nodes_expanded` or similar. Read the code to find it.

**CRITICAL:** Also update `grid_to_world_path()` — it does NOT call `find_path()` so it does not need changes.

**Also update `LayerPathfinder.find_layer_path()`** if it calls `find_path()` — it needs to handle the new tuple return. Read the code to check.

### Task 3: Update compute_path_worldpoints to use deterministic budget

Open `game/systems/navigation.py`. Find `compute_path_worldpoints()` (around line 100). Currently it:

1. Checks `budget.budget_available()` — returns `[]` if exhausted
2. Calls `time.perf_counter()` before `find_path()`
3. Calls `find_path()`
4. Calls `time.perf_counter()` after to compute `dt_ms`
5. Calls `budget.record_time(dt_ms)`

Change to:

```python
def compute_path_worldpoints(
    world,
    buildings: list,
    start_x: float, start_y: float,
    goal_x: float, goal_y: float,
) -> list[tuple[float, float]]:
    budget = get_pathfinding_budget()
    if not budget.budget_available():
        return []

    # Convert world coords to grid
    gx1, gy1 = int(start_x) // TILE_SIZE, int(start_y) // TILE_SIZE
    gx2, gy2 = int(goal_x) // TILE_SIZE, int(goal_y) // TILE_SIZE

    # Wall-clock timing for metrics only (does NOT gate budget)
    t0 = time.perf_counter()
    grid_path, expansions = find_path(world, (gx1, gy1), (gx2, gy2), buildings)
    t1 = time.perf_counter()
    wall_ms = (t1 - t0) * 1000.0

    # Record using deterministic expansion count
    budget.record_plan(expansions, wall_ms)

    # Update perf stats (observability)
    perf_stats.pathfinding.calls += 1
    perf_stats.pathfinding.total_ms += wall_ms
    if not grid_path:
        perf_stats.pathfinding.failures += 1
        return []

    return grid_to_world_path(grid_path)
```

The key change: `budget.record_plan(expansions, wall_ms)` instead of `budget.record_time(dt_ms)`. The budget decision uses `expansions` (deterministic), while `wall_ms` is recorded for perf dashboards only.

### Task 4: Update perf_stats to track expansions

Open `game/systems/perf_stats.py`. Add an `expansions` field to the pathfinding stats:

```python
@dataclass
class _PathStats:
    calls: int = 0
    failures: int = 0
    total_ms: float = 0.0
    total_expansions: int = 0  # NEW: total A* nodes expanded this frame
```

Then in `compute_path_worldpoints()`, also record:
```python
perf_stats.pathfinding.total_expansions += expansions
```

### Task 5: Add deterministic budget tests

Create or extend `tests/test_pathfinding_budget.py`:

```python
def test_budget_gates_on_expansion_count_not_time():
    """Budget exhaustion depends on expansion count, not wall-clock time."""
    from game.systems.navigation import PathfindingBudget

    budget = PathfindingBudget()
    budget.begin_frame()

    # Record plans with high wall-clock time but low expansions
    budget.record_plan(expansions=100, wall_ms=999.0)
    assert budget.budget_available(), (
        "Budget should still be available: only 100 expansions used, "
        "even though wall_ms is 999"
    )

    # Now exhaust the expansion budget
    budget.record_plan(expansions=PathfindingBudget.MAX_EXPANSIONS_PER_FRAME, wall_ms=0.1)
    assert not budget.budget_available(), (
        "Budget should be exhausted after MAX_EXPANSIONS_PER_FRAME expansions"
    )


def test_budget_gates_on_plan_count():
    """Budget also limits number of plans per frame."""
    from game.systems.navigation import PathfindingBudget

    budget = PathfindingBudget()
    budget.begin_frame()

    for i in range(PathfindingBudget.MAX_PLANS_PER_FRAME):
        assert budget.budget_available(), f"Budget should be available at plan {i}"
        budget.record_plan(expansions=1, wall_ms=0.01)

    assert not budget.budget_available(), (
        "Budget should be exhausted after MAX_PLANS_PER_FRAME plans"
    )


def test_budget_resets_each_frame():
    """begin_frame() resets all counters."""
    from game.systems.navigation import PathfindingBudget

    budget = PathfindingBudget()
    budget.begin_frame()
    budget.record_plan(expansions=99999, wall_ms=99999.0)
    assert not budget.budget_available()

    budget.begin_frame()
    assert budget.budget_available()
    assert budget._frame_plans == 0
    assert budget._frame_expansions == 0
    assert budget._frame_ms_used == 0.0


def test_find_path_returns_expansion_count():
    """find_path() returns (path, expansions) tuple."""
    from game.systems.pathfinding import find_path
    from game.engine import GameEngine
    import pygame

    engine = GameEngine(headless=True)
    try:
        world = engine.sim.world
        result = find_path(world, (10, 10), (15, 15), engine.sim.buildings)
        assert isinstance(result, tuple), f"find_path should return tuple, got {type(result)}"
        assert len(result) == 2, f"find_path should return (path, expansions), got len={len(result)}"
        path, expansions = result
        assert isinstance(path, list)
        assert isinstance(expansions, int)
        assert expansions >= 0
    finally:
        pygame.quit()
```

### Verification

```powershell
python -m pytest tests/test_pathfinding_budget.py -x -v
python -m pytest tests/test_wk63_engine_boundary.py -x -v
python -m pytest tests/ -x -q
python tools/determinism_guard.py
python tools/qa_smoke.py --quick
```

The key acceptance criteria:
- Budget decisions use expansion counts, not wall-clock time
- `find_path()` returns `(path, expansions)` tuple
- `time.perf_counter()` is only used for metrics, never for budget gating
- All callers of `find_path()` handle the new tuple return
- `determinism_guard.py` passes

---

## Gate 1 — Agent 11 Verification

**Owner:** Agent 11 (QA_TestEngineering_Lead)
**Intelligence:** LOW (running known commands and checking results)

Run all gates and verify Agent 03 + Agent 04 work:

```powershell
python -m pytest tests/ -x -q
python tools/determinism_guard.py
python tools/qa_smoke.py --quick
```

Also grep-verify:
- `entity_id` exists on Building, Enemy, Peasant, Guard classes
- `SelectionState` is imported and used in GameEngine
- `time.perf_counter` in navigation.py is only used inside a metrics block, not for budget decisions
- `find_path` returns a tuple

---

## Wave 2 — GameCommands Protocol Split

**Owner:** Agent 03 (TechnicalDirector_Architecture)
**Intelligence:** HIGH (novel architecture, cross-system design)

### Overview

Replace the monolithic `GameCommands` Protocol (43 members, 30 `Any`) with 5 narrow Protocol interfaces. Update `InputHandler` to accept the narrow ports.

**Files you may edit:**
- `game/game_commands.py` (rewrite)
- `game/input_handler.py` (update constructor + usage)
- `game/engine.py` (wire new command implementations)
- `tests/test_input_handler_gamecommands.py` (update mocks)
- `tests/test_wk63_engine_boundary.py` (update interface test)

**Files you must not edit:**
- `game/graphics/**`, `game/ui/**`, `ai/**`, `config.py`

### Task 1: Define the Protocol interfaces

Replace the content of `game/game_commands.py` with these Protocol definitions. Keep the file path the same to minimize import changes.

```python
"""Narrow command ports for InputHandler.

Each Protocol defines one responsibility domain. GameEngine implements
all of them through EngineBackedXxxCommands classes. InputHandler accepts
the protocols it needs, not a monolithic interface.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Any, Optional, Protocol, Tuple, Union, runtime_checkable

if TYPE_CHECKING:
    pass


@runtime_checkable
class CameraCommands(Protocol):
    """Camera position and zoom control."""

    @property
    def camera_x(self) -> float: ...
    @property
    def camera_y(self) -> float: ...
    @property
    def zoom(self) -> float: ...
    def zoom_by(self, factor: float) -> None: ...
    def center_on_castle(self, reset_zoom: bool = True) -> None: ...


@runtime_checkable
class SelectionCommands(Protocol):
    """Entity selection state and try-select methods."""

    @property
    def selected_hero(self) -> Any: ...
    @selected_hero.setter
    def selected_hero(self, v: Any) -> None: ...

    @property
    def selected_building(self) -> Any: ...
    @selected_building.setter
    def selected_building(self, v: Any) -> None: ...

    @property
    def selected_peasant(self) -> Any: ...
    @selected_peasant.setter
    def selected_peasant(self, v: Any) -> None: ...

    @property
    def selected_enemy(self) -> Any: ...
    @selected_enemy.setter
    def selected_enemy(self, v: Any) -> None: ...

    def try_select_hero(self, pos: Any) -> bool: ...
    def try_select_hero_at_world(self, wx: float, wy: float, radius: float = 24.0) -> bool: ...
    def try_select_tax_collector(self, pos: Any) -> bool: ...
    def try_select_guard(self, pos: Any) -> bool: ...
    def try_select_peasant(self, pos: Any) -> bool: ...
    def try_select_enemy(self, pos: Any) -> bool: ...
    def try_select_building(self, pos: Any) -> bool: ...


@runtime_checkable
class PlacementCommands(Protocol):
    """Building placement, economy checks, demolition."""

    @property
    def economy(self) -> Any: ...
    @property
    def buildings(self) -> Any: ...
    @property
    def world(self) -> Any: ...
    @property
    def building_menu(self) -> Any: ...
    @property
    def building_list_panel(self) -> Any: ...
    @property
    def build_catalog_panel(self) -> Any: ...
    @property
    def building_panel(self) -> Any: ...

    def place_building(self, *args: Any) -> None: ...


@runtime_checkable
class MenuCommands(Protocol):
    """UI panels, menus, overlays, audio, dev tools."""

    @property
    def hud(self) -> Any: ...
    @property
    def pause_menu(self) -> Any: ...
    @property
    def debug_panel(self) -> Any: ...
    @property
    def dev_tools_panel(self) -> Any: ...
    @property
    def micro_view(self) -> Any: ...
    @property
    def audio_system(self) -> Any: ...
    @property
    def input_manager(self) -> Any: ...

    @property
    def show_perf(self) -> bool: ...
    @show_perf.setter
    def show_perf(self, v: bool) -> None: ...

    def apply_hud_pin_action(self, action: str) -> None: ...
    def capture_screenshot(self) -> None: ...
    def send_player_message(self, *args: Any) -> None: ...


@runtime_checkable
class GameStateCommands(Protocol):
    """Game lifecycle, display settings, state queries."""

    @property
    def running(self) -> bool: ...
    @running.setter
    def running(self, v: bool) -> None: ...

    @property
    def paused(self) -> bool: ...
    @paused.setter
    def paused(self, v: bool) -> None: ...

    @property
    def display_mode(self) -> str: ...
    @property
    def window_size(self) -> Any: ...

    def get_game_state(self) -> dict: ...
    def apply_display_settings(self, display_mode: str, window_size: Any) -> None: ...
    def request_display_settings(self, display_mode: str, window_size: Any = None) -> None: ...
    def try_hire_hero(self) -> None: ...
    def place_bounty(self) -> None: ...

    # Engine-private hooks still needed by InputHandler for window drag, speed, etc.
    @property
    def _skip_event_processing_frames(self) -> int: ...
    @_skip_event_processing_frames.setter
    def _skip_event_processing_frames(self, v: int) -> None: ...

    @property
    def _borderless_drag_active(self) -> bool: ...
    @_borderless_drag_active.setter
    def _borderless_drag_active(self, v: bool) -> None: ...

    @property
    def _borderless_drag_start_pos(self) -> Any: ...
    @_borderless_drag_start_pos.setter
    def _borderless_drag_start_pos(self, v: Any) -> None: ...

    @property
    def _borderless_drag_window_offset(self) -> Any: ...
    @_borderless_drag_window_offset.setter
    def _borderless_drag_window_offset(self, v: Any) -> None: ...

    @property
    def _last_ui_cursor_pos(self) -> Any: ...
    @_last_ui_cursor_pos.setter
    def _last_ui_cursor_pos(self, v: Any) -> None: ...

    @property
    def _speed_before_pause(self) -> Any: ...
    @_speed_before_pause.setter
    def _speed_before_pause(self, v: Any) -> None: ...

    @property
    def _perf_close_rect(self) -> Any: ...

    def process_command(self, cmd: str) -> None: ...
```

**Note:** The `_` prefixed engine-private hooks stay in `GameStateCommands` for now. They are ugly but needed by InputHandler for window drag and speed control. Removing them is a future sprint task (extract WindowDragState and SpeedState).

### Task 2: Create concrete implementations

Below the Protocol definitions in `game/game_commands.py`, add a single concrete class that implements ALL protocols by delegating to GameEngine. This replaces `EngineBackedGameCommands`:

```python
class EngineCommandHub:
    """Concrete implementation of all command protocols, backed by GameEngine.

    Implements CameraCommands, SelectionCommands, PlacementCommands,
    MenuCommands, and GameStateCommands by delegating to a stored engine.

    InputHandler receives this single object but types its parameters
    as the narrow protocols for documentation and future splitting.
    """

    __slots__ = ("_engine",)

    def __init__(self, engine: "GameEngine") -> None:
        object.__setattr__(self, "_engine", engine)

    # --- CameraCommands ---
    @property
    def camera_x(self) -> float:
        return self._engine.camera_x

    @property
    def camera_y(self) -> float:
        return self._engine.camera_y

    @property
    def zoom(self) -> float:
        return self._engine.zoom

    def zoom_by(self, factor: float) -> None:
        self._engine.zoom_by(factor)

    def center_on_castle(self, reset_zoom: bool = True) -> None:
        self._engine.center_on_castle(reset_zoom)

    # --- SelectionCommands ---
    # (continue delegating every member to self._engine)
    # ... EVERY property and method from the old GameCommands must be present
    # ... Copy the delegation pattern from the existing EngineBackedGameCommands
```

**IMPORTANT:** You MUST delegate every single member that InputHandler currently uses. Read the existing `EngineBackedGameCommands` class carefully and keep every delegation. The only change is renaming the class and removing the old `GameCommands` Protocol.

### Task 3: Update InputHandler

Open `game/input_handler.py`. Change the constructor:

```python
from game.game_commands import (
    CameraCommands, SelectionCommands, PlacementCommands,
    MenuCommands, GameStateCommands,
)

class InputHandler:
    def __init__(self, commands) -> None:
        # commands implements all five protocols
        self.commands = commands
        self.camera: CameraCommands = commands
        self.selection: SelectionCommands = commands
        self.placement: PlacementCommands = commands
        self.menu: MenuCommands = commands
        self.state: GameStateCommands = commands
```

For this sprint, all five aliases point to the same `EngineCommandHub` object. This is intentional — it documents the dependency domains without requiring callers to change yet. Future sprints can split them.

**Also fix the _engine abstraction leak:** Find `handle_keydown` around lines 165-191 where InputHandler reaches through `c._engine` directly for command mode. Replace with:

```python
# OLD (broken abstraction):
if hasattr(c, '_engine') and c._engine._command_mode:
    ...
    c._engine.process_command(c._engine._command_buffer)

# NEW:
if hasattr(self.state, 'process_command'):
    # Command mode state is now accessed through GameStateCommands
    ...
```

Read the actual command mode code carefully before changing it. The `process_command` method is on the Protocol. The `_command_mode` and `_command_buffer` state needs to move to `GameStateCommands` or be accessible through it.

### Task 4: Update engine.py wiring

In `game/engine.py`, change the InputHandler construction:

```python
# OLD:
from game.game_commands import EngineBackedGameCommands
self.input_handler = InputHandler(EngineBackedGameCommands(self))

# NEW:
from game.game_commands import EngineCommandHub
self.input_handler = InputHandler(EngineCommandHub(self))
```

### Task 5: Keep backward compatibility alias

At the bottom of `game/game_commands.py`, add:

```python
# Backward compatibility for any tools/tests that import the old name
GameCommands = GameStateCommands  # closest match; update importers
EngineBackedGameCommands = EngineCommandHub
```

### Verification

```powershell
python -m pytest tests/test_input_handler_gamecommands.py -x -v
python -m pytest tests/test_wk63_engine_boundary.py -x -v
python -m pytest tests/ -x -q
python tools/qa_smoke.py --quick
```

The key acceptance criteria:
- InputHandler works with the new protocol interfaces
- No `c._engine` access in InputHandler
- All existing tests pass
- `qa_smoke.py` observe_sync scenarios pass (they exercise input/selection)

---

## Gate 2 — Final Verification

**Owner:** Agent 11 (QA_TestEngineering_Lead) + Agent 04 (determinism consult)
**Intelligence:** Agent 11 LOW, Agent 04 LOW

### Agent 11 tasks:

```powershell
python -m pytest tests/ -x -q
python tools/determinism_guard.py
python tools/qa_smoke.py --quick
python tools/validate_assets.py --report
```

Grep-verify:
- `GameCommands` old Protocol class is gone (only backward compat alias remains)
- `EngineCommandHub` exists and is used in engine.py
- `CameraCommands`, `SelectionCommands`, `PlacementCommands`, `MenuCommands`, `GameStateCommands` exist in game_commands.py
- `SelectionState` is used in GameEngine
- `_engine` does not appear in input_handler.py (except as part of `_engine` in comments or strings)
- `entity_id` exists on Building, Enemy, Peasant, Guard
- `PathfindingBudget` uses `_frame_expansions`, not `_frame_ms_used`, for budget decisions

### Agent 04 tasks:

- Review pathfinding budget changes for determinism
- Verify no wall-clock time gates gameplay decisions
- Run `python tools/determinism_guard.py`

---

## File Ownership (no collisions within a wave)

### Wave 1 (parallel)

| Agent | Files | Does NOT edit |
|-------|-------|---------------|
| Agent 03 | `game/entities/buildings/base.py`, `game/entities/enemy.py`, `game/entities/peasant.py`, `game/entities/guard.py`, `game/presentation/selection_state.py` (new), `game/sim_engine.py`, `game/engine.py`, `game/cleanup_manager.py`, `game/sim/snapshot.py` | `game/systems/navigation.py`, `game/systems/pathfinding.py`, `game/game_commands.py`, `game/input_handler.py` |
| Agent 04 | `game/systems/navigation.py`, `game/systems/pathfinding.py`, `game/systems/perf_stats.py`, `game/sim_engine.py` (ONLY the `begin_frame()` call line) | `game/engine.py`, `game/entities/**`, `game/game_commands.py`, `game/input_handler.py` |

**Conflict note:** Both Agent 03 and Agent 04 touch `game/sim_engine.py`. Agent 03 removes `selected_*` fields from `__init__` and `get_game_state`. Agent 04 only touches the `begin_frame()` call. These are in different sections of the file (init is ~line 123, get_game_state ~line 400, begin_frame call ~line 600). If the agents follow instructions, there will be no merge conflict. But Agent 04 should be told explicitly: **only edit lines 599-601 of sim_engine.py (the begin_frame call), nothing else in this file.**

### Wave 2

| Agent | Files | Does NOT edit |
|-------|-------|---------------|
| Agent 03 | `game/game_commands.py`, `game/input_handler.py`, `game/engine.py` (wiring only) | `game/systems/**`, `game/entities/**` |

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Selection migration breaks observe_sync scenarios | Property getters on GameEngine maintain same API — callers don't change |
| find_path tuple return breaks callers | Only 2 direct callers (navigation.py, LayerPathfinder) — both updated |
| GameCommands rename breaks tools/tests | Backward compat aliases at bottom of game_commands.py |
| Entity ID allocation not deterministic | Allocation order follows construction order, which is deterministic in sim |
| Linear scan in selection getters too slow | Only ~4 lookups per frame — negligible vs rendering cost |

---

## Sprint Success Criteria

- [ ] `python -m pytest tests/ -x -q` — all tests pass
- [ ] `python tools/determinism_guard.py` — PASS
- [ ] `python tools/qa_smoke.py --quick` — PASS
- [ ] Pathfinding budget uses deterministic expansion counts
- [ ] Selection state lives in `game/presentation/selection_state.py`
- [ ] All entity types have stable string IDs
- [ ] `GameCommands` replaced by 5 narrow Protocol interfaces
- [ ] InputHandler no longer accesses `commands._engine`
