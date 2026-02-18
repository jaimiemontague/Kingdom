---
name: WK8 Engine+Entities Refactor
overview: Week 8 sprint focused on decomposing the two most bloated files (engine.py, building.py), introducing an EventBus to decouple system-to-system communication, formalizing system interfaces, and grouping config into typed dataclasses — foundational work that reduces coupling and accelerates all future feature sprints.
todos:
  - id: r1-contracts
    content: "R1: Agent 03 proposes engine module boundaries/APIs; Agent 05 proposes building package structure + HiringBuilding mixin; Agent 04 reviews determinism; PM approves"
    status: pending
  - id: t1-input-handler
    content: "Track 1 Step 1: Extract InputHandler from engine.py (~320 lines) into game/input_handler.py"
    status: pending
  - id: t1-display-manager
    content: "Track 1 Step 2: Extract DisplayManager from engine.py (~150 lines) into game/display_manager.py"
    status: pending
  - id: t1-building-factory
    content: "Track 1 Step 3: Extract BuildingFactory from engine.py (~100 lines) into game/building_factory.py"
    status: pending
  - id: t1-cleanup-manager
    content: "Track 1 Step 4: Extract CleanupManager from engine.py (~120 lines) into game/cleanup_manager.py"
    status: pending
  - id: t1-update-slimdown
    content: "Track 1 Step 5: Refactor update() into named phase methods (~30 lines each)"
    status: pending
  - id: t2-building-enum
    content: "Track 2 Step 0: Define BuildingType(str, Enum) with all 27 building type keys — backward compatible, used by factory and all new modules"
    status: pending
  - id: t2-hiring-mixin
    content: "Track 2 Step 1: Create HiringBuilding mixin to eliminate ~200 lines of guild/temple duplication"
    status: pending
  - id: t2-split-modules
    content: "Track 2 Step 2: Split building.py into buildings/ package (base, guilds, temples, defensive, economic, special, castle)"
    status: pending
  - id: t2-import-shim
    content: "Track 2 Step 3: Create backward-compatible import shims so no external code changes needed"
    status: pending
  - id: t3-event-bus
    content: "Track 3A: Create EventBus + GameEventType enum in game/events.py; wire AudioSystem and VFXSystem as subscribers; replace manual routing in engine"
    status: pending
  - id: t3-system-protocol
    content: "Track 3B: Define GameSystem Protocol + SystemContext dataclass in game/systems/protocol.py; refactor CombatSystem and BuffSystem to conform"
    status: pending
  - id: t3-config-dataclasses
    content: "Track 3C: Group config.py into frozen dataclasses (CameraConfig, SpawnerConfig, EconomyConfig, etc.) with backward-compat module-level aliases"
    status: pending
  - id: t3-remaining-enums
    content: "Track 3D: Define HeroClass, EnemyType, BountyType as str Enums (HeroState/EnemyState already exist); use in new Track 3 code"
    status: pending
  - id: verify-determinism-audit
    content: "Verification: Agent 04 reviews all new files for sim boundary compliance and determinism"
    status: pending
  - id: verify-qa-gates
    content: "Verification: Agent 11 runs full gate suite + manual smoke after all tracks land"
    status: pending
  - id: verify-tooling-check
    content: "Verification: Agent 12 verifies tools still work with new file structure"
    status: pending
isProject: false
---

# WK8: Engine + Entity Refactor Sprint

## Why This, Why Now

After 7 sprints of feature work (v1.2.0 through v1.3.0), two files have become critical maintenance risks:

- `**game/engine.py**` (~1,900 lines) is a god class handling 17+ responsibilities: game loop, input, camera, display modes, entity management, system coordination, building placement, hero hiring, cleanup, rendering, perf overlay, early pacing, fog-of-war, audio/VFX routing, screenshot capture. Every sprint has agents colliding in this file.
- `**game/entities/building.py**` (~1,450 lines) packs 25+ building subclasses into a single file, with guilds and temples duplicating ~200 lines of hiring/tax logic across 11 classes.

Neither file has tests of its own — all coverage comes through headless smoke (`qa_smoke --quick`). The refactoring must preserve gate-green status at every step.

## Sprint Structure: Two Parallel Tracks

### Track 1: Engine Decomposition (Primary)

**Owner**: Agent 03 (TechnicalDirector)
**Consult**: Agent 08 (UI hooks), Agent 04 (determinism boundary)

Goal: Break `GameEngine` from 1 god class into engine + 4-5 focused modules, keeping the same public API so UI and systems code doesn't need changes yet.

#### Step 1: Extract `InputHandler` (new file: `game/input_handler.py`)

- Move `handle_events()`, `handle_keydown()`, `handle_mousedown()`, `select_building_for_placement()` (~320 lines)
- `InputHandler` receives pygame events, returns command objects (or calls engine methods)
- Engine delegates `self.input_handler.process(events)` in the main loop

#### Step 2: Extract `DisplayManager` (new file: `game/display_manager.py`)

- Move `apply_display_settings()` and display-related init code (~150 lines)
- Owns SDL window creation, mode switching (fullscreen/borderless/windowed), resolution detection
- Engine calls `self.display.apply(settings)` instead of inline logic

#### Step 3: Extract `BuildingFactory` (new file: `game/building_factory.py`)

- Move the `place_building()` if/elif chain that instantiates 20+ building types (~100 lines)
- Registry pattern: `BUILDING_REGISTRY = {"warrior_guild": WarriorGuild, ...}` with `create(type_key, x, y)` method
- Engine calls `self.building_factory.create(type_key, tx, ty)`

#### Step 4: Extract `CleanupManager` (new file: `game/cleanup_manager.py`)

- Move `_cleanup_destroyed_buildings()` (~120 lines)
- Encapsulates reference cleanup across heroes/enemies/peasants/guards/tax_collectors/bounties
- Engine calls `self.cleanup.process(buildings, heroes, enemies, ...)` after combat

#### Step 5: Slim `update()` into named phases

- The 294-line `update()` becomes a sequence of ~10 clearly named calls:
  - `self._update_camera(dt)`, `self._update_fog()`, `self._update_ai()`, `self._update_entities(dt)`, `self._update_systems()`, `self._process_combat()`, `self._cleanup()`, `self._route_events()`
- Each sub-method stays in engine.py for now (not extracted) but is max ~30 lines

**Expected result**: `engine.py` drops from ~1,900 to ~1,100 lines. New files are ~150-200 lines each.

### Track 2: Building Decomposition (Secondary)

**Owner**: Agent 05 (GameplaySystemsDesigner)
**Consult**: Agent 03 (contracts, imports), Agent 08 (building panel references)

Goal: Split `building.py` into a `buildings/` package with domain-specific modules, introduce typed building identifiers, and extract the guild/temple hiring mixin to eliminate ~200 lines of duplication.

#### Step 0: Define `BuildingType` enum (new file: `game/entities/buildings/types.py`)

- Create `BuildingType(str, Enum)` with all 27 building type keys (castle, warrior_guild, ranger_guild, ... house, farm, food_stand)
- Because it inherits from `str`, it compares equal to bare strings — fully backward compatible
- All new Track 2 modules should use `BuildingType` in type hints and registry keys
- The `BuildingFactory` registry from Track 1 should also adopt `BuildingType` as its key type
- The existing `config.py` dicts (`BUILDING_COSTS`, `BUILDING_SIZES`, `BUILDING_COLORS`) keep string keys for now — no changes needed there yet

#### Step 1: Create `HiringBuilding` mixin (new file: `game/entities/buildings/hiring_mixin.py`)

- Extract shared methods from all guilds + temples: `can_hire()`, `hire_hero()`, `add_tax_gold()`, `collect_taxes()`, `stored_tax_gold`
- All 11 classes (4 guilds + 7 temples) inherit from `Building` + `HiringBuilding`
- Eliminates ~200 lines of copy-pasted code

#### Step 2: Split into domain modules

- `game/entities/buildings/__init__.py` — re-exports all building classes (preserves import compatibility)
- `game/entities/buildings/base.py` — `Building` base class (~200 lines)
- `game/entities/buildings/guilds.py` — WarriorGuild, RangerGuild, RogueGuild, WizardGuild (~120 lines with mixin)
- `game/entities/buildings/temples.py` — All 7 temples (~100 lines with mixin)
- `game/entities/buildings/defensive.py` — Guardhouse, BallistaTower, WizardTower (~120 lines)
- `game/entities/buildings/economic.py` — Marketplace, Blacksmith, Inn, TradingPost (~200 lines)
- `game/entities/buildings/special.py` — Fairgrounds, Library, RoyalGardens, Palace (~150 lines)
- `game/entities/buildings/castle.py` — Castle (~60 lines, special enough to isolate)

#### Step 3: Update imports

- `game/entities/__init__.py` re-exports from `buildings/` (backward compatibility)
- `game/entities/building.py` becomes a thin re-export shim (deprecation bridge):

```python
  from game.entities.buildings import *  # backward compat
  

```

- No other files need to change their import statements

**Expected result**: 1,450-line monolith becomes 7 focused files of 60-200 lines each.

### Track 3: Architecture Foundations

**Owner**: Agent 03 (Event Bus + System Protocol + Enums), Agent 12 (Config Dataclasses)
**Consult**: Agent 04 (determinism review of EventBus), Agent 08 (UI event subscriptions)

Goal: Introduce the foundational patterns that make future feature work faster — centralized event routing, a formal system interface, typed enums for all game constants, and grouped config.

#### Step A: Event Bus + GameEventType enum (new files: `game/events.py`)

The engine currently acts as a manual switchboard — collecting event dicts from CombatSystem, merging enemy/building ranged events, then hand-routing them to AudioSystem and VFXSystem with try/except wrappers. There are 6+ separate routing blocks in engine.py.

**EventBus design:**

```python
class GameEventType(str, Enum):
    HERO_ATTACK = "hero_attack"
    RANGED_PROJECTILE = "ranged_projectile"
    ENEMY_KILLED = "enemy_killed"
    HERO_ATTACK_LAIR = "hero_attack_lair"
    LAIR_CLEARED = "lair_cleared"
    CASTLE_DESTROYED = "castle_destroyed"
    BUILDING_PLACED = "building_placed"
    BUILDING_DESTROYED = "building_destroyed"
    BOUNTY_PLACED = "bounty_placed"
    BOUNTY_CLAIMED = "bounty_claimed"

class EventBus:
    def subscribe(self, event_type: str, callback: Callable[[dict], None]) -> None: ...
    def emit(self, event: dict) -> None: ...
    def emit_batch(self, events: list[dict]) -> None: ...
    def flush(self) -> None: ...
```

**Wiring changes in engine.py:**

- Engine creates `self.event_bus = EventBus()` in `__init__`
- AudioSystem subscribes: `event_bus.subscribe("*", self.audio_system.on_event)` (AudioSystem internally filters by type and applies visibility gating)
- VFXSystem subscribes: `event_bus.subscribe("*", self.vfx_system.on_event)`
- AudioSystem keeps its `set_listener_view()` call — engine calls it once per frame before events flush (viewport context is still frame-dependent)
- Replace all 6+ manual routing blocks with `self.event_bus.emit_batch(events)`
- CombatSystem, CleanupManager, and player action methods emit to the bus instead of returning/collecting event lists

**Key constraint:** All subscriber callbacks are wrapped in try/except by the bus itself — no more per-call-site error handling.

#### Step B: System Interface Protocol (new file: `game/systems/protocol.py`)

Current systems have inconsistent APIs — CombatSystem takes `(heroes, enemies, buildings)` and returns events, BuffSystem takes `(heroes, buildings)` and returns nothing, EconomySystem has no update method at all. This makes the engine call each system with bespoke code.

**Protocol design:**

```python
@dataclass
class SystemContext:
    heroes: list
    enemies: list
    buildings: list
    world: object
    economy: object
    event_bus: EventBus

class GameSystem(Protocol):
    def update(self, ctx: SystemContext, dt: float) -> None: ...
```

- Systems that produce events now emit directly to `ctx.event_bus` instead of returning lists
- Engine can loop: `for system in self.systems: system.update(ctx, dt)`
- Refactor CombatSystem and BuffSystem first (they're the most active per-tick systems)
- BountySystem, LairSystem, NeutralBuildingSystem, EnemySpawner can adopt the protocol incrementally (not required this sprint, but the protocol exists for them)
- EconomySystem stays on-demand (not tick-driven) — it doesn't need the protocol

#### Step C: Config Dataclasses (Agent 12 — `config.py`)

Group the flat 264-line config into frozen dataclasses with backward-compatible module-level aliases.

**Groupings:**

- `WindowConfig` — WINDOW_WIDTH, WINDOW_HEIGHT, FPS, PROTOTYPE_VERSION, GAME_TITLE, DEFAULT_BORDERLESS
- `SimConfig` — DETERMINISTIC_SIM, SIM_TICK_HZ, SIM_SEED
- `MapConfig` — TILE_SIZE, MAP_WIDTH, MAP_HEIGHT
- `CameraConfig` — CAMERA_SPEED_PX_PER_SEC, CAMERA_EDGE_MARGIN_PX, ZOOM_MIN, ZOOM_MAX, ZOOM_STEP
- `HeroConfig` — HERO_HIRE_COST, HERO_BASE_HP, HERO_BASE_ATTACK, HERO_BASE_DEFENSE, HERO_SPEED
- `EnemyConfig` — all enemy HP/attack/speed constants, MAX_ALIVE_ENEMIES
- `LairConfig` — LAIR_INITIAL_COUNT, LAIR_MIN_DISTANCE_FROM_CASTLE_TILES, etc.
- `BountyConfig` — BOUNTY_REWARD_LOW/MED/HIGH, BOUNTY_BLACK_FOG_DISTANCE_PENALTY
- `EconomyConfig` — STARTING_GOLD, TAX_RATE
- `LLMConfig` — LLM_PROVIDER, API keys, cooldown, timeout
- `RangerConfig` — RANGER_EXPLORE_BLACK_FOG_BIAS, RANGER_FRONTIER_SCAN_RADIUS_TILES, etc.

**Backward compatibility:** Keep module-level names as aliases:

```python
WINDOW = WindowConfig()
WINDOW_WIDTH = WINDOW.width  # existing code still works
```

Building dicts (BUILDING_COSTS, BUILDING_SIZES, BUILDING_COLORS, BUILDING_CONSTRAINTS, BUILDING_PREREQUISITES) and color constants stay as-is — they don't fit neatly into a single dataclass and are already well-organized.

#### Step D: Remaining Enums (new file: `game/types.py`)

`HeroState` and `EnemyState` enums already exist in their entity files. The remaining string constants that should be enums:

```python
class HeroClass(str, Enum):
    WARRIOR = "warrior"
    RANGER = "ranger"
    ROGUE = "rogue"
    WIZARD = "wizard"

class EnemyType(str, Enum):
    GOBLIN = "goblin"
    WOLF = "wolf"
    SKELETON = "skeleton"
    SKELETON_ARCHER = "skeleton_archer"
    SPIDER = "spider"
    BANDIT = "bandit"

class BountyType(str, Enum):
    EXPLORE = "explore"
    ATTACK_LAIR = "attack_lair"
    DEFEND_BUILDING = "defend_building"
    HUNT_ENEMY_TYPE = "hunt_enemy_type"
```

All inherit from `str` so existing string comparisons keep working. New code written in this sprint should use the enums. Existing code migrates incrementally.

### Verification Wave (after all tracks land)

**Owner**: Agent 11 (QA), Agent 04 (Determinism)
**Consult**: Agent 12 (Tooling)

#### Agent 04: Determinism Audit

- Review all new files for sim boundary compliance
- Confirm EventBus doesn't introduce non-deterministic dispatch order (subscribers called in registration order)
- Confirm SystemContext doesn't leak render-side state into sim
- Run `python tools/determinism_guard.py` after each track lands
- Verify `BuildingFactory` registry doesn't introduce non-deterministic iteration

#### Agent 11: Gate Verification

- After all tracks land: run `python tools/qa_smoke.py --quick` (full suite)
- Run `python tools/validate_assets.py --report`
- Regression check: run all headless profiles (base, intent_bounty, hero_stuck_repro, no-enemies, mock-LLM)
- Manual smoke: 10 min `--no-llm` + 10 min `--provider mock` (confirm game still plays identically)

#### Agent 12: Tooling Check + Config Dataclasses

- Implement Track 3C (config dataclasses) — Agent 12 owns config.py tooling
- Verify `tools/observe_sync.py` and `tools/qa_smoke.py` still work with new import paths
- Update any tool that directly imports from `game.entities.building` or `game.engine` if needed
- Confirm `tools/determinism_guard.py` scans the new file locations

## Agent Assignment Summary


| Agent             | Role                   | Track                                                              | Priority |
| ----------------- | ---------------------- | ------------------------------------------------------------------ | -------- |
| 03 (TechDirector) | Primary implementer    | Track 1 (engine decomp) + Track 3A/B/D (EventBus, Protocol, Enums) | P0       |
| 05 (Gameplay)     | Primary implementer    | Track 2 (building decomp + BuildingType enum)                      | P0       |
| 12 (Tools)        | Implementer + Verifier | Track 3C (config dataclasses) + tooling verification               | P1       |
| 04 (Determinism)  | Reviewer               | Verification: determinism audit across all tracks                  | P1       |
| 08 (UX/UI)        | Consult                | Verify UI imports/hooks still work after all tracks                | P1       |
| 11 (QA)           | Verifier               | Verification: full gate suite + manual smoke                       | P0       |
| 02 (GameDirector) | Acceptance             | Final acceptance: game still feels the same                        | P2       |


**Silent (no work this sprint)**: Agents 06, 07, 09, 10, 13, 14

## Integration Order

1. **Track 1, Steps 1-5** (engine extraction + update slim-down) — IN PROGRESS (Agent 03)
2. **Track 2, Steps 0-3** (BuildingType enum + building package split) — IN PROGRESS (Agent 05)
3. **Track 3A+B+D** (EventBus + System Protocol + Enums) — Agent 03 after Track 1 completes
4. **Track 3C** (Config Dataclasses) — Agent 12, can run in parallel with Track 3A
5. **Verification Wave** — Agents 04, 11, 12 after all implementation tracks land

## Round Plan

- **R1 (Track 1)**: Agent 03 implements engine decomposition. IN PROGRESS.
- **R2 (Track 2)**: Agent 05 implements building decomposition + BuildingType enum. IN PROGRESS.
- **R3 (Track 3)**: Agent 03 implements EventBus + System Protocol + Enums (3A/B/D). Agent 12 implements Config Dataclasses (3C). STARTS AFTER TRACK 1.
- **R4 (Verification)**: Agents 04, 11 verify all tracks. Agent 12 verifies tooling. Agent 02 does acceptance.

## Non-Goals (explicitly excluded)

- **No AI refactoring** (`ai/basic_ai.py`) — owned by single agent, lower cross-team impact
- **No UI refactoring** (`game/ui/hud.py`, `building_panel.py`) — planned for a future sprint
- **No sim/render separation** in entities — deferred to WK9+
- **No unit test suite** — deferred to WK9+ (Agent 11 to propose)
- **No behavior changes** — the game must play identically before and after
- **No new features** — pure structural improvement
- **No version bump** — this is internal refactoring, not a player-facing release

## Success Criteria

- `game/engine.py` drops below 1,200 lines
- `game/entities/building.py` is replaced by a `buildings/` package with no file over 250 lines
- EventBus handles all event routing — no manual try/except routing blocks remain in engine
- At least CombatSystem and BuffSystem conform to the GameSystem Protocol
- `config.py` constants are accessible via both dataclass (`CAMERA.zoom_min`) and legacy names (`ZOOM_MIN`)
- `python tools/qa_smoke.py --quick` PASS
- `python tools/validate_assets.py --report` 0 errors
- `python tools/determinism_guard.py` PASS
- Manual 10-minute play in `--no-llm` and `--provider mock` shows no behavioral difference
- No import changes required outside of `game/` directory (backward-compat shims work)

## Risk Mitigation

- **Merge conflicts**: Tracks 1 and 2 touch different files; Track 3 touches engine.py (after Track 1) and config.py (independent)
- **Broken imports**: Backward-compat shims in `__init__.py` and `building.py` ensure no external breakage
- **EventBus dispatch order**: Subscribers are called in registration order (deterministic); Agent 04 verifies
- **Config backward compat**: Module-level aliases mean zero changes needed in consuming code
- **Behavioral regression**: Headless QA profiles catch simulation regressions automatically
- **Perf regression**: Agent 10 is on standby if perf overlay shows any tick-time increase after refactoring

