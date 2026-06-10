"""Instanced HP-bar shader (Mythos S6 ``inst-hp-bars``).

ONE camera-facing quad, hardware-instanced for every unit with hp>0, replaces
the legacy two-quad-per-unit Entity HP bar (``ursina_unit_overlays.sync_hp_bar``,
~144 scene nodes at the gate scenario) with a single draw call.

Per-instance data (2 RGBA32F texels in a buffer texture):

* texel0 = (world_x, world_y, world_z, fill_fraction) — the unit's BLENDED
  billboard-center position (same array that feeds the unit instance buffer,
  so bars never desync from sprites) + hp/max_hp;
* texel1 = (bar_w, bar_h, bar_y_offset, 0) in WORLD units — the legacy
  parent-local ``UnitVisualSpec`` dims pre-multiplied by the unit billboard
  scale on the CPU (legacy bars are children of a scaled billboard parent).

The fragment derives the legacy palette IN-SHADER, byte-matching
``sync_hp_bar``: fill > 0.5 -> ``color.green`` (0,1,0) else ``color.red``
(1,0,0); the uncovered remainder renders the gray bg ``color.rgb(0.25)``.
A full-size quad with ``uv.x <= fill`` coverage is pixel-equivalent to the
legacy left-anchored fg-quad-over-bg-quad stack.

Billboard math mirrors ``instanced_unit_shader`` (camRight/camUp from the
ModelView matrix); the bar's vertical offset rides camUp exactly like a child
of a legacy billboarded parent. Render state is set by the renderer to the
``configure_ks_overlay`` contract: bin ``fixed,110`` (WK124 — over buildings
at fixed,1 and inside-units at fixed,100), depth test/write off,
``set_two_sided(True)`` (the C7 invariant — single-sided camera-facing quads
backface-cull from the tilted RTS camera).
"""
from __future__ import annotations

from ursina.shader import Shader

instanced_hp_bar_shader = Shader(
    name="instanced_hp_bar_shader",
    language=Shader.GLSL,
    vertex="""#version 330

uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelViewMatrix;

in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;

out vec2 uvs;
out float fillFrac;

/* Panda buffer texture from Texture.setup_buffer_texture -> samplerBuffer. */
uniform samplerBuffer instanceData;

void main() {
    int base = gl_InstanceID * 2;
    vec4 posFill = texelFetch(instanceData, base);
    vec4 dims = texelFetch(instanceData, base + 1);

    vec3 camRight = vec3(
        p3d_ModelViewMatrix[0][0],
        p3d_ModelViewMatrix[1][0],
        p3d_ModelViewMatrix[2][0]);
    vec3 camUp = vec3(
        p3d_ModelViewMatrix[0][1],
        p3d_ModelViewMatrix[1][1],
        p3d_ModelViewMatrix[2][1]);

    /* Anisotropic billboard: x scaled by bar width, y by bar height, plus the
       bar's vertical offset along camUp (legacy bars are children of a
       billboarded parent, so their local +y offset rides the camera up). */
    vec3 worldPos = posFill.xyz
        + camRight * p3d_Vertex.x * dims.x
        + camUp * (p3d_Vertex.y * dims.y + dims.z);

    gl_Position = p3d_ModelViewProjectionMatrix * vec4(worldPos, 1.0);
    uvs = p3d_MultiTexCoord0;
    fillFrac = posFill.w;
}
""",
    fragment="""#version 330

in vec2 uvs;
in float fillFrac;
out vec4 fragColor;

void main() {
    /* Legacy palette (ursina_unit_overlays.sync_hp_bar): ratio > 0.5 -> green
       fg else red fg; bg quad is color.rgb(0.25). uv.x runs 0 (left) -> 1
       (right), so uv.x <= fill reproduces the left-anchored fg quad. */
    vec3 fg = (fillFrac > 0.5) ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0);
    vec3 col = (uvs.x <= fillFrac) ? fg : vec3(0.25, 0.25, 0.25);
    fragColor = vec4(col, 1.0);
}
""",
)

instanced_hp_bar_shader.compile(shader_includes=False)
