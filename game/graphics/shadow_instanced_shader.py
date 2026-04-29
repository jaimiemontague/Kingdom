"""Hardware-instanced blob shadow shader — reads same ``instanceData`` buffer as units (wk48).

Instances with negative ``posScale.w`` (projectiles / no-shadow flag) are clipped in the vertex stage.
"""
from __future__ import annotations

from ursina.shader import Shader

shadow_instanced_shader = Shader(
    name="shadow_instanced_shader",
    language=Shader.GLSL,
    vertex="""#version 330

uniform mat4 p3d_ModelViewProjectionMatrix;

in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;

out vec2 uvs;

uniform samplerBuffer instanceData;

void main() {
    int base = gl_InstanceID * 2;
    vec4 posScale = texelFetch(instanceData, base);

    float scaleSigned = posScale.w;
    /* Negative w: projectile / discard blob shadow (shared buffer with units). */
    if (scaleSigned < 0.0) {
        gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
        uvs = vec2(0.0);
        return;
    }

    float scale = scaleSigned;
    vec3 instancePos = posScale.xyz;

    /* Sit just above ``ursina_terrain_fog_collab`` base quad (y≈-0.05); old y=0.01 floated far above floor. */
    const float SHADOW_FLOOR_Y = -0.048;

    vec3 worldPos = vec3(
        instancePos.x + p3d_Vertex.x * scale * 1.2,
        SHADOW_FLOOR_Y,
        instancePos.z + p3d_Vertex.y * scale * 0.8
    );

    gl_Position = p3d_ModelViewProjectionMatrix * vec4(worldPos, 1.0);
    uvs = p3d_MultiTexCoord0;
}
""",
    fragment="""#version 330

in vec2 uvs;
out vec4 fragColor;

void main() {
    float dist = distance(uvs, vec2(0.5, 0.5));
    float alpha = smoothstep(0.5, 0.1, dist) * 0.65;
    if (alpha < 0.01) discard;
    fragColor = vec4(0.0, 0.0, 0.0, alpha);
}
""",
)

shadow_instanced_shader.compile(shader_includes=False)
