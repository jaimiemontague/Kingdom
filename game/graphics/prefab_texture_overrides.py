"""
Optional prefab texture overrides for curated building polish.

Prefab JSON stores paths relative to ``assets/`` so source model assets remain
untouched and custom polish can be scoped to one building.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_ROOT = PROJECT_ROOT / "assets"

_TEXTURE_CACHE: dict[str, Any] = {}
_OBJECT_SHADER: list[Any] = []
_UV_SHADER: list[Any] = []


_OBJECT_TEX_VERT = """
#version 150
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;
in vec4 p3d_Vertex;
in vec3 p3d_Normal;
out vec3 vWorldPos;
out vec3 vWorldNormal;
void main() {
    vec4 world_pos = p3d_ModelMatrix * p3d_Vertex;
    vWorldPos = world_pos.xyz;
    vWorldNormal = normalize(mat3(p3d_ModelMatrix) * p3d_Normal);
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
}
"""


_OBJECT_TEX_FRAG = """
#version 150
uniform sampler2D tex;
in vec3 vWorldPos;
in vec3 vWorldNormal;
out vec4 fragColor;
void main() {
    vec3 n = normalize(vWorldNormal);
    vec3 an = abs(n);
    vec2 uv;
    if (an.y >= an.x && an.y >= an.z) {
        uv = vWorldPos.xz * 0.75;
    } else if (an.x >= an.z) {
        uv = vWorldPos.zy * 0.75;
    } else {
        uv = vWorldPos.xy * 0.75;
    }
    vec4 texel = texture(tex, fract(uv));
    vec3 key_dir = normalize(vec3(0.45, 0.75, -0.35));
    float shade = 0.72 + 0.22 * max(dot(n, key_dir), 0.0);
    fragColor = vec4(texel.rgb * shade, texel.a);
}
"""

_UV_TEX_VERT = """
#version 150
uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;
out vec2 vTexCoord;
void main() {
    vTexCoord = p3d_MultiTexCoord0;
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
}
"""


_UV_TEX_FRAG = """
#version 150
uniform sampler2D tex;
in vec2 vTexCoord;
out vec4 fragColor;
void main() {
    fragColor = texture(tex, vTexCoord);
}
"""


def _object_texture_shader():
    if _OBJECT_SHADER:
        return _OBJECT_SHADER[0]
    from panda3d.core import Shader

    shader = Shader.make(Shader.SL_GLSL, vertex=_OBJECT_TEX_VERT, fragment=_OBJECT_TEX_FRAG)
    _OBJECT_SHADER.append(shader)
    return shader


def _uv_texture_shader():
    if _UV_SHADER:
        return _UV_SHADER[0]
    from panda3d.core import Shader

    shader = Shader.make(Shader.SL_GLSL, vertex=_UV_TEX_VERT, fragment=_UV_TEX_FRAG)
    _UV_SHADER.append(shader)
    return shader


def _resolve_asset_path(asset_rel: str) -> Path | None:
    raw = str(asset_rel or "").replace("\\", "/").strip().lstrip("/")
    if not raw:
        return None
    if raw.startswith("assets/"):
        raw = raw[len("assets/") :]
    path = (ASSETS_ROOT / raw).resolve()
    try:
        path.relative_to(ASSETS_ROOT.resolve())
    except ValueError:
        return None
    return path


def load_prefab_texture_override(asset_rel: str):
    path = _resolve_asset_path(asset_rel)
    if path is None or not path.is_file():
        return None
    key = path.as_posix()
    cached = _TEXTURE_CACHE.get(key)
    if cached is not None:
        return cached

    from ursina import Texture

    img = Image.open(path).convert("RGBA")
    tex = Texture(img, filtering=None)
    _TEXTURE_CACHE[key] = tex
    return tex


def apply_prefab_texture_override(entity: Any, asset_rel: str | None, mode: str | None = None) -> bool:
    if not asset_rel:
        return False
    tex = load_prefab_texture_override(str(asset_rel))
    if tex is None:
        return False
    mode_key = str(mode or "object").strip().lower()
    try:
        model = getattr(entity, "model", None)
        panda_tex = getattr(tex, "_texture", tex)
        shader = _uv_texture_shader() if mode_key == "uv" else _object_texture_shader()

        def _apply_to_node(node: Any) -> None:
            if hasattr(node, "clearTexture"):
                node.clearTexture()
            if hasattr(node, "setTexture"):
                node.setTexture(panda_tex, 1)
            if shader is not None and hasattr(node, "setShader"):
                node.setShader(shader)
            if hasattr(node, "setShaderInput"):
                node.setShaderInput("tex", panda_tex)

        if model is not None:
            _apply_to_node(model)
            matches = None
            if hasattr(model, "find_all_matches"):
                matches = model.find_all_matches("**")
            elif hasattr(model, "findAllMatches"):
                matches = model.findAllMatches("**")
            if matches is not None:
                for child in matches:
                    _apply_to_node(child)
        entity.texture = tex
        entity.shader = shader
        if hasattr(entity, "setShaderInput"):
            entity.setShaderInput("tex", panda_tex)
        # Override textures are authored at final game value; do not additionally
        # darken them via the source pack's color multiplier.
        from ursina import color

        entity.color = color.white
        if getattr(entity, "texture", None) is not None:
            entity.texture.filtering = None
        return True
    except Exception:
        return False


def clear_prefab_texture_override_cache() -> None:
    _TEXTURE_CACHE.clear()
