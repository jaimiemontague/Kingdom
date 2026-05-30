"""Click/screen selection handlers (hero / peasant / enemy / building / unit pick) — mechanical facade.

WK76 Round B-2d: these are pure mechanical moves of the GameEngine ``try_select_*``
methods (WK69/WK75 pattern). Each function takes the live ``GameEngine`` as ``engine``;
the body is the original method body with ``self.`` rewritten to ``engine.``. ``game.engine``
keeps 1-line delegating wrappers, so all call sites (input_handler / hud) and tests are
unchanged. Behavior is byte-identical.

The "39x set-one-selection-null-others" idiom cleanup is explicitly DEFERRED — this is a
PURE MOVE only; the selection logic is relocated as-is.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from config import TILE_SIZE

if TYPE_CHECKING:
    from game.engine import GameEngine


def try_select_hero(engine: "GameEngine", screen_pos: tuple) -> bool:
    """Try to select a hero at the given screen position. Returns True if selected.

    WK53 R4: uses 1.5x hero.size as click radius for more forgiving selection on
    heightmap terrain, and picks the closest hero when multiple overlap.
    """
    world_x, world_y = engine.pointer_world_xy(screen_pos)

    best = None
    best_d = float("inf")
    for hero in engine.heroes:
        if not hero.is_alive:
            continue
        d = hero.distance_to(world_x, world_y)
        # WK53 R4: 1.5x hero.size for forgiving click targets on terrain
        if d < hero.size * 1.5 and d < best_d:
            best_d = d
            best = hero

    if best is not None:
        engine.selected_hero = best
        engine.selected_peasant = None
        engine.selected_enemy = None
        return True

    return False


def try_select_hero_at_world(engine: "GameEngine", wx: float, wy: float, radius: float = 24.0) -> bool:
    """Pick the closest live hero within ``radius`` px of world position (watch-card map — WK52)."""
    best = None
    lim = float(radius) * float(radius)
    best_d2 = lim + 1.0
    for hero in engine.heroes:
        if not getattr(hero, "is_alive", True) or int(getattr(hero, "hp", 0)) <= 0:
            continue
        dx = float(getattr(hero, "x", 0.0)) - float(wx)
        dy = float(getattr(hero, "y", 0.0)) - float(wy)
        d2 = dx * dx + dy * dy
        if d2 < best_d2:
            best_d2 = d2
            best = hero
    if best is None:
        return False
    engine.selected_hero = best
    engine.selected_peasant = None
    engine.selected_building = None
    engine.selected_enemy = None
    if hasattr(engine, "building_panel"):
        try:
            engine.building_panel.deselect()
        except Exception:
            pass
    return True


def try_select_tax_collector(engine: "GameEngine", screen_pos: tuple) -> bool:
    """Try to select the tax collector at the given screen position. Returns True if selected. (wk16)"""
    if engine.tax_collector is None:
        return False
    world_x, world_y = engine.pointer_world_xy(screen_pos)
    tc = engine.tax_collector
    if tc.distance_to(world_x, world_y) < tc.size:
        engine.selected_hero = tc  # unified selection state for left panel
        engine.selected_building = None
        engine.selected_peasant = None
        engine.selected_enemy = None
        return True
    return False


def try_select_guard(engine: "GameEngine", screen_pos: tuple) -> bool:
    """Try to select a guard at the given screen position. Returns True if selected."""
    world_x, world_y = engine.pointer_world_xy(screen_pos)
    best = None
    best_d = float("inf")
    for guard in engine.guards:
        if not getattr(guard, "is_alive", True):
            continue
        d = guard.distance_to(world_x, world_y)
        if d < guard.size * 1.5 and d < best_d:
            best_d = d
            best = guard
    if best is not None:
        engine.selected_hero = best
        engine.selected_building = None
        engine.selected_peasant = None
        engine.selected_enemy = None
        return True
    return False


def try_select_peasant(engine: "GameEngine", screen_pos: tuple) -> bool:
    """Try to select a peasant at the given screen position. Returns True if selected."""
    world_x, world_y = engine.pointer_world_xy(screen_pos)
    for peasant in engine.peasants:
        if getattr(peasant, "is_alive", True) and peasant.distance_to(world_x, world_y) < peasant.size:
            engine.selected_peasant = peasant
            engine.selected_hero = None
            engine.selected_building = None
            engine.selected_enemy = None
            if hasattr(engine, "building_panel"):
                try:
                    engine.building_panel.deselect()
                except Exception:
                    pass
            return True
    return False


def try_select_enemy(engine: "GameEngine", screen_pos: tuple) -> bool:
    """Try to select an enemy at the given screen position. Returns True if selected (WK61)."""
    world_x, world_y = engine.pointer_world_xy(screen_pos)
    best = None
    best_d = float("inf")
    for enemy in engine.enemies:
        if not enemy.is_alive:
            continue
        d = enemy.distance_to(world_x, world_y)
        if d < enemy.size * 1.5 and d < best_d:
            best_d = d
            best = enemy
    if best is not None:
        engine.selected_enemy = best
        engine.selected_hero = None
        engine.selected_building = None
        engine.selected_peasant = None
        return True
    return False


def try_ursina_select_unit_at_screen(engine: "GameEngine", screen_pos: tuple) -> bool:
    """Ursina-only screen-space unit pick (WK61-R4-BUG-002). Returns True if selected."""
    if not getattr(engine, "_ursina_viewer", False):
        return False
    try:
        from game.graphics.ursina_pick import pick_unit_at_screen
    except Exception:
        return False

    hit = pick_unit_at_screen(
        screen_pos,
        heroes=engine.heroes,
        enemies=engine.enemies,
        peasants=engine.peasants,
        guards=engine.guards,
        tax_collector=engine.tax_collector,
        virtual_w=int(getattr(engine, "window_width", 1920) or 1920),
        virtual_h=int(getattr(engine, "window_height", 1080) or 1080),
    )
    if hit is None:
        return False

    kind, entity = hit
    if kind == "hero":
        engine.selected_hero = entity
        engine.selected_peasant = None
        engine.selected_enemy = None
        engine.selected_building = None
    elif kind == "tax_collector":
        engine.selected_hero = entity
        engine.selected_building = None
        engine.selected_peasant = None
        engine.selected_enemy = None
    elif kind == "guard":
        engine.selected_hero = entity
        engine.selected_building = None
        engine.selected_peasant = None
        engine.selected_enemy = None
    elif kind == "peasant":
        engine.selected_peasant = entity
        engine.selected_hero = None
        engine.selected_building = None
        engine.selected_enemy = None
        if hasattr(engine, "building_panel"):
            try:
                engine.building_panel.deselect()
            except Exception:
                pass
    elif kind == "enemy":
        engine.selected_enemy = entity
        engine.selected_hero = None
        engine.selected_building = None
        engine.selected_peasant = None
    else:
        return False
    return True


def try_select_building(engine: "GameEngine", screen_pos: tuple) -> bool:
    """Try to select a building at the given screen position. Returns True if selected.

    WK53 R4: inflates the building hit-test rect by a margin (half a tile) so that
    clicks near building edges register reliably. Complex Kenney kitbash models have
    geometry gaps that caused precise-click misses with the exact footprint rect.
    """
    world_x, world_y = engine.pointer_world_xy(screen_pos)

    # Margin in sim-pixels: half a tile on each side for forgiving click targets.
    margin = TILE_SIZE * 0.5

    best = None
    best_d2 = float("inf")

    for building in engine.buildings:
        rect = building.get_rect()
        # Inflate rect by margin on all sides for easier clicking
        if (
            (rect.x - margin) <= world_x < (rect.x + rect.width + margin)
            and (rect.y - margin) <= world_y < (rect.y + rect.height + margin)
        ):
            # Prefer the building whose center is closest to the click
            cx = rect.x + rect.width * 0.5
            cy = rect.y + rect.height * 0.5
            d2 = (world_x - cx) ** 2 + (world_y - cy) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best = building

    if best is not None:
        engine.selected_building = best
        engine.selected_peasant = None
        engine.selected_enemy = None
        engine.building_panel.select_building(best, engine.heroes)
        return True

    return False
