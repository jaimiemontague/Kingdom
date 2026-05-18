"""Terrain fragment shader with fog-of-war overlay (WK53 R3).

Samples the grass albedo texture (tiled) and a fog-of-war texture (1px-per-tile,
bilinear filtered) in the same draw call. The fog texture is alpha-blended over
the terrain color, giving pixel-perfect fog conformance to the terrain surface
with zero additional geometry or z-fighting.

The fog texture UV (``v_fog_uv``) maps [0,1] across the entire map extent, while
the grass UV (``uvs``) tiles at the configured tiles_per_repeat rate.
"""
from __future__ import annotations

from ursina.shader import Shader
from ursina.vec2 import Vec2

terrain_fog_shader = Shader(
    name="terrain_fog_shader",
    language=Shader.GLSL,
    vertex="""#version 130
uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;
out vec2 uvs;
out vec2 v_fog_uv;
uniform vec2 texture_scale;
uniform vec2 texture_offset;
uniform vec2 fog_uv_scale;
uniform vec2 fog_uv_offset;
in vec4 p3d_Color;
out vec4 vertex_color;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    uvs = (p3d_MultiTexCoord0 * texture_scale) + texture_offset;
    v_fog_uv = p3d_MultiTexCoord0 * fog_uv_scale + fog_uv_offset;
    vertex_color = p3d_Color;
}
""",
    fragment="""#version 140
uniform sampler2D p3d_Texture0;
uniform sampler2D fog_texture;
uniform vec4 p3d_ColorScale;
in vec2 uvs;
in vec2 v_fog_uv;
out vec4 fragColor;
in vec4 vertex_color;

uniform vec2 cave_entrance_0;
uniform vec2 cave_entrance_1;
uniform vec2 cave_entrance_2;
uniform vec2 cave_entrance_3;
uniform vec2 cave_entrance_4;
uniform vec2 cave_entrance_5;
uniform vec2 cave_entrance_6;
uniform vec2 cave_entrance_7;
uniform float cave_hole_radius;
uniform float cave_edge_width;

void main() {
    vec4 terrain = texture(p3d_Texture0, uvs) * p3d_ColorScale * vertex_color;
    vec4 fog = texture(fog_texture, v_fog_uv);

    float d0 = distance(v_fog_uv, cave_entrance_0);
    float d1 = distance(v_fog_uv, cave_entrance_1);
    float d2 = distance(v_fog_uv, cave_entrance_2);
    float d3 = distance(v_fog_uv, cave_entrance_3);
    float d4 = distance(v_fog_uv, cave_entrance_4);
    float d5 = distance(v_fog_uv, cave_entrance_5);
    float d6 = distance(v_fog_uv, cave_entrance_6);
    float d7 = distance(v_fog_uv, cave_entrance_7);
    float min_d = min(min(min(d0, d1), min(d2, d3)), min(min(d4, d5), min(d6, d7)));

    if (min_d < cave_hole_radius) discard;

    float cave_edge = 1.0;
    if (cave_edge_width > 0.0 && min_d < cave_hole_radius + cave_edge_width) {
        cave_edge = (min_d - cave_hole_radius) / cave_edge_width;
    }

    vec3 final_rgb = mix(terrain.rgb, fog.rgb, fog.a);
    final_rgb *= cave_edge;
    fragColor = vec4(final_rgb, 1.0);
}
""",
    default_input={
        "texture_scale": Vec2(1, 1),
        "texture_offset": Vec2(0.0, 0.0),
        "fog_uv_scale": Vec2(1, 1),
        "fog_uv_offset": Vec2(0.0, 0.0),
        "cave_entrance_0": Vec2(99.0, 99.0),
        "cave_entrance_1": Vec2(99.0, 99.0),
        "cave_entrance_2": Vec2(99.0, 99.0),
        "cave_entrance_3": Vec2(99.0, 99.0),
        "cave_entrance_4": Vec2(99.0, 99.0),
        "cave_entrance_5": Vec2(99.0, 99.0),
        "cave_entrance_6": Vec2(99.0, 99.0),
        "cave_entrance_7": Vec2(99.0, 99.0),
        "cave_hole_radius": 0.0,
        "cave_edge_width": 0.0,
    },
)
