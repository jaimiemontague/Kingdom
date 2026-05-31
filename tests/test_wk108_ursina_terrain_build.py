"""WK108 Round B seam test (Agent 11 / QA): the 2-method terrain-construction
cluster was moved VERBATIM from ``game/graphics/ursina_terrain_fog_collab.py``
into the new ``game/graphics/ursina_terrain_build.py`` using the owner-arg
pure-move pattern (WK87-107). Each method became a module-level
``def fn(owner, ...)`` function; ``UrsinaTerrainFogCollab`` keeps a 1-line
lazy-delegating wrapper with the EXACT original name + signature so every caller
(``ursina_renderer.py:572``'s ``self._terrain_fog.build_3d_terrain(world, ...)``
and ``tests/test_terrain_perf.py``) is unchanged.

The 2 moved functions::

* ``_batch_static_terrain_for_chunks(owner, root, tw, th)``
* ``build_3d_terrain(owner, world, buildings)``

INTRA-SLICE COUPLING (the one allowed call rewrite): ``build_3d_terrain`` calls
``_batch_static_terrain_for_chunks`` as a DIRECT co-resident module function
(``_batch_static_terrain_for_chunks(owner, root, tw, th)``) rather than through
the class wrapper. Both functions live in the new module, so no wrapper
round-trip is needed. The WK106/WK107 wrappers it also calls
(``track_visibility_gated_terrain``, ``_ensure_instanced_nature_renderer``,
``_build_terrain_chunks``, ``_build_terrain_ground_mesh``) stay on the class and
are reached via ``owner.<wrapper>(...)``.

THE ACYCLIC EDGE (invisible to import smoke): fog_collab -> ursina_terrain_build
is a LAZY edge — fog_collab imports the new module ONLY inside the wrapper bodies
(``from game.graphics import ursina_terrain_build``), never at module top.
ursina_terrain_build imports ``UrsinaTerrainFogCollab`` ONLY under
``if TYPE_CHECKING:`` (a string-lazy annotation, never a runtime import). Neither
direction creates a load cycle.

FUNCTION-LOCAL IMPORT (the lazy ``terrain_height`` dependency): the faithful move
preserved ``from game.graphics.terrain_height import get_terrain_height,
init_heightmap, is_initialized`` as a FUNCTION-LOCAL import inside
``build_3d_terrain`` (its original L639 position) — hoisting it would change the
import timing, so the test asserts it is present in source AND is NOT a
module-top-level node.

This guards the refactor SEAM, not the rendering behaviour itself. ursina render
code is NOT covered by the WK67 digest, ``determinism_guard`` (which excludes
``game/graphics/**``), or the pygame screenshot tool — render fidelity is
verified by Jaimie's DEFERRED before/after live Ursina captures (need a real
GPU/window the headless agents lack). What this test proves:

* each of the 2 names is a module-level function with an ``owner``-first
  signature;
* each ``UrsinaTerrainFogCollab`` wrapper DELEGATES — it forwards ``self`` as the
  ``owner`` arg and returns the module function's result (runtime spy);
* AST guard: ``ursina_terrain_build.py`` contains NO ``self`` reference anywhere
  (every ``self.`` was rewritten to ``owner.`` during the owner-arg move);
* AST guard: ``ursina_terrain_fog_collab.py`` has NO module-top import of
  ``ursina_terrain_build`` (the edge is lazy, inside wrapper bodies); and
  ``ursina_terrain_build.py`` imports ``UrsinaTerrainFogCollab`` ONLY under
  ``if TYPE_CHECKING:``;
* function-local-import guard: ``from game.graphics.terrain_height import
  get_terrain_height`` is present in source yet is NOT a module-top-level node
  (the lazy terrain_height dependency was preserved nested in
  ``build_3d_terrain``);
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
# imported (mirror tests/test_terrain_perf.py + test_wk107).
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import game.graphics.ursina_terrain_fog_collab as tfc
import game.graphics.ursina_terrain_build as ttb
from game.graphics.ursina_terrain_fog_collab import UrsinaTerrainFogCollab


# The 2 functions WK108 moved into ursina_terrain_build.py, in source order.
# Wrapper names are identical to the module function names.
MOVED_FUNCTIONS = (
    "_batch_static_terrain_for_chunks",
    "build_3d_terrain",
)


# ---------------------------------------------------------------------------
# (1) FN-EXISTS — each name is a module-level function on the new module
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_lives_on_terrain_build(name: str) -> None:
    """Each of the 2 names is a module-level function in
    ``ursina_terrain_build`` (``inspect.isfunction``)."""
    assert hasattr(ttb, name), f"{name} missing from ursina_terrain_build"
    assert inspect.isfunction(getattr(ttb, name)), (
        f"{name} is not a module-level function on ursina_terrain_build"
    )


# ---------------------------------------------------------------------------
# (2) OWNER-FIRST SIGNATURE — first param of each fn is named ``owner``
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_is_owner_first(name: str) -> None:
    """Each moved module function has an ``owner``-first signature (the owner-arg
    pure-move pattern): the first parameter is named ``owner``."""
    sig = inspect.signature(getattr(ttb, name))
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
    # _batch_static_terrain_for_chunks(self, root, tw, th)
    "_batch_static_terrain_for_chunks": ((object(), 4, 4), {}),
    # build_3d_terrain(self, world, buildings)
    "build_3d_terrain": ((object(), []), {}),
}


@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_wrapper_delegates(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """``UrsinaTerrainFogCollab.<name>`` delegates to ``ttb.<name>(self, ...)``.

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

    monkeypatch.setattr(ttb, name, recording_stub)

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


# ---------------------------------------------------------------------------
# (4) AST NO-``self`` — the moved code has no ``self`` reference anywhere
# ---------------------------------------------------------------------------
def test_terrain_build_has_no_self_reference() -> None:
    """AST guard: ``ursina_terrain_build.py`` contains NO ``ast.Name`` node with
    id ``self`` — every ``self.`` was rewritten to ``owner.`` during the
    owner-arg move (the source-level invariant the plan §2 mandates). We assert
    on ``ast.Name`` identifiers (NOT a text grep) because docstrings legitimately
    contain the substring "self"."""
    src_path = Path(ttb.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8-sig"), filename=str(src_path))
    offenders = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "self"
    ]
    assert not offenders, (
        "ursina_terrain_build.py still references 'self' "
        f"({len(offenders)} occurrence(s)); the owner-arg move must rewrite every "
        "'self' to 'owner'. Offending lines: "
        f"{sorted({getattr(n, 'lineno', -1) for n in offenders})}"
    )


# ---------------------------------------------------------------------------
# (5) AST NO-CYCLE — lazy edge: fog_collab has no module-top import of the new
#     module; the new module imports the collab class ONLY under TYPE_CHECKING.
# ---------------------------------------------------------------------------
def test_fog_collab_has_no_module_top_import_of_terrain_build() -> None:
    """AST guard: ``ursina_terrain_fog_collab.py`` must NOT import
    ``ursina_terrain_build`` at module top — the only references must be the lazy
    ``from game.graphics import ursina_terrain_build`` INSIDE the wrapper bodies.
    We inspect ONLY ``tree.body`` (top-level statements); a lazy import nested in
    a function body is correctly NOT flagged here."""
    src_path = Path(tfc.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8-sig"), filename=str(src_path))
    offenders: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith("ursina_terrain_build"):
                    offenders.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                if (
                    mod.endswith("ursina_terrain_build")
                    or alias.name == "ursina_terrain_build"
                ):
                    offenders.append(f"from {mod} import {alias.name}")
    assert not offenders, (
        "ursina_terrain_fog_collab.py has a module-top (runtime) import of "
        f"ursina_terrain_build (would risk a cycle): {offenders}. "
        "The edge must be lazy — inside the wrapper bodies only."
    )


def test_terrain_build_imports_collab_only_under_type_checking() -> None:
    """AST guard: ``ursina_terrain_build.py`` imports ``UrsinaTerrainFogCollab``
    ONLY inside an ``if TYPE_CHECKING:`` block — never as a top-level runtime
    import (which would create a load cycle).

    We assert: (a) NO module-top statement imports ``UrsinaTerrainFogCollab`` or
    the ``ursina_terrain_fog_collab`` module; (b) at least one such import EXISTS
    inside an ``if TYPE_CHECKING:`` block (proving it is the TYPE_CHECKING-only
    form the plan §3 mandates)."""
    src_path = Path(ttb.__file__)
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
        "ursina_terrain_build.py imports UrsinaTerrainFogCollab / "
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
        "ursina_terrain_build.py must import UrsinaTerrainFogCollab under an "
        "'if TYPE_CHECKING:' block (the type-only, no-runtime form)."
    )


# ---------------------------------------------------------------------------
# (6) FUNCTION-LOCAL-IMPORT GUARD — the lazy terrain_height dependency was
#     preserved as a FUNCTION-LOCAL import (present in source, NOT top-level)
# ---------------------------------------------------------------------------
def test_terrain_build_terrain_height_import_is_function_local() -> None:
    """The faithful move preserved the ``terrain_height`` dependency as a
    FUNCTION-LOCAL import inside ``build_3d_terrain`` (its original L639
    position). Assert the needle ``from game.graphics.terrain_height import
    get_terrain_height`` is present in source (it was carried over) AND that the
    ``from game.graphics.terrain_height import ...`` statement is NOT a
    module-top-level node in ``tree.body`` (it must be nested inside a function —
    hoisting it would change import timing)."""
    src_path = Path(ttb.__file__)
    src = src_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(src, filename=str(src_path))

    # (a) the needle is present in source (the import was carried over).
    needle = "from game.graphics.terrain_height import get_terrain_height"
    assert needle in src, (
        f"ursina_terrain_build.py is missing the function-local import {needle!r}; "
        "the lazy terrain_height dependency was not carried over (faithful move "
        "must preserve it)."
    )

    # (b) NO module-top-level node imports get_terrain_height from
    # game.graphics.terrain_height — it must be nested inside build_3d_terrain.
    top_offenders = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and (node.module or "").endswith("terrain_height")
        and any(a.name == "get_terrain_height" for a in node.names)
    ]
    assert not top_offenders, (
        "ursina_terrain_build.py hoisted the function-local terrain_height import "
        f"to module top (line(s) {[n.lineno for n in top_offenders]}). It guards "
        "import timing and MUST stay nested inside build_3d_terrain (hoisting it "
        "changes behavior)."
    )


# ---------------------------------------------------------------------------
# (7) NO CYCLE — fresh subprocess, BOTH import orders
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "first,second",
    [
        (
            "game.graphics.ursina_terrain_fog_collab",
            "game.graphics.ursina_terrain_build",
        ),
        (
            "game.graphics.ursina_terrain_build",
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
