"""Instanced billboard shader for unit rendering (wk47 R2a)."""
from __future__ import annotations

from ursina.shader import Shader
from ursina.vec2 import Vec2

instanced_unit_shader = Shader(
    name="instanced_unit_shader",
    language=Shader.GLSL,
    vertex="""#version 330

uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelViewMatrix;

in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;
out vec2 uvs;

/* Panda buffer texture from Texture.setup_buffer_texture → samplerBuffer (not sampler1D). */
uniform samplerBuffer instanceData;

void main() {
    int base = gl_InstanceID * 2;
    vec4 posScale = texelFetch(instanceData, base);
    vec4 uvRegion = texelFetch(instanceData, base + 1);

    vec3 instancePos = posScale.xyz;
    float scale = posScale.w;

    vec3 camRight = vec3(
        p3d_ModelViewMatrix[0][0],
        p3d_ModelViewMatrix[1][0],
        p3d_ModelViewMatrix[2][0]);
    vec3 camUp = vec3(
        p3d_ModelViewMatrix[0][1],
        p3d_ModelViewMatrix[1][1],
        p3d_ModelViewMatrix[2][1]);

    vec3 worldPos = instancePos
        + camRight * p3d_Vertex.x * scale
        + camUp * p3d_Vertex.y * scale;

    gl_Position = p3d_ModelViewProjectionMatrix * vec4(worldPos, 1.0);
    uvs = uvRegion.xy + p3d_MultiTexCoord0 * uvRegion.zw;
}
""",
    fragment="""#version 330
uniform sampler2D p3d_Texture0;
in vec2 uvs;
out vec4 fragColor;

void main() {
    vec4 texColor = texture(p3d_Texture0, uvs);
    if (texColor.a < 0.08) {
        discard;
    }
    fragColor = texColor;
}
""",
    default_input={
        "texture_scale": Vec2(1, 1),
        "texture_offset": Vec2(0.0, 0.0),
    },
)

instanced_unit_shader.compile(shader_includes=False)
