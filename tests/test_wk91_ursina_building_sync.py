"""WK91 Round B-8 seam test (Agent 11 / QA): the per-frame building render-sync
method was moved VERBATIM from ``game/graphics/ursina_renderer.py`` into the new
``game/graphics/ursina_building_sync.py`` as a module function:

* ``sync_snapshot_buildings(r, snapshot, world, active_ids)`` (was
  ``UrsinaRenderer._sync_snapshot_buildings``)

``UrsinaRenderer`` keeps a 1-line delegating wrapper (``_sync_snapshot_buildings``)
that forwards to that function with the renderer as the first argument, so the
``update()`` pipeline call sites are UNCHANGED. The renderer state the function
reads/writes (``_camera_active_layer``, ``_entities``, ``_unit_anim_state``,
``_debug_revealed_pois``, ``_poi_mystery_markers``, ``_entity_render``) and the
methods it calls (``_entity_in_view`` — the WK88 frustum wrapper) STAY on the
renderer; the function reaches them via ``r``.

This guards the refactor SEAM, not the rendering behaviour itself (that is covered
by the WK67 digest pin + the before/after ``ursina`` base_overview screenshots,
which Agent 11 confirmed visually identical — a pixel diff showed the ONLY change
is the fluctuating frame-time debug digit; every building renders identically):

* the moved function lives on ``ursina_building_sync`` and is callable;
* the ``UrsinaRenderer`` wrapper DELEGATES — it calls the module function with the
  renderer instance (``self``) as the first arg, forwards the remaining args
  (``snapshot, world, active_ids``), and returns its result (proved by
  spy+monkeypatch of the module function, and pinned by an AST check of the wrapper
  body);
* AST guard: ``ursina_building_sync.py`` has NO module-top import of
  ``ursina_renderer`` (the dependency points one way: renderer ->
  building_sync); a ``TYPE_CHECKING``-only import is allowed and is NOT a runtime
  import. The wrapper's lazy function-local import is fine and is verified
  separately by source inspection;
* a fresh interpreter can import both modules in EITHER order (no module-load
  cycle).
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Headless: never bring up a real display when ursina_renderer is imported.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import game.graphics.ursina_building_sync as building_sync
from game.graphics.ursina_renderer import UrsinaRenderer


# The function WK91 moved into ursina_building_sync.py.
MOVED_FUNCTIONS = ("sync_snapshot_buildings",)

# wrapper-name -> module-function-name (the delegation contract).
WRAPPER_TO_FN = {
    "_sync_snapshot_buildings": "sync_snapshot_buildings",
}


@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_lives_on_building_sync(name: str) -> None:
    """The moved function is present on ursina_building_sync and callable."""
    assert hasattr(building_sync, name), f"{name} missing from ursina_building_sync"
    assert callable(getattr(building_sync, name)), f"{name} is not callable"


def _bare_renderer() -> UrsinaRenderer:
    """A bare ``UrsinaRenderer`` instance with no ``__init__`` run.

    Constructing a real renderer needs an ursina window; ``object.__new__`` gives us
    an instance whose bound wrapper method we can call without the heavy graphics
    construction. The wrapper doesn't touch any instance state itself — it just
    forwards ``self`` — so the bare instance is sufficient to prove delegation.
    """
    return object.__new__(UrsinaRenderer)


def test_sync_snapshot_buildings_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """``UrsinaRenderer._sync_snapshot_buildings`` calls
    ``ursina_building_sync.sync_snapshot_buildings(self, snapshot, world, active_ids)``
    and returns its result.

    The wrapper does a lazy ``from game.graphics import ursina_building_sync`` then
    calls ``ursina_building_sync.sync_snapshot_buildings`` — so we patch the name ON
    the ``ursina_building_sync`` module (patch-where-used) and spy on the forwarded
    args.
    """
    r = _bare_renderer()
    calls: list[tuple] = []
    sentinel = object()

    def spy(rr, snapshot, world, active_ids):  # noqa: ANN001 - test spy
        calls.append((rr, snapshot, world, active_ids))
        return sentinel

    monkeypatch.setattr(building_sync, "sync_snapshot_buildings", spy)

    snap_marker = object()
    world_marker = object()
    ids_marker = object()
    result = r._sync_snapshot_buildings(snap_marker, world_marker, ids_marker)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    rr, snapshot, world, active_ids = calls[0]
    assert rr is r, "renderer (self) must be forwarded as the first arg"
    assert snapshot is snap_marker, "snapshot must be forwarded"
    assert world is world_marker, "world must be forwarded"
    assert active_ids is ids_marker, "active_ids must be forwarded"


def test_wrapper_calls_building_sync_module_in_source() -> None:
    """Source/AST belt-and-suspenders: the wrapper body contains a call to
    ``ursina_building_sync.sync_snapshot_buildings(self, ...)`` with ``self`` as the
    first argument. This pins the delegation even if a future monkeypatch path
    changed."""
    src_path = Path(sys.modules[UrsinaRenderer.__module__].__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8"), filename=str(src_path))

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
                # match ursina_building_sync.<target_fn>(self, ...)
                if (
                    isinstance(fn, ast.Attribute)
                    and fn.attr == target_fn
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id == "ursina_building_sync"
                    and call.args
                    and isinstance(call.args[0], ast.Name)
                    and call.args[0].id == "self"
                ):
                    found[node.name] = True

    _Visitor().visit(tree)
    missing = [w for w, ok in found.items() if not ok]
    assert not missing, (
        "wrapper(s) do not call ursina_building_sync.sync_snapshot_buildings(self, ...) "
        f"in source: {missing}"
    )


def test_building_sync_has_no_module_top_import_of_renderer() -> None:
    """AST guard: ursina_building_sync must not import ursina_renderer at module top
    (the dependency points one way: renderer -> building_sync). A ``TYPE_CHECKING``-only
    import is allowed and is NOT a runtime import, so we only flag unconditional
    module-top imports."""
    src_path = Path(building_sync.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8"), filename=str(src_path))
    offenders: list[str] = []
    for node in ast.iter_child_nodes(tree):  # module-top statements only
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith("ursina_renderer"):
                    offenders.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.endswith("ursina_renderer"):
                offenders.append(f"from {mod} import ...")
    assert not offenders, (
        "ursina_building_sync has a module-top (runtime) import of ursina_renderer "
        f"(would risk a cycle): {offenders}"
    )


@pytest.mark.parametrize(
    "first,second",
    [
        ("game.graphics.ursina_building_sync", "game.graphics.ursina_renderer"),
        ("game.graphics.ursina_renderer", "game.graphics.ursina_building_sync"),
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
