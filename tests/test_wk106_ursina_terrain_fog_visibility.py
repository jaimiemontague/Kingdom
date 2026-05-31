"""WK106 Round B seam test (Agent 11 / QA): the 9-method visibility-gating +
frustum chunk-culling + instanced-tree-fog cluster was moved VERBATIM from
``game/graphics/ursina_terrain_fog_collab.py`` into the new
``game/graphics/ursina_terrain_fog_visibility.py`` using the owner-arg pure-move
pattern (WK87-105). Each method became a module-level ``def fn(owner, ...)``
function; ``UrsinaTerrainFogCollab`` keeps a 1-line lazy-delegating wrapper with
the EXACT original name + signature so every external caller (build_3d_terrain,
ursina_renderer.py, growth_sync, test_terrain_perf) is unchanged.

The 9 moved functions::

* ``_apply_prop_visibility_state(owner, ent, *, fog_visible=None, chunk_visible=None)``
* ``track_visibility_gated_terrain(owner, ent, tx, ty)``
* ``untrack_visibility_gated_terrain(owner, ent)``
* ``sync_terrain_prop_tile_visibility(owner, ent, vis)``
* ``sync_visibility_gated_terrain(owner, world, fog_revision)``
* ``_build_terrain_chunks(owner)``
* ``cull_terrain_chunks(owner, visible_rect, world)``
* ``_ensure_instanced_nature_renderer(owner)``
* ``_sync_instanced_trees_fog(owner, world, fog_revision)``

THE TWO ACYCLIC EDGES (invisible to import smoke):

1. fog_collab -> fog_visibility is a LAZY edge: fog_collab imports the new module
   ONLY inside the wrapper bodies (``from game.graphics import
   ursina_terrain_fog_visibility``), never at module top. fog_visibility imports
   ``UrsinaTerrainFogCollab`` ONLY under ``if TYPE_CHECKING:`` (a string-lazy
   annotation, never a runtime import). Neither direction creates a load cycle.
2. fog_visibility back-imports ``_InstancedTreeStub`` from
   ``ursina_terrain_growth_sync`` (the WK104 single source of that DTO); it does
   NOT define its own copy.

This guards the refactor SEAM, not the rendering behaviour itself. ursina render
code is NOT covered by the WK67 digest, ``determinism_guard`` (which excludes
``game/graphics/**``), or the pygame screenshot tool — render fidelity is
verified by Jaimie's DEFERRED before/after live Ursina captures (need a real
GPU/window the headless agents lack). What this test proves:

* each of the 9 names is a module-level function with an ``owner``-first
  signature;
* each ``UrsinaTerrainFogCollab`` wrapper DELEGATES — it forwards ``self`` as the
  ``owner`` arg and returns the module function's result (runtime spy);
* AST guard: ``ursina_terrain_fog_visibility.py`` contains NO ``self`` reference
  anywhere (every ``self.`` was rewritten to ``owner.``);
* AST guard: ``ursina_terrain_fog_collab.py`` has NO module-top import of
  ``ursina_terrain_fog_visibility`` (the edge is lazy, inside wrapper bodies);
  and ``ursina_terrain_fog_visibility.py`` imports ``UrsinaTerrainFogCollab``
  ONLY under ``if TYPE_CHECKING:``;
* back-import source guard: ``ursina_terrain_fog_visibility.py`` back-imports
  ``_InstancedTreeStub`` and does NOT define its own copy;
* ``TERRAIN_CHUNK_SIZE`` is mirrored (== 16) and equal across both modules;
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
# imported (mirror tests/test_terrain_perf.py).
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import game.graphics.ursina_terrain_fog_collab as tfc
import game.graphics.ursina_terrain_fog_visibility as tfv
from game.graphics.ursina_terrain_fog_collab import UrsinaTerrainFogCollab


# The 9 functions WK106 moved into ursina_terrain_fog_visibility.py, in source
# order. Wrapper names are identical to the module function names.
MOVED_FUNCTIONS = (
    "_apply_prop_visibility_state",
    "track_visibility_gated_terrain",
    "untrack_visibility_gated_terrain",
    "sync_terrain_prop_tile_visibility",
    "sync_visibility_gated_terrain",
    "_build_terrain_chunks",
    "cull_terrain_chunks",
    "_ensure_instanced_nature_renderer",
    "_sync_instanced_trees_fog",
)


# ---------------------------------------------------------------------------
# (1) FN-EXISTS — each name is a module-level function on the new module
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_lives_on_fog_visibility(name: str) -> None:
    """Each of the 9 names is a module-level function in
    ``ursina_terrain_fog_visibility`` (``inspect.isfunction``)."""
    assert hasattr(tfv, name), f"{name} missing from ursina_terrain_fog_visibility"
    assert inspect.isfunction(getattr(tfv, name)), (
        f"{name} is not a module-level function on ursina_terrain_fog_visibility"
    )


# ---------------------------------------------------------------------------
# (2) OWNER-FIRST SIGNATURE — first param of each fn is named ``owner``
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_is_owner_first(name: str) -> None:
    """Each moved module function has an ``owner``-first signature (the owner-arg
    pure-move pattern): the first parameter is named ``owner``."""
    sig = inspect.signature(getattr(tfv, name))
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
# Mirror each ORIGINAL method signature (minus self). ``_apply_prop_visibility_state``
# is keyword-only after ``ent`` so its fog/chunk args are passed as kwargs.
_DUMMY_ARGS: dict[str, tuple[tuple, dict]] = {
    "_apply_prop_visibility_state": ((object(),), {"fog_visible": True}),
    "track_visibility_gated_terrain": ((object(), 3, 7), {}),
    "untrack_visibility_gated_terrain": ((object(),), {}),
    "sync_terrain_prop_tile_visibility": ((object(), object()), {}),
    "sync_visibility_gated_terrain": ((object(), 11), {}),
    "_build_terrain_chunks": ((), {}),
    "cull_terrain_chunks": (((0, 0, 1, 1), object()), {}),
    "_ensure_instanced_nature_renderer": ((), {}),
    "_sync_instanced_trees_fog": ((object(), 5), {}),
}


@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_wrapper_delegates(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """``UrsinaTerrainFogCollab.<name>`` delegates to ``tfv.<name>(self, ...)``.

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

    monkeypatch.setattr(tfv, name, recording_stub)

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
def test_fog_visibility_has_no_self_reference() -> None:
    """AST guard: ``ursina_terrain_fog_visibility.py`` contains NO ``ast.Name``
    node with id ``self`` — every ``self.`` was rewritten to ``owner.`` during
    the owner-arg move (the source-level invariant the plan §2 mandates)."""
    src_path = Path(tfv.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8-sig"), filename=str(src_path))
    offenders = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "self"
    ]
    assert not offenders, (
        "ursina_terrain_fog_visibility.py still references 'self' "
        f"({len(offenders)} occurrence(s)); the owner-arg move must rewrite every "
        "'self' to 'owner'. Offending lines: "
        f"{sorted({getattr(n, 'lineno', -1) for n in offenders})}"
    )


# ---------------------------------------------------------------------------
# (5) AST NO-CYCLE — lazy edge: fog_collab has no module-top import of the new
#     module; the new module imports the collab class ONLY under TYPE_CHECKING.
# ---------------------------------------------------------------------------
def test_fog_collab_has_no_module_top_import_of_fog_visibility() -> None:
    """AST guard: ``ursina_terrain_fog_collab.py`` must NOT import
    ``ursina_terrain_fog_visibility`` at module top — the only references must be
    the lazy ``from game.graphics import ursina_terrain_fog_visibility`` INSIDE
    the wrapper bodies. We inspect ONLY ``tree.body`` (top-level statements); a
    lazy import nested in a function body is correctly NOT flagged here."""
    src_path = Path(tfc.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8-sig"), filename=str(src_path))
    offenders: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith("ursina_terrain_fog_visibility"):
                    offenders.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                if (
                    mod.endswith("ursina_terrain_fog_visibility")
                    or alias.name == "ursina_terrain_fog_visibility"
                ):
                    offenders.append(f"from {mod} import {alias.name}")
    assert not offenders, (
        "ursina_terrain_fog_collab.py has a module-top (runtime) import of "
        f"ursina_terrain_fog_visibility (would risk a cycle): {offenders}. "
        "The edge must be lazy — inside the wrapper bodies only."
    )


def test_fog_visibility_imports_collab_only_under_type_checking() -> None:
    """AST guard: ``ursina_terrain_fog_visibility.py`` imports
    ``UrsinaTerrainFogCollab`` ONLY inside an ``if TYPE_CHECKING:`` block — never
    as a top-level runtime import (which would create a load cycle).

    We assert: (a) NO module-top statement imports ``UrsinaTerrainFogCollab`` or
    the ``ursina_terrain_fog_collab`` module; (b) at least one such import EXISTS
    inside an ``if TYPE_CHECKING:`` block (proving it is the TYPE_CHECKING-only
    form the plan §3 mandates)."""
    src_path = Path(tfv.__file__)
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
        "ursina_terrain_fog_visibility.py imports UrsinaTerrainFogCollab / "
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
        "ursina_terrain_fog_visibility.py must import UrsinaTerrainFogCollab "
        "under an 'if TYPE_CHECKING:' block (the type-only, no-runtime form)."
    )


# ---------------------------------------------------------------------------
# (6) BACK-IMPORT SOURCE GUARD — single source for _InstancedTreeStub
# ---------------------------------------------------------------------------
def test_fog_visibility_back_imports_stub_and_does_not_redefine_it() -> None:
    """Static-source guard: ``ursina_terrain_fog_visibility.py`` MUST back-import
    ``_InstancedTreeStub`` from ``ursina_terrain_growth_sync`` (the WK104 single
    source of the DTO) and MUST NOT define its own ``class _InstancedTreeStub``
    (a copy would silently diverge and break the ``isinstance`` check in
    ``_build_terrain_chunks``)."""
    src_path = Path(tfv.__file__)
    src = src_path.read_text(encoding="utf-8-sig")
    needle = (
        "from game.graphics.ursina_terrain_growth_sync import _InstancedTreeStub"
    )
    assert needle in src, (
        "ursina_terrain_fog_visibility.py is missing the _InstancedTreeStub "
        f"back-import line ({needle!r}); _build_terrain_chunks would NameError "
        "or use a stale copy"
    )
    assert "class _InstancedTreeStub" not in src, (
        "ursina_terrain_fog_visibility.py must NOT define its own "
        "class _InstancedTreeStub — it must back-import the single source from "
        "ursina_terrain_growth_sync (WK104)."
    )


# ---------------------------------------------------------------------------
# (7) CONSTANT MIRROR — TERRAIN_CHUNK_SIZE == 16 and equal across both modules
# ---------------------------------------------------------------------------
def test_terrain_chunk_size_mirrored_and_equal() -> None:
    """``TERRAIN_CHUNK_SIZE`` is mirrored locally in the new module and equals
    the canonical value in ``ursina_terrain_fog_collab`` (== 16)."""
    assert hasattr(tfv, "TERRAIN_CHUNK_SIZE"), (
        "ursina_terrain_fog_visibility is missing TERRAIN_CHUNK_SIZE"
    )
    assert tfv.TERRAIN_CHUNK_SIZE == tfc.TERRAIN_CHUNK_SIZE == 16, (
        f"TERRAIN_CHUNK_SIZE mismatch: tfv={tfv.TERRAIN_CHUNK_SIZE}, "
        f"tfc={tfc.TERRAIN_CHUNK_SIZE}; both must be 16 (mirror in sync)."
    )


# ---------------------------------------------------------------------------
# (8) NO CYCLE — fresh subprocess, BOTH import orders
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "first,second",
    [
        (
            "game.graphics.ursina_terrain_fog_collab",
            "game.graphics.ursina_terrain_fog_visibility",
        ),
        (
            "game.graphics.ursina_terrain_fog_visibility",
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
