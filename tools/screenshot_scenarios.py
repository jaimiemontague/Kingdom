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

from config import STARTING_BUILDINGS, TAX_STASH_BUILDING_TYPES, TILE_SIZE, MAP_WIDTH, MAP_HEIGHT
from game.entities.building import Building
from game.entities.hero import Hero
from game.entities.enemy import Enemy
from game.world import TileType


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
    # Optional override for capture surface (defaults to CLI --size)
    width: int | None = None
    height: int | None = None


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


def _find_terrain_focus(world, *, window: int = 12, step: int = 4) -> tuple[int, int]:
    """
    Find a deterministic terrain focus area with trees + paths and minimal water.
    Returns a grid coordinate to center the camera.
    """
    width = int(getattr(world, "width", MAP_WIDTH))
    height = int(getattr(world, "height", MAP_HEIGHT))
    tiles = getattr(world, "tiles", None)
    if tiles is None:
        return (width // 2, height // 2)

    best_score = None
    best_pos = (width // 2, height // 2)
    max_x = max(1, width - window - 1)
    max_y = max(1, height - window - 1)

    for gy in range(2, max_y, step):
        for gx in range(2, max_x, step):
            trees = 0
            paths = 0
            water = 0
            for y in range(gy, gy + window):
                row = tiles[y]
                for x in range(gx, gx + window):
                    tile = row[x]
                    if tile == TileType.TREE:
                        trees += 1
                    elif tile == TileType.PATH:
                        paths += 1
                    elif tile == TileType.WATER:
                        water += 1
            score = trees * 2 + paths - water * 3
            if best_score is None or score > best_score:
                best_score = score
                best_pos = (gx + window // 2, gy + window // 2)

    return best_pos


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

    # WK131: dress the scenario hero in full gear (weapon + armor + accessory +
    # backpack loot) so the hero-panel Gear block and watch-card gear line are
    # visible in the captures. Capture-only state — never runs in the game.
    try:
        from game.content.items import get_item

        for item_id in ("steel_sword", "chain_mail", "hawk_signet"):
            hero.equip(get_item(item_id))
        hero.add_to_backpack(get_item("healing_potion"))
        hero.add_to_backpack(get_item("swiftness_draught"))
    except Exception:
        pass

    def _apply_clear(engine2):
        engine2.selected_hero = None
        engine2.selected_building = None
        try:
            engine2.screenshot_hide_ui = False
        except Exception:
            pass
        if hasattr(engine2, "debug_panel"):
            engine2.debug_panel.visible = False
        if hasattr(engine2, "building_panel"):
            engine2.building_panel.deselect()

    def _apply_select_hero(engine2):
        _apply_clear(engine2)
        if hasattr(engine2, "hud"):
            engine2.hud.right_panel_visible = True
        engine2.selected_hero = hero

    def _apply_select_building(engine2):
        _apply_clear(engine2)
        if hasattr(engine2, "hud"):
            engine2.hud.right_panel_visible = True
        engine2.selected_building = inn
        if hasattr(engine2, "building_panel"):
            engine2.building_panel.select_building(inn, getattr(engine2, "heroes", []))

    def _apply_marketplace_taxable_gold(engine2):
        from game.entities.buildings.economic import Marketplace

        _apply_clear(engine2)
        if hasattr(engine2, "hud"):
            engine2.hud.right_panel_visible = True
        mp = Marketplace(cgx + 4, cgy - 2)
        mp.is_constructed = True
        mp.potions_researched = True
        mp.stored_tax_gold = 42
        engine2.buildings.append(mp)
        engine2.selected_building = mp
        if hasattr(engine2, "building_panel"):
            engine2.building_panel.select_building(mp, getattr(engine2, "heroes", []))

    def _apply_sidebar_pin_split(engine2):
        from game.sim.timebase import now_ms as sim_now_ms

        _apply_select_hero(engine2)
        hid = str(getattr(hero, "hero_id", "") or "")
        if hasattr(engine2, "hud"):
            engine2.hud._pin_slot.pin(hid, int(sim_now_ms()))
            engine2.hud._pin_slot.pinned_name = str(getattr(hero, "name", "Hero"))
            engine2.hud._pin_slot._just_pinned = False
            engine2.hud._watch_card_expanded = True
            engine2.hud._left_split_fracs = {"main": 0.32, "watch": 0.68}

    def _apply_pinned_chat(engine2):
        """WK115 BUG 3: pinned watch hero with Chat pressed — card must grow to fit chat."""
        from game.sim.timebase import now_ms as sim_now_ms

        _apply_select_hero(engine2)
        hid = str(getattr(hero, "hero_id", "") or "")
        hud = getattr(engine2, "hud", None)
        if hud is not None:
            hud._pin_slot.pin(hid, int(sim_now_ms()))
            hud._pin_slot.pinned_name = str(getattr(hero, "name", "Hero"))
            hud._pin_slot._just_pinned = False
            hud._watch_card_expanded = True
            hud._chat_visible = True
            # Small watch fraction so the un-grown split would be too short for the
            # chatbox; the BUG 3 fix must grow the watch segment to fit the chat band.
            hud._left_split_fracs = {"main": 0.7, "watch": 0.3}
            cp = getattr(hud, "_chat_panel", None)
            if cp is not None:
                cp.start_conversation(hero)
                cp.conversation_history.clear()
                cp.conversation_history.extend(
                    [
                        {"role": "player", "text": "Hold the gate while I rally the others."},
                        {"role": "hero", "text": "Aye, my liege — nothing passes me."},
                        {"role": "player", "text": "Good. Watch the treeline."},
                    ]
                )

    def _apply_debug_open(engine2):
        _apply_select_hero(engine2)
        if hasattr(engine2, "debug_panel"):
            engine2.debug_panel.visible = True

    def _apply_right_panel_hidden(engine2):
        _apply_clear(engine2)
        if hasattr(engine2, "hud"):
            engine2.hud.right_panel_visible = False
        engine2.selected_hero = hero

    def _apply_select_tax_collector(engine2):
        _apply_clear(engine2)
        if hasattr(engine2, "hud"):
            engine2.hud.right_panel_visible = True
        tc = getattr(engine2, "tax_collector", None)
        if tc is not None:
            engine2.selected_hero = tc

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
            filename="ui_panels_hidden.png",
            label="UI Panels: Right Panel Hidden",
            center_x=cx,
            center_y=cy,
            zoom=1.4,
            meta={"scenario": "ui_panels", "mode": "hidden"},
            apply=_apply_right_panel_hidden,
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
        Shot(
            filename="ui_panels_tax_collector.png",
            label="UI Panels: Tax Collector Selected (Left Panel)",
            center_x=cx,
            center_y=cy,
            zoom=1.4,
            meta={"scenario": "ui_panels", "mode": "tax_collector"},
            apply=_apply_select_tax_collector,
        ),
        Shot(
            filename="ui_panels_sidebar_split.png",
            label="UI Panels: Pinned Watch + Hero Split (WK61-R10)",
            center_x=cx,
            center_y=cy,
            zoom=1.4,
            meta={"scenario": "ui_panels", "mode": "sidebar_split"},
            apply=_apply_sidebar_pin_split,
        ),
        Shot(
            filename="ui_panels_marketplace_tax.png",
            label="UI Panels: Marketplace Taxable Gold $42 (WK61-R10)",
            center_x=cx,
            center_y=cy,
            zoom=1.4,
            meta={"scenario": "ui_panels", "mode": "marketplace_tax"},
            apply=_apply_marketplace_taxable_gold,
        ),
        Shot(
            filename="ui_panels_pinned_chat.png",
            label="UI Panels: Pinned Watch Hero + Chat Open (WK115 BUG 3)",
            center_x=cx,
            center_y=cy,
            zoom=1.4,
            meta={"scenario": "ui_panels", "mode": "pinned_chat"},
            apply=_apply_pinned_chat,
        ),
    ]


def scenario_ui_pause_menu(engine, *, seed: int) -> list[Shot]:
    """Capture the ESC pause menu UI."""
    _clear_dynamic_entities(engine)
    _clear_non_castle_buildings(engine)
    _reveal_all(engine.world)
    castle = next((b for b in engine.buildings if getattr(b, "building_type", "") == "castle"), None)
    if castle is None:
        gx = MAP_WIDTH // 2 - 1
        gy = MAP_HEIGHT // 2 - 1
        castle = _place_building(engine, "castle", gx, gy)

    def _apply_pause(engine2):
        try:
            engine2.screenshot_hide_ui = False
        except Exception:
            pass
        if hasattr(engine2, "pause_menu"):
            engine2.pause_menu.open()
            engine2.pause_menu.current_page = "main"

    cx = float(getattr(castle, "center_x", getattr(castle, "x", 0.0)))
    cy = float(getattr(castle, "center_y", getattr(castle, "y", 0.0)))
    return [
        Shot(
            filename="ui_pause_menu.png",
            label="UI: Pause Menu (ESC)",
            center_x=cx,
            center_y=cy,
            zoom=1.2,
            meta={"scenario": "ui_pause_menu", "seed": int(seed)},
            apply=_apply_pause,
        ),
    ]


def scenario_ui_build_catalog(engine, *, seed: int) -> list[Shot]:
    """Capture the castle build catalog UI."""
    _clear_dynamic_entities(engine)
    _clear_non_castle_buildings(engine)
    _reveal_all(engine.world)
    castle = next((b for b in engine.buildings if getattr(b, "building_type", "") == "castle"), None)
    if castle is None:
        gx = MAP_WIDTH // 2 - 1
        gy = MAP_HEIGHT // 2 - 1
        castle = _place_building(engine, "castle", gx, gy)

    def _apply_catalog(engine2):
        try:
            engine2.screenshot_hide_ui = False
        except Exception:
            pass
        if hasattr(engine2, "build_catalog_panel"):
            engine2.build_catalog_panel.open()

    cx = float(getattr(castle, "center_x", getattr(castle, "x", 0.0)))
    cy = float(getattr(castle, "center_y", getattr(castle, "y", 0.0)))
    return [
        Shot(
            filename="ui_build_catalog.png",
            label="UI: Build Catalog",
            center_x=cx,
            center_y=cy,
            zoom=1.2,
            meta={"scenario": "ui_build_catalog", "seed": int(seed)},
            apply=_apply_catalog,
        ),
    ]


def scenario_ui_audio_blacksmith(engine, *, seed: int) -> list[Shot]:
    """
    V1.3 extension capture set:
    - Audio page (3 sliders)
    - Blacksmith panel with research/purchase info
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
    blacksmith = _place_building(engine, "blacksmith", cgx + 6, cgy - 2)

    def _apply_audio(engine2):
        if hasattr(engine2, "screenshot_hide_ui"):
            engine2.screenshot_hide_ui = False
        if hasattr(engine2, "pause_menu"):
            engine2.pause_menu.open()
            engine2.pause_menu.current_page = "audio"

    def _apply_blacksmith(engine2):
        if hasattr(engine2, "screenshot_hide_ui"):
            engine2.screenshot_hide_ui = False
        if hasattr(engine2, "hud"):
            engine2.hud.right_panel_visible = True
        engine2.selected_hero = None
        engine2.selected_building = blacksmith

    cx = float(getattr(castle, "center_x", getattr(castle, "x", 0.0)))
    cy = float(getattr(castle, "center_y", getattr(castle, "y", 0.0)))
    bx = float(getattr(blacksmith, "center_x", getattr(blacksmith, "x", 0.0)))
    by = float(getattr(blacksmith, "center_y", getattr(blacksmith, "y", 0.0)))

    return [
        Shot(
            filename="ui_audio_page.png",
            label="UI: Audio Page (3 Sliders)",
            center_x=cx,
            center_y=cy,
            zoom=1.2,
            meta={"scenario": "ui_audio_blacksmith", "seed": int(seed), "page": "audio"},
            apply=_apply_audio,
        ),
        Shot(
            filename="ui_blacksmith_panel.png",
            label="UI: Blacksmith Panel",
            center_x=bx,
            center_y=by,
            zoom=1.6,
            meta={"scenario": "ui_audio_blacksmith", "seed": int(seed), "panel": "blacksmith"},
            apply=_apply_blacksmith,
        ),
    ]


def scenario_ui_polish_after(engine, *, seed: int) -> list[Shot]:
    """
    V1.3 UI polish capture set:
    - base overview (UI on)
    - right panel states (hero/building + hidden + debug)
    - pause menu
    - build catalog
    """
    shots: list[Shot] = []
    shots.extend(scenario_base_overview(engine, seed=int(seed)))
    shots.extend(scenario_ui_panels(engine, seed=int(seed)))
    shots.extend(scenario_ui_pause_menu(engine, seed=int(seed)))
    shots.extend(scenario_ui_build_catalog(engine, seed=int(seed)))
    return shots


def scenario_world_variation(engine, *, seed: int) -> list[Shot]:
    """
    V1.3 terrain/trees variety capture set (UI visible).
    Focuses on grass + trees + paths without fog edits.
    """
    _clear_dynamic_entities(engine)
    _clear_non_castle_buildings(engine)
    _reveal_all(engine.world)

    focus_gx, focus_gy = _find_terrain_focus(engine.world)
    focus_x, focus_y = _tile_center_px(focus_gx, focus_gy)

    def _apply_ui_visible(engine2):
        if hasattr(engine2, "screenshot_hide_ui"):
            engine2.screenshot_hide_ui = False

    return [
        Shot(
            filename="world_variation_overview.png",
            label="World Variation (Overview)",
            center_x=focus_x,
            center_y=focus_y,
            zoom=1.6,
            ticks=0,
            apply=_apply_ui_visible,
            meta={"scenario": "world_variation", "seed": int(seed)},
        ),
        Shot(
            filename="world_variation_closeup.png",
            label="World Variation (Close-up)",
            center_x=focus_x,
            center_y=focus_y,
            zoom=2.4,
            ticks=0,
            apply=_apply_ui_visible,
            meta={"scenario": "world_variation", "seed": int(seed), "zoom": "closeup"},
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


def scenario_building_debris(engine, *, seed: int) -> list[Shot]:
    """
    Capture building debris after manual demolition.
    Places a house, advances a few ticks, demolishes it deterministically, then captures post-demolish frame showing debris.
    
    WK5 Hotfix: Ensures debris is clearly visible after demolition.
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

    # Place a house building near the castle
    house_gx = cgx + 4
    house_gy = cgy + 2
    house = _place_building(engine, "house", house_gx, house_gy)

    # Get building center for camera (use this even after demolition for debris location)
    house_x = float(getattr(house, "center_x", getattr(house, "x", 0.0)))
    house_y = float(getattr(house, "center_y", getattr(house, "y", 0.0)))

    # Create a closure to capture the house reference for demolition
    # Note: apply() is called AFTER tick advance, so we demolish it after letting it settle
    def demolish_house(eng):
        """Demolish the house by setting hp=0 and calling cleanup to trigger debris spawning."""
        # Find the house by grid position (deterministic lookup)
        for b in eng.buildings:
            if (getattr(b, "building_type", "") == "house" and
                int(getattr(b, "grid_x", -1)) == house_gx and
                int(getattr(b, "grid_y", -1)) == house_gy):
                b.hp = 0
                # Call cleanup to trigger debris spawning (emit_messages=False to avoid HUD noise)
                if hasattr(eng, "_cleanup_destroyed_buildings"):
                    eng._cleanup_destroyed_buildings(emit_messages=False)
                break

    shots: list[Shot] = [
        Shot(
            filename="building_debris_overview.png",
            label="Building Debris (Overview)",
            center_x=house_x,
            center_y=house_y,
            zoom=2.0,
            ticks=3,  # Advance 3 ticks to let building settle visually
            apply=demolish_house,  # Demolish after tick advance (cleanup triggers debris event)
            meta={"scenario": "building_debris", "seed": int(seed), "building_type": "house"},
        ),
        Shot(
            filename="building_debris_closeup.png",
            label="Building Debris (Close-up)",
            center_x=house_x,
            center_y=house_y,
            zoom=3.5,
            ticks=1,  # Advance 1 tick after demolition to ensure debris VFX is spawned and visible
            meta={"scenario": "building_debris", "seed": int(seed), "zoom": "closeup"},
        ),
    ]

    return shots


def scenario_bounty_in_black_fog(engine, *, seed: int) -> list[Shot]:
    """
    Capture bounty marker visible in solid black fog (UNSEEN visibility).
    Places a bounty at unrevealed coordinates and ensures the marker is visible.
    
    WK6: Ensures bounties are visible even in black fog and Rangers can path to them.
    """
    _clear_dynamic_entities(engine)
    _clear_non_castle_buildings(engine)
    
    # Place castle as anchor
    castle = next((b for b in engine.buildings if getattr(b, "building_type", "") == "castle"), None)
    if castle is None:
        gx = MAP_WIDTH // 2 - 1
        gy = MAP_HEIGHT // 2 - 1
        castle = _place_building(engine, "castle", gx, gy)

    cgx = int(getattr(castle, "grid_x", MAP_WIDTH // 2))
    cgy = int(getattr(castle, "grid_y", MAP_HEIGHT // 2))

    # Reveal only the castle area (keep bounty area in black fog)
    # Use _reveal_all for now, then manually set bounty area to UNSEEN
    _reveal_all(engine.world)
    
    # Place bounty at unrevealed coordinates (far from castle, in black fog)
    bounty_gx = cgx + 20
    bounty_gy = cgy + 15
    bounty_x, bounty_y = _tile_center_px(bounty_gx, bounty_gy)
    
    # Ensure bounty tile and surrounding area are UNSEEN (black fog)
    from game.world import Visibility
    if hasattr(engine.world, "visibility"):
        vis = engine.world.visibility
        # Set bounty area to UNSEEN (black fog)
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                tx = bounty_gx + dx
                ty = bounty_gy + dy
                if 0 <= tx < len(vis[0]) and 0 <= ty < len(vis):
                    vis[ty][tx] = Visibility.UNSEEN
        # Also clear from currently_visible set if it exists
        if hasattr(engine.world, "_currently_visible"):
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    tx = bounty_gx + dx
                    ty = bounty_gy + dy
                    engine.world._currently_visible.discard((tx, ty))

    # Place bounty using bounty system
    if hasattr(engine, "bounty_system"):
        engine.bounty_system.place_bounty(bounty_x, bounty_y, reward=100, bounty_type="explore")
    else:
        # Fallback: create bounty manually if system not available
        from game.systems.bounty import Bounty
        if not hasattr(engine, "bounties"):
            engine.bounties = []
        bounty = Bounty(bounty_x, bounty_y, reward=100, bounty_type="explore")
        engine.bounties.append(bounty)

    shots: list[Shot] = [
        Shot(
            filename="bounty_in_black_fog_overview.png",
            label="Bounty in Black Fog (Overview)",
            center_x=bounty_x,
            center_y=bounty_y,
            zoom=2.0,
            ticks=0,
            meta={"scenario": "bounty_in_black_fog", "seed": int(seed), "bounty_type": "explore"},
        ),
        Shot(
            filename="bounty_in_black_fog_closeup.png",
            label="Bounty in Black Fog (Close-up)",
            center_x=bounty_x,
            center_y=bounty_y,
            zoom=3.5,
            ticks=0,
            meta={"scenario": "bounty_in_black_fog", "seed": int(seed), "zoom": "closeup"},
        ),
    ]

    return shots


def scenario_building_menu_open(engine, *, seed: int) -> list[Shot]:
    """
    Capture build menu panel when open.
    Opens the build menu and captures the clickable building list UI.
    
    WK6: Ensures build menu UI is visible and functional.
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

    # Place a few buildings for context
    cgx = int(getattr(castle, "grid_x", MAP_WIDTH // 2))
    cgy = int(getattr(castle, "grid_y", MAP_HEIGHT // 2))
    _place_building(engine, "marketplace", cgx + 6, cgy - 2)
    _place_building(engine, "inn", cgx + 6, cgy + 2)

    # Get castle center for camera
    castle_x = float(getattr(castle, "center_x", getattr(castle, "x", 0.0)))
    castle_y = float(getattr(castle, "center_y", getattr(castle, "y", 0.0)))

    # Apply hook to open build list panel (WK6)
    def _open_build_menu(eng):
        """Open the build list panel (BuildingListPanel)."""
        # Ensure UI is visible (not hidden for screenshots)
        if hasattr(eng, "screenshot_hide_ui"):
            eng.screenshot_hide_ui = False
        # Open building list panel (WK6 implementation)
        if hasattr(eng, "building_list_panel"):
            eng.building_list_panel.visible = True
            # Ensure panel is properly initialized
            if hasattr(eng.building_list_panel, "toggle"):
                # Use toggle to ensure proper state
                if not eng.building_list_panel.visible:
                    eng.building_list_panel.toggle()

    shots: list[Shot] = [
        Shot(
            filename="building_menu_open_overview.png",
            label="Building Menu Open (Overview)",
            center_x=castle_x,
            center_y=castle_y,
            zoom=1.5,
            ticks=0,
            apply=_open_build_menu,
            meta={"scenario": "building_menu_open", "seed": int(seed), "ui": "menu_open"},
        ),
        Shot(
            filename="building_menu_open_closeup.png",
            label="Building Menu Open (Close-up)",
            center_x=castle_x,
            center_y=castle_y,
            zoom=2.5,
            ticks=0,
            apply=_open_build_menu,
            meta={"scenario": "building_menu_open", "seed": int(seed), "zoom": "closeup", "ui": "menu_open"},
        ),
    ]

    return shots


def scenario_wk52_pin_alerts(engine, *, seed: int) -> list[Shot]:
    """WK52: Pinned hero watch card, radar minimap, memorial overlay."""
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
    _place_building(engine, "inn", cgx + 6, cgy + 2)
    hx, hy = _tile_center_px(cgx + 3, cgy + 1)
    hero = _place_hero(engine, "warrior", hx, hy)
    _place_enemy(engine, "wolf", hx + 180.0, hy + 120.0)

    from game.sim.timebase import now_ms as sim_now_ms

    cx = float(getattr(castle, "center_x", getattr(castle, "x", 0.0)))
    cy = float(getattr(castle, "center_y", getattr(castle, "y", 0.0)))

    def _prep_base(eng: Any) -> None:
        eng.screenshot_hide_ui = False
        eng.selected_hero = hero

    def _prep(eng: Any) -> None:
        _prep_base(eng)
        eng.hud._pin_slot.pin(str(hero.hero_id), int(sim_now_ms()))
        eng.hud._pin_slot.pinned_name = str(hero.name)

    def _apply_left_unpinned(eng: Any) -> None:
        _prep_base(eng)
        eng.hud._pin_slot.unpin()

    def _apply_expanded(eng: Any) -> None:
        _prep(eng)
        eng.hud._watch_card_expanded = True

    def _apply_minimized(eng: Any) -> None:
        _prep(eng)
        eng.hud._watch_card_expanded = False

    def _apply_radar(eng: Any) -> None:
        _apply_expanded(eng)

    def _apply_memorial(eng: Any) -> None:
        _prep(eng)
        from game.ui.memorial_card import MemorialRecord

        eng.hud._pending_memorial = MemorialRecord(
            hero_id=str(hero.hero_id),
            name=str(hero.name),
            hero_class="warrior",
            level=5,
            enemies_defeated=12,
            bounties_claimed=3,
            gold_earned=400,
        )
    def _apply_building_menu(eng: Any) -> None:
        _prep(eng)
        eng.hud._watch_card_expanded = True
        wg = next((b for b in eng.buildings if getattr(b, "building_type", "") == "warrior_guild"), None)
        if wg is None:
            wg = _place_building(eng, "warrior_guild", cgx + 5, cgy + 2)
        eng.selected_building = wg
        eng.selected_peasant = None
        eng.building_panel.select_building(wg, eng.heroes)

    def _apply_building_interior(eng: Any) -> None:
        _apply_building_menu(eng)
        wg = eng.selected_building
        if wg is not None and hasattr(eng.hud, "building_interior_overlay"):
            eng.hud.building_interior_overlay.show(wg)
            eng.paused = True

    return [
        Shot(
            filename="wk52_watch_card_expanded.png",
            label="WK52 watch card expanded",
            center_x=cx,
            center_y=cy,
            zoom=1.0,
            ticks=0,
            apply=_apply_expanded,
            meta={"scenario": "wk52_pin_alerts", "seed": int(seed)},
        ),
        Shot(
            filename="wk52_watch_card_minimized.png",
            label="WK52 watch card minimized",
            center_x=cx,
            center_y=cy,
            zoom=1.0,
            ticks=0,
            apply=_apply_minimized,
            meta={"scenario": "wk52_pin_alerts", "seed": int(seed)},
        ),
        Shot(
            filename="wk52_pin_radar_minimap.png",
            label="WK52 radar minimap",
            center_x=cx,
            center_y=cy,
            zoom=1.0,
            ticks=0,
            apply=_apply_radar,
            meta={"scenario": "wk52_pin_alerts", "seed": int(seed)},
        ),
        Shot(
            filename="wk52_left_menu_unpinned.png",
            label="WK52 Heroes column unpinned vs minimap",
            center_x=cx,
            center_y=cy,
            zoom=1.0,
            ticks=0,
            apply=_apply_left_unpinned,
            meta={"scenario": "wk52_pin_alerts", "seed": int(seed)},
        ),
        Shot(
            filename="wk52_building_menu.png",
            label="WK52 building menu left column with pin",
            center_x=cx,
            center_y=cy,
            zoom=1.0,
            ticks=0,
            apply=_apply_building_menu,
            meta={"scenario": "wk52_pin_alerts", "seed": int(seed)},
        ),
        Shot(
            filename="wk52_building_interior.png",
            label="WK52 building interior overlay",
            center_x=cx,
            center_y=cy,
            zoom=1.0,
            ticks=0,
            apply=_apply_building_interior,
            meta={"scenario": "wk52_pin_alerts", "seed": int(seed)},
        ),
        Shot(
            filename="wk52_memorial_card.png",
            label="WK52 memorial card",
            center_x=cx,
            center_y=cy,
            zoom=1.0,
            ticks=0,
            apply=_apply_memorial,
            meta={"scenario": "wk52_pin_alerts", "seed": int(seed)},
        ),
    ]


def _building_type_key(building) -> str:
    bt = getattr(building, "building_type", "")
    return str(getattr(bt, "value", bt) or "").strip().lower()


def _seed_tax_gold_for_capture(engine) -> list[str]:
    """Seed deterministic tax gold on every tax-stash building (WK61 hold-G capture)."""
    seeded: list[str] = []
    for building in list(getattr(engine, "buildings", []) or []):
        bts = _building_type_key(building)
        if bts not in TAX_STASH_BUILDING_TYPES:
            continue
        if hasattr(building, "add_tax_gold"):
            building.add_tax_gold(42)
        else:
            building.stored_tax_gold = 42
        seeded.append(bts)
    return seeded


URSINA_CAPTURE_SCENARIOS: dict[str, dict[str, object]] = {
    "wk61_hold_g_tax_overlay": {
        "patch_path": "tools/wk61_r10_capture_patch.py",
        "default_ticks": 5400,
        "default_out_subdir": "wk61_r10_hold_g",
        "stem": "hold_g_tax_overlay",
        "env": {
            "KINGDOM_URSINA_PREFAB_TEST_LAYOUT": "1",
            "KINGDOM_URSINA_REVEAL_ON_START": "1",
            "KINGDOM_URSINA_EDITORCAMERA": "0",
            "KINGDOM_URSINA_CAM_FOCUS_SPAN": "32",
        },
    },
    # WK67 Round A-2 (Wave 5): the primary (Ursina) renderer had NO registered
    # melee-combat capture scenario — thin coverage of the unit-render/anim boundary.
    # This spawns a warrior hero adjacent to a goblin near the castle, forces a melee
    # strike + hurt one-shot, and holds the pose for a byte-reproducible capture under
    # DETERMINISTIC_SIM (fixed castle-focus camera at blend=0; FPS/frame-time debug
    # overlay disabled by the patch so only the deterministic scene is in the PNG).
    "ursina_melee_combat": {
        # ~8s warmup (480 ticks at 60 Hz) so terrain/models/shaders are fully loaded
        # before the grab — the held strike pose is tick-independent, but the scene
        # must have rendered. A shorter warmup can capture a pre-render (blank) frame
        # on a cold model cache.
        "patch_path": "tools/wk67_combat_capture_patch.py",
        "default_ticks": 480,
        "default_out_subdir": "wk67_combat",
        "stem": "ursina_melee_combat",
        "env": {
            "KINGDOM_URSINA_REVEAL_ON_START": "1",
            "KINGDOM_URSINA_EDITORCAMERA": "0",
            "KINGDOM_URSINA_CAM_FOCUS_BUILDING_TYPE": "castle",
            "KINGDOM_URSINA_CAM_FOCUS_SPAN": "16",
        },
    },
    # WK122-T3: deterministic guardhouse two-arrow capture (Jaimie's explicit ask —
    # "start the game with the guard tower firing at an enemy and screenshot to make
    # sure you see 2 distinct arrows"). The patch places the REAL Guardhouse + ONE
    # goblin within GUARDHOUSE_ARROW_RANGE_TILES (default 3 tiles apart), holds the
    # goblin alive/in-range, resets _arrow_timer each tick so the live Guardhouse.update
    # genuinely fires (faithfulness/integration proof), and pins two mid-flight
    # ProjectileVFX (distinct guardhouse origins, factor 40 X / 8 Y -> +/-20px / +/-4px,
    # the same the real building uses -> same target) AFTER the tick so the grab always
    # shows two distinct arrow billboards. Fixed oblique camera framed (tight, span 4)
    # on the TWO-ARROW midpoint so the small billboards read; FPS overlay disabled.
    # PM can iterate framing without code edits via env knobs (no default override
    # needed here): KINGDOM_WK122_SEP_TILES (int 3), KINGDOM_WK122_CAM_SPAN (4.0),
    # KINGDOM_WK122_CAM_ELEV (0.8), KINGDOM_WK122_PROGRESS (0.4),
    # KINGDOM_WK122_ARROW_OFFSET_X (40.0), KINGDOM_WK122_ARROW_OFFSET_Y (8.0).
    "ursina_guardhouse_arrows": {
        "patch_path": "tools/wk122_guardhouse_arrows_capture_patch.py",
        "default_ticks": 480,
        "default_out_subdir": "wk122_guardhouse_arrows",
        "stem": "guardhouse_arrows",
        "env": {
            "KINGDOM_URSINA_REVEAL_ON_START": "1",
            "KINGDOM_URSINA_EDITORCAMERA": "0",
        },
    },
    # WK124-T3: deterministic WIZARD spell capture. The patch places ONE real
    # Hero(hero_class="wizard") + ONE goblin ~3 tiles apart (inside the wizard's
    # 4.5-tile WIZARD_ATTACK_RANGE_TILES), holds the enemy alive/in-range, resets
    # the wizard attack_cooldown each tick so the live CombatSystem genuinely emits
    # a ranged_projectile {projectile_kind:"magic"} (faithfulness/integration proof),
    # and pins ONE mid-flight ProjectileVFX(kind="magic") AFTER the tick so the grab
    # always shows the purple magic orb. The wizard's "attack" (staff cast) clip is
    # locked to a mid-cast frame so the body cast-pose holds. Fixed oblique camera
    # framed (span 5) on the held orb; FPS overlay disabled. PM framing knobs (no
    # default override needed): KINGDOM_WK124_SEP_TILES (3), KINGDOM_WK124_CAM_SPAN
    # (5.0), KINGDOM_WK124_CAM_ELEV (0.8), KINGDOM_WK124_PROGRESS (0.45). Scene is
    # selected by KINGDOM_WK124_SCENE=wizard (set below).
    "ursina_wizard_cast": {
        "patch_path": "tools/wk124_wizard_cleric_capture_patch.py",
        "default_ticks": 480,
        "default_out_subdir": "wk124_wizard_cast",
        "stem": "wizard_cast",
        "env": {
            "KINGDOM_URSINA_REVEAL_ON_START": "1",
            "KINGDOM_URSINA_EDITORCAMERA": "0",
            "KINGDOM_URSINA_DISABLE_NEUTRAL_SPAWN": "1",
            "KINGDOM_WK124_SCENE": "wizard",
        },
    },
    # WK124-T4: deterministic CLERIC heal capture. The patch places ONE real
    # Hero(hero_class="cleric") + ONE wounded Hero(hero_class="warrior") ally ~2 tiles
    # apart (inside CLERIC_HEAL_RADIUS_TILES=4), re-wounds the ally below the 0.85
    # heal threshold and resets the cleric _heal_cooldown_until_ms each tick so the
    # live ClericHealSystem genuinely emits hero_heal (faithfulness), and pins ONE
    # mid-flight ProjectileVFX(kind="heal") AFTER the tick so the grab always shows the
    # GREEN heal bolt cleric->ally. (The green particle burst is pygame-only; the heal
    # billboard is what reads in the Ursina 3D path.) Fixed oblique camera framed
    # (span 5) on the held bolt; FPS overlay disabled. Same KINGDOM_WK124_* framing
    # knobs as the wizard scene. Scene selected by KINGDOM_WK124_SCENE=cleric.
    "ursina_cleric_heal": {
        "patch_path": "tools/wk124_wizard_cleric_capture_patch.py",
        "default_ticks": 480,
        "default_out_subdir": "wk124_cleric_heal",
        "stem": "cleric_heal",
        "env": {
            "KINGDOM_URSINA_REVEAL_ON_START": "1",
            "KINGDOM_URSINA_EDITORCAMERA": "0",
            "KINGDOM_URSINA_DISABLE_NEUTRAL_SPAWN": "1",
            "KINGDOM_WK124_SCENE": "cleric",
        },
    },
    # WK132: one-shot capture of a single new POI prefab placed (discovered) south of
    # the castle with a fixed footprint-framed oblique camera. Select the POI with
    # KINGDOM_WK132_POI (mysterious_well | ruined_outpost | windmill_ruin |
    # ancient_ruins | dragon_cave); framing knobs KINGDOM_WK132_CAM_SPAN /
    # KINGDOM_WK132_CAM_ELEV. Run once per POI, overriding the env var:
    #   $env:KINGDOM_WK132_POI="dragon_cave"; python tools/run_ursina_capture_once.py `
    #       --scenario ursina_wk132_poi --out docs/screenshots/wk132_pois --stem dragon_cave
    "ursina_wk132_poi": {
        "patch_path": "tools/wk132_poi_capture_patch.py",
        "default_ticks": 480,
        "default_out_subdir": "wk132_pois",
        "stem": "wk132_poi",
        "env": {
            "KINGDOM_URSINA_REVEAL_ON_START": "1",
            "KINGDOM_URSINA_EDITORCAMERA": "0",
            "KINGDOM_URSINA_DISABLE_NEUTRAL_SPAWN": "1",
        },
    },
    # WK133: Herald's Post + Quest-Giver NPC + yellow "!" capture. Places a constructed
    # post, the sim spawns the giver, a quest is armed via the real engine action so
    # is_open flips and the "!" shows. KINGDOM_WK133_ARM_QUEST=0 captures the off state.
    "ursina_wk133_quest_giver": {
        "patch_path": "tools/wk133_quest_giver_capture_patch.py",
        "default_ticks": 600,
        "default_out_subdir": "wk133_quest_giver",
        "stem": "quest_giver",
        "env": {
            "KINGDOM_URSINA_REVEAL_ON_START": "1",
            "KINGDOM_URSINA_EDITORCAMERA": "0",
            "KINGDOM_URSINA_DISABLE_NEUTRAL_SPAWN": "1",
        },
    },
}


def get_ursina_capture_scenario(scenario_name: str) -> dict[str, object]:
    """Return Ursina one-shot capture config for ``tools/run_ursina_capture_once.py --scenario``."""
    key = str(scenario_name).strip()
    cfg = URSINA_CAPTURE_SCENARIOS.get(key)
    if cfg is None:
        known = ", ".join(sorted(URSINA_CAPTURE_SCENARIOS))
        raise ValueError(f"Unknown Ursina capture scenario: {key!r} (known: {known})")
    return dict(cfg)


def scenario_wk61_hold_g_tax_overlay(engine, *, seed: int) -> list[Shot]:
    """WK61 R10: WK60 starting buildings + hold-G tax overlay (seed tax, force G held)."""
    _clear_dynamic_entities(engine)
    _reveal_all(engine.world)

    castle = next((b for b in engine.buildings if getattr(b, "building_type", "") == "castle"), None)
    if castle is None:
        gx = MAP_WIDTH // 2 - 1
        gy = MAP_HEIGHT // 2 - 1
        castle = _place_building(engine, "castle", gx, gy)

    for btype, gx, gy in STARTING_BUILDINGS:
        existing = next(
            (b for b in engine.buildings if _building_type_key(b) == str(btype).strip().lower()),
            None,
        )
        if existing is None:
            placed = _place_building(engine, str(btype), int(gx), int(gy))
            placed.is_constructed = True

    seeded = _seed_tax_gold_for_capture(engine)
    cx = float(getattr(castle, "center_x", getattr(castle, "x", 0.0)))
    cy = float(getattr(castle, "center_y", getattr(castle, "y", 0.0)))

    def _apply_hold_g(eng: Any) -> None:
        from game.graphics.ursina_renderer import set_tax_gold_overlay_held

        _seed_tax_gold_for_capture(eng)
        set_tax_gold_overlay_held(True)
        eng.screenshot_hide_ui = False
        eng.selected_hero = None
        eng.selected_peasant = None
        eng.selected_building = None
        if hasattr(eng, "debug_panel"):
            eng.debug_panel.visible = False

    return [
        Shot(
            filename="wk61_hold_g_tax_overlay.png",
            label="WK61 R10: hold-G tax overlay on starting buildings",
            center_x=cx,
            center_y=cy,
            zoom=1.2,
            ticks=0,
            apply=_apply_hold_g,
            meta={
                "scenario": "wk61_hold_g_tax_overlay",
                "seed": int(seed),
                "seeded_tax_types": sorted(set(seeded)),
                "starting_buildings": list(STARTING_BUILDINGS),
            },
        ),
    ]


def scenario_wk61_guardhouse_hp_panel(engine, *, seed: int) -> list[Shot]:
    """WK61 R5: selected Guardhouse left panel shows HP above Demolish."""
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
    guardhouse = _place_building(engine, "guardhouse", cgx - 7, cgy + 3)
    guardhouse.is_constructed = True

    cx = float(getattr(guardhouse, "center_x", getattr(guardhouse, "x", 0.0)))
    cy = float(getattr(guardhouse, "center_y", getattr(guardhouse, "y", 0.0)))

    def _apply_select_guardhouse(eng: Any) -> None:
        eng.screenshot_hide_ui = False
        eng.selected_hero = None
        eng.selected_peasant = None
        eng.selected_building = guardhouse
        if hasattr(eng, "building_panel"):
            eng.building_panel.select_building(guardhouse, eng.heroes)
        if hasattr(eng, "debug_panel"):
            eng.debug_panel.visible = False

    return [
        Shot(
            filename="wk61_guardhouse_hp_panel.png",
            label="WK61 R5: Guardhouse selected with HP in left panel",
            center_x=cx,
            center_y=cy,
            zoom=1.6,
            ticks=0,
            apply=_apply_select_guardhouse,
            meta={"scenario": "wk61_guardhouse_hp_panel", "seed": int(seed), "ticket": "WK61-R5-BUG-001"},
        ),
    ]


def scenario_wk61_hero_menu_chat(engine, *, seed: int) -> list[Shot]:
    """WK61 R9: Hero menu chat split layout — readable chat without pin."""
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
    hx, hy = _tile_center_px(cgx + 3, cgy + 1)
    hero = _place_hero(engine, "warrior", hx, hy)
    hero.name = "Sir Aldric"

    cx = float(getattr(castle, "center_x", getattr(castle, "x", 0.0)))
    cy = float(getattr(castle, "center_y", getattr(castle, "y", 0.0)))

    def _apply_hero_menu_chat(eng: Any) -> None:
        eng.screenshot_hide_ui = False
        eng.selected_building = None
        eng.selected_peasant = None
        eng.selected_hero = hero
        if hasattr(eng, "debug_panel"):
            eng.debug_panel.visible = False
        hud = getattr(eng, "hud", None)
        if hud is not None:
            hud._pin_slot.unpin()
            cp = hud._chat_panel
            cp.start_conversation(hero)
            cp.conversation_history.clear()
            cp.conversation_history.extend(
                [
                    {"role": "player", "text": "Scout the eastern woods for threats."},
                    {
                        "role": "hero",
                        "text": "I'll range ahead and report anything that moves in the treeline.",
                    },
                    {"role": "player", "text": "Stay within sight of the castle walls."},
                    {"role": "hero", "text": "Understood, my liege."},
                ]
            )

    return [
        Shot(
            filename="wk61_hero_menu_chat_1024.png",
            label="WK61 R9: Hero menu chat readable split (1024x576)",
            center_x=cx,
            center_y=cy,
            zoom=1.4,
            ticks=0,
            width=1024,
            height=576,
            apply=_apply_hero_menu_chat,
            meta={"scenario": "wk61_hero_menu_chat", "seed": int(seed), "ticket": "WK61-R9-BUG-001"},
        ),
        Shot(
            filename="wk61_hero_menu_chat_1920.png",
            label="WK61 R9: Hero menu chat readable split (1920x1080)",
            center_x=cx,
            center_y=cy,
            zoom=1.4,
            ticks=0,
            width=1920,
            height=1080,
            apply=_apply_hero_menu_chat,
            meta={"scenario": "wk61_hero_menu_chat", "seed": int(seed), "ticket": "WK61-R9-BUG-001"},
        ),
    ]


def scenario_ursina_melee_combat(engine, *, seed: int) -> list[Shot]:
    """WK67 Round A-2 (Wave 5): hero strikes an adjacent enemy (strike + hurt one-shot).

    Mirrors ``tools/wk67_combat_capture_patch.py`` (the registered Ursina capture
    scenario) for the pygame render path: a warrior hero on a tile adjacent to a goblin
    near the castle, with the hero in FIGHTING state targeting the enemy and the
    strike/hurt one-shot anim triggers stamped so the captured frame shows a melee pose.
    """
    from game.entities.hero import HeroState

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

    hero_x, hero_y = _tile_center_px(cgx + 2, cgy + 3)
    enemy_x, enemy_y = _tile_center_px(cgx + 3, cgy + 3)  # one tile east → melee range

    hero = _place_hero(engine, "warrior", hero_x, hero_y)
    hero.name = "Sir Aldric"
    enemy = _place_enemy(engine, "goblin", enemy_x, enemy_y)

    if hasattr(hero, "state"):
        hero.state = HeroState.FIGHTING
    hero.target = enemy
    enemy.target = hero

    def _force_strike(eng: Any) -> None:
        eng.screenshot_hide_ui = True
        eng.selected_hero = None
        eng.selected_peasant = None
        eng.selected_building = None
        if hasattr(eng, "debug_panel"):
            eng.debug_panel.visible = False
        # Stamp the one-shot triggers so the renderer plays strike + hurt this frame.
        hero._render_anim_trigger = "attack"
        hero._anim_trigger_seq = int(getattr(hero, "_anim_trigger_seq", 0) or 0) + 1
        enemy._render_anim_trigger = "hurt"
        enemy._anim_trigger_seq = int(getattr(enemy, "_anim_trigger_seq", 0) or 0) + 1

    mid_x = (hero_x + enemy_x) / 2.0
    mid_y = (hero_y + enemy_y) / 2.0

    return [
        Shot(
            filename="ursina_melee_combat.png",
            label="WK67 W5: hero melee strike + enemy hurt (adjacent)",
            center_x=mid_x,
            center_y=mid_y,
            zoom=3.0,
            ticks=0,
            apply=_force_strike,
            meta={
                "scenario": "ursina_melee_combat",
                "seed": int(seed),
                "hero": "warrior",
                "enemy": "goblin",
            },
        ),
    ]


def scenario_wk133_quest_ui(engine, *, seed: int) -> list[Shot]:
    """WK133 (WK126-T9): Herald's Post quest UI — selected-post card with the
    'Create Quest' button, the quest-create modal mid-flow, and the modal's
    active-quest board with an open quest listed."""
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

    # Constructed Herald's Post + a discovered lair to target (world is revealed).
    from game.entities.lair import GoblinCamp

    post = _place_building(engine, "herald_post", cgx + 5, cgy + 1)
    engine.buildings.append(GoblinCamp(cgx + 14, cgy + 6))
    hx, hy = _tile_center_px(cgx + 3, cgy + 2)
    _place_hero(engine, "warrior", hx, hy)

    def _base(eng: Any) -> None:
        eng.screenshot_hide_ui = False
        eng.selected_hero = None
        eng.selected_peasant = None
        if hasattr(eng, "debug_panel"):
            eng.debug_panel.visible = False
        eng.economy.player_gold = 500
        eng.selected_building = post
        eng.building_panel.select_building(post, eng.heroes)
        qcp = eng.building_panel.quest_create_panel
        if qcp.visible:
            qcp.close()

    def _apply_post_selected(eng: Any) -> None:
        _base(eng)

    def _apply_create_panel(eng: Any) -> None:
        _base(eng)
        qcp = eng.building_panel.quest_create_panel
        qcp.open(post, eng.get_game_state())
        # Mid-flow state: raid type chosen, first discovered lair targeted, Med reward.
        qcp.selected_type = "raid_lair"
        qcp.target_index = 0
        qcp.reward_key = "med"

    def _apply_active_quest(eng: Any) -> None:
        _base(eng)
        qs = eng.sim.quest_system
        if not qs.get_active_quests():
            eng.sim.create_quest(
                getattr(post, "entity_id", None), "slay_enemy_type", "goblin", 140, count=5
            )
        qcp = eng.building_panel.quest_create_panel
        qcp.open(post, eng.get_game_state())

    px = float(getattr(post, "center_x", getattr(post, "x", 0.0)))
    py = float(getattr(post, "center_y", getattr(post, "y", 0.0)))
    return [
        Shot(
            filename="wk133_herald_post_selected.png",
            label="WK133: Herald's Post selected (Create Quest button)",
            center_x=px,
            center_y=py,
            zoom=1.4,
            ticks=0,
            apply=_apply_post_selected,
            meta={"scenario": "wk133_quest_ui", "seed": int(seed), "shot": "post_selected"},
        ),
        Shot(
            filename="wk133_quest_create_panel.png",
            label="WK133: Quest-create modal (raid_lair mid-flow)",
            center_x=px,
            center_y=py,
            zoom=1.4,
            ticks=0,
            apply=_apply_create_panel,
            meta={"scenario": "wk133_quest_ui", "seed": int(seed), "shot": "create_panel"},
        ),
        Shot(
            filename="wk133_quest_board_active.png",
            label="WK133: Active-quest board with an open quest",
            center_x=px,
            center_y=py,
            zoom=1.4,
            ticks=0,
            apply=_apply_active_quest,
            meta={"scenario": "wk133_quest_ui", "seed": int(seed), "shot": "active_quest_board"},
        ),
    ]


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
    if scenario_name == "ui_pause_menu":
        return scenario_ui_pause_menu(engine, seed=int(seed))
    if scenario_name == "ui_build_catalog":
        return scenario_ui_build_catalog(engine, seed=int(seed))
    if scenario_name in ("ui_audio_blacksmith", "v1_3_audio_blacksmith"):
        return scenario_ui_audio_blacksmith(engine, seed=int(seed))
    if scenario_name in ("ui_polish_after", "v1_3_after", "v1.3_after"):
        return scenario_ui_polish_after(engine, seed=int(seed))
    if scenario_name in ("world_variation", "terrain_variety", "v1_3_world_variation"):
        return scenario_world_variation(engine, seed=int(seed))
    if scenario_name == "worker_catalog":
        return scenario_worker_catalog(engine, seed=int(seed))
    if scenario_name == "ranged_projectiles":
        return scenario_ranged_projectiles(engine, seed=int(seed))
    if scenario_name == "building_debris":
        return scenario_building_debris(engine, seed=int(seed))
    if scenario_name == "bounty_in_black_fog":
        return scenario_bounty_in_black_fog(engine, seed=int(seed))
    if scenario_name == "building_menu_open":
        return scenario_building_menu_open(engine, seed=int(seed))
    if scenario_name == "wk52_pin_alerts":
        return scenario_wk52_pin_alerts(engine, seed=int(seed))
    if scenario_name == "wk61_hold_g_tax_overlay":
        return scenario_wk61_hold_g_tax_overlay(engine, seed=int(seed))
    if scenario_name == "wk61_guardhouse_hp_panel":
        return scenario_wk61_guardhouse_hp_panel(engine, seed=int(seed))
    if scenario_name == "wk61_hero_menu_chat":
        return scenario_wk61_hero_menu_chat(engine, seed=int(seed))
    if scenario_name == "ursina_melee_combat":
        return scenario_ursina_melee_combat(engine, seed=int(seed))
    if scenario_name == "wk133_quest_ui":
        return scenario_wk133_quest_ui(engine, seed=int(seed))
    raise ValueError(f"Unknown scenario: {scenario_name}")


