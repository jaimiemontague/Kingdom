"""Startup prewarm for cold first-spawn assets (Mythos S2: unit-prewarm-extension).

Extends the WK122 ``prewarm_building_prefab_models`` pattern (ursina_prefabs.py)
— which covers ONLY building piece meshes, including every construction-stage
variant — to the remaining one-time lazy loads that hitch the first gameplay
frames (.cursor/plans/mythos_lag_fix_candidates.json, rank 15):

* the 2048x2048 unit sprite atlas (every hero class / enemy type / worker frame
  plus the arrow VFX frame) builds lazily on the FIRST unit render — measured
  269 ms CPU + ~16 MB GPU upload inside that frame
  (unit_atlas.py via ursina_renderer.py:426);
* the projectile/magic/heal billboard textures generate on the first volley
  (ursina_misc_props_sync.py:59-73);
* the first ``Text`` loads the font (314 ms worst first-ever measured) and
  renders the first glyph pages; the first billboard/overlay states trigger
  driver GLSL compiles (5-50 ms each on iGPUs);
* when ``KINGDOM_URSINA_INSTANCING=1``, the instanced unit renderer's shaders /
  buffer textures / geom nodes warm on its first update.

Strategy: build each asset through the SAME code paths / cache keys the
per-frame sync uses (so the in-game lookups are guaranteed cache hits), create
one hidden warm bundle (unit billboard + HP-bar quads + name/gold Text) that
exercises the exact render states units use, push it through
``NodePath.prepare_scene(gsg)`` — Panda3D's canonical no-draw warm-up that
uploads textures / prepares shaders & vertex buffers WITHOUT rendering a frame
(so nothing can visibly flash) — then destroy the bundle (orphan-free via
``free_entity_overlays``, the WK123 C1 contract).

Behavior-preserving: identical assets, just created at load time instead of
mid-play. Bounded: the candidate cites ~0.3-0.5 s of startup; every stage is
individually try/except-guarded so a failure (e.g. headless, no GSG) never
blocks startup.
"""
from __future__ import annotations

import os
import time


def prewarm_unit_spawn_assets(renderer=None, base=None) -> dict:
    """Warm the cold first-spawn assets at startup. Returns per-stage ms timings.

    ``renderer`` (UrsinaRenderer, optional): receives the pre-built VFX textures
    (``_projectile_tex``/``_magic_tex``/``_heal_tex`` — exactly what
    ``sync_snapshot_projectiles`` would lazily assign on the first volley) and,
    under ``KINGDOM_URSINA_INSTANCING=1``, the pre-initialized
    ``_instanced_unit_renderer``.
    ``base`` (the Ursina/ShowBase app, optional): supplies the GSG for
    ``prepare_scene`` GPU uploads; without it the CPU-side warm still runs.
    """
    timings: dict = {}
    t_total = time.perf_counter()

    # ------------------------------------------------------------------
    # (a) Unit sprite atlas — covers every unit sprite texture per
    # hero class / enemy type / worker type (they are all packed into the one
    # atlas consumed by BOTH the legacy billboard path and the instanced path).
    # ------------------------------------------------------------------
    atlas_tex = None
    frame_uv = None
    t0 = time.perf_counter()
    try:
        from game.graphics.unit_atlas import ATLAS_SIZE, FRAME_SIZE, UnitAtlasBuilder

        atlas = UnitAtlasBuilder.get()  # builds the 2048x2048 surface (the 269 ms CPU cost)
        atlas_tex = atlas.get_ursina_texture()  # creates the GPU-side Texture object
        frame_uv = (FRAME_SIZE / ATLAS_SIZE, FRAME_SIZE / ATLAS_SIZE)
        timings["unit_atlas_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
    except Exception:
        timings["unit_atlas_ms"] = -1.0

    # ------------------------------------------------------------------
    # (b) Projectile VFX billboard textures (arrow / magic / heal) with the
    # EXACT cache keys sync_snapshot_projectiles uses, then pre-assign them to
    # the renderer attrs its lazy branch would set on the first volley.
    # ------------------------------------------------------------------
    vfx_textures = []
    t0 = time.perf_counter()
    try:
        from game.graphics.terrain_texture_bridge import TerrainTextureBridge
        from game.graphics.vfx import (
            get_heal_billboard_surface,
            get_magic_billboard_surface,
            get_projectile_billboard_surface,
        )

        arrow_tex = TerrainTextureBridge.surface_to_texture(
            get_projectile_billboard_surface(),
            cache_key=("ursina", "projectile_arrow_billboard_v1"),
        )
        magic_tex = TerrainTextureBridge.surface_to_texture(
            get_magic_billboard_surface(),
            cache_key=("ursina", "projectile_magic_billboard_v1"),
        )
        heal_tex = TerrainTextureBridge.surface_to_texture(
            get_heal_billboard_surface(),
            cache_key=("ursina", "projectile_heal_billboard_v1"),
        )
        vfx_textures = [t for t in (arrow_tex, magic_tex, heal_tex) if t is not None]
        if renderer is not None:
            # Identical objects to what the first volley's lazy branch would
            # create (same bridge cache keys) — it now finds them pre-set.
            if getattr(renderer, "_projectile_tex", None) is None:
                renderer._projectile_tex = arrow_tex
            if getattr(renderer, "_magic_tex", None) is None:
                renderer._magic_tex = magic_tex
            if getattr(renderer, "_heal_tex", None) is None:
                renderer._heal_tex = heal_tex
        timings["vfx_textures_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
    except Exception:
        timings["vfx_textures_ms"] = -1.0

    # ------------------------------------------------------------------
    # (c) Hidden warm bundle: one unit-style billboard (atlas texture + sprite
    # shader + transparency/depth states) + real HP-bar quads + real name/gold
    # Text labels (font load + glyph pages + text shader + overlay bin states),
    # plus one tiny quad per VFX texture. Built through the SAME helpers the
    # live renderer uses so the warmed GL state objects match exactly.
    # ------------------------------------------------------------------
    warm_roots = []
    t0 = time.perf_counter()
    try:
        from ursina import Entity, color

        from game.graphics.ursina_entity_render_collab import UrsinaEntityRenderCollab
        from game.graphics.ursina_unit_overlays import (
            ensure_ks_name_label,
            sync_hero_gold_label,
            sync_hp_bar,
        )
        from game.graphics.visual_specs import HERO_SPEC

        # Tiny + far below the terrain: even if a frame were rendered before the
        # bundle is destroyed, nothing is visible. prepare_scene ignores position.
        _hidden = dict(scale=(1e-3, 1e-3, 1), position=(0.0, -1000.0, 0.0))

        ent = Entity(model="quad", color=color.white, billboard=True, **_hidden)
        UrsinaEntityRenderCollab.apply_pixel_billboard_settings(ent)
        ent._ks_billboard_configured = True
        if atlas_tex is not None and frame_uv is not None:
            ent.texture = atlas_tex  # forces the 16 MB atlas into the warmed state
            ent.texture_scale = frame_uv
        sync_hp_bar(ent, hp=80, max_hp=100, spec=HERO_SPEC)
        ensure_ks_name_label(
            ent, "_ks_name_label", "Aa", y=HERO_SPEC.label_y, scale=HERO_SPEC.label_scale
        )
        sync_hero_gold_label(ent, gold=9, taxed_gold=0)
        warm_roots.append(ent)

        for tex in vfx_textures:
            q = Entity(model="quad", color=color.white, texture=tex, billboard=True, **_hidden)
            UrsinaEntityRenderCollab.apply_pixel_billboard_settings(q)
            q._ks_billboard_configured = True
            warm_roots.append(q)
        timings["warm_bundle_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
    except Exception:
        timings["warm_bundle_ms"] = -1.0

    # ------------------------------------------------------------------
    # GPU prepare: upload textures / prepare shaders + vertex buffers for the
    # warm bundle subtrees on the real GSG, WITHOUT rendering a frame.
    # ------------------------------------------------------------------
    gsg = None
    try:
        win = getattr(base, "win", None) if base is not None else None
        if win is not None:
            gsg = win.getGsg()
    except Exception:
        gsg = None
    t0 = time.perf_counter()
    if gsg is not None:
        for np_ in warm_roots:
            try:
                np_.prepare_scene(gsg)
            except Exception:
                pass
        timings["prepare_scene_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
    else:
        timings["prepare_scene_ms"] = -1.0

    # ------------------------------------------------------------------
    # (d) Instanced unit renderer (opt-in path only): pre-build its buffer
    # textures / instanced geoms / shaders and hand the instance to the
    # renderer so its first update() reuses it instead of cold-constructing.
    # Geoms sit at instance_count=0 — zero draw, invisible.
    # ------------------------------------------------------------------
    if os.environ.get("KINGDOM_URSINA_INSTANCING", "0") == "1" and renderer is not None:
        t0 = time.perf_counter()
        try:
            if not hasattr(renderer, "_instanced_unit_renderer"):
                from game.graphics.instanced_unit_renderer import InstancedUnitRenderer

                inst = InstancedUnitRenderer()
                inst._ensure_initialized()
                if gsg is not None:
                    for np_ in (
                        inst._geom_node_outside,
                        inst._geom_node_inside,
                        inst._shadow_geom_node,
                    ):
                        if np_ is not None:
                            try:
                                np_.prepare_scene(gsg)
                            except Exception:
                                pass
                renderer._instanced_unit_renderer = inst
            timings["instanced_renderer_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
        except Exception:
            timings["instanced_renderer_ms"] = -1.0

    # ------------------------------------------------------------------
    # Tear the warm bundle down orphan-free (WK123 C1 contract: overlay/child
    # sweep BEFORE destroying the parent so nothing lingers in scene.entities).
    # ------------------------------------------------------------------
    try:
        import ursina as _u

        from game.graphics.ursina_unit_overlays import free_entity_overlays

        for np_ in warm_roots:
            try:
                free_entity_overlays(np_)
            except Exception:
                pass
            try:
                _u.destroy(np_)
            except Exception:
                pass
    except Exception:
        pass

    timings["total_ms"] = round((time.perf_counter() - t_total) * 1000.0, 1)
    return timings
