"""WK90 Round B-7 seam test (Agent 11 / QA): the three isolated per-frame
"misc prop" sync methods moved VERBATIM from ``game/graphics/ursina_renderer.py``
into the new ``game/graphics/ursina_misc_props_sync.py`` as module functions:

* ``sync_snapshot_projectiles(r, snapshot, active_ids)`` (was ``_sync_snapshot_projectiles``)
* ``sync_snapshot_bounties(r, snapshot, active_ids)``    (was ``_sync_snapshot_bounties``)
* ``sync_snapshot_rubble(r, snapshot)``                  (was ``_sync_snapshot_rubble``)

``UrsinaRenderer`` keeps 1-line delegating wrappers (``_sync_snapshot_projectiles`` /
``_sync_snapshot_bounties`` / ``_sync_snapshot_rubble``) that forward to those
functions with the renderer as the first argument, so the ``update()`` pipeline call
sites are UNCHANGED. The renderer state these read/write
(``_projectile_tex``, ``_entity_render``, ``_bounty_entities``, ``_rubble_entities``
and the ``_BOUNTY_*`` visual constants) STAYS on the renderer; the functions read it
via ``r``.

This guards the refactor SEAM, not the rendering behaviour itself (that is covered by
the WK67 digest pin + the before/after ``ursina_melee_combat`` / base_overview
screenshots, which Agent 11 confirmed visually identical — in fact byte-identical):

* the 3 moved functions live on ``ursina_misc_props_sync`` and are callable;
* the ``UrsinaRenderer`` wrappers DELEGATE — they call the module function with the
  renderer instance (``self``) as the first arg, forward the remaining args, and return
  its result (proved by spy+monkeypatch of the module functions, and pinned by an AST
  check of the wrapper bodies);
* AST guard: ``ursina_misc_props_sync.py`` has NO module-top import of
  ``ursina_renderer`` (the dependency points one way: renderer -> misc_props_sync); the
  wrappers' lazy function-local import is fine and is verified separately by source
  inspection;
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

import game.graphics.ursina_misc_props_sync as misc_props
from game.graphics.ursina_renderer import UrsinaRenderer


# The functions WK90 moved into ursina_misc_props_sync.py.
MOVED_FUNCTIONS = (
    "sync_snapshot_projectiles",
    "sync_snapshot_bounties",
    "sync_snapshot_rubble",
)

# wrapper-name -> module-function-name (the delegation contract).
WRAPPER_TO_FN = {
    "_sync_snapshot_projectiles": "sync_snapshot_projectiles",
    "_sync_snapshot_bounties": "sync_snapshot_bounties",
    "_sync_snapshot_rubble": "sync_snapshot_rubble",
}


@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_lives_on_misc_props_sync(name: str) -> None:
    """Every moved function is present on ursina_misc_props_sync and callable."""
    assert hasattr(misc_props, name), f"{name} missing from ursina_misc_props_sync"
    assert callable(getattr(misc_props, name)), f"{name} is not callable"


def _bare_renderer() -> UrsinaRenderer:
    """A bare ``UrsinaRenderer`` instance with no ``__init__`` run.

    Constructing a real renderer needs an ursina window; ``object.__new__`` gives us an
    instance whose bound wrapper methods we can call without the heavy graphics
    construction. The wrappers don't touch any instance state themselves — they just
    forward ``self`` — so the bare instance is sufficient to prove delegation.
    """
    return object.__new__(UrsinaRenderer)


def test_sync_snapshot_projectiles_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """``UrsinaRenderer._sync_snapshot_projectiles`` calls
    ``ursina_misc_props_sync.sync_snapshot_projectiles(self, snapshot, active_ids)`` and
    returns its result.

    The wrapper does a lazy ``from game.graphics import ursina_misc_props_sync`` then
    calls ``ursina_misc_props_sync.sync_snapshot_projectiles`` — so we patch the name ON
    the ``ursina_misc_props_sync`` module (patch-where-used) and spy on the forwarded
    args.
    """
    r = _bare_renderer()
    calls: list[tuple] = []
    sentinel = object()

    def spy(rr, snapshot, active_ids):  # noqa: ANN001 - test spy
        calls.append((rr, snapshot, active_ids))
        return sentinel

    monkeypatch.setattr(misc_props, "sync_snapshot_projectiles", spy)

    snap_marker = object()
    ids_marker = object()
    result = r._sync_snapshot_projectiles(snap_marker, ids_marker)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    rr, snapshot, active_ids = calls[0]
    assert rr is r, "renderer (self) must be forwarded as the first arg"
    assert snapshot is snap_marker, "snapshot must be forwarded"
    assert active_ids is ids_marker, "active_ids must be forwarded"


def test_sync_snapshot_bounties_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """``UrsinaRenderer._sync_snapshot_bounties`` calls
    ``ursina_misc_props_sync.sync_snapshot_bounties(self, snapshot, active_ids)`` and
    returns its result."""
    r = _bare_renderer()
    calls: list[tuple] = []
    sentinel = object()

    def spy(rr, snapshot, active_ids):  # noqa: ANN001 - test spy
        calls.append((rr, snapshot, active_ids))
        return sentinel

    monkeypatch.setattr(misc_props, "sync_snapshot_bounties", spy)

    snap_marker = object()
    ids_marker = object()
    result = r._sync_snapshot_bounties(snap_marker, ids_marker)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    rr, snapshot, active_ids = calls[0]
    assert rr is r, "renderer (self) must be forwarded as the first arg"
    assert snapshot is snap_marker, "snapshot must be forwarded"
    assert active_ids is ids_marker, "active_ids must be forwarded"


def test_sync_snapshot_rubble_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """``UrsinaRenderer._sync_snapshot_rubble`` calls
    ``ursina_misc_props_sync.sync_snapshot_rubble(self, snapshot)`` and returns its
    result. (This wrapper takes only ``snapshot`` — no ``active_ids``.)"""
    r = _bare_renderer()
    calls: list[tuple] = []
    sentinel = object()

    def spy(rr, snapshot):  # noqa: ANN001 - test spy
        calls.append((rr, snapshot))
        return sentinel

    monkeypatch.setattr(misc_props, "sync_snapshot_rubble", spy)

    snap_marker = object()
    result = r._sync_snapshot_rubble(snap_marker)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    rr, snapshot = calls[0]
    assert rr is r, "renderer (self) must be forwarded as the first arg"
    assert snapshot is snap_marker, "snapshot must be forwarded"


def test_wrappers_call_misc_props_sync_module_in_source() -> None:
    """Source/AST belt-and-suspenders: each wrapper body contains a call to
    ``ursina_misc_props_sync.<fn>(self, ...)`` with ``self`` as the first argument. This
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
                # match ursina_misc_props_sync.<target_fn>(self, ...)
                if (
                    isinstance(fn, ast.Attribute)
                    and fn.attr == target_fn
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id == "ursina_misc_props_sync"
                    and call.args
                    and isinstance(call.args[0], ast.Name)
                    and call.args[0].id == "self"
                ):
                    found[node.name] = True

    _Visitor().visit(tree)
    missing = [w for w, ok in found.items() if not ok]
    assert not missing, (
        "wrapper(s) do not call ursina_misc_props_sync.<fn>(self, ...) in source: "
        f"{missing}"
    )


def test_misc_props_sync_has_no_module_top_import_of_renderer() -> None:
    """AST guard: ursina_misc_props_sync must not import ursina_renderer at module top
    (the dependency points one way: renderer -> misc_props_sync). A ``TYPE_CHECKING``-only
    import is allowed and is NOT a runtime import, so we only flag unconditional
    module-top imports."""
    src_path = Path(misc_props.__file__)
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
        "ursina_misc_props_sync has a module-top (runtime) import of ursina_renderer "
        f"(would risk a cycle): {offenders}"
    )


@pytest.mark.parametrize(
    "first,second",
    [
        ("game.graphics.ursina_misc_props_sync", "game.graphics.ursina_renderer"),
        ("game.graphics.ursina_renderer", "game.graphics.ursina_misc_props_sync"),
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
