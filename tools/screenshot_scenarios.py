"""
Deterministic screenshot scenarios for the Visual Snapshot System.

These scenarios should:
- Avoid wall-clock dependencies (use sim-time ticks if advancing)
- Avoid LLM usage
- Be deterministic under a fixed seed
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from config import TILE_SIZE, MAP_WIDTH, MAP_HEIGHT
from game.entities.building import Building
from game.entities.hero import Hero
from game.entities.enemy import Enemy


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "tools" / "assets_manifest.json"


@dataclass(frozen=True)
class Shot:
    filename: str
    label: str
    # World-space center to frame
    center_x: float
    center_y: float
    zoom: float = 1.0
    ticks: int = 0
    meta: dict[str, Any] | None = None
    # Optional per-shot mutator hook (selection/UI toggles/etc)
    apply: Callable[[Any], None] | None = None


def _load_asset_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _reveal_all(world) -> None:
    """Disable fog-of-war for captures by marking all tiles VISIBLE if the grid exists."""
    vis = getattr(world, "visibility", None)
    if not isinstance(vis, list):
        return
    try:
        # Visibility.VISIBLE == 2 (see game/world.py)
        for y in range(len(vis)):
            row = vis[y]
            for x in range(len(row)):
                row[x] = 2
        # Also keep currently_visible consistent if the implementation uses it.
        if hasattr(world, "_currently_visible"):
            world._currently_visible = {(x, y) for y in range(len(vis)) for x in range(len(vis[y]))}
    except Exception:
        return


def _clear_non_castle_buildings(engine) -> None:
    engine.buildings = [b for b in engine.buildings if getattr(b, "building_type", "") == "castle"]


def _clear_dynamic_entities(engine) -> None:
    engine.enemies = []
    engine.peasants = []
    engine.guards = []
    try:
        engine.bounty_system.bounties = []
    except Exception:
        pass


def _place_building(engine, building_type: str, gx: int, gy: int) -> Building:
    b = Building(gx, gy, building_type=str(building_type))
    # Make it look "built" and targetable.
    if hasattr(b, "is_constructed"):
        b.is_constructed = True
    if hasattr(b, "construction_started"):
        b.construction_started = True
    # Some entities expose is_targetable as a read-only property; don't force-set it for screenshots.
    if hasattr(b, "max_hp") and hasattr(b, "hp"):
        b.hp = getattr(b, "max_hp", b.hp)
    engine.buildings.append(b)
    return b


def _place_hero(engine, hero_class: str, x: float, y: float) -> Hero:
    h = Hero(float(x), float(y), hero_class=str(hero_class))
    engine.heroes.append(h)
    return h


def _place_enemy(engine, enemy_type: str, x: float, y: float) -> Enemy:
    e = Enemy(float(x), float(y), enemy_type=str(enemy_type))
    engine.enemies.append(e)
    return e


def _tile_center_px(gx: int, gy: int) -> tuple[float, float]:
    return (gx * TILE_SIZE + TILE_SIZE / 2.0, gy * TILE_SIZE + TILE_SIZE / 2.0)


def _fit_grid_positions(
    *,
    building_types: list[str],
    building_sizes: dict[str, tuple[int, int]],
    start_gx: int,
    start_gy: int,
    max_cols: int = 6,
    padding_tiles: int = 1,
) -> dict[str, tuple[int, int]]:
    """
    Lay out buildings in a deterministic grid using their footprint sizes.
    Returns mapping building_type -> (grid_x, grid_y).
    """
    positions: dict[str, tuple[int, int]] = {}
    cx = int(start_gx)
    cy = int(start_gy)
    col = 0
    row_h = 0

    for bt in building_types:
        w, h = building_sizes.get(bt, (2, 2))
        if col >= max_cols:
            col = 0
            cx = int(start_gx)
            cy += row_h + padding_tiles
            row_h = 0

        positions[bt] = (cx, cy)
        cx += w + padding_tiles
        row_h = max(row_h, h)
        col += 1

    return positions


def scenario_building_catalog(engine, *, seed: int, asset_manifest_path: Path = DEFAULT_MANIFEST) -> list[Shot]:
    """
    Place one instance of each building type (from tools/assets_manifest.json) in a grid.
    Capture:
    - one overview
    - one close-up per building type
    """
    _clear_dynamic_entities(engine)
    _clear_non_castle_buildings(engine)
    _reveal_all(engine.world)

    asset_manifest = _load_asset_manifest(asset_manifest_path)
    building_types: list[str] = list(asset_manifest.get("buildings", {}).get("types", []))
    # Castle already exists; we still include it as a shot target, but don't place a second one.
    place_types = [bt for bt in building_types if bt != "castle"]

    # Resolve sizes from config (imported via Building class module).
    from config import BUILDING_SIZES

    castle = next((b for b in engine.buildings if getattr(b, "building_type", "") == "castle"), None)
    if castle is None:
        # If engine didn't build one for some reason, create it at center.
        gx = MAP_WIDTH // 2 - 1
        gy = MAP_HEIGHT // 2 - 1
        castle = _place_building(engine, "castle", gx, gy)

    # Grid start slightly above-left of castle footprint.
    start_gx = max(2, int(getattr(castle, "grid_x", MAP_WIDTH // 2)) - 18)
    start_gy = max(2, int(getattr(castle, "grid_y", MAP_HEIGHT // 2)) - 10)

    positions = _fit_grid_positions(
        building_types=place_types,
        building_sizes=BUILDING_SIZES,
        start_gx=start_gx,
        start_gy=start_gy,
        max_cols=6,
        padding_tiles=1,
    )

    # Place the catalog buildings.
    placed: dict[str, Building] = {}
    for bt, (gx, gy) in positions.items():
        placed[bt] = _place_building(engine, bt, gx, gy)

    # Frame overview roughly centered on the grid.
    # Use castle as anchor; the layout is designed to sit near the castle.
    shots: list[Shot] = []

    shots.append(
        Shot(
            filename="building_catalog_overview.png",
            label="Building Catalog (Overview)",
            center_x=float(getattr(castle, "center_x", getattr(castle, "x", 0.0))),
            center_y=float(getattr(castle, "center_y", getattr(castle, "y", 0.0))),
            zoom=1.0,
            ticks=0,
            meta={"scenario": "building_catalog", "seed": int(seed)},
        )
    )

    # Close-up per building type (including castle).
    def _b_center(obj) -> tuple[float, float]:
        return float(getattr(obj, "center_x", getattr(obj, "x", 0.0))), float(getattr(obj, "center_y", getattr(obj, "y", 0.0)))

    if castle is not None:
        cx, cy = _b_center(castle)
        shots.append(
            Shot(
                filename="building_castle_closeup.png",
                label="Building: castle",
                center_x=cx,
                center_y=cy,
                zoom=2.0,
                ticks=0,
                meta={"building_type": "castle"},
            )
        )

    for bt in building_types:
        if bt == "castle":
            continue
        b = placed.get(bt)
        if b is None:
            continue
        cx, cy = _b_center(b)
        shots.append(
            Shot(
                filename=f"building_{bt}_closeup.png",
                label=f"Building: {bt}",
                center_x=cx,
                center_y=cy,
                zoom=2.0,
                ticks=0,
                meta={"building_type": bt},
            )
        )

    return shots


def scenario_enemy_catalog(engine, *, seed: int, asset_manifest_path: Path = DEFAULT_MANIFEST) -> list[Shot]:
    """
    Spawn one instance of each enemy type (from tools/assets_manifest.json) in a neat row.
    Capture:
    - overview (row)
    - one close-up per enemy type
    """
    _clear_dynamic_entities(engine)
    _clear_non_castle_buildings(engine)
    _reveal_all(engine.world)

    asset_manifest = _load_asset_manifest(asset_manifest_path)
    enemy_types: list[str] = list(asset_manifest.get("enemies", {}).get("types", []))

    # Anchor near the castle but with enough empty space around for close-ups.
    castle = next((b for b in engine.buildings if getattr(b, "building_type", "") == "castle"), None)
    if castle is None:
        gx = MAP_WIDTH // 2 - 1
        gy = MAP_HEIGHT // 2 - 1
        castle = _place_building(engine, "castle", gx, gy)

    base_gx = max(2, int(getattr(castle, "grid_x", MAP_WIDTH // 2)) - 10)
    base_gy = min(MAP_HEIGHT - 4, int(getattr(castle, "grid_y", MAP_HEIGHT // 2)) + 10)

    placed: dict[str, Enemy] = {}
    for i, et in enumerate(enemy_types):
        gx = min(MAP_WIDTH - 3, base_gx + i * 3)
        gy = base_gy
        x, y = _tile_center_px(gx, gy)
        placed[et] = _place_enemy(engine, et, x, y)

    # Overview: center on the row midpoint.
    if enemy_types:
        mid = enemy_types[len(enemy_types) // 2]
        mx, my = float(getattr(placed[mid], "x", 0.0)), float(getattr(placed[mid], "y", 0.0))
    else:
        mx, my = float(getattr(castle, "center_x", 0.0)), float(getattr(castle, "center_y", 0.0))

    shots: list[Shot] = [
        Shot(
            filename="enemy_catalog_overview.png",
            label="Enemy Catalog (Overview)",
            center_x=mx,
            center_y=my,
            zoom=2.0,
            meta={"scenario": "enemy_catalog", "seed": int(seed)},
        )
    ]

    for et in enemy_types:
        e = placed.get(et)
        if e is None:
            continue
        shots.append(
            Shot(
                filename=f"enemy_{et}_closeup.png",
                label=f"Enemy: {et}",
                center_x=float(getattr(e, "x", 0.0)),
                center_y=float(getattr(e, "y", 0.0)),
                zoom=3.0,
                meta={"enemy_type": et},
            )
        )

    return shots


def scenario_base_overview(engine, *, seed: int) -> list[Shot]:
    """
    A representative 'starter town' overview: castle + several core buildings + a few heroes/enemies.
    Intended for style comparisons (scale/readability/contrast).
    """
    _clear_dynamic_entities(engine)
    _clear_non_castle_buildings(engine)
    _reveal_all(engine.world)

    castle = next((b for b in engine.buildings if getattr(b, "building_type", "") == "castle"), None)
    if castle is None:
        gx = MAP_WIDTH // 2 - 1
        gy = MAP_HEIGHT // 2 - 1
        castle = _place_building(engine, "castle", gx, gy)

    cgx = int(getattr(castle, "grid_x", MAP_WIDTH // 2))
    cgy = int(getattr(castle, "grid_y", MAP_HEIGHT // 2))

    # Small curated set of buildings that matter most for readability.
    layout = [
        ("marketplace", cgx + 6, cgy - 2),
        ("inn", cgx + 6, cgy + 2),
        ("blacksmith", cgx - 7, cgy - 2),
        ("guardhouse", cgx - 7, cgy + 3),
        ("warrior_guild", cgx + 2, cgy - 7),
        ("ranger_guild", cgx - 3, cgy - 7),
        ("wizard_guild", cgx + 1, cgy + 7),
        ("rogue_guild", cgx - 3, cgy + 7),
        ("house", cgx + 10, cgy + 6),
        ("farm", cgx + 12, cgy + 9),
        ("food_stand", cgx + 9, cgy + 10),
    ]

    for bt, gx, gy in layout:
        gx = max(2, min(MAP_WIDTH - 3, int(gx)))
        gy = max(2, min(MAP_HEIGHT - 3, int(gy)))
        _place_building(engine, bt, gx, gy)

    # Place a few heroes near the castle for a representative crowd.
    hx, hy = _tile_center_px(cgx + 3, cgy + 1)
    _place_hero(engine, "warrior", hx, hy)
    hx, hy = _tile_center_px(cgx + 4, cgy + 2)
    _place_hero(engine, "ranger", hx, hy)
    hx, hy = _tile_center_px(cgx + 2, cgy + 3)
    _place_hero(engine, "rogue", hx, hy)
    hx, hy = _tile_center_px(cgx + 1, cgy + 2)
    _place_hero(engine, "wizard", hx, hy)

    # Place a couple enemies off to the side to check combat readability layers.
    ex, ey = _tile_center_px(cgx - 12, cgy + 10)
    _place_enemy(engine, "goblin", ex, ey)
    ex, ey = _tile_center_px(cgx - 14, cgy + 10)
    _place_enemy(engine, "wolf", ex, ey)

    def _apply_world_clean(engine2):
        engine2.selected_hero = None
        engine2.selected_building = None
        if hasattr(engine2, "debug_panel"):
            engine2.debug_panel.visible = False
        engine2.screenshot_hide_ui = True

    def _apply_ui_default(engine2):
        engine2.selected_hero = None
        engine2.selected_building = None
        if hasattr(engine2, "debug_panel"):
            engine2.debug_panel.visible = False
        engine2.screenshot_hide_ui = False

    cx = float(getattr(castle, "center_x", getattr(castle, "x", 0.0)))
    cy = float(getattr(castle, "center_y", getattr(castle, "y", 0.0)))
    return [
        Shot(
            filename="base_overview__Z1__world_clean.png",
            label="Base Overview (Z1, world clean)",
            center_x=cx,
            center_y=cy,
            zoom=1.0,
            meta={"scenario": "base_overview", "seed": int(seed), "zoom": 1.0, "ui": "world_clean"},
            apply=_apply_world_clean,
        ),
        Shot(
            filename="base_overview__Z1__ui_default.png",
            label="Base Overview (Z1, UI default)",
            center_x=cx,
            center_y=cy,
            zoom=1.0,
            meta={"scenario": "base_overview", "seed": int(seed), "zoom": 1.0, "ui": "ui_default"},
            apply=_apply_ui_default,
        ),
        Shot(
            filename="base_overview__Z2__world_clean.png",
            label="Base Overview (Z2, world clean)",
            center_x=cx,
            center_y=cy,
            zoom=1.6,
            meta={"scenario": "base_overview", "seed": int(seed), "zoom": 1.6, "ui": "world_clean"},
            apply=_apply_world_clean,
        ),
        Shot(
            filename="base_overview__Z2__ui_default.png",
            label="Base Overview (Z2, UI default)",
            center_x=cx,
            center_y=cy,
            zoom=1.6,
            meta={"scenario": "base_overview", "seed": int(seed), "zoom": 1.6, "ui": "ui_default"},
            apply=_apply_ui_default,
        ),
    ]


def scenario_ui_panels(engine, *, seed: int) -> list[Shot]:
    """
    Capture UI manageability/readability: right info panel (hero/building) + debug panel.
    Uses per-shot apply() hooks to toggle selection and panel visibility.
    """
    _clear_dynamic_entities(engine)
    _clear_non_castle_buildings(engine)
    _reveal_all(engine.world)

    castle = next((b for b in engine.buildings if getattr(b, "building_type", "") == "castle"), None)
    if castle is None:
        gx = MAP_WIDTH // 2 - 1
        gy = MAP_HEIGHT // 2 - 1
        castle = _place_building(engine, "castle", gx, gy)

    cgx = int(getattr(castle, "grid_x", MAP_WIDTH // 2))
    cgy = int(getattr(castle, "grid_y", MAP_HEIGHT // 2))

    # Ensure we have at least one building + hero to select.
    inn = _place_building(engine, "inn", cgx + 6, cgy + 2)
    hx, hy = _tile_center_px(cgx + 3, cgy + 1)
    hero = _place_hero(engine, "warrior", hx, hy)

    def _apply_clear(engine2):
        engine2.selected_hero = None
        engine2.selected_building = None
        if hasattr(engine2, "debug_panel"):
            engine2.debug_panel.visible = False

    def _apply_select_hero(engine2):
        _apply_clear(engine2)
        engine2.selected_hero = hero

    def _apply_select_building(engine2):
        _apply_clear(engine2)
        engine2.selected_building = inn

    def _apply_debug_open(engine2):
        _apply_select_hero(engine2)
        if hasattr(engine2, "debug_panel"):
            engine2.debug_panel.visible = True

    cx = float(getattr(castle, "center_x", getattr(castle, "x", 0.0)))
    cy = float(getattr(castle, "center_y", getattr(castle, "y", 0.0)))
    return [
        Shot(
            filename="ui_panels_hero.png",
            label="UI Panels: Hero Selected (Right Panel)",
            center_x=cx,
            center_y=cy,
            zoom=1.4,
            meta={"scenario": "ui_panels", "mode": "hero"},
            apply=_apply_select_hero,
        ),
        Shot(
            filename="ui_panels_building.png",
            label="UI Panels: Building Selected (Right Panel)",
            center_x=cx,
            center_y=cy,
            zoom=1.4,
            meta={"scenario": "ui_panels", "mode": "building"},
            apply=_apply_select_building,
        ),
        Shot(
            filename="ui_panels_debug.png",
            label="UI Panels: Debug Panel Open",
            center_x=cx,
            center_y=cy,
            zoom=1.4,
            meta={"scenario": "ui_panels", "mode": "debug"},
            apply=_apply_debug_open,
        ),
    ]


def _place_worker(engine, worker_type: str, x: float, y: float):
    """Place a worker (peasant or tax_collector) at the given coordinates."""
    if worker_type == "peasant":
        from game.entities.peasant import Peasant
        w = Peasant(float(x), float(y))
        engine.peasants.append(w)
        return w
    elif worker_type == "tax_collector":
        from game.entities.tax_collector import TaxCollector
        # TaxCollector needs a castle reference; use the first castle found
        castle = next((b for b in engine.buildings if getattr(b, "building_type", "") == "castle"), None)
        if castle is None:
            # Create a dummy castle if none exists
            gx = MAP_WIDTH // 2 - 1
            gy = MAP_HEIGHT // 2 - 1
            castle = _place_building(engine, "castle", gx, gy)
        w = TaxCollector(castle)
        w.x = float(x)
        w.y = float(y)
        engine.tax_collector = w
        return w
    else:
        raise ValueError(f"Unknown worker type: {worker_type}")


def scenario_worker_catalog(engine, *, seed: int, asset_manifest_path: Path = DEFAULT_MANIFEST) -> list[Shot]:
    """
    Spawn one instance of each worker type (peasant, tax_collector) near the castle.
    Capture:
    - overview (both workers visible)
    - one close-up per worker type
    """
    _clear_dynamic_entities(engine)
    _clear_non_castle_buildings(engine)
    _reveal_all(engine.world)

    asset_manifest = _load_asset_manifest(asset_manifest_path)
    worker_types: list[str] = list(asset_manifest.get("workers", {}).get("types", []))

    # Anchor near the castle
    castle = next((b for b in engine.buildings if getattr(b, "building_type", "") == "castle"), None)
    if castle is None:
        gx = MAP_WIDTH // 2 - 1
        gy = MAP_HEIGHT // 2 - 1
        castle = _place_building(engine, "castle", gx, gy)

    cgx = int(getattr(castle, "grid_x", MAP_WIDTH // 2))
    cgy = int(getattr(castle, "grid_y", MAP_HEIGHT // 2))

    placed: dict[str, object] = {}
    for i, wt in enumerate(worker_types):
        gx = cgx + 4 + i * 3
        gy = cgy + 2
        x, y = _tile_center_px(gx, gy)
        placed[wt] = _place_worker(engine, wt, x, y)

    # Overview: center on the midpoint between workers
    if worker_types:
        mid = worker_types[len(worker_types) // 2]
        w = placed.get(mid)
        if w is not None:
            mx, my = float(getattr(w, "x", 0.0)), float(getattr(w, "y", 0.0))
        else:
            mx, my = float(getattr(castle, "center_x", 0.0)), float(getattr(castle, "center_y", 0.0))
    else:
        mx, my = float(getattr(castle, "center_x", 0.0)), float(getattr(castle, "center_y", 0.0))

    shots: list[Shot] = [
        Shot(
            filename="worker_catalog_overview.png",
            label="Worker Catalog (Overview)",
            center_x=mx,
            center_y=my,
            zoom=2.0,
            meta={"scenario": "worker_catalog", "seed": int(seed)},
        )
    ]

    for wt in worker_types:
        w = placed.get(wt)
        if w is None:
            continue
        shots.append(
            Shot(
                filename=f"worker_{wt}_closeup.png",
                label=f"Worker: {wt}",
                center_x=float(getattr(w, "x", 0.0)),
                center_y=float(getattr(w, "y", 0.0)),
                zoom=3.0,
                meta={"worker_type": wt},
            )
        )

    return shots


def scenario_ranged_projectiles(engine, *, seed: int) -> list[Shot]:
    """
    Capture ranged projectiles mid-flight.
    Places a ranged attacker (ranger or skeleton_archer) and a target, then advances
    sim ticks to trigger an attack and capture when projectile is visible.
    """
    _clear_dynamic_entities(engine)
    _clear_non_castle_buildings(engine)
    _reveal_all(engine.world)

    # Place castle as anchor
    castle = next((b for b in engine.buildings if getattr(b, "building_type", "") == "castle"), None)
    if castle is None:
        gx = MAP_WIDTH // 2 - 1
        gy = MAP_HEIGHT // 2 - 1
        castle = _place_building(engine, "castle", gx, gy)

    cgx = int(getattr(castle, "grid_x", MAP_WIDTH // 2))
    cgy = int(getattr(castle, "grid_y", MAP_HEIGHT // 2))

    # Place a ranged attacker (ranger) and a target (enemy)
    attacker_x, attacker_y = _tile_center_px(cgx - 5, cgy)
    target_x, target_y = _tile_center_px(cgx + 5, cgy)

    attacker = _place_hero(engine, "ranger", attacker_x, attacker_y)
    target = _place_enemy(engine, "goblin", target_x, target_y)

    # Set up attack state (attacker targets the enemy)
    if hasattr(attacker, "target"):
        attacker.target = target
    if hasattr(attacker, "state"):
        attacker.state = "attack"  # or whatever the attack state constant is

    # Center point between attacker and target (where projectile should be mid-flight)
    mid_x = (attacker_x + target_x) / 2.0
    mid_y = (attacker_y + target_y) / 2.0

    shots: list[Shot] = [
        Shot(
            filename="ranged_projectiles_overview.png",
            label="Ranged Projectiles (Overview)",
            center_x=mid_x,
            center_y=mid_y,
            zoom=2.0,
            ticks=20,  # WK5 Build B: Updated for slower projectiles (250-450ms = 15-27 ticks at 60 FPS). 20 ticks = mid-flight.
            meta={"scenario": "ranged_projectiles", "seed": int(seed), "attacker": "ranger", "target": "goblin"},
        ),
        Shot(
            filename="ranged_projectiles_closeup.png",
            label="Ranged Projectiles (Close-up)",
            center_x=mid_x,
            center_y=mid_y,
            zoom=3.5,
            ticks=25,  # WK5 Build B: Updated for slower projectiles. 25 ticks = later in flight, still visible.
            meta={"scenario": "ranged_projectiles", "seed": int(seed), "zoom": "closeup"},
        ),
    ]

    return shots


def get_scenario(engine, scenario_name: str, *, seed: int) -> list[Shot]:
    scenario_name = str(scenario_name).strip()
    if scenario_name == "building_catalog":
        return scenario_building_catalog(engine, seed=int(seed))
    if scenario_name == "enemy_catalog":
        return scenario_enemy_catalog(engine, seed=int(seed))
    if scenario_name == "base_overview":
        return scenario_base_overview(engine, seed=int(seed))
    if scenario_name == "ui_panels":
        return scenario_ui_panels(engine, seed=int(seed))
    if scenario_name == "worker_catalog":
        return scenario_worker_catalog(engine, seed=int(seed))
    if scenario_name == "ranged_projectiles":
        return scenario_ranged_projectiles(engine, seed=int(seed))
    raise ValueError(f"Unknown scenario: {scenario_name}")


