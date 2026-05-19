"""WK58 Wave 8 / Section 4.C — Panda3D ``GeoMipTerrain`` LOD path.

The default WK53 terrain path builds a custom 62,500-vert indexed Mesh and
uploads it once. That works fine for the default camera, but on zoom-out the
fragment shader covers more of the screen and the lack of distance-LOD turns
into a fill-rate / cull cost the player feels as a frame-rate drop.

When ``KINGDOM_URSINA_GEOMIPTERRAIN=1`` is set, this module builds a
``GeoMipTerrain`` from the SAME ``world.heightmap`` array that the custom Mesh
consumes. The two paths are mutually exclusive (one or the other becomes the
display mesh) and ``get_terrain_height()`` continues to read from the
``terrain_height`` module's source-of-truth Perlin array — so prop/unit/building
Y-placement is invariant across the env flag.

Design notes (see WK58 Section 4.C):

- GeoMipTerrain wants a power-of-2-plus-one heightfield image (e.g. 257, 513).
  The world heightmap is ``(2*tw+1) x (2*th+1)`` — for a 250-tile map that is
  501 grid samples per side. We resample to the nearest ``2^n + 1`` that fits
  (typically 513) so block_size powers of 2 carve the grid evenly. Resampling
  is bilinear and only affects the displayed mesh — heights read by
  ``get_terrain_height`` come from the unresampled Perlin source.

- Castle flat is baked into the source heightmap by ``World.generate_heightmap``
  BEFORE we read it, so the GeoMipTerrain image inherits the flat plateau for
  free — no extra carving needed on the image side.

- Fog-of-war shader is the same ``terrain_fog_shader`` the WK53 path uses.
  GeoMipTerrain returns a NodePath we set the shader on; ``ensure_fog_overlay``
  uploads the fog texture as a shader uniform via ``set_shader_input`` exactly
  as it does for the custom Mesh.

- LOD focal point is ``base.camera`` so distance bands tighten as the player
  zooms out. ``terrain.update()`` must be called once per frame from
  ``UrsinaRenderer.update``.

This module never touches ``terrain_height`` state; it just reads the array.
"""

from __future__ import annotations

import math
import os
from typing import Any, Optional

from ursina import Entity, Vec2, color
from ursina.shaders import unlit_shader

from game.graphics.ursina_coords import SCALE
from game.graphics.terrain_fog_shader import terrain_fog_shader


# Env var contract -----------------------------------------------------------

GEOMIP_ENV_VAR = "KINGDOM_URSINA_GEOMIPTERRAIN"


def geomipterrain_enabled() -> bool:
    """Return ``True`` if the GeoMipTerrain display path is enabled.

    Default is ``False`` — the custom Mesh path stays primary until visual +
    perf parity is screenshot-confirmed.
    """
    return os.environ.get(GEOMIP_ENV_VAR, "0").strip() == "1"


# Power-of-two helpers -------------------------------------------------------

def _nearest_pow2_plus_one(n: int) -> int:
    """Return the smallest ``2^k + 1`` that is >= ``n`` (clamped at 1025).

    GeoMipTerrain accepts arbitrary image sizes but its block-size LOD only
    bands cleanly when both axes are ``2^k + 1`` and the block size divides
    ``(size - 1)``. For a 501-sample input we pick 513 (= 512 + 1, so block
    sizes 32 and 64 both divide 512 evenly).
    """
    n = max(33, int(n))  # at least 32 + 1
    k = 5  # 2^5 + 1 = 33
    while (1 << k) + 1 < n:
        k += 1
        if k > 10:  # cap at 2^10 + 1 = 1025 (safety net for 500-tile maps)
            break
    return (1 << k) + 1


def _bilinear_sample(hmap: list[list[float]], gw: int, gh: int,
                     fx: float, fy: float) -> float:
    """Bilinearly sample ``hmap[gz][gx]`` at float grid coords ``(fx, fy)``.

    Out-of-range coordinates clamp to the grid edge. ``fy`` is the row index
    (Z direction), ``fx`` is the column index (X direction).
    """
    fx = max(0.0, min(float(gw - 1), float(fx)))
    fy = max(0.0, min(float(gh - 1), float(fy)))
    x0 = int(fx)
    y0 = int(fy)
    x1 = min(x0 + 1, gw - 1)
    y1 = min(y0 + 1, gh - 1)
    tx = fx - x0
    ty = fy - y0
    h00 = hmap[y0][x0]
    h10 = hmap[y0][x1]
    h01 = hmap[y1][x0]
    h11 = hmap[y1][x1]
    h0 = h00 + (h10 - h00) * tx
    h1 = h01 + (h11 - h01) * tx
    return h0 + (h1 - h0) * ty


# Heightfield image ----------------------------------------------------------

def build_heightfield_image(
    hmap: list[list[float]],
    gw: int,
    gh: int,
    height_scale: float,
    img_size: int,
):
    """Build a grayscale ``PNMImage`` heightfield for GeoMipTerrain.

    ``hmap[gz][gx]`` is the raw Perlin array (already including castle-flat
    plateau and zone elevation biases — see ``World.generate_heightmap``).
    Pixel values are in [0, 1] normalised against ``height_scale``; the final
    world Y elevation is recovered by GeoMipTerrain via ``set_factor``.

    Args:
        hmap:         2D float array (``[gz][gx]``) of heights, range
                      ``[0, height_scale]``.
        gw, gh:       grid dimensions of the source heightmap.
        height_scale: ``TERRAIN_HEIGHT_SCALE`` — divides pixel values for the
                      [0,1] storage range. GeoMipTerrain will multiply back.
        img_size:     output image edge in pixels (must be ``2^k + 1``).

    Returns:
        ``PNMImage`` of size ``(img_size, img_size)`` in 1-channel grayscale.
    """
    from panda3d.core import PNMImage

    img = PNMImage(img_size, img_size, 1)  # 1 channel = grayscale
    scale = max(1e-6, float(height_scale))

    # Map image pixel (px, py) -> grid float coord (fx, fy).
    # Image px=0 corresponds to grid x=0; px=img_size-1 -> grid x=gw-1.
    sx = float(gw - 1) / float(img_size - 1)
    sy = float(gh - 1) / float(img_size - 1)

    for py in range(img_size):
        fy = float(py) * sy
        for px in range(img_size):
            fx = float(px) * sx
            h = _bilinear_sample(hmap, gw, gh, fx, fy)
            v = max(0.0, min(1.0, h / scale))
            img.set_gray(px, py, v)
    return img


# Terrain builder ------------------------------------------------------------

class GeoMipTerrainHandle:
    """Holder for the GeoMipTerrain object + its root NodePath + per-frame hook.

    The ``UrsinaRenderer`` stashes one of these on
    ``self._geomip_terrain_handle`` while ``KINGDOM_URSINA_GEOMIPTERRAIN=1``.
    Its only public methods are ``update_lod()`` (called once per frame from
    ``UrsinaRenderer.update``) and ``destroy()`` (called when the terrain is
    rebuilt).
    """

    def __init__(
        self,
        terrain,
        wrap_entity: Entity,
        block_size: int,
        near: float,
        far: float,
        img_size: int,
        height_scale: float,
        world_w: float,
        world_d: float,
    ) -> None:
        self.terrain = terrain
        self.wrap_entity = wrap_entity
        self.block_size = int(block_size)
        self.near = float(near)
        self.far = float(far)
        self.img_size = int(img_size)
        self.height_scale = float(height_scale)
        self.world_w = float(world_w)
        self.world_d = float(world_d)
        self._destroyed = False

    def update_lod(self) -> None:
        """Refresh LOD blocks against the current camera position.

        Cheap (a few microseconds when no blocks change). Safe to call every
        frame; GeoMipTerrain internally early-outs when ``is_dirty()`` is False.
        """
        if self._destroyed or self.terrain is None:
            return
        try:
            self.terrain.update()
        except Exception:
            pass

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        try:
            root_np = self.terrain.get_root()
            root_np.remove_node()
        except Exception:
            pass
        try:
            import ursina as _u
            _u.destroy(self.wrap_entity)
        except Exception:
            pass
        self.terrain = None
        self.wrap_entity = None


def build_geomip_terrain(
    parent_entity: Entity,
    hmap: list[list[float]],
    gw: int,
    gh: int,
    tw: int,
    th: int,
    world_w: float,
    world_d: float,
    height_scale: float,
    tiles_per_repeat: float = 2.0,
) -> Optional[GeoMipTerrainHandle]:
    """Construct a Panda3D ``GeoMipTerrain`` from the world heightmap.

    The returned handle owns the GeoMipTerrain instance and the wrapper Ursina
    Entity that holds the fog shader uniforms (so ``ensure_fog_overlay`` can
    target the same ``set_shader_input`` API as the custom Mesh path).

    Args:
        parent_entity: terrain root Entity (``terrain_3d_root``) — the wrapper
                       Entity reparents under this so destroy semantics match
                       the custom Mesh path.
        hmap:          ``world.heightmap`` 2D array.
        gw, gh:        ``world.heightmap_grid_w/h``.
        tw, th:        map size in tiles (``world.width``, ``world.height``).
        world_w/d:     map extent in world units along X / Z axes.
        height_scale:  ``config.TERRAIN_HEIGHT_SCALE``.
        tiles_per_repeat: grass texture tiling — must match the custom Mesh
                          path so the fog UV transform is consistent.

    Returns:
        ``GeoMipTerrainHandle`` on success, or ``None`` if GeoMipTerrain or
        PNMImage are unavailable in this Panda3D build.
    """
    # Import inside the function so module load doesn't drag Panda3D internals
    # into headless test paths that don't need GeoMipTerrain.
    try:
        from panda3d.core import (
            GeoMipTerrain,
            Filename,
            SamplerState,
            Texture,
            TextureStage,
        )
    except ImportError:
        return None

    # Resample the heightmap to a power-of-two-plus-one image so block-size
    # powers of 2 divide ``(img_size - 1)`` cleanly. Falls back to 513 for the
    # standard 250-tile map (501 source samples -> 513 pixels).
    img_size = _nearest_pow2_plus_one(max(gw, gh))
    img = build_heightfield_image(hmap, gw, gh, height_scale, img_size)

    # Build the terrain
    terrain = GeoMipTerrain("kingdom_geomip_terrain")
    terrain.set_heightfield(img)
    # block_size 32 is the Panda3D documented sweet spot for sub-1000-pixel
    # heightfields. (img_size - 1) must be a multiple — it is (512 % 32 == 0).
    terrain.set_block_size(32)
    # Near/far govern when LOD changes happen relative to the focal point. The
    # default playtest cam sits ~70 world units above terrain; we want full
    # detail near the camera and coarser away from it. Values are in world
    # units along terrain X/Z.
    terrain.set_near(20.0)
    terrain.set_far(120.0)
    # Min level 0 = full detail; max level is inferred from block_size.
    terrain.set_min_level(0)
    # Auto-flatten 'strong' folds dead state at build time but rebuilds on
    # update() — we want 'medium' so the per-frame update() is cheap.
    # AFMOff is fine for our case (single GeoMipTerrain, no batching).
    terrain.set_auto_flatten(GeoMipTerrain.AFMOff)

    # Focal point: Panda3D's camera lives at ``base.camera``. We don't have
    # ``base`` until the Ursina app boots, but at this point in build_3d_terrain
    # it exists; pull it lazily via the builtin scope.
    try:
        import builtins
        _base = getattr(builtins, "base", None)
        if _base is not None and getattr(_base, "camera", None) is not None:
            terrain.set_focal_point(_base.camera)
    except Exception:
        pass

    terrain.generate()

    # Reparent the GeoMipTerrain root NodePath under an Ursina Entity so the
    # shader-input pipeline (terrain_fog_shader, fog_uv_*, fog_texture) lines
    # up with what ``ensure_fog_overlay`` already does for the custom Mesh.
    #
    # We use a thin Entity that owns no model of its own; the GeoMipTerrain
    # root NodePath is reparented under it via ``reparent_to``. The Entity's
    # shader and shader inputs apply to all NodePaths beneath it.
    wrap = Entity(
        parent=parent_entity,
        name="geomip_terrain_wrap",
        position=(0.0, 0.0, 0.0),
        collision=False,
        add_to_scene_entities=False,
    )

    try:
        root_np = terrain.get_root()
        # The image's (px=0, py=0) sample is at world (X=0, Z=0). The custom
        # mesh path lays X=0..w_world and Z=-(d_world)..0 (negative Z, see
        # build_3d_terrain). GeoMipTerrain's default coordinate system places
        # the terrain at root, with X in [0, img_size-1] and Y in
        # [0, img_size-1] (Panda3D Y is the second axis of the image).
        #
        # We need the displayed terrain to span the SAME world rectangle the
        # custom Mesh used:
        #   X axis: 0 .. w_world
        #   Z axis: -d_world .. 0
        #   Y axis (vertical): heightfield_pixel * factor
        #
        # GeoMipTerrain in Panda3D uses (X, Y, Z) where Z is vertical, so we
        # need a coordinate swap to match Ursina/Kingdom convention (Y vertical,
        # Z lateral). The cleanest swap is a rotation: rotate the root NodePath
        # -90° around X so terrain Z (depth) maps to Ursina -Z (back of map),
        # and terrain Y (height pixels) maps to Ursina +Y.
        sx = float(world_w) / float(img_size - 1)
        sy = float(height_scale)
        sz = float(world_d) / float(img_size - 1)
        # set_factor multiplies the [0,1] pixel value to give world-unit height.
        terrain.set_factor(sy)
        # Scale the X/Z plane to match the map extent. Note: we set per-axis
        # scale on the NodePath since GeoMipTerrain itself is unit-spaced.
        root_np.set_scale(sx, sz, 1.0)
        # Rotate so the terrain lies on the Ursina XZ plane with Y up.
        # GeoMipTerrain default: Z-up; Ursina: Y-up. Rotate -90 around X.
        root_np.set_hpr(0.0, -90.0, 0.0)
        # Translate the (X=0, Z=0) corner of the terrain to (0, 0, -world_d)
        # in Ursina world space (matches custom Mesh's min-Z corner).
        root_np.set_pos(0.0, 0.0, -float(world_d))
        root_np.reparent_to(wrap)
    except Exception:
        # If anything in the NodePath wiring fails we destroy the wrap and
        # bail; ``build_3d_terrain`` will fall through to its existing
        # custom-Mesh path (env=1 silently degrades to env=0).
        try:
            import ursina as _u
            _u.destroy(wrap)
        except Exception:
            pass
        return None

    # Apply the WK53 fog shader + grass texture. The wrap Entity is just a
    # parent transform; GeoMipTerrain's root NodePath is reparented under it
    # and the shader / texture / shader-inputs need to apply on the root NP
    # itself (Ursina's Entity.shader / Entity.texture only set state on the
    # Entity's own NodePath — render-state inheritance into GeoMipTerrain
    # children is not reliable when GeoMipTerrain installs its own per-block
    # RenderState during ``generate()``). So we drop down to Panda3D and set
    # shader + texture + uniforms directly on ``terrain.get_root()``.
    try:
        from panda3d.core import TextureStage as _TS, Filename as _Filename
        # Ursina's terrain_fog_shader is a thin wrapper around Panda3D's
        # ``Shader``; the actual Panda3D shader object is on ``.value``
        # (Ursina stores it lazily, so we trigger compilation by reading it
        # on the wrap first).
        wrap.shader = terrain_fog_shader  # forces shader load
        try:
            _p3d_shader = terrain_fog_shader._shader  # set after compile
        except AttributeError:
            _p3d_shader = None
        # Fallback: read via the wrap Entity which Ursina populated post-load.
        if _p3d_shader is None:
            try:
                _p3d_shader = wrap.shader._shader
            except Exception:
                _p3d_shader = None
        root_np = terrain.get_root()
        if _p3d_shader is not None:
            try:
                root_np.set_shader(_p3d_shader)
            except Exception:
                pass
        # Shader inputs — must be set on the root NodePath so the GeoMipTerrain
        # block subnodes inherit them.
        tex_repeats_x = float(tw) / float(tiles_per_repeat) if tw > 0 else 1.0
        tex_repeats_y = float(th) / float(tiles_per_repeat) if th > 0 else 1.0
        try:
            root_np.set_shader_input("texture_scale", Vec2(tex_repeats_x, tex_repeats_y))
            root_np.set_shader_input("texture_offset", Vec2(0.0, 0.0))
            # fog_uv: GeoMipTerrain auto UVs span [0, 1] across the heightfield
            # already; the fog texture's row layout flips N/S so we negate Y
            # and offset by 1.
            root_np.set_shader_input("fog_uv_scale", Vec2(1.0, -1.0))
            root_np.set_shader_input("fog_uv_offset", Vec2(0.0, 1.0))
        except Exception:
            pass
    except Exception:
        pass

    # Grass albedo texture — load via the SAME PIL/Ursina loader the custom
    # Mesh path uses, then bind the underlying Panda3D Texture directly on
    # the GeoMipTerrain root NodePath. Without a valid p3d_Texture0 sample
    # the fog shader multiplies fog colour by white and the terrain reads as
    # a pale flat shape.
    try:
        from ursina import Texture as _UrsTexture
        from PIL import Image as _PILImage
        from game.graphics.ursina_environment import PROJECT_ROOT
        grass_path = (
            PROJECT_ROOT
            / "assets"
            / "models"
            / "Models"
            / "Textures"
            / "floor_ground_grass.png"
        )
        if grass_path.is_file():
            grass_img = _PILImage.open(grass_path).convert("RGBA")
            grass_tex = _UrsTexture(grass_img, filtering=None)
            # Set on wrap so ``ensure_fog_overlay`` can still inspect ``texture``.
            wrap.texture = grass_tex
            # Bind directly on the GeoMipTerrain root NodePath. Try the Ursina
            # Texture's internal Panda3D Texture object first; fall back to
            # the Ursina Texture itself which Panda3D usually accepts.
            try:
                _p3d_tex = getattr(grass_tex, "_texture", None) or grass_tex
                terrain.get_root().set_texture(_p3d_tex, 1)
            except Exception:
                try:
                    terrain.get_root().set_texture(grass_tex, 1)
                except Exception:
                    pass
    except Exception:
        pass

    return GeoMipTerrainHandle(
        terrain=terrain,
        wrap_entity=wrap,
        block_size=32,
        near=20.0,
        far=120.0,
        img_size=img_size,
        height_scale=height_scale,
        world_w=world_w,
        world_d=world_d,
    )
