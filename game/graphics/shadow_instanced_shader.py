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
    /* Mythos S6: 3 texels per instance (matches instanced_unit_shader) —
       texel0 = pos + signed x-scale, texel1 = uv region, texel2.x = y-scale. */
    int base = gl_InstanceID * 3;
    vec4 posScale = texelFetch(instanceData, base);
    vec4 extra = texelFetch(instanceData, base + 2);

    float scaleSigned = posScale.w;
    /* Negative w: projectile / discard blob shadow (shared buffer with units). */
    if (scaleSigned < 0.0) {
        gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
        uvs = vec2(0.0);
        return;
    }

    float scale = scaleSigned;
    float scaleY = (extra.x > 0.0) ? extra.x : scale;
    vec3 instancePos = posScale.xyz;

    /* Mythos S6 (`inst-parity-gap-fixes`): terrain-following blob. The instance
       Y now includes get_terrain_height (units sit ON hills), so derive the
       floor from the unit's feet (center - half height) instead of the old
       global SHADOW_FLOOR_Y=-0.048 plane, which was wrong on any elevation.
       The small -0.002 bias + the node's set_depth_offset(10) keep it from
       depth-fighting the terrain. */
    float floorY = instancePos.y - scaleY * 0.5 - 0.002;

    vec3 worldPos = vec3(
        instancePos.x + p3d_Vertex.x * scale * 1.2,
        floorY,
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
