"""WK67 Round A-2 (Wave 5) — Ursina melee-combat capture patch (import before main).

Registered Ursina capture scenario ``ursina_melee_combat`` (see
``tools/screenshot_scenarios.py:URSINA_CAPTURE_SCENARIOS``). The primary (Ursina)
renderer had NO registered melee-combat scenario, so the unit-render/anim boundary
on the shipping renderer had thin visual coverage. This patch spawns a warrior hero
adjacent to a goblin near the castle, forces a melee strike + hurt one-shot pose, and
holds it so the auto-screenshot captures the strike+hurt frame.

Determinism (byte-identical across two ``DETERMINISTIC_SIM=1`` runs):

1. The wall-clock **FPS / frame-time debug overlay** (``window.fps_counter`` enabled at
   ``ursina_app.py``) renders a varying number into the framebuffer the screenshot grabs.
   We DISABLE it for the capture (debug toggle) so only the deterministic scene remains.

2. The number of sim ticks executed before the wall-clock auto-exit deadline varies
   run-to-run (the Ursina update loop ticks on ``time.dt``), so we do NOT rely on the
   sim reaching an exact tick. Instead we:
     - use a FIXED (non-EditorCamera) camera framed on the castle (blend=0, no follow
       jitter) — set via the scenario env vars (KINGDOM_URSINA_EDITORCAMERA=0 +
       KINGDOM_URSINA_CAM_FOCUS_BUILDING_TYPE=castle + KINGDOM_URSINA_CAM_FOCUS_SPAN);
     - re-pin the combat scene (positions / state / hp / alive / anim triggers) after
       every sim tick so the strike+hurt stays held regardless of how many ticks ran;
     - lock the displayed anim clip+frame for the two combatants to a FIXED mid-clip
       index via a thin wrapper over ``UrsinaRenderer._compute_anim_frame`` — so the
       captured pose is identical every frame, independent of tick count / wall clock.

This module performs NO import-time ``os.environ`` mutation (the scenario env is set by
``tools/run_ursina_capture_once.py`` before the subprocess starts).
"""
from __future__ import annotations

from config import MAP_WIDTH, MAP_HEIGHT, TILE_SIZE

# Marker attributes used to recognise our two planted combatants without holding a
# direct reference inside the renderer wrapper (entities may be re-resolved per tick).
_HERO_TAG = "_wk67_combat_hero"
_ENEMY_TAG = "_wk67_combat_enemy"


def _building_type_key(building) -> str:
    bt = getattr(building, "building_type", "")
    return str(getattr(bt, "value", bt) or "").strip().lower()


def _reveal_all(world) -> None:
    """Mark every tile VISIBLE (Visibility.VISIBLE == 2) so the combatants are not fogged."""
    vis = getattr(world, "visibility", None)
    if not isinstance(vis, list):
        return
    try:
        for y in range(len(vis)):
            row = vis[y]
            for x in range(len(row)):
                row[x] = 2
        if hasattr(world, "_currently_visible"):
            world._currently_visible = {
                (x, y) for y in range(len(vis)) for x in range(len(vis[y]))
            }
    except Exception:
        return


def _find_castle(engine):
    castle = next(
        (b for b in getattr(engine, "buildings", []) if _building_type_key(b) == "castle"),
        None,
    )
    return castle


def _setup_combat_scene(engine) -> tuple[object, object]:
    """Place a warrior hero + a goblin enemy on adjacent tiles near the castle.

    Returns ``(hero, enemy)``. Both are tagged so the per-tick re-pin and the renderer
    anim wrapper can recognise them.
    """
    from game.entities.hero import Hero, HeroState
    from game.entities.enemy import Enemy

    # Clear other dynamic entities so the strike/hurt pose is the only combat on screen.
    engine.enemies = []
    engine.peasants = []
    engine.guards = []
    try:
        engine.bounty_system.bounties = []
    except Exception:
        pass

    # Keep only the castle so the framed shot is clean (castle + the two combatants).
    castle = _find_castle(engine)
    engine.buildings = [b for b in getattr(engine, "buildings", []) if b is castle]

    if castle is not None:
        cgx = int(getattr(castle, "grid_x", MAP_WIDTH // 2))
        cgy = int(getattr(castle, "grid_y", MAP_HEIGHT // 2))
    else:
        cgx, cgy = MAP_WIDTH // 2, MAP_HEIGHT // 2

    # Adjacent tiles just south of the castle, in front of the gate where the camera frames.
    hero_gx, hero_gy = cgx, cgy + 4
    enemy_gx, enemy_gy = hero_gx + 1, hero_gy  # one tile apart → within melee range

    def _tile_center(gx: int, gy: int) -> tuple[float, float]:
        return (gx * TILE_SIZE + TILE_SIZE / 2.0, gy * TILE_SIZE + TILE_SIZE / 2.0)

    hx, hy = _tile_center(hero_gx, hero_gy)
    ex, ey = _tile_center(enemy_gx, enemy_gy)

    hero = Hero(hx, hy, hero_class="warrior")
    hero.name = "Sir Aldric"
    enemy = Enemy(ex, ey, enemy_type="goblin")

    # Hero faces the enemy and is locked into FIGHTING with the enemy as target so
    # CombatSystem permits the strike; enemy faces the hero.
    hero.state = HeroState.FIGHTING
    hero.target = enemy
    enemy.target = hero

    setattr(hero, _HERO_TAG, True)
    setattr(enemy, _ENEMY_TAG, True)

    engine.heroes = [hero]
    engine.enemies = [enemy]

    # Park selection / debug UI so they cannot perturb the frame.
    for attr in ("selected_hero", "selected_peasant", "selected_building"):
        if hasattr(engine, attr):
            setattr(engine, attr, None)
    if hasattr(engine, "screenshot_hide_ui"):
        engine.screenshot_hide_ui = True

    _hold_combat_pose(hero, enemy, hero_pos=(hx, hy), enemy_pos=(ex, ey))
    return hero, enemy


def _hold_combat_pose(hero, enemy, *, hero_pos, enemy_pos) -> None:
    """Re-stamp the strike/hurt one-shot triggers and pin positions / hp / state.

    Called once at setup and after every sim tick so the held pose survives AI/combat
    mutation (movement, cooldowns, death) regardless of how many ticks run before
    capture. Keeps both combatants alive with full hp so the goblin never dies and the
    hero never wanders off.
    """
    from game.entities.hero import HeroState

    hx, hy = hero_pos
    ex, ey = enemy_pos

    # Pin positions (adjacent, within melee range) and combat intent.
    hero.x, hero.y = hx, hy
    hero.state = HeroState.FIGHTING
    hero.target = enemy
    try:
        hero.hp = getattr(hero, "max_hp", hero.hp)
    except Exception:
        pass
    # Reset cooldown so CombatSystem keeps re-issuing the strike each cycle.
    if hasattr(hero, "attack_cooldown"):
        hero.attack_cooldown = 0

    enemy.x, enemy.y = ex, ey
    enemy.target = hero
    try:
        enemy.hp = getattr(enemy, "max_hp", enemy.hp)
    except Exception:
        pass

    # Force the one-shot anim triggers (the renderer plays them when the seq advances).
    hero._render_anim_trigger = "attack"
    hero._anim_trigger_seq = int(getattr(hero, "_anim_trigger_seq", 0) or 0) + 1
    enemy._render_anim_trigger = "hurt"
    enemy._anim_trigger_seq = int(getattr(enemy, "_anim_trigger_seq", 0) or 0) + 1


def _disable_spawner(engine) -> None:
    """Stop wave/neutral spawns so no stray enemies wander into the framed combat."""
    sim = getattr(engine, "sim", None)
    spawner = getattr(sim, "spawner", None) if sim is not None else None
    if spawner is not None:
        for attr in ("spawn_interval", "spawn_interval_sec", "spawn_timer"):
            if hasattr(spawner, attr):
                try:
                    setattr(spawner, attr, 1.0e9)
                except Exception:
                    pass
    neutral = getattr(engine, "neutral_building_system", None)
    if neutral is not None and hasattr(neutral, "spawn_interval_sec"):
        try:
            neutral.spawn_interval_sec = 1.0e9
        except Exception:
            pass


def _frame_camera_on_combat(hero, enemy) -> None:
    """Point a FIXED (non-EditorCamera) oblique camera at the combat midpoint.

    The scenario env sets ``KINGDOM_URSINA_EDITORCAMERA=0`` so ``ursina_app`` already
    installed a static (non-orbit) camera; we re-aim it precisely at the strike so the
    two combatants fill the frame. A fixed camera at blend=0 removes any follow/orbit
    jitter from the byte-comparison.
    """
    import math

    from ursina import Vec3, camera

    from game.graphics.ursina_renderer import sim_px_to_world_xz

    mid_x = (hero.x + enemy.x) / 2.0
    mid_y = (hero.y + enemy.y) / 2.0
    cx, cz = sim_px_to_world_xz(mid_x, mid_y)

    span = 10.0  # world units across the frame — tight on the two units
    hfov = math.radians(float(camera.fov))
    d = (span * 0.5) / max(1e-6, math.tan(hfov * 0.5))
    elev = d * 0.8
    back = d
    camera.position = Vec3(cx, elev, cz - back)
    camera.look_at(Vec3(cx, 0, cz))


def _disable_fps_overlay() -> None:
    """Disable the wall-clock FPS / frame-time debug overlay so the captured PNG is
    deterministic (the overlay text varies per run and lives in the grabbed framebuffer).
    """
    try:
        from ursina import window

        if getattr(window, "fps_counter", None) is not None:
            window.fps_counter.enabled = False
    except Exception:
        pass


def _wrap_renderer_anim(renderer) -> None:
    """Lock the displayed clip+frame for the two combatants to a fixed mid-clip index.

    This removes any dependence on tick count / wall-clock from the captured pose: the
    hero always renders a mid-swing ``attack`` frame and the goblin a mid-recoil ``hurt``
    frame. All other entities fall through to the unmodified computation.
    """
    if getattr(renderer, "_wk67_combat_anim_wrapped", False):
        return
    orig = renderer._compute_anim_frame

    def _mid_clip_frame(clip_name: str, unit_type: str, class_key: str) -> tuple:
        clips = renderer._get_cached_clips(unit_type, class_key)
        clip = clips.get(clip_name)
        if clip is None:
            return clip_name, 0
        n = len(getattr(clip, "frames", ()) or ())
        if n <= 1:
            return clip_name, 0
        # Mid-clip, biased toward the extended/recoil frame (clearly reads as a strike).
        idx = min(n - 1, (n // 2) + 1)
        return clip_name, idx

    def patched(obj_id, entity, unit_type, class_key, base_clip_fn):
        if getattr(entity, _HERO_TAG, False):
            return _mid_clip_frame("attack", unit_type, class_key)
        if getattr(entity, _ENEMY_TAG, False):
            return _mid_clip_frame("hurt", unit_type, class_key)
        return orig(obj_id, entity, unit_type, class_key, base_clip_fn)

    renderer._compute_anim_frame = patched
    renderer._wk67_combat_anim_wrapped = True


def apply_patch() -> None:
    from game.graphics import ursina_app as ua

    orig_init = ua.UrsinaApp.__init__

    def patched_init(self, ai_controller_factory):
        orig_init(self, ai_controller_factory)

        _disable_fps_overlay()
        _reveal_all(self.engine.world)
        _disable_spawner(self.engine)
        hero, enemy = _setup_combat_scene(self.engine)
        hero_pos = (hero.x, hero.y)
        enemy_pos = (enemy.x, enemy.y)

        # Lock the rendered combat pose (independent of tick / wall clock).
        renderer = getattr(self, "renderer", None)
        if renderer is not None:
            _wrap_renderer_anim(renderer)

        # Aim the fixed camera straight at the strike.
        _frame_camera_on_combat(hero, enemy)

        # Re-pin the held pose after every sim tick so AI/combat mutation cannot move
        # the combatants or kill the goblin before the wall-clock auto-exit fires.
        orig_tick = self.engine.tick_simulation

        def patched_tick(dt):
            result = orig_tick(dt)
            # The renderer may be created after __init__; wrap lazily if needed.
            r = getattr(self, "renderer", None)
            if r is not None:
                _wrap_renderer_anim(r)
            _hold_combat_pose(hero, enemy, hero_pos=hero_pos, enemy_pos=enemy_pos)
            # Keep the scene free of any spawned strays.
            if list(self.engine.enemies) != [enemy]:
                self.engine.enemies = [enemy]
            if list(self.engine.heroes) != [hero]:
                self.engine.heroes = [hero]
            # Re-aim the fixed camera (the update loop re-derives FOV from zoom each
            # frame; re-frame against the current FOV so the shot stays locked).
            _frame_camera_on_combat(hero, enemy)
            return result

        self.engine.tick_simulation = patched_tick

        print(
            "[wk67-combat-capture] hero=warrior@"
            f"({hero_pos[0]:.0f},{hero_pos[1]:.0f}) "
            f"enemy=goblin@({enemy_pos[0]:.0f},{enemy_pos[1]:.0f}) "
            "strike+hurt pose held; fps overlay disabled",
            flush=True,
        )

    ua.UrsinaApp.__init__ = patched_init


apply_patch()
