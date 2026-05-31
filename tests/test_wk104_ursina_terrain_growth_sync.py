"""WK104 Round B-21 seam test (Agent 11 / QA): the dynamic-growth sync cluster
was moved VERBATIM from ``game/graphics/ursina_terrain_fog_collab.py`` into the new
``game/graphics/ursina_terrain_growth_sync.py`` using the WK87-92 owner-arg pattern:

* ``sync_dynamic_trees(owner, world, snapshot_trees)``
  (was ``UrsinaTerrainFogCollab.sync_dynamic_trees``)
* ``sync_log_stacks(owner, world, snapshot_log_stacks)``
  (was ``UrsinaTerrainFogCollab.sync_log_stacks``)
* ``class _InstancedTreeStub`` (standalone DTO; moved byte-identical, no
  ``self.``->``owner.`` rewrite — it keeps its own ``self`` because it is a class)

``UrsinaTerrainFogCollab`` keeps 1-line delegating wrappers (same names + signatures)
that forward to the module functions with the collab instance as the first argument,
so ``ursina_renderer.py:580/582`` (``self._terrain_fog.sync_dynamic_trees(...)`` /
``sync_log_stacks(...)``) is UNCHANGED. The owner state the functions read/write
(``owner._tree_sync_tick_counter``, ``owner._last_growth_by_tile``,
``owner._terrain_chunks``, ``owner._chunks_built``, ``owner._instanced_trees_on``,
``owner._instanced_nature_renderer``, ``owner._tree_instance_ids``, plus the renderer
collab state via ``owner._r._tree_entities`` / ``owner._r._terrain_entity`` /
``owner._r._log_stack_entities``) and the FOG/A helper methods they cross-call
(``owner.track_visibility_gated_terrain``, ``owner.untrack_visibility_gated_terrain``,
``owner.sync_terrain_prop_tile_visibility``, ``owner._ensure_instanced_nature_renderer``)
STAY on ``UrsinaTerrainFogCollab``; the functions reach them via ``owner``.

THE BACK-IMPORT (critical — invisible to import smoke): ``_InstancedTreeStub`` moved
OUT of ``ursina_terrain_fog_collab.py``. The code that constructs it (``build_3d_terrain``)
and ``isinstance``-checks it (``cull_terrain_chunks`` / ``_build_terrain_chunks``) later
migrated out of fog_collab too: into ``ursina_terrain_build`` (build_3d_terrain, WK108) and
``ursina_terrain_fog_visibility`` (cull/_build_terrain_chunks, WK106). Each of those consumer
modules MUST keep a top-level
``from game.graphics.ursina_terrain_growth_sync import _InstancedTreeStub`` (a one-way
edge -> growth_sync; growth_sync never imports them at runtime, so acyclic). fog_collab no
longer references the stub, so it correctly no longer carries the import. WITHOUT this line
those consumer methods raise ``NameError`` at call time — which NO headless test catches at
runtime, so test (5) statically asserts the line in each consumer module.

This guards the refactor SEAM, not the rendering behaviour itself. ursina render code
is NOT covered by the WK67 digest, ``determinism_guard`` (which excludes
``game/graphics/**``), or the pygame screenshot tool — render fidelity is verified by
Jaimie's DEFERRED before/after live Ursina captures (need a real GPU/window the
headless agents lack). What this test proves:

* each moved function lives on ``ursina_terrain_growth_sync`` and is callable, with an
  ``owner``-first signature; ``_InstancedTreeStub`` exists in the new module AND the
  back-import from ``ursina_terrain_fog_collab`` resolves to the SAME class object;
* each ``UrsinaTerrainFogCollab`` wrapper DELEGATES — it calls the module function with
  the collab instance (``self``) as the first arg, forwards the remaining args, and
  returns its result (proved by spy+monkeypatch of the module functions, and pinned by
  an AST check of the wrapper bodies);
* AST guard: ``ursina_terrain_growth_sync.py`` has NO module-top runtime import of
  ``ursina_terrain_fog_collab`` (the dependency points one way; a ``TYPE_CHECKING``-only
  import of ``UrsinaTerrainFogCollab`` is allowed and is NOT a runtime import);
* a fresh interpreter can import both modules in EITHER order (no module-load cycle);
* the back-import line is present in each stub-consumer module source
  (``ursina_terrain_fog_visibility`` / ``ursina_terrain_build``);
* ``TERRAIN_CHUNK_SIZE`` is mirrored locally (== 16) and is NOT back-imported from
  ``ursina_terrain_fog_collab`` (no back-edge).
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Headless: never bring up a real display when the ursina collab is imported.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import game.graphics.ursina_terrain_growth_sync as growth_sync
from game.graphics.ursina_terrain_fog_collab import UrsinaTerrainFogCollab


# The two functions WK104 moved into ursina_terrain_growth_sync.py.
MOVED_FUNCTIONS = (
    "sync_dynamic_trees",
    "sync_log_stacks",
)

# wrapper-name -> module-function-name (the delegation contract). Wrapper names are
# identical to the module function names here (the public method names are preserved).
WRAPPER_TO_FN = {
    "sync_dynamic_trees": "sync_dynamic_trees",
    "sync_log_stacks": "sync_log_stacks",
}


# ---------------------------------------------------------------------------
# (1) EXISTENCE — moved functions + the relocated DTO + the back-import identity
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_lives_on_growth_sync(name: str) -> None:
    """The moved function is present on ursina_terrain_growth_sync and callable."""
    assert hasattr(growth_sync, name), f"{name} missing from ursina_terrain_growth_sync"
    assert callable(getattr(growth_sync, name)), f"{name} is not callable"


@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_is_owner_first(name: str) -> None:
    """Each moved module function has an ``owner``-first signature (the WK92 owner-arg
    pattern): the first positional parameter is the collab owner."""
    import inspect

    sig = inspect.signature(getattr(growth_sync, name))
    params = list(sig.parameters)
    assert params, f"{name} has no parameters; expected an owner-first signature"
    assert params[0] == "owner", (
        f"{name} first param is {params[0]!r}; expected 'owner' (owner-arg pure-move)"
    )


def test_instanced_tree_stub_exists_in_new_module() -> None:
    """``_InstancedTreeStub`` lives in the new module and is a class."""
    assert hasattr(growth_sync, "_InstancedTreeStub"), (
        "_InstancedTreeStub missing from ursina_terrain_growth_sync"
    )
    assert isinstance(growth_sync._InstancedTreeStub, type), (
        "_InstancedTreeStub must be a class"
    )


def test_instanced_tree_stub_back_import_is_same_object() -> None:
    """The relocated ``_InstancedTreeStub`` is a SINGLE shared class object, not a copy.
    Its consumers migrated OUT of ursina_terrain_fog_collab: cull_terrain_chunks /
    _build_terrain_chunks -> ursina_terrain_fog_visibility (WK106); build_3d_terrain ->
    ursina_terrain_build (WK108). Each back-imports the stub from ursina_terrain_growth_sync
    and must resolve to the same object (no duplicate class)."""
    from game.graphics.ursina_terrain_fog_visibility import (
        _InstancedTreeStub as vis_stub,
    )
    from game.graphics.ursina_terrain_build import (
        _InstancedTreeStub as build_stub,
    )

    assert vis_stub is growth_sync._InstancedTreeStub, (
        "_InstancedTreeStub imported from ursina_terrain_fog_visibility is NOT the same "
        "object as ursina_terrain_growth_sync._InstancedTreeStub (back-import broken)"
    )
    assert build_stub is growth_sync._InstancedTreeStub, (
        "_InstancedTreeStub imported from ursina_terrain_build is NOT the same object "
        "as ursina_terrain_growth_sync._InstancedTreeStub (back-import broken)"
    )


# ---------------------------------------------------------------------------
# (2) WRAPPERS DELEGATE — runtime spy + source/AST belt-and-suspenders
# ---------------------------------------------------------------------------
def _bare_collab() -> UrsinaTerrainFogCollab:
    """A bare ``UrsinaTerrainFogCollab`` instance with no ``__init__`` run.

    Constructing a real collab needs an ursina window; ``object.__new__`` gives us an
    instance whose bound wrapper method we can call without the heavy graphics
    construction. The wrapper doesn't touch any instance state itself — it just
    forwards ``self`` — so the bare instance is sufficient to prove delegation.
    """
    return object.__new__(UrsinaTerrainFogCollab)


@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_wrapper_delegates(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """``UrsinaTerrainFogCollab.<name>`` -> ``growth_sync.<name>(self, world, snapshot)``.

    Spy+monkeypatch the module function and assert the collab is forwarded as ``self``
    (first arg), the remaining args pass through, and the result is returned. Both
    moved fns share the same ``(world, snapshot)`` arg shape.
    """
    fc = _bare_collab()
    calls: list[tuple] = []
    sentinel = object()

    def spy(owner, arg1, arg2):  # noqa: ANN001 - test spy
        calls.append((owner, arg1, arg2))
        return sentinel

    monkeypatch.setattr(growth_sync, name, spy)

    world_marker = object()
    snap_marker = object()
    result = getattr(fc, name)(world_marker, snap_marker)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    owner, arg1, arg2 = calls[0]
    assert owner is fc, "collab (self) must be forwarded as the first arg"
    assert arg1 is world_marker, "world must be forwarded"
    assert arg2 is snap_marker, "snapshot must be forwarded"


def test_wrappers_call_growth_sync_module_in_source() -> None:
    """Source/AST belt-and-suspenders: every wrapper body contains a call to
    ``ursina_terrain_growth_sync.<fn>(self, ...)`` with ``self`` as the first argument.
    This pins the delegation even if a future monkeypatch path changed."""
    src_path = Path(sys.modules[UrsinaTerrainFogCollab.__module__].__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8-sig"), filename=str(src_path))

    found: dict[str, bool] = {w: False for w in WRAPPER_TO_FN}

    class _Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            if node.name not in WRAPPER_TO_FN:
                return
            target_fn = WRAPPER_TO_FN[node.name]
            for call in ast.walk(node):
                if not isinstance(call, ast.Call):
                    continue
                fn = call.func
                # match ursina_terrain_growth_sync.<target_fn>(self, ...)
                if (
                    isinstance(fn, ast.Attribute)
                    and fn.attr == target_fn
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id == "ursina_terrain_growth_sync"
                    and call.args
                    and isinstance(call.args[0], ast.Name)
                    and call.args[0].id == "self"
                ):
                    found[node.name] = True

    _Visitor().visit(tree)
    missing = [w for w, ok in found.items() if not ok]
    assert not missing, (
        "wrapper(s) do not call ursina_terrain_growth_sync.<fn>(self, ...) in source: "
        f"{missing}"
    )


# ---------------------------------------------------------------------------
# (3) AST NO-CYCLE GUARD — new module has no module-top runtime fog_collab import
# ---------------------------------------------------------------------------
def test_growth_sync_has_no_module_top_import_of_fog_collab() -> None:
    """AST guard: ursina_terrain_growth_sync must not import ursina_terrain_fog_collab
    at module top (the dependency points one way: fog_collab -> growth_sync). A
    ``TYPE_CHECKING``-guarded import of ``UrsinaTerrainFogCollab`` is allowed and is NOT
    a runtime import, so we only flag UNCONDITIONAL module-top imports (those whose
    parent is the module body, not a ``if TYPE_CHECKING:`` block)."""
    src_path = Path(growth_sync.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8-sig"), filename=str(src_path))
    offenders: list[str] = []
    # iter_child_nodes -> module-top statements only; nodes inside an
    # ``if TYPE_CHECKING:`` block are NOT direct children of the module, so a
    # TYPE_CHECKING-guarded import is correctly NOT flagged here.
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith("ursina_terrain_fog_collab"):
                    offenders.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.endswith("ursina_terrain_fog_collab"):
                offenders.append(f"from {mod} import ...")
    assert not offenders, (
        "ursina_terrain_growth_sync has a module-top (runtime) import of "
        f"ursina_terrain_fog_collab (would risk a cycle): {offenders}"
    )


# ---------------------------------------------------------------------------
# (4) NO CYCLE — fresh subprocess, BOTH import orders
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "first,second",
    [
        (
            "game.graphics.ursina_terrain_growth_sync",
            "game.graphics.ursina_terrain_fog_collab",
        ),
        (
            "game.graphics.ursina_terrain_fog_collab",
            "game.graphics.ursina_terrain_growth_sync",
        ),
    ],
)
def test_fresh_subprocess_imports_both_orders(first: str, second: str) -> None:
    """A fresh interpreter can import both modules in EITHER order without a
    module-load cycle. Runs out-of-process so already-imported modules in this session
    cannot mask an import-order bug."""
    repo_root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env.setdefault("SDL_VIDEODRIVER", "dummy")
    code = (
        "import importlib;"
        f"importlib.import_module({first!r});"
        f"importlib.import_module({second!r});"
        "print('OK')"
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
    assert "OK" in proc.stdout, f"missing OK marker. STDOUT:\n{proc.stdout}"


# ---------------------------------------------------------------------------
# (5) BACK-IMPORT SOURCE GUARD — the silent-NameError back-edge no runtime test catches
# ---------------------------------------------------------------------------
def test_back_import_line_present_in_stub_consumers() -> None:
    """Static-source guard: every module that constructs / ``isinstance``-checks
    ``_InstancedTreeStub`` MUST contain the line
    ``from game.graphics.ursina_terrain_growth_sync import _InstancedTreeStub``.
    Without it those methods raise ``NameError`` at CALL time — a path no headless
    import-smoke or seam test exercises, so we pin it in the source text. The consumers
    migrated out of ursina_terrain_fog_collab in WK106/WK108: _build_terrain_chunks /
    cull_terrain_chunks (ursina_terrain_fog_visibility) and build_3d_terrain
    (ursina_terrain_build). fog_collab no longer references the stub, so it correctly
    no longer carries the import."""
    import game.graphics.ursina_terrain_fog_visibility as vis_mod
    import game.graphics.ursina_terrain_build as build_mod

    needle = (
        "from game.graphics.ursina_terrain_growth_sync import _InstancedTreeStub"
    )
    for mod in (vis_mod, build_mod):
        src = Path(mod.__file__).read_text(encoding="utf-8-sig")
        assert needle in src, (
            f"{mod.__name__} is missing the _InstancedTreeStub back-import line "
            f"({needle!r}); its stub consumer would NameError at call time"
        )


# ---------------------------------------------------------------------------
# (6) TERRAIN_CHUNK_SIZE MIRROR — local constant == 16, NOT back-imported
# ---------------------------------------------------------------------------
def test_terrain_chunk_size_mirrored_value() -> None:
    """The new module mirrors ``TERRAIN_CHUNK_SIZE == 16`` locally (it is referenced
    bare inside ``sync_dynamic_trees`` for chunk registration)."""
    assert hasattr(growth_sync, "TERRAIN_CHUNK_SIZE"), (
        "ursina_terrain_growth_sync is missing TERRAIN_CHUNK_SIZE"
    )
    assert growth_sync.TERRAIN_CHUNK_SIZE == 16, (
        f"TERRAIN_CHUNK_SIZE mirror is {growth_sync.TERRAIN_CHUNK_SIZE}; expected 16 "
        "(must stay in sync with ursina_terrain_fog_collab.TERRAIN_CHUNK_SIZE)"
    )


def test_terrain_chunk_size_not_back_imported_from_fog_collab() -> None:
    """AST guard: ``TERRAIN_CHUNK_SIZE`` is a local mirror, NOT imported from
    ``ursina_terrain_fog_collab`` (importing it would create the very back-edge cycle
    the mirror exists to avoid). Assert no ``from ...ursina_terrain_fog_collab import
    TERRAIN_CHUNK_SIZE`` anywhere in the module (top-level or guarded)."""
    src_path = Path(growth_sync.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8-sig"), filename=str(src_path))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.endswith("ursina_terrain_fog_collab"):
                for alias in node.names:
                    if alias.name == "TERRAIN_CHUNK_SIZE":
                        offenders.append(f"from {mod} import TERRAIN_CHUNK_SIZE")
    assert not offenders, (
        "ursina_terrain_growth_sync back-imports TERRAIN_CHUNK_SIZE from "
        f"ursina_terrain_fog_collab (back-edge): {offenders}"
    )
