# Master Plan: Building & Nature Systems Multi-Stage Refactor

This master plan outlines a robust, multi-sprint architectural approach to overhaul the Kingdom simulation's building construction and nature systems. 

**ATTENTION IMPLEMENTING AGENTS:** This document contains precise architectural constraints, reasoning, and code examples. Read the "Friction Points" and "Architecture Options" carefully before making any changes. You do not share the author's context; follow the explicit instructions and code formatting examples provided below.

---

## 1. System Map: Affected Files

You will modify or create the following files across the sprints. If you need to touch a file not on this list, stop and reconsider your approach.

### Core & Sim Engine
*   `config.py`: Add new constants for building costs, timings, and builder peasant visual configurations.
*   `game/sim_engine.py`: Update the `SimEngine.update` method to pass peasants to the `NeutralBuildingSystem` and tick the new `NatureSystem`. Update `_update_fog_of_war` for builder LoS.
*   `game/world.py`: Update `generate_terrain` for initial forest clustering. Provide a method to find the nearest tree `world.find_nearest_tree(x, y)`.

### Systems (Game Logic)
*   `game/systems/neutral_buildings.py`: Must be modified to spawn unconstructed plots and instantiate `BuilderPeasant` entities.
*   `game/systems/nature.py` **[NEW]**: A new system to tick tree growth and spawning.
*   `ai/behaviors/task_durations.py`: Add `CHOP_TREE_DURATION` and `HARVEST_LOG_DURATION`.

### Entities (Sim Objects)
*   `game/entities/peasant.py` / `game/entities/builder_peasant.py` **[NEW]**: The state machine for the new builder peasant.
*   `game/entities/buildings/base.py`: Handles `is_constructed` flag and HP.
*   `game/entities/neutral_buildings.py`: Overriding default instantiation to allow `is_constructed=False` and initial HP = 1.
*   `game/entities/nature.py` **[NEW]**: Define `Tree` data structure for tracking growth.

### Presentation Layer (Renderer & UI)
*   `game/graphics/ursina_renderer.py`: Mapping the `BuilderPeasant` to a visually distinct 3D model (green tint) and handling dynamic scaling of tree entities based on their growth stage.
*   `game/graphics/ursina_terrain_fog_collab.py`: Removing static tree tile scattering and implementing a dictionary map to lookup and scale tree entities dynamically.
*   `assets/prefabs/buildings/*`: Prefab JSONs for 0%, 20%, 50% construction stages.

---

## 2. Stage 1: Neutral Building Construction

**Objective:** Neutral buildings (House, Food Stand, Farm) must no longer spawn instantly. They must spawn as 1 HP "plots," and a Builder Peasant must spawn from the Castle to construct them.

### Architecture Options for `BuilderPeasant`
1.  **Inheritance (RECOMMENDED):** Create `class BuilderPeasant(Peasant)` in a new file `builder_peasant.py` or within `peasant.py`.
    *   *Tradeoffs:* Cleanest separation. Regular peasants keep their simple repair state machine. You must ensure `SimEngine` updates both normal peasants and builder peasants.
2.  **State Flagging:** Add `self.is_builder = True` to the existing `Peasant` class.
    *   *Tradeoffs:* Creates a bloated state machine. Standard peasants will have unreachable "Find Tree" code, violating single-responsibility principles. DO NOT USE this option.

### Friction Points & Implementation Instructions
*   **Friction:** `NeutralBuildingSystem.tick()` currently accepts `(dt, buildings, heroes, castle)`. It has no way to spawn a peasant into the sim's `peasants` list.
    *   *Agent Instruction:* Modify the signature to `tick(self, dt: float, buildings: list, heroes: list, peasants: list, castle)`. Update the call site in `game/sim_engine.py` accordingly.
*   **Friction:** Buildings default to 100% HP.
    *   *Agent Instruction:* In `game/entities/neutral_buildings.py`, modify the `__init__` methods of `House`, `FoodStand`, and `Farm` to accept `is_constructed: bool = True`. If `False`, set `self.hp = 1` and `self.is_constructed = False`.
*   **Peasant LoS:** Update `SimEngine._update_fog_of_war` to add a 6-tile radius for peasants, identical to the logic for heroes but with `r=6`.

### Code Example for Agents (State Machine setup):
```python
class BuilderPeasant(Peasant):
    def __init__(self, x, y, target_plot):
        super().__init__(x, y)
        self.state = "MOVE_TO_PLOT"
        self.target_building = target_plot
        self.wood_inventory = 0

    def update(self, dt, game_state):
        if self.state == "MOVE_TO_PLOT":
            # Logic to move to self.target_building
            pass
```

### Tests to Design
*   `tests/test_builder_lifecycle.py`: Initialize headless `SimEngine`. Force `NeutralBuildingSystem` to spawn a House. Assert `buildings[-1].is_constructed == False`. Assert a `BuilderPeasant` is spawned. Tick time forward and assert the building is completed and peasant is removed.

---

## 3. Stage 2: Dynamic Tree Growth

**Objective:** Transition from random static tree scattering to dynamic tree growth. Trees cluster into forests and grow from 25% -> 50% -> 75% -> 100% over 6 minutes.

### Architecture Options for Tree Data
1.  **Entity Array (RECOMMENDED):** `sim.trees = [Tree(x, y), ...]`. `NatureSystem` iterates over this array.
    *   *Tradeoffs:* High object count, but aligns perfectly with existing `buildings` and `heroes` arrays. Easy to pass to `UrsinaRenderer` via `SimStateSnapshot`.
2.  **Grid Metadata:** Store `world.tree_growth[y][x] = stage`.
    *   *Tradeoffs:* Less memory, but the Presentation Layer has to poll a massive 2D array every frame to see if a tree's visual scale needs updating. DO NOT USE.

### Friction Points & Implementation Instructions
*   **Friction:** `ursina_terrain_fog_collab.py` currently instantiates tree models directly via `Entity(model=tree_model...)` and immediately forgets the reference.
    *   *Agent Instruction:* In `ursina_terrain_fog_collab.py`, you must create a dictionary lookup `self._r._tree_entities[(tx, ty)] = tree_ent`. Add a new method `sync_dynamic_trees(trees_from_snapshot)` that iterates over the snapshot trees, looks up the corresponding 3D entity via the `(grid_x, grid_y)` key, and sets its `scale` to `TreeScale * tree.growth_stage`.
*   **Friction:** Generating forests vs random noise.
    *   *Agent Instruction:* In `world.py`, update `generate_terrain`. Instead of a flat 5% chance per tile, implement a simple cellular automata pass or cluster-spawning (e.g., if a tile is a tree, neighbors have a 40% chance to be a tree).

### Code Example for Agents (Renderer Sync):
```python
# In game/graphics/ursina_terrain_fog_collab.py
def sync_dynamic_trees(self, snapshot_trees):
    for t in snapshot_trees:
        ent = self._r._tree_entities.get((t.grid_x, t.grid_y))
        if ent:
            base_scale = TERRAIN_SCALE_MULTIPLIER * TREE_SCALE_MULTIPLIER
            s = base_scale * t.growth_percentage  # 0.25, 0.5, 0.75, 1.0
            ent.scale = (s, s, s)
```

### Tests to Design
*   `tests/test_nature_growth.py`: Instantiate `NatureSystem` and a 25% `Tree`. Tick `NatureSystem` by 6 simulated minutes. Assert `tree.growth_percentage == 1.0`.

---

## 4. Stage 3: Lumberjack Economy

**Objective:** The Builder Peasant must gather wood from trees before they can construct their assigned building.

### Architecture Options for Logs
1.  **Virtual Harvesting (RECOMMENDED):** Do not spawn a physical "Log" entity in the simulation engine. Instead, the `BuilderPeasant` state machine handles a 5s `CHOP` wait and a 5s `HARVEST` wait.
    *   *Tradeoffs:* Extremely simple. Avoids pathfinding errors where peasants target logs that get destroyed or blocked.
2.  **Physical Log Entity:** Chops spawn a `Log` entity that sits on the map.
    *   *Tradeoffs:* Requires new collision, rendering, and targeting logic. Creates race conditions if two peasants target the same log. DO NOT USE.

### Friction Points & Implementation Instructions
*   **Friction:** The peasant needs to find the nearest tree, but trees aren't buildings.
    *   *Agent Instruction:* Add `find_nearest_tree(x, y)` to `game/world.py` (or pass the `sim.trees` list to the peasant). It must filter out trees that are in `Visibility.UNSEEN` fog.
*   **Friction:** Tax Collector behavior.
    *   *Agent Instruction:* Ensure the `TaxCollector` in `sim_engine.py` only searches `sim.buildings`, never `sim.trees` or `peasants`, so it doesn't accidentally try to path to trees or collect wood.

### Code Example for Agents (Wood Yields):
```python
# config.py
WOOD_COST_HOUSE = 10
WOOD_COST_FOOD_STAND = 10
WOOD_COST_FARM = 20

def get_wood_yield(growth_percentage):
    if growth_percentage >= 1.0: return 10
    if growth_percentage >= 0.75: return 7
    if growth_percentage >= 0.50: return 5
    return 0 # Cannot harvest
```

### Tests to Design
*   `tests/test_lumberjack_economy.py`: Assert that a `BuilderPeasant` assigned to a `Farm` (cost 20) loops through the `FIND_TREE` -> `CHOP` -> `HARVEST` cycle multiple times until `self.wood_inventory >= 20` before entering the `BUILDING` state.
