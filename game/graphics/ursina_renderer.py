"""
Translates the GameEngine simulation state into Ursina 3D entities.
Uses orthographic 2D-style view with flat quads for all game objects.
"""
from ursina import Entity, color, Text, camera

# Basic colors for our low-fi MVP
COLOR_HERO = color.azure
COLOR_ENEMY = color.red
COLOR_PEASANT = color.orange
COLOR_GUARD = color.yellow
COLOR_BUILDING = color.light_gray
COLOR_CASTLE = color.gold
COLOR_LAIR = color.brown

# Conversion factor: game uses pixel coordinates (150*32=4800),
# but Ursina orthographic works best with smaller values.
# We'll divide all game positions by this to get Ursina world coords.
SCALE = 32.0  # 1 Ursina unit = 1 tile (32 px)


def px_to_world(px_x, px_y):
    """Convert game pixel coordinates to Ursina world coordinates."""
    return px_x / SCALE, px_y / SCALE


class UrsinaRenderer:
    def __init__(self, engine):
        self.engine = engine

        # Entity mappings: simulation object id() -> Ursina Entity
        self._entities = {}

        # Draw the world base once
        import config
        tiles_w = config.MAP_WIDTH
        tiles_h = config.MAP_HEIGHT

        # No ground quad needed — the Panda3D background color (set in ursina_app.py)
        # fills the entire view with green. A quad on top of it was rendering white
        # due to Ursina's default shader ignoring our color.

        # Status Text UI (2D overlay, not affected by camera)
        self.status_text = Text(
            text='Kingdom Sim - Ursina Viewer',
            position=(-0.85, 0.47),
            scale=1.2,
            color=color.black,
            background=True,
        )

    def _get_or_create_entity(self, sim_obj, model='quad', col=color.white, scale=(1, 1)):
        obj_id = id(sim_obj)
        if obj_id not in self._entities:
            ent = Entity(model=model, color=col, scale=scale)
            self._entities[obj_id] = ent
        return self._entities[obj_id], obj_id

    def update(self):
        """Called every frame by the Ursina app loop."""
        try:
            from game.types import HeroClass
        except Exception:
            HeroClass = None

        gs = self.engine.get_game_state()

        # Track valid IDs this frame to prune dead entities
        active_ids = set()

        # Update Buildings
        for b in gs['buildings']:
            is_castle = getattr(b, 'building_type', '') == 'castle'
            is_lair = hasattr(b, 'stash_gold')  # Lairs have gold stash
            if is_castle:
                c, sz = COLOR_CASTLE, (3, 3)
            elif is_lair:
                c, sz = COLOR_LAIR, (2, 2)
            else:
                c, sz = COLOR_BUILDING, (2, 2)

            ent, obj_id = self._get_or_create_entity(b, col=c, scale=sz)
            wx, wy = px_to_world(b.x + b.width / 2, b.y + b.height / 2)
            ent.position = (wx, wy, 0)
            active_ids.add(obj_id)

        # Update Heroes
        for h in gs['heroes']:
            c = COLOR_HERO
            if HeroClass:
                hc = getattr(h, 'hero_class', None)
                if hc == HeroClass.RANGER:
                    c = color.lime
                elif hc == HeroClass.WIZARD:
                    c = color.magenta
                elif hc == HeroClass.ROGUE:
                    c = color.violet

            ent, obj_id = self._get_or_create_entity(h, model='circle', col=c, scale=(0.6, 0.6))
            wx, wy = px_to_world(h.x, h.y)
            ent.position = (wx, wy, -0.1)
            active_ids.add(obj_id)

        # Update Enemies
        for e in gs['enemies']:
            ent, obj_id = self._get_or_create_entity(e, model='quad', col=COLOR_ENEMY, scale=(0.5, 0.5))
            wx, wy = px_to_world(e.x, e.y)
            ent.position = (wx, wy, -0.1)
            active_ids.add(obj_id)

        # Update Peasants
        for p in gs['peasants']:
            ent, obj_id = self._get_or_create_entity(p, model='quad', col=COLOR_PEASANT, scale=(0.3, 0.3))
            wx, wy = px_to_world(p.x, p.y)
            ent.position = (wx, wy, -0.05)
            active_ids.add(obj_id)

        # Update Guards
        for g in gs['guards']:
            ent, obj_id = self._get_or_create_entity(g, model='quad', col=COLOR_GUARD, scale=(0.5, 0.5))
            wx, wy = px_to_world(g.x, g.y)
            ent.position = (wx, wy, -0.08)
            active_ids.add(obj_id)

        # Update Status Text
        heroes_alive = len([h for h in gs['heroes'] if getattr(h, 'is_alive', True)])
        enemies_alive = len(gs['enemies'])
        self.status_text.text = (
            f"Gold: {gs['gold']}  |  Heroes: {heroes_alive}  |  "
            f"Enemies: {enemies_alive}  |  Buildings: {len(gs['buildings'])}"
        )

        # Prune dead entities
        dead_ids = set(self._entities.keys()) - active_ids
        for obj_id in dead_ids:
            ent = self._entities.pop(obj_id)
            import ursina
            ursina.destroy(ent)
