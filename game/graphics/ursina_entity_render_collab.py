"""Billboard + 3D building entity creation/sync (WK41 R2 collaborator; no UrsinaRenderer import)."""

from __future__ import annotations

from pathlib import Path

import config
from ursina import Entity, Vec3, color

from game.graphics.ursina_prefabs import (
    _PREFAB_FIT_INSET,
    _building_3d_origin_y,
    _footprint_scale_3d,
    _load_prefab_instance,
)
from game.graphics.ursina_sprite_unlit_shader import sprite_unlit_shader
from ursina.shaders import lit_with_shadows_shader, unlit_shader

class UrsinaEntityRenderCollab:
    """Owns billboard / mesh entity helpers that mutate ``renderer._entities``."""

    __slots__ = ("_r",)

    def __init__(self, renderer: "UrsinaRenderer") -> None:
        self._r = renderer

    def get_or_create_entity(
        self,
        sim_obj,
        *,
        model="cube",
        col=color.white,
        scale=(1, 1, 1),
        rotation=(0, 0, 0),
        texture=None,
        billboard=False,
    ):
        obj_id = id(sim_obj)
        ents = self._r._entities
        if obj_id not in ents:
            kw = dict(
                model=model,
                color=col,
                scale=scale,
                rotation=rotation,
                billboard=billboard,
            )
            if texture is not None:
                kw["texture"] = texture
            ent = Entity(**kw)
            if billboard:
                UrsinaEntityRenderCollab.apply_pixel_billboard_settings(ent)
                ent._ks_billboard_configured = True
            ents[obj_id] = ent
        return ents[obj_id], obj_id

    def get_or_create_3d_building_entity(self, sim_obj, model_path: str, col) -> tuple:
        import ursina as u

        obj_id = id(sim_obj)
        ents = self._r._entities
        if obj_id in ents:
            ent = ents[obj_id]
            if getattr(ent, "_ks_building_mode", None) != "mesh_3d":
                u.destroy(ent)
                del ents[obj_id]
            elif getattr(ent, "_ks_mesh_model_path", None) != model_path:
                u.destroy(ent)
                del ents[obj_id]

        if obj_id not in ents:
            ent = Entity(
                model=model_path,
                color=col,
                collider=None,
                double_sided=True,
            )
            ent._ks_building_mode = "mesh_3d"
            ent._ks_mesh_model_path = model_path
            ent._ks_billboard_configured = False
            UrsinaEntityRenderCollab.apply_lit_3d_building_settings(ent)
            ents[obj_id] = ent
        return ents[obj_id], obj_id

    def get_or_create_prefab_building_entity(self, sim_obj, prefab_path: Path, col) -> tuple:
        import ursina as u

        obj_id = id(sim_obj)
        ents = self._r._entities
        if obj_id in ents:
            ent = ents[obj_id]
            if getattr(ent, "_ks_building_mode", None) != "prefab" or getattr(
                ent, "_ks_prefab_path", None
            ) != str(prefab_path):
                u.destroy(ent)
                del ents[obj_id]

        if obj_id not in ents:
            root = _load_prefab_instance(prefab_path, Vec3(0, 0, 0))
            root.color = col
            root._ks_building_mode = "prefab"
            root._ks_prefab_path = str(prefab_path)
            root.collision = False
            ents[obj_id] = root
        return ents[obj_id], obj_id

    @staticmethod
    def apply_pixel_billboard_settings(ent: Entity) -> None:
        from panda3d.core import TransparencyAttrib

        ent.shader = sprite_unlit_shader
        ent.double_sided = True
        ent.setTransparency(TransparencyAttrib.M_alpha)
        ent.set_depth_write(False)
        ent.render_queue = 1
        ent.hide(0b0001)

    @staticmethod
    def sync_inside_hero_draw_layer(ent: Entity, is_inside: bool) -> None:
        want = bool(is_inside)
        if getattr(ent, "_ks_inside_layer", None) is want:
            return
        ent._ks_inside_layer = want
        if want:
            ent.render_queue = 3
            ent.set_depth_test(False)
        else:
            ent.render_queue = 1
            ent.set_depth_test(True)

    @staticmethod
    def set_texture_if_changed(ent: Entity, tex) -> None:
        if getattr(ent, "_texture", None) is tex:
            return
        ent.texture = tex

    @staticmethod
    def set_shader_if_changed(ent: Entity, sh) -> None:
        if getattr(ent, "_shader", None) is sh:
            return
        ent.shader = sh

    @staticmethod
    def sync_billboard_entity(
        ent: Entity,
        *,
        tex,
        tint_col,
        scale_xyz: tuple[float, float, float],
        pos_xyz: tuple[float, float, float],
        shader,
        tint_textured: bool = False,
    ) -> None:
        UrsinaEntityRenderCollab.set_texture_if_changed(ent, tex)
        # Most sprite sheets should render with their native colors (white multiplier).
        # Only a few entities (e.g., BuilderPeasant) intentionally use a tint multiplier.
        target_color = tint_col if (tint_textured and tex is not None) else (color.white if tex is not None else tint_col)
        if getattr(ent, "_ks_last_color", None) != target_color:
            ent.color = target_color
            ent._ks_last_color = target_color
        if getattr(ent, "_ks_last_scale", None) != scale_xyz:
            ent.scale = scale_xyz
            ent._ks_last_scale = scale_xyz
        if not getattr(ent, "_ks_billboard_configured", False):
            ent.billboard = True
            UrsinaEntityRenderCollab.apply_pixel_billboard_settings(ent)
            ent._ks_billboard_configured = True
        UrsinaEntityRenderCollab.set_shader_if_changed(ent, shader)
        ent.position = pos_xyz

    @staticmethod
    def apply_lit_3d_building_settings(ent: Entity) -> None:
        from panda3d.core import TransparencyAttrib

        ent.billboard = False
        _shadows = bool(getattr(config, "URSINA_DIRECTIONAL_SHADOWS", False))
        ent.shader = lit_with_shadows_shader if _shadows else unlit_shader
        ent.double_sided = True
        ent.render_queue = 1
        ent.collision = False
        try:
            ent.setTransparency(TransparencyAttrib.M_none)
        except Exception:
            pass
        ent.set_depth_test(True)
        ent.set_depth_write(True)

    @staticmethod
    def sync_3d_building_entity(
        ent: Entity,
        *,
        mesh_kind: str,
        model_path: str,
        wx: float,
        wz: float,
        fx: float,
        fz: float,
        hy: float,
        tint_col,
        state: str,
    ) -> None:
        UrsinaEntityRenderCollab.set_texture_if_changed(ent, None)
        scale_xyz = _footprint_scale_3d(mesh_kind, fx, fz, hy)
        if getattr(ent, "_ks_last_scale", None) != scale_xyz:
            ent.scale = scale_xyz
            ent._ks_last_scale = scale_xyz
        _sx, sy, _sz = scale_xyz
        oy = _building_3d_origin_y(model_path, sy)
        ent.position = (wx, oy, wz)
        _shadows = bool(getattr(config, "URSINA_DIRECTIONAL_SHADOWS", False))
        want_shader = lit_with_shadows_shader if _shadows else unlit_shader
        UrsinaEntityRenderCollab.set_shader_if_changed(ent, want_shader)
        if state == "damaged":
            ent.color = color.rgb(0.78, 0.42, 0.42)
        elif state == "construction":
            ent.color = color.rgb(0.72, 0.72, 0.65)
        else:
            ent.color = tint_col

    @staticmethod
    def sync_prefab_building_entity(
        ent: Entity,
        *,
        mesh_kind: str,
        wx: float,
        wz: float,
        fx: float,
        fz: float,
        hy: float,
        tint_col,
        state: str,
    ) -> None:
        UrsinaEntityRenderCollab.set_texture_if_changed(ent, None)
        authored_w, authored_d = getattr(ent, "_ks_prefab_authored_ft", (1.0, 1.0))
        spread_x, spread_z = getattr(ent, "_ks_prefab_xz_spread", (0.0, 0.0))
        effective_w = max(float(authored_w), float(spread_x) + 1.0)
        effective_d = max(float(authored_d), float(spread_z) + 1.0)
        scale_x = (fx / max(effective_w, 1e-6)) * _PREFAB_FIT_INSET
        scale_z = (fz / max(effective_d, 1e-6)) * _PREFAB_FIT_INSET
        scale_xyz = (scale_x, 1.0, scale_z)
        if getattr(ent, "_ks_last_scale", None) != scale_xyz:
            ent.scale = scale_xyz
            ent._ks_last_scale = scale_xyz
        ga = float(getattr(ent, "_ks_ground_anchor_y", 0.0))
        ent.position = (wx, ga, wz)
        if state == "damaged":
            ent.color = color.rgb(0.78, 0.42, 0.42)
        elif state == "construction":
            ent.color = color.rgb(0.72, 0.72, 0.65)
        else:
            ent.color = tint_col
