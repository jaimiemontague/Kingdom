"""Player-driven action handlers (hire / build / bounty / HUD pin) — mechanical facade.

WK75 Round B-2c: these are pure mechanical moves of the GameEngine action methods
(WK69 pattern). Each function takes the live ``GameEngine`` as ``engine``; the body is
the original method body with ``self.`` rewritten to ``engine.``. ``game.engine`` keeps
1-line delegating wrappers, so all call sites (input_handler / hud / command_bar) and
tests are unchanged. Behavior is byte-identical.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from config import (
    TILE_SIZE,
    BOUNTY_REWARD_LOW,
    BOUNTY_REWARD_MED,
    BOUNTY_REWARD_HIGH,
)
from game.entities import Hero
from game.events import GameEventType
from game.types import BountyType, HeroClass

if TYPE_CHECKING:
    from game.engine import GameEngine


def try_hire_hero(engine: "GameEngine"):
    """Try to hire a hero from the selected guild building or auto-locate one."""
    allowed = frozenset({"warrior_guild", "ranger_guild", "rogue_guild", "wizard_guild", "temple"})

    def _is_hirable_guild(b) -> bool:
        bt = getattr(b, "building_type", "")
        if bt not in allowed:
            return False
        # Match building_panel / navigation: missing is_constructed → treat as built (see Building base).
        return getattr(b, "is_constructed", True) is True

    guild = None
    sel = engine.selected_building
    if sel is not None and _is_hirable_guild(sel):
        guild = sel

    if guild is None:
        for b in engine.buildings:
            if _is_hirable_guild(b):
                guild = b
                break

    if guild is None:
        engine.hud.add_message("Requires a constructed guild (Warrior/Ranger/Rogue/Wizard) or Temple!", (255, 100, 100))
        if engine.audio_system is not None:
            engine.audio_system.play_sfx("ui_error")
        return

    # WK60 Feature 3: check guild hero cap before hiring
    if hasattr(guild, "can_hire") and not guild.can_hire():
        engine.hud.add_message("Guild is full!", (255, 100, 100))
        if engine.audio_system is not None:
            engine.audio_system.play_sfx("ui_error")
        return

    if not engine.economy.can_afford_hero():
        engine.hud.add_message("Not enough gold to hire!", (255, 100, 100))
        if engine.audio_system is not None:
            engine.audio_system.play_sfx("ui_error")
        return

    # Hire the hero
    engine.economy.hire_hero()
    guild.hire_hero()

    # Spawn hero near guild
    class_by_guild = {
        "warrior_guild": HeroClass.WARRIOR.value,
        "ranger_guild": HeroClass.RANGER.value,
        "rogue_guild": HeroClass.ROGUE.value,
        "wizard_guild": HeroClass.WIZARD.value,
        "temple": HeroClass.CLERIC.value,
    }
    hero_class = class_by_guild.get(guild.building_type, HeroClass.WARRIOR.value)
    hero = Hero(
        guild.center_x + TILE_SIZE,
        guild.center_y,
        hero_class=hero_class
    )
    # Set the hero's home building to this guild
    hero.home_building = guild

    engine.heroes.append(hero)
    if hasattr(hero, "set_event_bus"):
        hero.set_event_bus(engine.event_bus)
    engine.hud.add_message(f"{hero.name} the {hero_class.title()} joins your kingdom!", (100, 255, 100))
    engine.event_bus.emit({
        "type": "hero_hired",
        "x": float(hero.x),
        "y": float(hero.y),
    })


def place_building(engine: "GameEngine", grid_x: int, grid_y: int):
    """Place the selected building."""
    building_type = engine.building_menu.selected_building

    if not engine.economy.buy_building(building_type):
        engine.hud.add_message("Not enough gold!", (255, 100, 100))
        if engine.audio_system is not None:
            engine.audio_system.play_sfx("ui_error")
        return

    # Create the building
    building = engine.building_factory.create(building_type, grid_x, grid_y)

    if building is None:
        return

    # WK45: If the player builds over a sapling, remove it (and clear the tile) so it
    # doesn't persist as an invisible blocking TREE tile.
    try:
        w, h = getattr(building, "size", (1, 1))
        engine.sim.remove_trees_in_footprint(int(grid_x), int(grid_y), int(w), int(h))
    except Exception:
        pass

    # Newly placed buildings start unconstructed (1 HP, non-targetable) until a peasant begins building.
    if hasattr(building, "mark_unconstructed"):
        building.mark_unconstructed()

    engine.buildings.append(building)
    if hasattr(building, "set_event_bus"):
        building.set_event_bus(engine.event_bus)
    engine.building_menu.cancel_selection()
    engine.hud.add_message(f"Placed: {building_type.replace('_', ' ').title()} (awaiting construction)", (100, 255, 100))

    # Queue building placement event for EventBus subscribers (Audio/VFX).
    engine.event_bus.emit({
        "type": GameEventType.BUILDING_PLACED.value,
        "x": float(grid_x * TILE_SIZE),
        "y": float(grid_y * TILE_SIZE),
    })


def place_bounty(engine: "GameEngine"):
    """Place a bounty at the current mouse position."""
    mouse_pos = engine.input_manager.get_mouse_pos() if getattr(engine, "input_manager", None) else pygame.mouse.get_pos()
    world_x, world_y = engine.pointer_world_xy((mouse_pos[0], mouse_pos[1]))

    # Bounty reward tiers (player-paid; cost == reward).
    mods = engine.input_manager.get_key_mods() if getattr(engine, "input_manager", None) else {'shift': False, 'ctrl': False, 'alt': False}
    if not getattr(engine, "input_manager", None): # Fallback
        pg_mods = pygame.key.get_mods()
        mods = {'ctrl': bool(pg_mods & pygame.KMOD_CTRL), 'shift': bool(pg_mods & pygame.KMOD_SHIFT)}

    if mods.get('ctrl'):
        reward = int(BOUNTY_REWARD_HIGH)
    elif mods.get('shift'):
        reward = int(BOUNTY_REWARD_MED)
    else:
        reward = int(BOUNTY_REWARD_LOW)

    if not engine.economy.add_bounty(reward):
        engine.hud.add_message("Not enough gold for bounty!", (255, 100, 100))
        if engine.audio_system is not None:
            engine.audio_system.play_sfx("ui_error")
        return

    engine.bounty_system.place_bounty(world_x, world_y, reward, BountyType.EXPLORE.value)
    engine.hud.add_message(f"Bounty placed (${reward}). Heroes will respond.", (255, 215, 0))

    # Queue bounty placement event for EventBus subscribers (Audio/VFX).
    engine.event_bus.emit({
        "type": GameEventType.BOUNTY_PLACED.value,
        "x": float(world_x),
        "y": float(world_y),
    })


def apply_hud_pin_action(engine: "GameEngine", action: str) -> None:
    """WK51: Pin / unpin / recall (UI state + camera + selection only)."""
    from game.sim.timebase import now_ms as sim_now_ms

    hud = getattr(engine, "hud", None)
    if hud is None:
        return
    pin_slot = getattr(hud, "_pin_slot", None)
    if pin_slot is None:
        return
    now_ms = int(sim_now_ms())
    if action == "open_memorial":
        engine.paused = True
        setattr(engine, "_ursina_hud_force_upload", True)
        return
    if action == "close_memorial_unpause":
        engine.paused = False
        mc = getattr(hud, "memorial_card", None)
        if mc is not None:
            mc.hide()
        if hasattr(hud, "_pending_memorial"):
            hud._pending_memorial = None
        setattr(engine, "_ursina_hud_force_upload", True)
        return
    if action == "open_building_interior":
        engine.paused = True
        setattr(engine, "_ursina_hud_force_upload", True)
        return
    if action == "close_building_interior_unpause":
        engine.paused = False
        bio = getattr(hud, "building_interior_overlay", None)
        if bio is not None:
            bio.hide()
        setattr(engine, "_ursina_hud_force_upload", True)
        return
    if action == "confirm_demolish":
        dco = getattr(hud, "demolish_confirm_overlay", None)
        if dco is not None and dco.visible:
            building = dco.building
            dco.hide()
            if building and building in engine.buildings and building.building_type != "castle":
                building.hp = 0
                engine._cleanup_destroyed_buildings(emit_messages=False)
                building_name = building.building_type.replace("_", " ").title()
                hud.add_message(f"Demolished: {building_name}", (255, 255, 255))
                engine.building_panel.deselect()
                engine.selected_building = None
        setattr(engine, "_ursina_hud_force_upload", True)
        return
    if action == "expand_watch_card":
        if hasattr(hud, "_watch_card_expanded"):
            hud._watch_card_expanded = True
        setattr(engine, "_ursina_hud_force_upload", True)
        return
    if action == "pin_hero":
        sel = getattr(engine, "selected_hero", None)
        if sel is None:
            return
        hid = str(getattr(sel, "hero_id", "") or "").strip()
        if not hid:
            return
        pin_slot.pin(hid, now_ms)
        setattr(engine, "_ursina_hud_force_upload", True)
        return
    if action == "unpin_hero":
        pin_slot.unpin()
        setattr(engine, "_ursina_hud_force_upload", True)
        return
    if action == "recall_pinned_hero":
        if pin_slot.is_fallen() or pin_slot.hero_id is None:
            return
        target = engine._find_hero_by_id(pin_slot.hero_id)
        if target is None:
            return
        engine.selected_hero = target
        engine.center_camera_on_world_pos(float(target.x), float(target.y))
        if hasattr(engine, "hud"):
            try:
                if pin_slot.hero_id is not None and not getattr(engine.hud, "_watch_card_expanded", True):
                    engine.hud._watch_card_expanded = True
            except Exception:
                pass
        return
