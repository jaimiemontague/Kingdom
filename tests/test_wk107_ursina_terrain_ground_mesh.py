"""WK107 Round B seam test (Agent 11 / QA): the 3-method ground-surface cluster
was moved VERBATIM from ``game/graphics/ursina_terrain_fog_collab.py`` into the
new ``game/graphics/ursina_terrain_ground_mesh.py`` using the owner-arg
pure-move pattern (WK87-106). Each method became a module-level
``def fn(owner, ...)`` function; ``UrsinaTerrainFogCollab`` keeps a 1-line
lazy-delegating wrapper with the EXACT original name + signature so every caller
(``build_3d_terrain``'s ``self._build_terrain_ground_mesh(...)`` and any external
``update_cave_entrance_shader`` caller) is unchanged. ``build_3d_terrain`` and
``_batch_static_terrain_for_chunks`` STAY in the class this sprint (they become
WK108), so ``tests/test_terrain_perf.py`` needs NO change — its
``patch.object(UrsinaTerrainFogCollab, "_build_terrain_ground_mesh", ...)``
patches the new wrapper, and the wrapper is what ``build_3d_terrain`` calls.

The 3 moved functions::

* ``_build_terrain_ground_mesh(owner, root, world, tw, th, ts, w_world, d_world, has_heightmap)``
* ``update_cave_entrance_shader(owner, pois, map_width, map_height)``
* ``_apply_grass_texture(owner, ground_ent, tw, th, use_texture_scale=True)``

THE ACYCLIC EDGE (invisible to import smoke): fog_collab -> ground_mesh is a
LAZY edge — fog_collab imports the new module ONLY inside the wrapper bodies
(``from game.graphics import ursina_terrain_ground_mesh``), never at module top.
ground_mesh imports ``UrsinaTerrainFogCollab`` ONLY under ``if TYPE_CHECKING:``
(a string-lazy annotation, never a runtime import). Neither direction creates a
load cycle.

FEATURE-GATE / OPTIONAL-DEPENDENCY FALLBACKS (the function-local imports): the
faithful move preserved ``from ursina import Mesh`` (inside the displaced-mesh
``try/except ImportError: return``), ``from PIL import Image`` (inside the grass
texture ``try``), and ``from config import UNDERGROUND_HOLE_RADIUS_TILES``
(inside ``update_cave_entrance_shader`` after its feature-gate ``return``) as
FUNCTION-LOCAL imports — hoisting them would change behavior, so the test
asserts they are present in source AND are NOT module-top-level nodes.

This guards the refactor SEAM, not the rendering behaviour itself. ursina render
code is NOT covered by the WK67 digest, ``determinism_guard`` (which excludes
``game/graphics/**``), or the pygame screenshot tool — render fidelity is
verified by Jaimie's DEFERRED before/after live Ursina captures (need a real
GPU/window the headless agents lack). What this test proves:

* each of the 3 names is a module-level function with an ``owner``-first
  signature;
* each ``UrsinaTerrainFogCollab`` wrapper DELEGATES — it forwards ``self`` as the
  ``owner`` arg and returns the module function's result (runtime spy), including
  the ``use_texture_scale=`` keyword form of ``_apply_grass_texture``;
* AST guard: ``ursina_terrain_ground_mesh.py`` contains NO ``self`` reference
  anywhere (every ``self.`` was rewritten to ``owner.``);
* AST guard: ``ursina_terrain_fog_collab.py`` has NO module-top import of
  ``ursina_terrain_ground_mesh`` (the edge is lazy, inside wrapper bodies); and
  ``ursina_terrain_ground_mesh.py`` imports ``UrsinaTerrainFogCollab`` ONLY under
  ``if TYPE_CHECKING:``;
* function-local-import guard: ``from ursina import Mesh`` / ``from PIL import
  Image`` / ``from config import UNDERGROUND_HOLE_RADIUS_TILES`` are present in
  source yet are NOT module-top-level nodes (the optional-dependency / feature
  fallbacks were preserved);
* a fresh interpreter can import both modules in EITHER order (no load cycle).
"""
from __future__ import annotations

import ast
import inspect
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Headless: never bring up a real display/audio device when the ursina collab is
# imported (mirror tests/test_terrain_perf.py + test_wk106).
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import game.graphics.ursina_terrain_fog_collab as tfc
import game.graphics.ursina_terrain_ground_mesh as tgm
from game.graphics.ursina_terrain_fog_collab import UrsinaTerrainFogCollab


# The 3 functions WK107 moved into ursina_terrain_ground_mesh.py, in source
# order. Wrapper names are identical to the module function names.
MOVED_FUNCTIONS = (
    "_build_terrain_ground_mesh",
    "update_cave_entrance_shader",
    "_apply_grass_texture",
)


# ---------------------------------------------------------------------------
# (1) FN-EXISTS — each name is a module-level function on the new module
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_lives_on_ground_mesh(name: str) -> None:
    """Each of the 3 names is a module-level function in
    ``ursina_terrain_ground_mesh`` (``inspect.isfunction``)."""
    assert hasattr(tgm, name), f"{name} missing from ursina_terrain_ground_mesh"
    assert inspect.isfunction(getattr(tgm, name)), (
        f"{name} is not a module-level function on ursina_terrain_ground_mesh"
    )


# ---------------------------------------------------------------------------
# (2) OWNER-FIRST SIGNATURE — first param of each fn is named ``owner``
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_is_owner_first(name: str) -> None:
    """Each moved module function has an ``owner``-first signature (the owner-arg
    pure-move pattern): the first parameter is named ``owner``."""
    sig = inspect.signature(getattr(tgm, name))
    params = list(sig.parameters)
    assert params, f"{name} has no parameters; expected an owner-first signature"
    assert params[0] == "owner", (
        f"{name} first param is {params[0]!r}; expected 'owner' (owner-arg pure-move)"
    )


# ---------------------------------------------------------------------------
# (3) WRAPPER DELEGATION — wrapper forwards ``self`` as ``owner`` arg 1
# ---------------------------------------------------------------------------
def _bare_collab() -> UrsinaTerrainFogCollab:
    """A bare ``UrsinaTerrainFogCollab`` with no ``__init__`` run.

    Constructing a real collab needs an ursina window; ``object.__new__`` gives
    us an instance whose bound wrapper method we can call without the heavy
    graphics construction. The wrapper itself touches no instance state — it just
    forwards ``self`` to the (monkeypatched) module function — so the bare
    instance is sufficient to prove delegation.
    """
    return object.__new__(UrsinaTerrainFogCollab)


# wrapper-name -> the args the wrapper is invoked with on the bare instance.
# Mirror each ORIGINAL method signature (minus self).
_DUMMY_ARGS: dict[str, tuple[tuple, dict]] = {
    # _build_terrain_ground_mesh(self, root, world, tw, th, ts, w_world, d_world, has_heightmap)
    "_build_terrain_ground_mesh": (
        (object(), object(), 1, 1, 1, 1.0, 1.0, False),
        {},
    ),
    # update_cave_entrance_shader(self, pois, map_width, map_height)
    "update_cave_entrance_shader": (([], 10, 10), {}),
    # _apply_grass_texture(self, ground_ent, tw, th, use_texture_scale=True)
    "_apply_grass_texture": ((object(), 1, 1), {}),
}


@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_wrapper_delegates(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """``UrsinaTerrainFogCollab.<name>`` delegates to ``tgm.<name>(self, ...)``.

    Monkeypatch the module function to a sentinel-recording stub, call the
    WRAPPER on a bare collab instance, and assert (a) the wrapper returns the
    stub's sentinel and (b) the stub recorded the collab instance as its first
    positional arg (``self`` forwarded as ``owner``)."""
    inst = _bare_collab()
    calls: list[tuple] = []
    sentinel = object()

    def recording_stub(*args, **kwargs):  # noqa: ANN002, ANN003 - test spy
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(tgm, name, recording_stub)

    args, kwargs = _DUMMY_ARGS[name]
    result = getattr(inst, name)(*args, **kwargs)

    assert result is sentinel, (
        f"wrapper {name} must return the module function's result (the sentinel)"
    )
    assert len(calls) == 1, f"module function {name} must be called exactly once"
    rec_args, _rec_kwargs = calls[0]
    assert rec_args, f"{name} stub recorded no positional args (owner missing)"
    assert rec_args[0] is inst, (
        f"wrapper {name} must forward the collab instance (self) as the first "
        f"positional arg (owner); got {rec_args[0]!r}"
    )


def test_apply_grass_texture_wrapper_forwards_keyword(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ``_apply_grass_texture`` wrapper forwards both its positional args AND
    the ``use_texture_scale=`` keyword. Exercise BOTH the positional-default form
    (``inst._apply_grass_texture(object(), 1, 1)``) and the explicit-keyword form
    (``..., use_texture_scale=False``); assert the keyword is forwarded to the
    module function (it is passed through as a keyword by the wrapper)."""
    inst = _bare_collab()
    calls: list[tuple] = []
    sentinel = object()

    def recording_stub(*args, **kwargs):  # noqa: ANN002, ANN003 - test spy
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(tgm, "_apply_grass_texture", recording_stub)

    # Positional form: the wrapper supplies the default use_texture_scale=True.
    ge1 = object()
    result1 = inst._apply_grass_texture(ge1, 1, 1)
    assert result1 is sentinel
    assert len(calls) == 1
    args1, kwargs1 = calls[0]
    assert args1[0] is inst, "owner (self) must be forwarded as first positional"
    assert args1[1] is ge1, "ground_ent must be forwarded"
    assert kwargs1.get("use_texture_scale") is True, (
        "wrapper must forward the default use_texture_scale=True as a keyword"
    )

    # Explicit-keyword form: use_texture_scale=False must be forwarded verbatim.
    ge2 = object()
    result2 = inst._apply_grass_texture(ge2, 1, 1, use_texture_scale=False)
    assert result2 is sentinel
    assert len(calls) == 2
    args2, kwargs2 = calls[1]
    assert args2[0] is inst
    assert args2[1] is ge2
    assert kwargs2.get("use_texture_scale") is False, (
        "wrapper must forward use_texture_scale=False to the module function"
    )


# ---------------------------------------------------------------------------
# (4) AST NO-``self`` — the moved code has no ``self`` reference anywhere
# ---------------------------------------------------------------------------
def test_ground_mesh_has_no_self_reference() -> None:
    """AST guard: ``ursina_terrain_ground_mesh.py`` contains NO ``ast.Name`` node
    with id ``self`` — every ``self.`` was rewritten to ``owner.`` during the
    owner-arg move (the source-level invariant the plan §2 mandates). We assert on
    ``ast.Name`` identifiers (NOT a text grep) because docstrings legitimately
    contain the substring "self"."""
    src_path = Path(tgm.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8-sig"), filename=str(src_path))
    offenders = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "self"
    ]
    assert not offenders, (
        "ursina_terrain_ground_mesh.py still references 'self' "
        f"({len(offenders)} occurrence(s)); the owner-arg move must rewrite every "
        "'self' to 'owner'. Offending lines: "
        f"{sorted({getattr(n, 'lineno', -1) for n in offenders})}"
    )


# ---------------------------------------------------------------------------
# (5) AST NO-CYCLE — lazy edge: fog_collab has no module-top import of the new
#     module; the new module imports the collab class ONLY under TYPE_CHECKING.
# ---------------------------------------------------------------------------
def test_fog_collab_has_no_module_top_import_of_ground_mesh() -> None:
    """AST guard: ``ursina_terrain_fog_collab.py`` must NOT import
    ``ursina_terrain_ground_mesh`` at module top — the only references must be the
    lazy ``from game.graphics import ursina_terrain_ground_mesh`` INSIDE the
    wrapper bodies. We inspect ONLY ``tree.body`` (top-level statements); a lazy
    import nested in a function body is correctly NOT flagged here."""
    src_path = Path(tfc.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8-sig"), filename=str(src_path))
    offenders: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith("ursina_terrain_ground_mesh"):
                    offenders.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                if (
                    mod.endswith("ursina_terrain_ground_mesh")
                    or alias.name == "ursina_terrain_ground_mesh"
                ):
                    offenders.append(f"from {mod} import {alias.name}")
    assert not offenders, (
        "ursina_terrain_fog_collab.py has a module-top (runtime) import of "
        f"ursina_terrain_ground_mesh (would risk a cycle): {offenders}. "
        "The edge must be lazy — inside the wrapper bodies only."
    )


def test_ground_mesh_imports_collab_only_under_type_checking() -> None:
    """AST guard: ``ursina_terrain_ground_mesh.py`` imports
    ``UrsinaTerrainFogCollab`` ONLY inside an ``if TYPE_CHECKING:`` block — never
    as a top-level runtime import (which would create a load cycle).

    We assert: (a) NO module-top statement imports ``UrsinaTerrainFogCollab`` or
    the ``ursina_terrain_fog_collab`` module; (b) at least one such import EXISTS
    inside an ``if TYPE_CHECKING:`` block (proving it is the TYPE_CHECKING-only
    form the plan §3 mandates)."""
    src_path = Path(tgm.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8-sig"), filename=str(src_path))

    def _imports_collab(node: ast.AST) -> bool:
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.endswith("ursina_terrain_fog_collab"):
                return True
            return any(a.name == "UrsinaTerrainFogCollab" for a in node.names)
        if isinstance(node, ast.Import):
            return any(
                a.name.endswith("ursina_terrain_fog_collab") for a in node.names
            )
        return False

    # (a) no runtime (module-top) import of the collab module/class.
    top_offenders = [n for n in tree.body if _imports_collab(n)]
    assert not top_offenders, (
        "ursina_terrain_ground_mesh.py imports UrsinaTerrainFogCollab / "
        "ursina_terrain_fog_collab at module top (runtime) — it must be guarded "
        "under 'if TYPE_CHECKING:' only (cycle risk)."
    )

    # (b) it IS imported under an ``if TYPE_CHECKING:`` block.
    found_under_type_checking = False
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        test = node.test
        is_type_checking = (
            isinstance(test, ast.Name) and test.id == "TYPE_CHECKING"
        ) or (
            isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
        )
        if not is_type_checking:
            continue
        for sub in ast.walk(node):
            if _imports_collab(sub):
                found_under_type_checking = True
    assert found_under_type_checking, (
        "ursina_terrain_ground_mesh.py must import UrsinaTerrainFogCollab "
        "under an 'if TYPE_CHECKING:' block (the type-only, no-runtime form)."
    )


# ---------------------------------------------------------------------------
# (6) FUNCTION-LOCAL-IMPORT GUARD — optional-dependency / feature-gate fallbacks
#     were preserved as FUNCTION-LOCAL imports (present in source, NOT top-level)
# ---------------------------------------------------------------------------
_FUNCTION_LOCAL_IMPORT_NEEDLES = (
    "from ursina import Mesh",
    "from PIL import Image",
    "from config import UNDERGROUND_HOLE_RADIUS_TILES",
)


def test_ground_mesh_function_local_imports_preserved() -> None:
    """The faithful move preserved the optional-dependency / feature-gate
    fallbacks as FUNCTION-LOCAL imports. Assert each needle is present in source
    (it was carried) AND that NONE of these imports is a module-top-level node in
    ``tree.body`` (they must be nested inside functions — hoisting them would
    change behavior)."""
    src_path = Path(tgm.__file__)
    src = src_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(src, filename=str(src_path))

    # (a) each needle is present in source (the import was carried over).
    for needle in _FUNCTION_LOCAL_IMPORT_NEEDLES:
        assert needle in src, (
            f"ursina_terrain_ground_mesh.py is missing the function-local import "
            f"{needle!r}; the optional-dependency / feature-gate fallback was not "
            "carried over (faithful move must preserve it)."
        )

    # (b) NONE of these imports appears as a module-top-level node — they must be
    # nested inside function bodies.
    def _matches_needle(node: ast.AST) -> str | None:
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            names = {a.name for a in node.names}
            if mod == "ursina" and "Mesh" in names:
                return "from ursina import Mesh"
            if mod == "PIL" and "Image" in names:
                return "from PIL import Image"
            if mod == "config" and "UNDERGROUND_HOLE_RADIUS_TILES" in names:
                return "from config import UNDERGROUND_HOLE_RADIUS_TILES"
        return None

    top_offenders = [
        match for node in tree.body if (match := _matches_needle(node)) is not None
    ]
    assert not top_offenders, (
        "ursina_terrain_ground_mesh.py hoisted a function-local fallback import to "
        f"module top: {top_offenders}. These guard optional-dependency / "
        "feature-gate fallbacks and MUST stay nested inside their functions "
        "(hoisting them changes behavior)."
    )


# ---------------------------------------------------------------------------
# (7) NO CYCLE — fresh subprocess, BOTH import orders
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "first,second",
    [
        (
            "game.graphics.ursina_terrain_fog_collab",
            "game.graphics.ursina_terrain_ground_mesh",
        ),
        (
            "game.graphics.ursina_terrain_ground_mesh",
            "game.graphics.ursina_terrain_fog_collab",
        ),
    ],
)
def test_fresh_subprocess_imports_both_orders(first: str, second: str) -> None:
    """A fresh interpreter can import both modules in EITHER order without a
    module-load cycle. Runs out-of-process so already-imported modules in this
    session cannot mask an import-order bug."""
    repo_root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env.setdefault("SDL_VIDEODRIVER", "dummy")
    env.setdefault("SDL_AUDIODRIVER", "dummy")
    code = (
        "import importlib;"
        f"importlib.import_module({first!r});"
        f"importlib.import_module({second!r});"
        "print('ok')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, (
        f"fresh import {first} -> {second} failed (rc={proc.returncode}).\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    assert "ok" in proc.stdout, f"missing 'ok' marker. STDOUT:\n{proc.stdout}"
