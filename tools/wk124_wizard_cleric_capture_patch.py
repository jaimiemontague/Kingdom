"""WK124-T3/T4 — Ursina wizard-spell + cleric-heal VFX capture patch (import before main).

Registers TWO Ursina capture scenarios (see
``tools/screenshot_scenarios.py:URSINA_CAPTURE_SCENARIOS``) so the PM can
screenshot-verify the two new WK124 combat VFX on the GPU box:

* ``ursina_wizard_cast``  — a wizard hero casting a MAGIC projectile (purple orb,
  ``kind == "magic"``) at an enemy, held mid-flight, with the wizard's staff
  cast-pose body animation locked.
* ``ursina_cleric_heal``  — a cleric healing a WOUNDED allied warrior: a GREEN
  heal "bolt" (``kind == "heal"``) flying cleric -> ally, held mid-flight (the
  Ursina 3D path renders the heal billboard; the green particle burst is a
  pygame-only effect, so the bolt billboard is what reads in 3D).

Which scene to build is selected by the ``KINGDOM_WK124_SCENE`` env var
(``wizard`` | ``cleric``), set by the scenario ``env`` block in
``screenshot_scenarios.py``. This mirrors how ``tools/run_ursina_capture_once.py``
applies a ``--scenario``'s ``env`` before launching, so no code edits are needed
to pick a scene.

Modeled CLOSELY on ``tools/wk122_guardhouse_arrows_capture_patch.py`` (the
registered guardhouse two-arrow capture) and ``tools/wk67_combat_capture_patch.py``
(the melee strike+hurt anim lock).

Robustness — why two mechanisms per scene (belt + suspenders):

1. The SIM path (FAITHFULNESS / live integration proof):
   * wizard: real ``Hero(hero_class="wizard")`` (``is_ranged_attacker=True``,
     ``attack_range = TILE_SIZE * WIZARD_ATTACK_RANGE_TILES``) is placed in
     FIGHTING state with the enemy as target, ~3 tiles away (inside the 4.5-tile
     range). Each tick we keep the enemy alive/in-range and reset the wizard
     ``attack_cooldown = 0`` so ``CombatSystem`` re-emits a real
     ``ranged_projectile {projectile_kind: "magic"}`` -> ``ProjectileVFX(kind="magic")``.
   * cleric: real ``Hero(hero_class="cleric")`` + a real
     ``Hero(hero_class="warrior")`` ally ~2 tiles apart. Each tick we re-WOUND the
     ally (hp set below the 0.85 heal threshold) and reset the cleric
     ``_heal_cooldown_until_ms = 0`` so ``ClericHealSystem`` re-emits a real
     ``hero_heal`` -> green burst + ``ProjectileVFX(kind="heal")`` bolt.

2. The PIN path (VISIBILITY guarantee): projectile VFX lifetimes are short
   (0.25-0.45 s) and a sim-driven cast may not coincide with the exact frame the
   screenshot grabs. To GUARANTEE the orb/bolt billboard is in the captured frame,
   we additionally re-pin EXACTLY one ``ProjectileVFX`` (correct ``kind``) in
   ``engine.vfx_system._projectiles`` AFTER the real tick, at a fixed mid progress
   between caster and target. This makes the visible billboard independent of
   sim/cast timing and wall-clock tick count.

For the wizard we ALSO lock the wizard's "attack" clip (the staff cast pose) to a
fixed mid-clip frame via a thin wrapper over
``UrsinaRenderer._compute_anim_frame`` (mirrors ``wk67_combat_capture_patch``), so
the captured body pose is tick-independent.

PM iteration knobs (read at app-init, no code edits needed) — all parsed safely
with a fallback to the module default if unset/invalid:

  KINGDOM_WK124_SCENE        (str,   default "wizard")  "wizard" | "cleric"
  KINGDOM_WK124_SEP_TILES    (int,   default 3/2)       caster<->target distance (tiles)
  KINGDOM_WK124_CAM_SPAN     (float, default 5.0)       world-unit span across the frame
  KINGDOM_WK124_CAM_ELEV     (float, default 0.8)       camera-elevation factor (* back dist)
  KINGDOM_WK124_PROGRESS     (float, default 0.45)      held mid-flight progress of the pin

Determinism: the FPS/frame-time debug overlay (varying text in the grabbed
framebuffer) is disabled; the camera is a FIXED (non-EditorCamera) oblique camera
re-aimed each tick on the caster->target midpoint. This module performs NO
import-time ``os.environ`` mutation (the scenario env is set by
``tools/run_ursina_capture_once.py``).
"""
from __future__ import annotations

import os

from config import (
    MAP_WIDTH,
    MAP_HEIGHT,
    TILE_SIZE,
    WIZARD_ATTACK_RANGE_TILES,
    WIZARD_SPELL_COLOR,
    WIZARD_SPELL_SIZE_PX,
    CLERIC_HEAL_RADIUS_TILES,
    CLERIC_HEAL_MIN_TARGET_PCT,
)

# Held mid-flight progress for the pinned billboard (mid-gap reads cleanly).
_PINNED_PROGRESS = 0.45

# Caster<->target separation (tiles). Wizard default 3 (< 4.5 range); cleric 2.
_SEP_TILES_WIZARD = 3
_SEP_TILES_CLERIC = 2

# Camera framing defaults (world units / factor). Span 5 fits both units + the pin.
_CAM_SPAN = 5.0
_CAM_ELEV_FACTOR = 0.8

# Marker tags so the renderer anim wrapper can recognise our planted caster.
_WIZARD_TAG = "_wk124_wizard"

# Heal-bolt / magic-orb billboard tints (match the shipped VFX spec so the pinned
# billboard looks identical to a live cast). The Ursina path picks the texture by
# ``kind`` (magic/heal); ``color`` is carried for parity with the sim spec.
_MAGIC_COLOR = tuple(WIZARD_SPELL_COLOR)
_MAGIC_TIP = (235, 200, 255)
_HEAL_COLOR = (90, 220, 120)
_HEAL_TIP = (235, 255, 200)


# --- env helpers -------------------------------------------------------------------

def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None:
        return str(default)
    val = str(raw).strip().lower()
    return val if val else str(default)


def _env_float(name: str, default: float) -> float:
    """Parse a float env knob; return ``default`` on missing/blank/invalid input."""
    raw = os.environ.get(name)
    if raw is None:
        return float(default)
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return float(default)


def _env_int(name: str, default: int) -> int:
    """Parse an int env knob; return ``default`` on missing/blank/invalid input."""
    raw = os.environ.get(name)
    if raw is None:
        return int(default)
    try:
        return int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return int(default)


def _resolve_scene() -> str:
    """Return the selected scene: 'wizard' or 'cleric' (default 'wizard')."""
    scene = _env_str("KINGDOM_WK124_SCENE", "wizard")
    return "cleric" if scene == "cleric" else "wizard"


def _resolve_knobs(scene: str) -> dict[str, float]:
    """Resolve every PM-overridable framing knob once (used for setup + marker print)."""
    default_sep = _SEP_TILES_CLERIC if scene == "cleric" else _SEP_TILES_WIZARD
    return {
        "sep_tiles": float(_env_int("KINGDOM_WK124_SEP_TILES", int(default_sep))),
        "span": _env_float("KINGDOM_WK124_CAM_SPAN", _CAM_SPAN),
        "elev": _env_float("KINGDOM_WK124_CAM_ELEV", _CAM_ELEV_FACTOR),
        "progress": _env_float("KINGDOM_WK124_PROGRESS", _PINNED_PROGRESS),
    }


# --- scene helpers (modeled on wk122 / wk67) ---------------------------------------

def _building_type_key(building) -> str:
    bt = getattr(building, "building_type", "")
    return str(getattr(bt, "value", bt) or "").strip().lower()


def _reveal_all(world) -> None:
    """Mark every tile VISIBLE (Visibility.VISIBLE == 2) so the scene is not fogged."""
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
    return next(
        (b for b in getattr(engine, "buildings", []) if _building_type_key(b) == "castle"),
        None,
    )


def _tile_center(gx: int, gy: int) -> tuple[float, float]:
    return (gx * TILE_SIZE + TILE_SIZE / 2.0, gy * TILE_SIZE + TILE_SIZE / 2.0)


def _clear_scene(engine) -> tuple[int, int]:
    """Strip dynamic entities + non-castle buildings; return castle grid (cgx, cgy)."""
    engine.enemies = []
    engine.peasants = []
    engine.guards = []
    engine.heroes = []
    try:
        engine.bounty_system.bounties = []
    except Exception:
        pass

    castle = _find_castle(engine)
    engine.buildings = [b for b in getattr(engine, "buildings", []) if b is castle]

    if castle is not None:
        cgx = int(getattr(castle, "grid_x", MAP_WIDTH // 2))
        cgy = int(getattr(castle, "grid_y", MAP_HEIGHT // 2))
    else:
        cgx, cgy = MAP_WIDTH // 2, MAP_HEIGHT // 2

    for attr in ("selected_hero", "selected_peasant", "selected_building"):
        if hasattr(engine, attr):
            setattr(engine, attr, None)
    if hasattr(engine, "screenshot_hide_ui"):
        engine.screenshot_hide_ui = True
    return cgx, cgy


# --- WIZARD scene ------------------------------------------------------------------

def _setup_wizard_scene(engine, knobs: dict[str, float]) -> tuple[object, object]:
    """Place ONE wizard hero + ONE enemy within the wizard's spell range.

    Returns ``(wizard, enemy)``. The enemy is ``sep_tiles`` east of the wizard,
    kept inside ``WIZARD_ATTACK_RANGE_TILES`` (4.5) so the spell always has a valid
    in-range target. The wizard is FIGHTING with the enemy as its target so
    ``CombatSystem`` permits the cast.
    """
    from game.entities.hero import Hero, HeroState
    from game.entities.enemy import Enemy

    cgx, cgy = _clear_scene(engine)

    sep = int(knobs["sep_tiles"])
    # Keep inside the spell range (floor to int below 4.5 -> max 4) and >= 1.
    sep = max(1, min(sep, int(WIZARD_ATTACK_RANGE_TILES)))

    wiz_gx, wiz_gy = cgx, cgy + 4
    enemy_gx, enemy_gy = wiz_gx + sep, wiz_gy

    wx, wy = _tile_center(wiz_gx, wiz_gy)
    ex, ey = _tile_center(enemy_gx, enemy_gy)

    wizard = Hero(wx, wy, hero_class="wizard")
    wizard.name = "Magister Vael"
    enemy = Enemy(ex, ey, enemy_type="goblin")

    wizard.state = HeroState.FIGHTING
    wizard.target = enemy
    enemy.target = wizard
    setattr(wizard, _WIZARD_TAG, True)

    engine.heroes = [wizard]
    engine.enemies = [enemy]
    return wizard, enemy


def _hold_wizard_pose(engine, wizard, enemy, *, wiz_pos, enemy_pos, knobs) -> None:
    """Keep the wizard casting + a magic orb mid-flight after every sim tick.

    Pins positions/HP/state, resets ``attack_cooldown = 0`` so the real
    ``CombatSystem`` re-emits a ``magic`` ranged_projectile each tick (faithfulness),
    re-stamps the "attack" (staff cast) one-shot trigger, then re-pins ONE mid-flight
    ``ProjectileVFX(kind="magic")`` (visibility) so the captured frame always shows the
    purple orb.
    """
    from game.entities.hero import HeroState

    wx, wy = wiz_pos
    ex, ey = enemy_pos

    wizard.x, wizard.y = wx, wy
    wizard.state = HeroState.FIGHTING
    wizard.target = enemy
    try:
        wizard.hp = getattr(wizard, "max_hp", wizard.hp)
    except Exception:
        pass
    if hasattr(wizard, "attack_cooldown"):
        wizard.attack_cooldown = 0
    # Re-stamp the staff cast (the wizard's "attack" clip renders the cast pose).
    wizard._render_anim_trigger = "attack"
    wizard._anim_trigger_seq = int(getattr(wizard, "_anim_trigger_seq", 0) or 0) + 1

    enemy.x, enemy.y = ex, ey
    enemy.target = wizard
    try:
        enemy.hp = getattr(enemy, "max_hp", enemy.hp)
    except Exception:
        pass

    if list(engine.enemies) != [enemy]:
        engine.enemies = [enemy]
    if list(engine.heroes) != [wizard]:
        engine.heroes = [wizard]

    _pin_projectile(
        engine,
        from_xy=(wx, wy),
        to_xy=(ex, ey),
        kind="magic",
        color=_MAGIC_COLOR,
        tip_color=_MAGIC_TIP,
        size_px=int(WIZARD_SPELL_SIZE_PX),
        progress=float(knobs["progress"]),
    )


# --- CLERIC scene ------------------------------------------------------------------

def _setup_cleric_scene(engine, knobs: dict[str, float]) -> tuple[object, object]:
    """Place ONE cleric + ONE wounded allied warrior within heal radius.

    Returns ``(cleric, ally)``. The ally is ``sep_tiles`` east of the cleric, inside
    ``CLERIC_HEAL_RADIUS_TILES`` (4). The ally starts wounded (~40% HP, below the 0.85
    heal threshold) so the cleric immediately heals it.
    """
    from game.entities.hero import Hero

    cgx, cgy = _clear_scene(engine)

    sep = int(knobs["sep_tiles"])
    sep = max(1, min(sep, int(CLERIC_HEAL_RADIUS_TILES) - 1))

    cle_gx, cle_gy = cgx, cgy + 4
    ally_gx, ally_gy = cle_gx + sep, cle_gy

    cx, cy = _tile_center(cle_gx, cle_gy)
    ax, ay = _tile_center(ally_gx, ally_gy)

    cleric = Hero(cx, cy, hero_class="cleric")
    cleric.name = "Sister Mirelle"
    ally = Hero(ax, ay, hero_class="warrior")
    ally.name = "Sir Aldric"

    _wound_ally(ally)

    engine.heroes = [cleric, ally]
    engine.enemies = []
    return cleric, ally


def _wound_ally(ally) -> None:
    """Drop the ally to ~40% HP (below CLERIC_HEAL_MIN_TARGET_PCT so it's a target)."""
    try:
        max_hp = int(getattr(ally, "max_hp", 60))
        target_pct = min(0.4, float(CLERIC_HEAL_MIN_TARGET_PCT) - 0.2)
        ally.hp = max(1, int(max_hp * target_pct))
    except Exception:
        pass


def _hold_cleric_pose(engine, cleric, ally, *, cle_pos, ally_pos, knobs) -> None:
    """Keep the cleric healing + a green heal bolt mid-flight after every sim tick.

    Pins positions, re-WOUNDS the ally below the heal threshold, resets the cleric's
    ``_heal_cooldown_until_ms = 0`` so ``ClericHealSystem`` re-emits a real ``hero_heal``
    each tick (faithfulness), re-stamps the cleric cast pose, then re-pins ONE
    mid-flight ``ProjectileVFX(kind="heal")`` (visibility) so the captured frame always
    shows the green heal bolt.
    """
    cx, cy = cle_pos
    ax, ay = ally_pos

    cleric.x, cleric.y = cx, cy
    try:
        cleric.hp = getattr(cleric, "max_hp", cleric.hp)
    except Exception:
        pass
    # Reset cooldown so the real ClericHealSystem fires a fresh heal every tick.
    cleric._heal_cooldown_until_ms = 0
    cleric.target = ally
    # Re-stamp the cleric cast pose ("attack" clip = the cast gesture).
    cleric._render_anim_trigger = "attack"
    cleric._anim_trigger_seq = int(getattr(cleric, "_anim_trigger_seq", 0) or 0) + 1

    ally.x, ally.y = ax, ay
    _wound_ally(ally)  # re-wound so the cleric keeps targeting it

    if list(engine.heroes) != [cleric, ally]:
        engine.heroes = [cleric, ally]
    if list(engine.enemies) != []:
        engine.enemies = []

    _pin_projectile(
        engine,
        from_xy=(cx, cy),
        to_xy=(ax, ay),
        kind="heal",
        color=_HEAL_COLOR,
        tip_color=_HEAL_TIP,
        size_px=3,
        progress=float(knobs["progress"]),
    )


# --- shared pin / camera / overlay -------------------------------------------------

def _pin_projectile(
    engine,
    *,
    from_xy: tuple[float, float],
    to_xy: tuple[float, float],
    kind: str,
    color: tuple[int, int, int],
    tip_color: tuple[int, int, int],
    size_px: int,
    progress: float,
) -> None:
    """Force EXACTLY one mid-flight ``ProjectileVFX`` of ``kind`` into the VFX system.

    Guarantees the orb/bolt billboard is on screen regardless of sim cast timing:
    rebuilds the projectile each tick at the held progress. Any sim-spawned
    projectiles are cleared first so the frame contains exactly the one pinned
    billboard (no duplicate clutter). The Ursina path picks the billboard texture by
    ``kind`` ("magic" -> purple orb, "heal" -> green orb).
    """
    from game.graphics.vfx import ProjectileVFX

    vfx = getattr(engine, "vfx_system", None)
    if vfx is None:
        return
    projectiles = getattr(vfx, "_projectiles", None)
    if not isinstance(projectiles, list):
        return

    fx, fy = from_xy
    tx, ty = to_xy
    projectiles[:] = [
        ProjectileVFX(
            from_x=float(fx),
            from_y=float(fy),
            to_x=float(tx),
            to_y=float(ty),
            progress=float(progress),
            # Lifetime/age chosen so progress holds and the projectile does not
            # expire before the next tick re-pins it.
            lifetime=10.0,
            age=float(progress) * 10.0,
            color=tuple(color),
            tip_color=tuple(tip_color),
            size_px=int(size_px),
            kind=str(kind),
        )
    ]


def _projectile_world_pos(from_xy, to_xy, progress) -> tuple[float, float]:
    """Pinned-projectile world-pixel (x, y) at the held progress (for camera aim)."""
    fx, fy = from_xy
    tx, ty = to_xy
    px = float(fx) + (float(tx) - float(fx)) * float(progress)
    py = float(fy) + (float(ty) - float(fy)) * float(progress)
    return px, py


def _disable_spawner(engine) -> None:
    """Stop wave/neutral spawns so no stray enemies wander into the framed scene."""
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


def _disable_fps_overlay() -> None:
    """Disable the wall-clock FPS / frame-time debug overlay so the PNG is deterministic."""
    try:
        from ursina import window

        if getattr(window, "fps_counter", None) is not None:
            window.fps_counter.enabled = False
    except Exception:
        pass


def _frame_camera_on_gap(from_xy, to_xy, knobs) -> None:
    """Point a FIXED (non-EditorCamera) oblique camera at the pinned-projectile point.

    The scenario env sets ``KINGDOM_URSINA_EDITORCAMERA=0`` so ``ursina_app`` already
    installed a static camera; we re-aim it precisely at the held mid-flight projectile
    world position so the orb/bolt sits dead-center, large enough to read at the (tight)
    span. blend=0 removes orbit jitter.
    """
    import math

    from ursina import Vec3, camera

    from game.graphics.ursina_renderer import sim_px_to_world_xz

    aim_x, aim_y = _projectile_world_pos(from_xy, to_xy, float(knobs["progress"]))
    cx, cz = sim_px_to_world_xz(aim_x, aim_y)

    # Vertically center the billboard: it sits at terrain_height + PROJECTILE_BILLBOARD_Y.
    # This map has rolling terrain (terrain_y well above 0), so look at the projectile's
    # true 3D Y (not world Y=0, which aims far below and pushes it to the top edge).
    try:
        from game.graphics.terrain_height import get_terrain_height, is_initialized
        from game.graphics.ursina_misc_props_sync import PROJECTILE_BILLBOARD_Y

        wy = (get_terrain_height(cx, cz) if is_initialized() else 0.0) + PROJECTILE_BILLBOARD_Y
        look_at_y = wy
    except Exception:
        look_at_y = 0.3

    span = float(knobs["span"])
    elev_factor = float(knobs["elev"])
    hfov = math.radians(float(camera.fov))
    d = (span * 0.5) / max(1e-6, math.tan(hfov * 0.5))
    elev = d * elev_factor
    back = d
    camera.position = Vec3(cx, look_at_y + elev, cz - back)
    camera.look_at(Vec3(cx, look_at_y, cz))

    _frame_camera_on_gap.last_look_at_y = look_at_y


def _wrap_renderer_anim(renderer) -> None:
    """Lock the wizard's "attack" (staff cast) clip to a fixed mid-clip frame.

    Removes any dependence on tick count / wall-clock from the captured cast pose:
    the tagged wizard always renders a mid-cast frame. All other entities fall through
    to the unmodified computation. (Mirrors ``wk67_combat_capture_patch``.)
    """
    if getattr(renderer, "_wk124_anim_wrapped", False):
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
        idx = min(n - 1, (n // 2) + 1)
        return clip_name, idx

    def patched(obj_id, entity, unit_type, class_key, base_clip_fn=None):
        if getattr(entity, _WIZARD_TAG, False):
            return _mid_clip_frame("attack", unit_type, class_key)
        return orig(obj_id, entity, unit_type, class_key, base_clip_fn)

    renderer._compute_anim_frame = patched
    renderer._wk124_anim_wrapped = True


# --- patch entrypoint --------------------------------------------------------------

def apply_patch() -> None:
    from game.graphics import ursina_app as ua

    orig_init = ua.UrsinaApp.__init__

    def patched_init(self, ai_controller_factory):
        orig_init(self, ai_controller_factory)

        scene = _resolve_scene()
        knobs = _resolve_knobs(scene)

        _disable_fps_overlay()
        _reveal_all(self.engine.world)
        _disable_spawner(self.engine)

        if scene == "cleric":
            cleric, ally = _setup_cleric_scene(self.engine, knobs)
            cle_pos = (cleric.x, cleric.y)
            ally_pos = (ally.x, ally.y)
            from_xy, to_xy = cle_pos, ally_pos

            _frame_camera_on_gap(from_xy, to_xy, knobs)
            _hold_cleric_pose(
                self.engine, cleric, ally,
                cle_pos=cle_pos, ally_pos=ally_pos, knobs=knobs,
            )

            orig_tick = self.engine.tick_simulation

            def patched_tick(dt):
                result = orig_tick(dt)
                _hold_cleric_pose(
                    self.engine, cleric, ally,
                    cle_pos=cle_pos, ally_pos=ally_pos, knobs=knobs,
                )
                _frame_camera_on_gap(from_xy, to_xy, knobs)
                return result

            self.engine.tick_simulation = patched_tick

            look_at_y = float(getattr(_frame_camera_on_gap, "last_look_at_y", 0.0))
            print(
                "[wk124-vfx-capture] scene=cleric "
                f"cleric@({cle_pos[0]:.0f},{cle_pos[1]:.0f}) "
                f"ally=warrior@({ally_pos[0]:.0f},{ally_pos[1]:.0f}) "
                f"heal_radius_tiles={CLERIC_HEAL_RADIUS_TILES} "
                f"min_target_pct={CLERIC_HEAL_MIN_TARGET_PCT} "
                f"sep_tiles={int(knobs['sep_tiles'])} "
                f"span={knobs['span']:.3g} elev={knobs['elev']:.3g} "
                f"progress={knobs['progress']:.3g} look_at_y={look_at_y:.3f}; "
                "green heal bolt (kind=heal) pinned mid-flight; fps overlay disabled",
                flush=True,
            )
        else:
            wizard, enemy = _setup_wizard_scene(self.engine, knobs)
            wiz_pos = (wizard.x, wizard.y)
            enemy_pos = (enemy.x, enemy.y)
            from_xy, to_xy = wiz_pos, enemy_pos

            renderer = getattr(self, "renderer", None)
            if renderer is not None:
                _wrap_renderer_anim(renderer)

            _frame_camera_on_gap(from_xy, to_xy, knobs)
            _hold_wizard_pose(
                self.engine, wizard, enemy,
                wiz_pos=wiz_pos, enemy_pos=enemy_pos, knobs=knobs,
            )

            orig_tick = self.engine.tick_simulation

            def patched_tick(dt):
                result = orig_tick(dt)
                r = getattr(self, "renderer", None)
                if r is not None:
                    _wrap_renderer_anim(r)
                _hold_wizard_pose(
                    self.engine, wizard, enemy,
                    wiz_pos=wiz_pos, enemy_pos=enemy_pos, knobs=knobs,
                )
                _frame_camera_on_gap(from_xy, to_xy, knobs)
                return result

            self.engine.tick_simulation = patched_tick

            look_at_y = float(getattr(_frame_camera_on_gap, "last_look_at_y", 0.0))
            print(
                "[wk124-vfx-capture] scene=wizard "
                f"wizard@({wiz_pos[0]:.0f},{wiz_pos[1]:.0f}) "
                f"enemy=goblin@({enemy_pos[0]:.0f},{enemy_pos[1]:.0f}) "
                f"range_tiles={WIZARD_ATTACK_RANGE_TILES} "
                f"spell_size_px={WIZARD_SPELL_SIZE_PX} "
                f"sep_tiles={int(knobs['sep_tiles'])} "
                f"span={knobs['span']:.3g} elev={knobs['elev']:.3g} "
                f"progress={knobs['progress']:.3g} look_at_y={look_at_y:.3f}; "
                "purple magic orb (kind=magic) pinned mid-flight + staff cast pose; "
                "fps overlay disabled",
                flush=True,
            )

    ua.UrsinaApp.__init__ = patched_init


apply_patch()
