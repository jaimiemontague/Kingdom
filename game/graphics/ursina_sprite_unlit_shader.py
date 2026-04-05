"""
Unlit shader for textured billboards with alpha cutout (WK21 R3).

Default unlit_shader multiplies RGBA but does not discard fully-transparent
texels; with SRCALPHA sprites that can read as dark outlines ("black stick
figures"). This variant discards low-alpha fragments so filled sprite pixels
blend correctly.
"""
from __future__ import annotations

from ursina.shader import Shader
from ursina.vec2 import Vec2

sprite_unlit_shader = Shader(
    name="sprite_unlit_shader",
    language=Shader.GLSL,
    vertex="""#version 130
uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;
out vec2 uvs;
uniform vec2 texture_scale;
uniform vec2 texture_offset;
in vec4 p3d_Color;
out vec4 vertex_color;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    uvs = (p3d_MultiTexCoord0 * texture_scale) + texture_offset;
    vertex_color = p3d_Color;
}
""",
    fragment="""#version 140
uniform sampler2D p3d_Texture0;
uniform vec4 p3d_ColorScale;
in vec2 uvs;
out vec4 fragColor;
in vec4 vertex_color;

void main() {
    vec4 t = texture(p3d_Texture0, uvs) * p3d_ColorScale * vertex_color;
    if (t.a < 0.08) {
        discard;
    }
    fragColor = t;
}
""",
    default_input={
        "texture_scale": Vec2(1, 1),
        "texture_offset": Vec2(0.0, 0.0),
    },
)
