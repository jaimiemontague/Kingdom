"""WK92 Round B-9 seam test (Agent 11 / QA): the five per-frame per-unit-kind
render-sync methods were moved VERBATIM from ``game/graphics/ursina_renderer.py``
into the new ``game/graphics/ursina_unit_sync.py`` as module functions:

* ``sync_snapshot_heroes(r, snapshot, active_ids, HeroClass)``
  (was ``UrsinaRenderer._sync_snapshot_heroes``)
* ``sync_snapshot_enemies(r, snapshot, world, active_ids)``
  (was ``UrsinaRenderer._sync_snapshot_enemies``)
* ``sync_snapshot_peasants(r, snapshot, active_ids)``
  (was ``UrsinaRenderer._sync_snapshot_peasants``)
* ``sync_snapshot_guards(r, snapshot, active_ids)``
  (was ``UrsinaRenderer._sync_snapshot_guards``)
* ``sync_snapshot_tax_collector(r, snapshot, active_ids)``
  (was ``UrsinaRenderer._sync_snapshot_tax_collector``)

``UrsinaRenderer`` keeps 1-line delegating wrappers (same names + signatures) that
forward to the module functions with the renderer as the first argument, so the
``update()`` pipeline call sites are UNCHANGED. The renderer state the functions
read/write (``_camera_active_layer``, ``_entities``, ``_entity_render`` collab,
``_unit_anim_state`` / ``_unit_facing_state`` reached via the anim/facing wrappers)
and the methods they call (``_entity_in_view`` — WK88 frustum wrapper;
``_facing_from_dto`` — WK89 anim wrapper; ``_sync_unit_atlas_billboard``) STAY on
the renderer; the functions reach them via ``r``.

This guards the refactor SEAM, not the rendering behaviour itself (that is covered
by the WK67 digest pin + the before/after ``ursina`` base + combat screenshots,
which Agent 11 confirmed visually identical via pixel-diff — the ONLY differences
are the fluctuating frame-time debug HUD digit and a 2-px corner AA flicker; every
unit kind renders identically):

* each moved function lives on ``ursina_unit_sync`` and is callable;
* each ``UrsinaRenderer`` wrapper DELEGATES — it calls the module function with the
  renderer instance (``self``) as the first arg, forwards the remaining args
  (incl. ``HeroClass`` for heroes / ``world`` for enemies), and returns its result
  (proved by spy+monkeypatch of the module functions, and pinned by an AST check of
  the wrapper bodies);
* AST guard: ``ursina_unit_sync.py`` has NO module-top import of ``ursina_renderer``
  (the dependency points one way: renderer -> unit_sync); a ``TYPE_CHECKING``-only
  import is allowed and is NOT a runtime import. The wrappers' lazy function-local
  imports are fine and are verified separately by the AST delegation check;
* a fresh interpreter can import both modules in EITHER order (no module-load cycle).
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

import game.graphics.ursina_unit_sync as unit_sync
from game.graphics.ursina_renderer import UrsinaRenderer


# The five functions WK92 moved into ursina_unit_sync.py.
MOVED_FUNCTIONS = (
    "sync_snapshot_heroes",
    "sync_snapshot_enemies",
    "sync_snapshot_peasants",
    "sync_snapshot_guards",
    "sync_snapshot_tax_collector",
)

# wrapper-name -> module-function-name (the delegation contract).
WRAPPER_TO_FN = {
    "_sync_snapshot_heroes": "sync_snapshot_heroes",
    "_sync_snapshot_enemies": "sync_snapshot_enemies",
    "_sync_snapshot_peasants": "sync_snapshot_peasants",
    "_sync_snapshot_guards": "sync_snapshot_guards",
    "_sync_snapshot_tax_collector": "sync_snapshot_tax_collector",
}


@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_lives_on_unit_sync(name: str) -> None:
    """The moved function is present on ursina_unit_sync and callable."""
    assert hasattr(unit_sync, name), f"{name} missing from ursina_unit_sync"
    assert callable(getattr(unit_sync, name)), f"{name} is not callable"


def _bare_renderer() -> UrsinaRenderer:
    """A bare ``UrsinaRenderer`` instance with no ``__init__`` run.

    Constructing a real renderer needs an ursina window; ``object.__new__`` gives us
    an instance whose bound wrapper method we can call without the heavy graphics
    construction. The wrapper doesn't touch any instance state itself — it just
    forwards ``self`` — so the bare instance is sufficient to prove delegation.
    """
    return object.__new__(UrsinaRenderer)


def test_heroes_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_sync_snapshot_heroes`` -> ``sync_snapshot_heroes(self, snapshot, active_ids, HeroClass)``.

    The hero wrapper forwards an EXTRA ``HeroClass`` arg after ``active_ids`` — assert
    it is forwarded in the right position.
    """
    r = _bare_renderer()
    calls: list[tuple] = []
    sentinel = object()

    def spy(rr, snapshot, active_ids, HeroClass):  # noqa: ANN001 - test spy
        calls.append((rr, snapshot, active_ids, HeroClass))
        return sentinel

    monkeypatch.setattr(unit_sync, "sync_snapshot_heroes", spy)

    snap_marker = object()
    ids_marker = object()
    heroclass_marker = object()
    result = r._sync_snapshot_heroes(snap_marker, ids_marker, heroclass_marker)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    rr, snapshot, active_ids, HeroClass = calls[0]
    assert rr is r, "renderer (self) must be forwarded as the first arg"
    assert snapshot is snap_marker, "snapshot must be forwarded"
    assert active_ids is ids_marker, "active_ids must be forwarded"
    assert HeroClass is heroclass_marker, "HeroClass must be forwarded (heroes-only extra arg)"


def test_enemies_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_sync_snapshot_enemies`` -> ``sync_snapshot_enemies(self, snapshot, world, active_ids)``.

    The enemy wrapper forwards an EXTRA ``world`` arg between ``snapshot`` and
    ``active_ids`` — assert it is forwarded in the right position.
    """
    r = _bare_renderer()
    calls: list[tuple] = []
    sentinel = object()

    def spy(rr, snapshot, world, active_ids):  # noqa: ANN001 - test spy
        calls.append((rr, snapshot, world, active_ids))
        return sentinel

    monkeypatch.setattr(unit_sync, "sync_snapshot_enemies", spy)

    snap_marker = object()
    world_marker = object()
    ids_marker = object()
    result = r._sync_snapshot_enemies(snap_marker, world_marker, ids_marker)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    rr, snapshot, world, active_ids = calls[0]
    assert rr is r, "renderer (self) must be forwarded as the first arg"
    assert snapshot is snap_marker, "snapshot must be forwarded"
    assert world is world_marker, "world must be forwarded (enemies-only extra arg)"
    assert active_ids is ids_marker, "active_ids must be forwarded"


@pytest.mark.parametrize(
    "wrapper_name,fn_name",
    [
        ("_sync_snapshot_peasants", "sync_snapshot_peasants"),
        ("_sync_snapshot_guards", "sync_snapshot_guards"),
        ("_sync_snapshot_tax_collector", "sync_snapshot_tax_collector"),
    ],
)
def test_simple_wrapper_delegates(
    wrapper_name: str, fn_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """peasants / guards / tax_collector wrappers ->
    ``<fn>(self, snapshot, active_ids)`` (the simple ``(snapshot, active_ids)``
    signature, no extra arg). Spy+monkeypatch the module function and assert the
    renderer is forwarded as ``self`` and the args pass through, and the result is
    returned."""
    r = _bare_renderer()
    calls: list[tuple] = []
    sentinel = object()

    def spy(rr, snapshot, active_ids):  # noqa: ANN001 - test spy
        calls.append((rr, snapshot, active_ids))
        return sentinel

    monkeypatch.setattr(unit_sync, fn_name, spy)

    snap_marker = object()
    ids_marker = object()
    result = getattr(r, wrapper_name)(snap_marker, ids_marker)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    rr, snapshot, active_ids = calls[0]
    assert rr is r, "renderer (self) must be forwarded as the first arg"
    assert snapshot is snap_marker, "snapshot must be forwarded"
    assert active_ids is ids_marker, "active_ids must be forwarded"


def test_wrappers_call_unit_sync_module_in_source() -> None:
    """Source/AST belt-and-suspenders: every wrapper body contains a call to
    ``ursina_unit_sync.<fn>(self, ...)`` with ``self`` as the first argument. This
    pins the delegation even if a future monkeypatch path changed."""
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
                # match ursina_unit_sync.<target_fn>(self, ...)
                if (
                    isinstance(fn, ast.Attribute)
                    and fn.attr == target_fn
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id == "ursina_unit_sync"
                    and call.args
                    and isinstance(call.args[0], ast.Name)
                    and call.args[0].id == "self"
                ):
                    found[node.name] = True

    _Visitor().visit(tree)
    missing = [w for w, ok in found.items() if not ok]
    assert not missing, (
        "wrapper(s) do not call ursina_unit_sync.<fn>(self, ...) in source: " f"{missing}"
    )


def test_unit_sync_has_no_module_top_import_of_renderer() -> None:
    """AST guard: ursina_unit_sync must not import ursina_renderer at module top
    (the dependency points one way: renderer -> unit_sync). A ``TYPE_CHECKING``-only
    import is allowed and is NOT a runtime import, so we only flag unconditional
    module-top imports."""
    src_path = Path(unit_sync.__file__)
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
        "ursina_unit_sync has a module-top (runtime) import of ursina_renderer "
        f"(would risk a cycle): {offenders}"
    )


@pytest.mark.parametrize(
    "first,second",
    [
        ("game.graphics.ursina_unit_sync", "game.graphics.ursina_renderer"),
        ("game.graphics.ursina_renderer", "game.graphics.ursina_unit_sync"),
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
