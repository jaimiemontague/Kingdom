"""WK88 Round B-5 seam test (Agent 11 / QA): the camera frustum-culling math moved
VERBATIM from ``game/graphics/ursina_renderer.py`` into
``game/graphics/ursina_frustum.py`` as module functions ``get_visible_tile_rect(r)``
and ``entity_in_view(r, sim_x, sim_y)``, and ``UrsinaRenderer`` keeps 1-line
delegating wrappers (``_get_visible_tile_rect`` / ``_entity_in_view``) that forward to
those functions with the renderer as the first argument.

This guards the refactor SEAM, not the culling behaviour itself (that is covered by
the WK58/WK61 tests + the before/after base_overview screenshots, which Agent 11
confirmed byte-identical):

* the 2 moved functions live on ``ursina_frustum`` and are callable;
* the ``UrsinaRenderer`` wrappers DELEGATE — they call the module function with the
  renderer instance (``self``) as the first arg and forward the remaining args, and
  return its result (proved by spy+monkeypatch of the module functions);
* AST guard: ``ursina_frustum.py`` has NO module-top import of ``ursina_renderer``
  (the dependency points one way: renderer -> frustum); the wrappers' lazy
  function-local import is fine and is verified separately by source inspection;
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

import game.graphics.ursina_frustum as frustum
from game.graphics.ursina_renderer import UrsinaRenderer


# The functions WK88 moved into ursina_frustum.py.
MOVED_FUNCTIONS = (
    "get_visible_tile_rect",
    "entity_in_view",
)


@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_lives_on_frustum(name: str) -> None:
    """Every moved function is present on ursina_frustum and callable."""
    assert hasattr(frustum, name), f"{name} missing from ursina_frustum"
    assert callable(getattr(frustum, name)), f"{name} is not callable"


def _bare_renderer() -> UrsinaRenderer:
    """A bare ``UrsinaRenderer`` instance with no ``__init__`` run.

    Constructing a real renderer needs an ursina window; ``object.__new__`` gives us
    an instance whose bound wrapper methods we can call without the heavy graphics
    construction. The wrappers don't touch any instance state themselves — they just
    forward ``self`` — so the bare instance is sufficient to prove delegation.
    """
    return object.__new__(UrsinaRenderer)


def test_get_visible_tile_rect_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """``UrsinaRenderer._get_visible_tile_rect`` calls
    ``ursina_frustum.get_visible_tile_rect(self)`` and returns its result.

    The wrapper does a lazy ``from game.graphics import ursina_frustum`` then calls
    ``ursina_frustum.get_visible_tile_rect`` — so we patch the name ON the
    ``ursina_frustum`` module (patch-where-used) and spy on the forwarded args.
    """
    r = _bare_renderer()
    calls: list[tuple] = []
    sentinel = (1, 2, 3, 4)

    def spy(rr):  # noqa: ANN001 - test spy
        calls.append((rr,))
        return sentinel

    monkeypatch.setattr(frustum, "get_visible_tile_rect", spy)

    result = r._get_visible_tile_rect()

    assert result == sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    assert calls[0][0] is r, "renderer (self) must be forwarded as the first arg"


def test_entity_in_view_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """``UrsinaRenderer._entity_in_view`` calls
    ``ursina_frustum.entity_in_view(self, sim_x, sim_y)`` and returns its result,
    forwarding the (sim_x, sim_y) args positionally."""
    r = _bare_renderer()
    calls: list[tuple] = []

    def spy(rr, sim_x, sim_y):  # noqa: ANN001 - test spy
        calls.append((rr, sim_x, sim_y))
        return "SENTINEL_BOOL"

    monkeypatch.setattr(frustum, "entity_in_view", spy)

    result = r._entity_in_view(12.5, 34.0)

    assert result == "SENTINEL_BOOL", "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    assert calls[0][0] is r, "renderer (self) must be forwarded as the first arg"
    assert calls[0][1] == 12.5 and calls[0][2] == 34.0, "sim_x/sim_y must be forwarded"


def test_wrappers_call_frustum_module_in_source() -> None:
    """Source/AST belt-and-suspenders: each wrapper body contains a call to
    ``ursina_frustum.<fn>(...)`` with ``self`` as the first argument. This pins the
    delegation even if a future monkeypatch path changed."""
    src_path = Path(UrsinaRenderer.__module__ and sys.modules[UrsinaRenderer.__module__].__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8"), filename=str(src_path))

    wrapper_to_fn = {
        "_get_visible_tile_rect": "get_visible_tile_rect",
        "_entity_in_view": "entity_in_view",
    }
    found: dict[str, bool] = {w: False for w in wrapper_to_fn}

    class _Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            if node.name not in wrapper_to_fn:
                return
            target_fn = wrapper_to_fn[node.name]
            for call in ast.walk(node):
                if not isinstance(call, ast.Call):
                    continue
                fn = call.func
                # match ursina_frustum.<target_fn>(self, ...)
                if (
                    isinstance(fn, ast.Attribute)
                    and fn.attr == target_fn
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id == "ursina_frustum"
                    and call.args
                    and isinstance(call.args[0], ast.Name)
                    and call.args[0].id == "self"
                ):
                    found[node.name] = True

    _Visitor().visit(tree)
    missing = [w for w, ok in found.items() if not ok]
    assert not missing, (
        "wrapper(s) do not call ursina_frustum.<fn>(self, ...) in source: " f"{missing}"
    )


def test_frustum_has_no_module_top_import_of_renderer() -> None:
    """AST guard: ursina_frustum must not import ursina_renderer at module top (the
    dependency points one way: renderer -> frustum). A ``TYPE_CHECKING``-only import
    is allowed and is NOT a runtime import, so we only flag unconditional module-top
    imports."""
    src_path = Path(frustum.__file__)
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
        "ursina_frustum has a module-top (runtime) import of ursina_renderer "
        f"(would risk a cycle): {offenders}"
    )


@pytest.mark.parametrize(
    "first,second",
    [
        ("game.graphics.ursina_frustum", "game.graphics.ursina_renderer"),
        ("game.graphics.ursina_renderer", "game.graphics.ursina_frustum"),
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
