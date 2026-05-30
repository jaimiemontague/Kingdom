"""Universal command / cheat-chat console — mechanical facade over :class:`game.engine.GameEngine`.

WK75 Round B-2c: pure mechanical move of ``GameEngine.process_command`` (WK69 pattern).
``process_command`` takes the live ``GameEngine`` as ``engine``; the body is the original
method body with ``self.`` rewritten to ``engine.``. ``game.engine.GameEngine`` keeps a
1-line delegating wrapper (ursina_app.py calls ``engine.process_command('/revealmap')``),
so all call sites and tests are unchanged. Behavior is byte-identical.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from game.world import Visibility

if TYPE_CHECKING:
    from game.engine import GameEngine


def process_command(engine: "GameEngine", text: str) -> None:
    """Handle a typed command or chat message from the universal input."""
    text = text.strip()
    if not text:
        return

    parts = text.split(None, 1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""
    hud = engine.hud if hasattr(engine, 'hud') else None

    if cmd in ('/revealmap', '/nowar', '/reveal'):
        world = getattr(engine, 'world', None)
        if world is None and hasattr(engine, 'sim'):
            world = getattr(engine.sim, 'world', None)
        if world:
            world.fog_disabled = True
            for ty in range(world.height):
                for tx in range(world.width):
                    world.visibility[ty][tx] = Visibility.VISIBLE
            world._currently_visible = []
            sim = getattr(engine, 'sim', engine)
            sim._fog_revealers_snapshot = None
            engine._fog_revision = getattr(engine, '_fog_revision', 0) + 100
            poi_count = 0
            for poi in getattr(sim, 'pois', []):
                if not getattr(poi, 'is_discovered', False):
                    poi.is_discovered = True
                    poi_count += 1
            msg = "Fog of war disabled — all entities visible!"
            if poi_count:
                msg += f" ({poi_count} POI{'s' if poi_count != 1 else ''} revealed)"
            if hud:
                hud.add_message(msg, (100, 255, 100))

    elif cmd == '/gold':
        amount = 500
        if arg:
            try:
                amount = int(arg)
            except ValueError:
                if hud:
                    hud.add_message("Usage: /gold <amount>", (255, 200, 100))
                return
        engine.economy.player_gold += amount
        if hud:
            hud.add_message(f"Added {amount} gold (total: {engine.economy.player_gold})", (255, 215, 0))

    elif cmd == '/speed':
        if not arg:
            if hud:
                from game.sim.timebase import get_time_multiplier
                hud.add_message(f"Speed: {get_time_multiplier():.1f}x. Usage: /speed <0.5-5>", (200, 200, 255))
            return
        try:
            val = float(arg)
            val = max(0.0, min(5.0, val))
            from game.sim.timebase import set_time_multiplier
            set_time_multiplier(val)
            if hud:
                hud.add_message(f"Speed set to {val:.1f}x", (200, 200, 255))
        except ValueError:
            if hud:
                hud.add_message("Usage: /speed <0.5-5>", (255, 200, 100))

    elif cmd == '/heal':
        healed = 0
        for hero in engine.heroes:
            if getattr(hero, 'is_alive', False) and getattr(hero, 'hp', 0) < getattr(hero, 'max_hp', 1):
                hero.hp = hero.max_hp
                healed += 1
        if hud:
            if healed:
                hud.add_message(f"Healed {healed} hero{'es' if healed != 1 else ''}!", (100, 255, 100))
            else:
                hud.add_message("No heroes need healing.", (200, 200, 200))

    elif cmd == '/kill':
        killed = 0
        for enemy in list(engine.enemies):
            if getattr(enemy, 'is_alive', False):
                enemy.hp = 0
                enemy.is_alive = False
                killed += 1
        if hud:
            hud.add_message(f"Killed {killed} enem{'ies' if killed != 1 else 'y'}!", (255, 100, 100))

    elif cmd == '/spawn':
        engine.try_hire_hero()

    elif cmd == '/pause':
        engine.paused = not engine.paused
        if hud:
            hud.add_message("Paused" if engine.paused else "Unpaused", (200, 200, 255))

    elif cmd == '/help':
        if hud:
            hud.add_message("/gold [n] /speed [x] /heal /kill /spawn /reveal /pause", (180, 220, 255))

    elif cmd.startswith('/'):
        if hud:
            hud.add_message(f"Unknown command: {cmd}. Type /help", (255, 100, 100))

    else:
        if hud:
            hud.add_message(f"> {text}", (200, 200, 200))
