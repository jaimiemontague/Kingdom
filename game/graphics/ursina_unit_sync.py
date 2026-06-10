"""Per-frame per-unit-kind render-sync for the Ursina renderer.

WK92, Round B-9. Pure-move of the five per-unit-kind per-frame render-sync
methods out of ``game/graphics/ursina_renderer.py`` (the last big chunk of the
ursina_renderer split):

* ``sync_snapshot_heroes``         — hero atlas-UV billboards + HP bar / name /
  gold / rest / facing overlays (was ``_sync_snapshot_heroes``)
* ``sync_snapshot_enemies``        — enemy atlas-UV billboards + HP bar / name /
  facing (was ``_sync_snapshot_enemies``)
* ``sync_snapshot_peasants``       — peasant/worker atlas-UV billboards + HP bar /
  name (was ``_sync_snapshot_peasants``)
* ``sync_snapshot_guards``         — guard atlas-UV billboards + HP bar / name
  (was ``_sync_snapshot_guards``)
* ``sync_snapshot_tax_collector``  — tax-collector atlas-UV billboard + name /
  carried-gold label (was ``_sync_snapshot_tax_collector``)

Each function takes the ``UrsinaRenderer`` instance as ``r`` and reads/writes its
state (``r._camera_active_layer``, ``r._entities``, ``r._entity_render`` collab,
``r._unit_anim_state`` / ``r._unit_facing_state`` — accessed transitively via the
anim/facing wrappers) and calls its methods exactly as the original methods read
``self.*``: ``r._entity_in_view`` (WK88 frustum wrapper), ``r._facing_from_dto``
(WK89 anim wrapper), and ``r._sync_unit_atlas_billboard`` /
``r._entity_render.get_or_create_entity`` / ``r._entity_render.sync_inside_hero_draw_layer``.

The unit-billboard scale constants (``UNIT_BILLBOARD_SCALE`` / ``ENEMY_SCALE`` /
``PEASANT_SCALE_XZ`` / ``PEASANT_SCALE_Y`` / ``GUARD_SCALE_XZ`` /
``GUARD_SCALE_Y``) and the fallback tint colors (``COLOR_HERO`` / ``COLOR_ENEMY``)
are recomputed here identically to the ursina_renderer module-level values
(config-/color-derived, no renderer import needed — same cycle-free pattern as
WK90/WK91). The bare-name overlay helpers (``_ensure_ks_name_label`` /
``_configure_ks_overlay``) are thin local wrappers over
``ursina_unit_overlays`` — identical to the ones the renderer keeps.

``UrsinaRenderer`` keeps 1-line delegating wrappers (``_sync_snapshot_heroes`` /
``_sync_snapshot_enemies`` / ``_sync_snapshot_peasants`` /
``_sync_snapshot_guards`` / ``_sync_snapshot_tax_collector``) that import this
module lazily, so the ``update()`` pipeline call sites are unchanged and there is
no import cycle (this module never imports ``ursina_renderer`` at module top).
Leaf deps only.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

import config
from ursina import color

from game.graphics.ursina_sprite_unlit_shader import sprite_unlit_shader
from game.graphics.ursina_coords import sim_px_to_world_xz
from game.graphics.terrain_height import get_terrain_height, is_initialized as _terrain_height_ok
from game.graphics.visual_specs import (
    HERO_SPEC, ENEMY_SPEC, PEASANT_SPEC, GUARD_SPEC, TAX_COLLECTOR_SPEC,
)
from game.graphics.ursina_unit_overlays import (
    configure_ks_overlay as _configure_ks_overlay_impl,
    ensure_ks_name_label as _ensure_ks_name_label_impl,
    sync_hp_bar,
    sync_hero_gold_label,
    sync_hero_rest_label,
    sync_hero_overlays_facing,
    sync_quest_giver_marker,
    sync_unit_overlays_facing,
)
from game.world import Visibility

if TYPE_CHECKING:
    from game.graphics.ursina_renderer import UrsinaRenderer
    from game.sim.snapshot import SimStateSnapshot

# Fallback tint when hero class is unresolved or texture upload fails — match Warrior shirt (HeroSpriteSpec).
# Recomputed here identically to the ursina_renderer module-level values.
COLOR_HERO = color.rgb(180 / 255.0, 45 / 255.0, 45 / 255.0)
COLOR_ENEMY = color.red

# Unit-billboard scale constants — recomputed here identically to the
# ursina_renderer module-level values (config-derived, no renderer import needed).
_US = float(getattr(config, "UNIT_SPRITE_PIXELS", config.TILE_SIZE)) / float(config.TILE_SIZE)
# Pixel billboard height in world units; scales with UNIT_SPRITE_PIXELS so larger raster reads larger on screen.
UNIT_BILLBOARD_SCALE = 0.62 * _US
ENEMY_SCALE = 0.5 * _US
_WB = float(getattr(config, "URSINA_WORKER_BILLBOARD_BASE", 0.42))
_WYM = float(getattr(config, "URSINA_WORKER_BILLBOARD_Y_SCALE_MUL", 0.55))
PEASANT_SCALE_XZ = _WB * _US
PEASANT_SCALE_Y = PEASANT_SCALE_XZ * _WYM
GUARD_SCALE_XZ = 0.5 * _US
GUARD_SCALE_Y = 0.7 * _US


def _configure_ks_overlay(ent) -> None:
    """Depth-off + on-top so labels/HP/gold overlays are not hidden by terrain or prefabs.

    WK62: delegates to ``ursina_unit_overlays.configure_ks_overlay``.
    """
    _configure_ks_overlay_impl(ent)


def _ensure_ks_name_label(
    ent,
    attr: str,
    text: str,
    *,
    y: float = 0.55,
    scale: float = 10,
    label_color=None,
) -> None:
    """WK62: delegates to ``ursina_unit_overlays.ensure_ks_name_label``."""
    _ensure_ks_name_label_impl(ent, attr, text, y=y, scale=scale, label_color=label_color)


def sync_snapshot_heroes(r: "UrsinaRenderer", snapshot: "SimStateSnapshot", active_ids: set, HeroClass) -> None:
    # Heroes — atlas UV billboards (WK59 perf: single shared texture, UV offset per frame)
    # WK68 R2 (Agent 09): consume frozen UnitDTOs and key r._entities on the stable
    # dto.entity_id (string) — NOT id(h). id() of a per-frame DTO is unstable; entity_id
    # is consistent across create / cull / re-enable / destroy.
    _active_layer = r._camera_active_layer
    for h in getattr(snapshot, "hero_dtos", ()):
        if not getattr(h, "is_alive", True):
            continue
        obj_id = h.entity_id
        # WK57 Wave 3: Layer-aware visibility — hide heroes on a different layer
        _hero_layer = getattr(h, 'layer', 0)
        if _hero_layer != _active_layer:
            _h_existing = r._entities.get(obj_id)
            if _h_existing is not None:
                _h_existing.enabled = False
                active_ids.add(obj_id)
            continue
        # WK59 perf: frustum culling — skip heroes outside visible tile rect
        if not r._entity_in_view(h.x, h.y):
            _h_existing = r._entities.get(obj_id)
            if _h_existing is not None:
                _h_existing.enabled = False
                active_ids.add(obj_id)
            continue
        # Re-enable hero if it was previously culled and is now in view
        _h_reenable = r._entities.get(obj_id)
        if _h_reenable is not None and getattr(_h_reenable, "enabled", True) is False:
            _h_reenable.enabled = True
        col = COLOR_HERO
        if HeroClass:
            hc = getattr(h, "hero_class", None)
            if hc == HeroClass.WARRIOR or str(hc).lower() == "warrior":
                col = color.white
            elif hc == HeroClass.RANGER or str(hc).lower() == "ranger":
                col = color.lime
            elif hc == HeroClass.WIZARD or str(hc).lower() == "wizard":
                col = color.magenta
            elif hc == HeroClass.ROGUE or str(hc).lower() == "rogue":
                col = color.violet
            elif hc == HeroClass.CLERIC or str(hc).lower() == "cleric":
                col = color.rgb(48 / 255, 186 / 255, 178 / 255)

        hc_key = str(getattr(h, "hero_class", "warrior") or "warrior").lower()
        sy = UNIT_BILLBOARD_SCALE
        ent, obj_id = r._entity_render.get_or_create_entity(
            h,
            model="quad",
            col=color.white,
            scale=(sy, sy, 1),
            texture=None,
            billboard=True,
            key=obj_id,
        )
        wx, wz = sim_px_to_world_xz(h.x, h.y)
        terrain_y = get_terrain_height(wx, wz) if _terrain_height_ok() else 0.0
        y_center = terrain_y + sy * 0.5
        facing = r._facing_from_dto(h)
        sx = sy * facing  # negative scale_x flips the billboard horizontally

        r._sync_unit_atlas_billboard(
            ent, obj_id, h, "hero", hc_key, None,
            col, (sx, sy, 1), (wx, y_center, wz), sprite_unlit_shader,
        )
        # Layer compositing (not Y offset): draw after building billboards; skip depth so the
        # "inside" bubble paints over the same footprint as the facade.
        r._entity_render.sync_inside_hero_draw_layer(ent, bool(getattr(h, "is_inside_building", False)))

        # --- R5: Native Ursina health bar (Agent 09) ---
        # WK62: delegates to ursina_unit_overlays.sync_hp_bar
        _h_hp = int(getattr(h, 'hp', 0) or 0)
        _h_max_hp = int(getattr(h, 'max_hp', 1) or 1)
        sync_hp_bar(ent, _h_hp, _h_max_hp, HERO_SPEC)

        # --- R5: Hero name label (Agent 08) ---
        hero_name = getattr(h, 'name', '') or ''
        _ensure_ks_name_label(ent, '_ks_name_label', hero_name, y=HERO_SPEC.label_y, scale=HERO_SPEC.label_scale)

        # --- R5: Hero gold display (Agent 08) ---
        # WK62: delegates to ursina_unit_overlays.sync_hero_gold_label
        hero_gold = int(getattr(h, 'gold', 0) or 0)
        hero_taxed = int(getattr(h, 'taxed_gold', 0) or 0)
        sync_hero_gold_label(ent, hero_gold, hero_taxed)

        # --- R5: Hero rest indicator (Agent 08) ---
        # WK62: delegates to ursina_unit_overlays.sync_hero_rest_label
        # WK68 R2 (Agent 09): BEHAVIOR-PRESERVING. The legacy line compared the live
        # ``hero.state`` (a plain ``HeroState`` Enum, NOT a str-enum) to the string
        # 'RESTING' — which is ALWAYS False, so the "Zzz" label never showed. The DTO
        # flattens state to the string 'RESTING' when resting, so reading dto.state
        # here would FLIP this on and add a label that legacy never drew. To keep the
        # captures byte-identical we reproduce the legacy always-False result.
        # (Latent dead indicator — flagged to Agent 08/UX; fix belongs in their lane.)
        is_resting = False
        sync_hero_rest_label(ent, is_resting)

        # WK61-R4-BUG-001: un-mirror overlay children when parent faces left.
        # WK62: delegates to ursina_unit_overlays.sync_hero_overlays_facing
        sync_hero_overlays_facing(ent, facing)

        active_ids.add(obj_id)


def sync_snapshot_enemies(r: "UrsinaRenderer", snapshot: "SimStateSnapshot", world, active_ids: set) -> None:
    # Enemies — atlas UV billboards (WK59 perf: single shared texture)
    # WK68 R2 (Agent 09): frozen UnitDTOs keyed on the stable dto.entity_id (not id(e)).
    _active_layer = r._camera_active_layer
    ts = float(config.TILE_SIZE)
    for e in getattr(snapshot, "enemy_dtos", ()):
        obj_id = e.entity_id
        # WK57 Wave 3: Layer-aware visibility — hide enemies on a different layer
        _enemy_layer = getattr(e, 'layer', 0)
        if _enemy_layer != _active_layer:
            _e_existing = r._entities.get(obj_id)
            if _e_existing is not None:
                _e_existing.enabled = False
                active_ids.add(obj_id)
            continue

        tx, ty = int(e.x / ts), int(e.y / ts)
        is_visible = True
        if 0 <= ty < world.height and 0 <= tx < world.width:
            is_visible = (world.visibility[ty][tx] == Visibility.VISIBLE)

        if not getattr(e, "is_alive", True) or not is_visible:
            continue
        # WK59 perf: frustum culling — skip enemies outside visible tile rect
        if not r._entity_in_view(e.x, e.y):
            _e_existing = r._entities.get(obj_id)
            if _e_existing is not None:
                _e_existing.enabled = False
                active_ids.add(obj_id)
            continue
        # Re-enable enemy if it was previously culled and is now in view
        _e_reenable = r._entities.get(obj_id)
        if _e_reenable is not None and getattr(_e_reenable, "enabled", True) is False:
            _e_reenable.enabled = True
        s = ENEMY_SCALE
        col = COLOR_ENEMY
        et_key = str(getattr(e, "enemy_type", "goblin") or "goblin").lower()
        ent, obj_id = r._entity_render.get_or_create_entity(
            e,
            model="quad",
            col=color.white,
            scale=(s, s, 1),
            texture=None,
            billboard=True,
            key=obj_id,
        )
        wx, wz = sim_px_to_world_xz(e.x, e.y)
        terrain_y = get_terrain_height(wx, wz) if _terrain_height_ok() else 0.0
        facing_e = r._facing_from_dto(e)
        sx_e = s * facing_e

        r._sync_unit_atlas_billboard(
            ent, obj_id, e, "enemy", et_key, None,
            col, (sx_e, s, 1), (wx, terrain_y + s * 0.5, wz), sprite_unlit_shader,
        )

        # --- R5: Native Ursina health bar (Agent 09) ---
        # WK62: delegates to ursina_unit_overlays.sync_hp_bar
        _e_hp = int(getattr(e, 'hp', 0) or 0)
        _e_max_hp = int(getattr(e, 'max_hp', 1) or 1)
        sync_hp_bar(ent, _e_hp, _e_max_hp, ENEMY_SPEC)

        enemy_label = str(getattr(e, "enemy_type", "enemy") or "enemy").replace("_", " ").title()
        _ensure_ks_name_label(ent, "_ks_name_label", enemy_label, y=ENEMY_SPEC.label_y, scale=ENEMY_SPEC.label_scale)

        # WK62: delegates to ursina_unit_overlays.sync_unit_overlays_facing
        sync_unit_overlays_facing(ent, facing_e)

        active_ids.add(obj_id)


def sync_snapshot_peasants(r: "UrsinaRenderer", snapshot: "SimStateSnapshot", active_ids: set) -> None:
    # Peasants — atlas UV billboards (WK59 perf: single shared texture)
    # WK68 R2 (Agent 09): frozen UnitDTOs keyed on the stable dto.entity_id (not id(p)).
    _active_layer = r._camera_active_layer
    for p in getattr(snapshot, "peasant_dtos", ()):
        if not getattr(p, "is_alive", True):
            continue
        if bool(getattr(p, "is_inside_castle", False)):
            continue
        obj_id = p.entity_id
        # WK57 Wave 3: Peasants are always surface (layer 0) — hide when camera underground
        if _active_layer != 0:
            _p_existing = r._entities.get(obj_id)
            if _p_existing is not None:
                _p_existing.enabled = False
                active_ids.add(obj_id)
            continue
        # WK59 perf: frustum culling — skip peasants outside visible tile rect
        if not r._entity_in_view(p.x, p.y):
            _p_existing = r._entities.get(obj_id)
            if _p_existing is not None:
                _p_existing.enabled = False
                active_ids.add(obj_id)
            continue
        # Re-enable peasant if it was previously culled and is now in view
        _p_reenable = r._entities.get(obj_id)
        if _p_reenable is not None and getattr(_p_reenable, "enabled", True) is False:
            _p_reenable.enabled = True
        sx = PEASANT_SCALE_XZ
        sy = PEASANT_SCALE_Y
        col = color.white
        wk = str(getattr(p, "render_worker_type", "peasant") or "peasant")
        ent, obj_id = r._entity_render.get_or_create_entity(
            p,
            model="quad",
            col=color.white,
            scale=(sx, sy, 1),
            texture=None,
            billboard=True,
            key=obj_id,
        )
        wx, wz = sim_px_to_world_xz(p.x, p.y)
        terrain_y = get_terrain_height(wx, wz) if _terrain_height_ok() else 0.0

        r._sync_unit_atlas_billboard(
            ent, obj_id, p, "worker", wk, None,
            col, (sx, sy, 1), (wx, terrain_y + sy * 0.5, wz), sprite_unlit_shader,
        )

        # --- R5: Native Ursina health bar (Agent 09) ---
        # WK62: delegates to ursina_unit_overlays.sync_hp_bar
        _p_hp = int(getattr(p, 'hp', 0) or 0)
        _p_max_hp = int(getattr(p, 'max_hp', 1) or 1)
        sync_hp_bar(ent, _p_hp, _p_max_hp, PEASANT_SPEC)

        worker_label = str(getattr(p, "render_worker_type", "peasant") or "peasant").replace("_", " ").title()
        _ensure_ks_name_label(ent, "_ks_name_label", worker_label, y=PEASANT_SPEC.label_y, scale=PEASANT_SPEC.label_scale)

        active_ids.add(obj_id)


def sync_snapshot_guards(r: "UrsinaRenderer", snapshot: "SimStateSnapshot", active_ids: set) -> None:
    # Guards — atlas UV billboards (WK59 perf: single shared texture)
    # WK68 R2 (Agent 09): frozen UnitDTOs keyed on the stable dto.entity_id (not id(g)).
    _active_layer = r._camera_active_layer
    for g in getattr(snapshot, "guard_dtos", ()):
        if not getattr(g, "is_alive", True):
            continue
        obj_id = g.entity_id
        # WK57 Wave 3: Guards are always surface (layer 0) — hide when camera underground
        if _active_layer != 0:
            _g_existing = r._entities.get(obj_id)
            if _g_existing is not None:
                _g_existing.enabled = False
                active_ids.add(obj_id)
            continue
        # WK59 perf: frustum culling — skip guards outside visible tile rect
        if not r._entity_in_view(g.x, g.y):
            _g_existing = r._entities.get(obj_id)
            if _g_existing is not None:
                _g_existing.enabled = False
                active_ids.add(obj_id)
            continue
        # Re-enable guard if it was previously culled and is now in view
        _g_reenable = r._entities.get(obj_id)
        if _g_reenable is not None and getattr(_g_reenable, "enabled", True) is False:
            _g_reenable.enabled = True
        col = color.white
        ent, obj_id = r._entity_render.get_or_create_entity(
            g,
            model="quad",
            col=color.white,
            scale=(GUARD_SCALE_XZ, GUARD_SCALE_Y, 1),
            texture=None,
            billboard=True,
            key=obj_id,
        )
        wx, wz = sim_px_to_world_xz(g.x, g.y)
        terrain_y = get_terrain_height(wx, wz) if _terrain_height_ok() else 0.0

        r._sync_unit_atlas_billboard(
            ent, obj_id, g, "worker", "guard", None,
            col, (GUARD_SCALE_XZ, GUARD_SCALE_Y, 1),
            (wx, terrain_y + GUARD_SCALE_Y * 0.5, wz), sprite_unlit_shader,
        )

        # --- R5: Native Ursina health bar (Agent 09) ---
        # WK62: delegates to ursina_unit_overlays.sync_hp_bar
        _g_hp = int(getattr(g, 'hp', 0) or 0)
        _g_max_hp = int(getattr(g, 'max_hp', 1) or 1)
        sync_hp_bar(ent, _g_hp, _g_max_hp, GUARD_SPEC)

        _ensure_ks_name_label(ent, "_ks_name_label", "Guard", y=GUARD_SPEC.label_y, scale=GUARD_SPEC.label_scale)

        active_ids.add(obj_id)


def sync_snapshot_tax_collector(r: "UrsinaRenderer", snapshot: "SimStateSnapshot", active_ids: set) -> None:
    # Tax Collector — atlas UV billboards (WK59 perf: single shared texture)
    # WK68 R2 (Agent 09): frozen UnitDTO (tax_collector_dto) keyed on the stable
    # dto.entity_id (not id(tc)).
    tc = getattr(snapshot, "tax_collector_dto", None)
    if tc is not None:
        tc_id = tc.entity_id
        if not getattr(tc, "is_alive", True):
            pass
        # WK57 Wave 3: Tax collector is always surface — hide when camera underground
        elif r._camera_active_layer != 0:
            _tc_existing = r._entities.get(tc_id)
            if _tc_existing is not None:
                _tc_existing.enabled = False
                active_ids.add(tc_id)
        else:
            col = color.white
            sx = PEASANT_SCALE_XZ
            sy = PEASANT_SCALE_Y
            ent, obj_id = r._entity_render.get_or_create_entity(
                tc,
                model="quad",
                col=color.white,
                scale=(sx, sy, 1),
                texture=None,
                billboard=True,
                key=tc_id,
            )
            wx, wz = sim_px_to_world_xz(tc.x, tc.y)
            terrain_y = get_terrain_height(wx, wz) if _terrain_height_ok() else 0.0

            r._sync_unit_atlas_billboard(
                ent, obj_id, tc, "worker", "tax_collector", None,
                col, (sx, sy, 1), (wx, terrain_y + sy * 0.5, wz), sprite_unlit_shader,
            )

            _ensure_ks_name_label(ent, "_ks_name_label", "Tax Collector", y=TAX_COLLECTOR_SPEC.label_y, scale=TAX_COLLECTOR_SPEC.label_scale)

            # --- R5: Tax collector gold display (Agent 08) ---
            carried = int(getattr(tc, 'carried_gold', 0) or 0)
            tc_gold_ent = getattr(ent, '_ks_tc_gold', None)
            if carried > 0:
                tc_text = f"${carried}"
                if tc_gold_ent is None:
                    from ursina import Text as UrsinaText
                    tc_gold_ent = UrsinaText(
                        text=tc_text, parent=ent, origin=(0, 0), scale=10,
                        color=color.rgb(1.0, 0.8, 0.2), billboard=True, y=0.35,
                    )
                    _configure_ks_overlay(tc_gold_ent)
                    ent._ks_tc_gold = tc_gold_ent
                else:
                    if tc_gold_ent.text != tc_text:
                        tc_gold_ent.text = tc_text
                    tc_gold_ent.enabled = True
                    _configure_ks_overlay(tc_gold_ent)
            elif tc_gold_ent is not None:
                tc_gold_ent.enabled = False

            active_ids.add(obj_id)


class QuestGiverRenderState(NamedTuple):
    """Frozen plain-data quest-giver render state (WK133 fix, Agent 09).

    Value-copied off the live ``QuestGiver`` at the render boundary
    (``attach_quest_giver_states``) so the renderer never holds a live, mutable
    sim object — same L1 boundary rule as the WK66/WK68 ``*_dtos``.
    """

    giver_id: str
    x: float
    y: float
    is_open: bool
    is_alive: bool


def attach_quest_giver_states(snapshot, engine) -> None:
    """WK133 fix (Agent 09): export quest givers across the render boundary.

    ROOT CAUSE of the WK133 T8 FAIL capture: ``RenderSnapshot`` has no
    quest-giver field and ``SimEngine.build_snapshot`` never exports
    ``self.quest_givers`` — so ``snapshot_quest_giver_states`` (tolerated-absent
    by design) ALWAYS returned ``()`` and neither the NPC billboard nor the "!"
    marker could ever render, even though the sim-side giver existed and
    ``is_open`` was True.

    The sim lane is frozen for this round (digest safety), so the export lives
    HERE, render-side: called by ``ursina_app_frame.run_frame`` immediately
    after ``engine.build_snapshot()``. It value-copies each live giver into a
    frozen :class:`QuestGiverRenderState` and attaches the tuple as
    ``snapshot.quest_givers`` (the exact fallback field
    ``snapshot_quest_giver_states`` already reads; ``object.__setattr__``
    because ``RenderSnapshot`` is a frozen dataclass). No-op — zero per-frame
    cost beyond one getattr — when no givers exist (pre-quest games, the WK67
    digest scenario), and the sim's own ``quest_giver_dtos`` field still wins
    if/when a later wave adds it to ``build_snapshot``.
    """
    sim = getattr(engine, "sim", engine)
    givers = getattr(sim, "quest_givers", None)
    if not givers:
        return
    try:
        states = tuple(
            QuestGiverRenderState(
                giver_id=str(getattr(g, "giver_id", "") or ""),
                x=float(getattr(g, "x", 0.0)),
                y=float(getattr(g, "y", 0.0)),
                is_open=bool(getattr(g, "is_open", False)),
                is_alive=bool(getattr(g, "is_alive", True)),
            )
            for g in givers
        )
        object.__setattr__(snapshot, "quest_givers", states)
    except Exception:
        # Never let a render-boundary nicety kill the frame loop.
        return


def snapshot_quest_giver_states(snapshot) -> tuple:
    """Plain-data quest-giver render states off the snapshot (WK126 T8).

    Reads ``snapshot.quest_giver_dtos`` first (the proper frozen-DTO field once
    the sim exposes it), falling back to ``snapshot.quest_givers``. Both are
    tolerated-absent (``()``), so pre-quest snapshots and the WK67 digest path
    are untouched. Each state needs only: giver_id, x, y, is_open.
    """
    states = getattr(snapshot, "quest_giver_dtos", None)
    if states is None:
        states = getattr(snapshot, "quest_givers", None)
    return tuple(states) if states else ()


def sync_snapshot_quest_givers(r: "UrsinaRenderer", snapshot: "SimStateSnapshot", active_ids: set) -> None:
    # Quest Giver (WK126 T8 + WK133 fix, Agent 09) — classic (non-instanced)
    # Entity billboard per the WK133 PM decision of record, exactly like bounty
    # flags: called from BOTH renderer branches (instanced + legacy). Stationary
    # NPC beside its Herald's Post, rendered via the SAME atlas-UV path as the
    # tax collector (the PM-designated humanoid stand-in sprite — no herald
    # atlas entry yet) + "Herald" name label + the yellow "!" overhead marker
    # that shows only while the giver has an open offer (giver.is_open). Keyed
    # on the stable giver_id (the owning post's entity_id) — never id() of a
    # per-frame state object.
    for qg in snapshot_quest_giver_states(snapshot):
        gid = str(getattr(qg, "giver_id", "") or getattr(qg, "entity_id", "") or "")
        if not gid or not getattr(qg, "is_alive", True):
            continue
        obj_id = f"quest_giver:{gid}"
        # WK57 Wave 3: quest givers are always surface — hide when camera underground.
        if r._camera_active_layer != 0:
            existing = r._entities.get(obj_id)
            if existing is not None:
                existing.enabled = False
                active_ids.add(obj_id)
            continue

        # Tax-collector scale so the stand-in atlas frame keeps its aspect
        # (exactly the sync_snapshot_tax_collector dimensions).
        sx = PEASANT_SCALE_XZ
        sy = PEASANT_SCALE_Y
        ent, obj_id = r._entity_render.get_or_create_entity(
            qg,
            model="quad",
            col=color.white,
            scale=(sx, sy, 1),
            texture=None,
            billboard=True,
            key=obj_id,
        )
        if not getattr(ent, "enabled", True):
            ent.enabled = True
        wx, wz = sim_px_to_world_xz(float(getattr(qg, "x", 0.0)), float(getattr(qg, "y", 0.0)))
        terrain_y = get_terrain_height(wx, wz) if _terrain_height_ok() else 0.0
        # Atlas-UV billboard — identical call shape to the tax collector. The
        # QuestGiverRenderState carries no state/anim fields, so
        # base_clip_from_dto resolves to the looping "idle" clip; the giver is
        # stationary, so after the first frame this is dirty-gated
        # attribute-compare-only work (FPS guardrails).
        r._sync_unit_atlas_billboard(
            ent, obj_id, qg, "worker", "tax_collector", None,
            color.white, (sx, sy, 1), (wx, terrain_y + sy * 0.5, wz), sprite_unlit_shader,
        )

        _ensure_ks_name_label(
            ent, "_ks_name_label", "Herald",
            y=TAX_COLLECTOR_SPEC.label_y, scale=TAX_COLLECTOR_SPEC.label_scale,
        )
        # Yellow "!" — lazily created once, .enabled-toggled per frame, freed by
        # free_entity_overlays via _OVERLAY_CHILD_ATTRS on giver removal.
        sync_quest_giver_marker(ent, bool(getattr(qg, "is_open", False)))

        active_ids.add(obj_id)
