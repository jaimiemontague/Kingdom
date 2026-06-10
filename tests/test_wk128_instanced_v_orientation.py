"""WK128 — instanced unit renderer V-orientation parity with the legacy path.

Live-playtest bug: creatures rendered UPSIDE-DOWN on the (now default)
instanced unit path. Root cause: a double V-flip —

* the instanced quad's texcoords are authored TOP-DOWN
  (``_create_instanced_quad``: tc.y = 0 at the top vertex, 1 at the bottom),
* AND the vertex shader applied the legacy bottom-up ``texture_offset``
  V-flip (``_v0 = 1 - uvRegion.y - uvRegion.w; v = _v0 + tc.y * w``), which
  legacy pairs with Ursina's BOTTOM-UP quad uvs (uv.y = 1 at the top vertex).

Combined, the screen-top row sampled ``1 - v0 - vh`` (the sprite's BOTTOM row
on the Ursina-uploaded, FLIP_TOP_BOTTOM atlas texture) instead of legacy's
``1 - v0`` (the sprite's TOP row) — flipping EVERY atlas sprite.

These tests are artifact-driven (they evaluate the REAL shader GLSL, the REAL
geom texcoords, the REAL Ursina quad uvs, and the REAL legacy offset formula
from ursina_renderer.py source), so they FAIL on the buggy mapping and guard
any future drift on either path. Coverage: every frame of every kind packed
in the unit atlas (all hero classes, all enemy types, all workers, all
projectile kinds), the unpacked boss-kind fallback regions, and the
facing-flip (negative u-width) variant.

Headless: pure CPU math + an offscreen Ursina bootstrap for the geom build.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


# ---------------------------------------------------------------------------
# Offscreen Ursina bootstrap (module-scoped) — same pattern as
# tests/test_mythos_instanced_overlays.py.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def ursina_app():
    try:
        from panda3d.core import load_prc_file_data

        load_prc_file_data("", "window-type offscreen\n")
        load_prc_file_data("", "audio-library-name null\n")
        import ursina  # noqa: F401
        from ursina import Ursina
    except Exception as e:  # pragma: no cover - environment dependent
        pytest.skip(f"Panda3D/Ursina import unavailable for offscreen test: {e}")

    try:
        app = Ursina()
    except Exception as e:  # pragma: no cover - environment dependent
        pytest.skip(f"Could not initialise offscreen Ursina: {e}")

    yield app

    try:
        app.destroy()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Helpers: evaluate the REAL artifacts (no formula duplication in the test).
# ---------------------------------------------------------------------------
def _split_top_level_commas(s: str) -> list[str]:
    parts, depth, cur = [], 0, []
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def _instanced_shader_v(uv, tc_y: float) -> float:
    """Evaluate the ACTUAL instanced vertex shader's uv.y mapping in Python.

    Substitutes the uv region + texcoord into the GLSL source of
    ``instanced_unit_shader`` (float temporaries included), so a shader edit
    changes this result — the test is pinned to the artifact, not a copy.
    """
    from game.graphics.instanced_unit_shader import instanced_unit_shader

    src = getattr(instanced_unit_shader, "vertex", None)
    if not src:
        src = Path("game/graphics/instanced_unit_shader.py").read_text(encoding="utf-8")

    def sub(expr: str) -> str:
        expr = " ".join(expr.split())  # GLSL exprs may span lines
        expr = expr.replace("uvRegion.x", "_u").replace("uvRegion.y", "_v")
        expr = expr.replace("uvRegion.z", "_uw").replace("uvRegion.w", "_vh")
        expr = expr.replace("p3d_MultiTexCoord0.x", "_tcx")
        expr = expr.replace("p3d_MultiTexCoord0.y", "_tcy")
        return expr

    env = {
        "_u": float(uv[0]), "_v": float(uv[1]),
        "_uw": float(uv[2]), "_vh": float(uv[3]),
        "_tcx": 0.0, "_tcy": float(tc_y),
    }
    # GLSL float temporaries (e.g. _vTop / _v0) — evaluate the ones that only
    # depend on the uv region; skip the instance-buffer ones (posScale etc.).
    for m in re.finditer(r"float\s+(\w+)\s*=\s*([^;]+);", src):
        try:
            env[m.group(1)] = eval(  # noqa: S307 - controlled shader source
                sub(m.group(2)), {"__builtins__": {}}, dict(env)
            )
        except Exception:
            pass

    m = re.search(r"uvs\s*=\s*vec2\((.+?)\);", src, re.S)
    assert m, "could not find `uvs = vec2(...)` in instanced_unit_shader vertex GLSL"
    args = _split_top_level_commas(m.group(1))
    assert len(args) == 2, f"expected 2 vec2 args, got {args!r}"
    return float(eval(sub(args[1]), {"__builtins__": {}}, env))  # noqa: S307


def _legacy_v(uv, tc_y: float) -> float:
    """Evaluate the ACTUAL legacy mapping: Ursina sprite shader
    ``v = tc.y * texture_scale.y + texture_offset.y`` with the offset/scale the
    REAL ``_sync_unit_atlas_billboard`` sets — both extracted from
    ursina_renderer.py source so drift there changes this result too.
    """
    import game.graphics.ursina_renderer as ur

    src = Path(ur.__file__).read_text(encoding="utf-8")
    m = re.search(r"new_offset\s*=\s*\(([^\n]+)\)", src)
    assert m, "could not find `new_offset = (...)` in ursina_renderer.py"
    offset = eval(  # noqa: S307 - controlled renderer source
        f"({m.group(1)})", {"__builtins__": {}}, {"uv": tuple(uv)}
    )
    m2 = re.search(r"ent\.texture_scale\s*=\s*\(([^\n]+)\)", src)
    assert m2, "could not find `ent.texture_scale = (...)` in ursina_renderer.py"
    scale = eval(  # noqa: S307
        f"({m2.group(1)})",
        {"__builtins__": {}},
        {"FRAME_SIZE": ur.FRAME_SIZE, "ATLAS_SIZE": ur.ATLAS_SIZE},
    )
    # ursina_sprite_unlit_shader: uvs = tc * texture_scale + texture_offset
    return float(tc_y) * float(scale[1]) + float(offset[1])


def _geom_tc_extremes(geom) -> tuple[float, float]:
    """Read (tc_y at the TOP vertex, tc_y at the BOTTOM vertex) from the REAL
    instanced quad geom's vertex data (vertex.y is screen-up via camUp)."""
    from panda3d.core import GeomVertexReader

    vdata = geom.get_vertex_data()
    vr = GeomVertexReader(vdata, "vertex")
    tr = GeomVertexReader(vdata, "texcoord")
    rows = []
    while not vr.is_at_end():
        v = vr.get_data3()
        t = tr.get_data2()
        rows.append((float(v.y), float(t.y)))
    top_tc = max(rows, key=lambda r: r[0])[1]
    bottom_tc = min(rows, key=lambda r: r[0])[1]
    return top_tc, bottom_tc


def _ursina_quad_tc_extremes() -> tuple[float, float]:
    """Same extraction for the REAL Ursina 'quad' model the legacy path uses."""
    from ursina.models.procedural.quad import Quad

    mesh = Quad(radius=0, segments=8, aspect=1, scale=(1, 1), mode="ngon")
    rows = list(zip([v[1] for v in mesh.vertices], [uv[1] for uv in mesh.uvs]))
    top_tc = max(rows, key=lambda r: r[0])[1]
    bottom_tc = min(rows, key=lambda r: r[0])[1]
    return top_tc, bottom_tc


# Required atlas coverage: every renderable kind (idle/arrow frame 0 must be
# packed — guards the atlas build against silently dropping a kind).
REQUIRED_KINDS = [
    ("hero", "warrior"), ("hero", "ranger"), ("hero", "rogue"),
    ("hero", "wizard"), ("hero", "cleric"),
    ("enemy", "goblin"), ("enemy", "wolf"), ("enemy", "skeleton"),
    ("enemy", "skeleton_archer"), ("enemy", "spider"), ("enemy", "bandit"),
    ("worker", "peasant"), ("worker", "peasant_builder"),
    ("worker", "guard"), ("worker", "tax_collector"),
    ("vfx", "projectile"),
]
# Boss kinds are NOT packed in the atlas — lookup_uv returns the shared
# fallback region in BOTH paths; V-parity must hold for it too.
BOSS_KINDS = [("enemy", "bandit_lord"), ("enemy", "demon_overlord")]


def test_v_orientation_parity_all_kinds(ursina_app):
    """For EVERY frame of EVERY kind in the unit atlas (plus boss fallbacks and
    the facing-flip variant): the v-coordinate sampled at the sprite's TOP row
    and BOTTOM row must be IDENTICAL under the legacy billboard path and the
    instanced shader path. Fails when either path flips V relative to the other.
    """
    from game.graphics.instanced_unit_renderer import InstancedUnitRenderer
    from game.graphics.instanced_unit_renderer import _flip_uv_horizontal
    from game.graphics.unit_atlas import UnitAtlasBuilder

    atlas = UnitAtlasBuilder.get()

    # Coverage guard: every required kind has at least its frame-0 region packed.
    packed_kinds = {(k[0], k[1]) for k in atlas._uv_map}
    for kind in REQUIRED_KINDS:
        assert kind in packed_kinds, f"atlas is missing kind {kind!r}"

    # Real instanced geom texcoords (top/bottom of the camUp-aligned quad).
    r = InstancedUnitRenderer()
    r._ensure_initialized()
    try:
        inst_top_tc, inst_bottom_tc = _geom_tc_extremes(r._geom)
    finally:
        r.destroy()

    # Real legacy quad texcoords.
    leg_top_tc, leg_bottom_tc = _ursina_quad_tc_extremes()

    regions = dict(atlas._uv_map)
    for unit_type, class_key in BOSS_KINDS:
        regions[(unit_type, class_key, "idle", 0)] = atlas.lookup_uv(
            unit_type, class_key, "idle", 0
        )

    assert regions, "unit atlas has no packed frames"

    bad: list[str] = []
    for key, uv in regions.items():
        variants = [("", uv), ("[facing-flipped]", _flip_uv_horizontal(uv))]
        for tag, region in variants:
            v_inst_top = _instanced_shader_v(region, inst_top_tc)
            v_leg_top = _legacy_v(uv, leg_top_tc)
            v_inst_bot = _instanced_shader_v(region, inst_bottom_tc)
            v_leg_bot = _legacy_v(uv, leg_bottom_tc)
            if abs(v_inst_top - v_leg_top) > 1e-6 or abs(v_inst_bot - v_leg_bot) > 1e-6:
                if len(bad) < 8:
                    bad.append(
                        f"{key}{tag}: top inst={v_inst_top:.6f} leg={v_leg_top:.6f}; "
                        f"bottom inst={v_inst_bot:.6f} leg={v_leg_bot:.6f}"
                    )
                else:
                    bad.append("...")
                break
    assert not bad, (
        "instanced V-orientation diverges from legacy (sprites render "
        "upside-down) for:\n" + "\n".join(bad[:9])
    )


def test_v_orientation_spans_sprite_band(ursina_app):
    """Sanity: both paths must sample WITHIN the sprite's own atlas V band
    (after the Ursina FLIP_TOP_BOTTOM upload, that band is
    [1 - v0 - vh, 1 - v0]) and traverse its full height — guards against a
    'fix' that merely equalises both paths on the wrong band."""
    from game.graphics.instanced_unit_renderer import InstancedUnitRenderer
    from game.graphics.unit_atlas import UnitAtlasBuilder

    atlas = UnitAtlasBuilder.get()
    uv = atlas.lookup_uv("hero", "warrior", "idle", 0)

    r = InstancedUnitRenderer()
    r._ensure_initialized()
    try:
        inst_top_tc, inst_bottom_tc = _geom_tc_extremes(r._geom)
    finally:
        r.destroy()

    v_top = _instanced_shader_v(uv, inst_top_tc)
    v_bot = _instanced_shader_v(uv, inst_bottom_tc)
    # Sprite top row sits at GL v = 1 - v0 (Ursina uploads FLIP_TOP_BOTTOM);
    # bottom row at 1 - v0 - vh.
    assert v_top == pytest.approx(1.0 - uv[1], abs=1e-6), (
        "screen-top must sample the sprite's TOP row (v = 1 - v0)"
    )
    assert v_bot == pytest.approx(1.0 - uv[1] - uv[3], abs=1e-6), (
        "screen-bottom must sample the sprite's BOTTOM row (v = 1 - v0 - vh)"
    )
