"""WK89 Round B-6 seam test (Agent 11 / QA): the per-frame unit-animation-frame
computation moved VERBATIM from ``game/graphics/ursina_renderer.py`` into the existing
``game/graphics/ursina_units_anim.py`` as module functions:

* ``compute_anim_frame(r, obj_id, entity, unit_type, class_key, base_clip_fn=None)``
* ``facing_from_dto(r, dto)``
* ``base_clip_from_dto(dto)``

``UrsinaRenderer`` keeps 1-line delegating wrappers (``_compute_anim_frame`` /
``_facing_from_dto``) that forward to those functions with the renderer as the first
argument, and RE-EXPORTS ``base_clip_from_dto`` under the legacy name
``ursina_renderer._base_clip_from_dto`` so any importer of that name keeps working.
The per-entity anim-state FSM (``_unit_anim_state``), the movement-facing scratch
(``_unit_facing_state``) and the sim-tick id (``_frame_tick_id``, the WK67 sim-tick
anim-clock basis) STAY on the renderer; the functions read them via ``r``.

This guards the refactor SEAM, not the animation behaviour itself (that is covered by
the WK67 anim-tick determinism tests + the WK67 digest pin + the before/after
``ursina_melee_combat`` / base_overview screenshots, which Agent 11 confirmed visually
identical):

* the 3 moved functions live on ``ursina_units_anim`` and are callable;
* the ``UrsinaRenderer`` wrappers DELEGATE — they call the module function with the
  renderer instance (``self``) as the first arg, forward the remaining args, and return
  its result (proved by spy+monkeypatch of the module functions, and pinned by an AST
  check of the wrapper bodies);
* ``ursina_renderer._base_clip_from_dto`` IS ``ursina_units_anim.base_clip_from_dto``
  (the same function object — a pure re-export, not a copy);
* AST guard: ``ursina_units_anim.py`` has NO module-top import of ``ursina_renderer``
  (the dependency points one way: renderer -> units_anim); the wrappers' lazy
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

import game.graphics.ursina_units_anim as anim
import game.graphics.ursina_renderer as ursina_renderer
from game.graphics.ursina_renderer import UrsinaRenderer


# The functions WK89 moved into / homed in ursina_units_anim.py.
MOVED_FUNCTIONS = (
    "compute_anim_frame",
    "facing_from_dto",
    "base_clip_from_dto",
)


@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_lives_on_units_anim(name: str) -> None:
    """Every moved function is present on ursina_units_anim and callable."""
    assert hasattr(anim, name), f"{name} missing from ursina_units_anim"
    assert callable(getattr(anim, name)), f"{name} is not callable"


def _bare_renderer() -> UrsinaRenderer:
    """A bare ``UrsinaRenderer`` instance with no ``__init__`` run.

    Constructing a real renderer needs an ursina window; ``object.__new__`` gives us an
    instance whose bound wrapper methods we can call without the heavy graphics
    construction. The wrappers don't touch any instance state themselves — they just
    forward ``self`` — so the bare instance is sufficient to prove delegation.
    """
    return object.__new__(UrsinaRenderer)


def test_compute_anim_frame_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """``UrsinaRenderer._compute_anim_frame`` calls
    ``ursina_units_anim.compute_anim_frame(self, obj_id, entity, unit_type, class_key,
    base_clip_fn)`` and returns its result.

    The wrapper does a lazy ``from game.graphics import ursina_units_anim`` then calls
    ``ursina_units_anim.compute_anim_frame`` — so we patch the name ON the
    ``ursina_units_anim`` module (patch-where-used) and spy on the forwarded args.
    """
    r = _bare_renderer()
    calls: list[tuple] = []
    sentinel = ("attack", 3)

    def spy(rr, obj_id, entity, unit_type, class_key, base_clip_fn=None):  # noqa: ANN001
        calls.append((rr, obj_id, entity, unit_type, class_key, base_clip_fn))
        return sentinel

    monkeypatch.setattr(anim, "compute_anim_frame", spy)

    marker_fn = object()
    result = r._compute_anim_frame(101, "ENTITY", "hero", "knight", base_clip_fn=marker_fn)

    assert result == sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    rr, obj_id, entity, unit_type, class_key, base_clip_fn = calls[0]
    assert rr is r, "renderer (self) must be forwarded as the first arg"
    assert obj_id == 101
    assert entity == "ENTITY"
    assert unit_type == "hero"
    assert class_key == "knight"
    assert base_clip_fn is marker_fn, "base_clip_fn must be forwarded"


def test_facing_from_dto_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """``UrsinaRenderer._facing_from_dto`` calls
    ``ursina_units_anim.facing_from_dto(self, dto)`` and returns its result."""
    r = _bare_renderer()
    calls: list[tuple] = []

    def spy(rr, dto):  # noqa: ANN001 - test spy
        calls.append((rr, dto))
        return -1

    monkeypatch.setattr(anim, "facing_from_dto", spy)

    dto_marker = object()
    result = r._facing_from_dto(dto_marker)

    assert result == -1, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    assert calls[0][0] is r, "renderer (self) must be forwarded as the first arg"
    assert calls[0][1] is dto_marker, "dto must be forwarded"


def test_base_clip_from_dto_is_reexported_same_object() -> None:
    """``ursina_renderer._base_clip_from_dto`` IS
    ``ursina_units_anim.base_clip_from_dto`` — a pure re-export (same object), not a
    copy/wrapper. Guards the legacy ``ursina_renderer._base_clip_from_dto`` import path.
    """
    assert hasattr(ursina_renderer, "_base_clip_from_dto"), (
        "ursina_renderer must re-export _base_clip_from_dto"
    )
    assert ursina_renderer._base_clip_from_dto is anim.base_clip_from_dto, (
        "ursina_renderer._base_clip_from_dto must be the SAME object as "
        "ursina_units_anim.base_clip_from_dto (re-export, not a copy)"
    )


def test_wrappers_call_units_anim_module_in_source() -> None:
    """Source/AST belt-and-suspenders: each wrapper body contains a call to
    ``ursina_units_anim.<fn>(...)`` with ``self`` as the first argument. This pins the
    delegation even if a future monkeypatch path changed."""
    src_path = Path(sys.modules[UrsinaRenderer.__module__].__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8"), filename=str(src_path))

    wrapper_to_fn = {
        "_compute_anim_frame": "compute_anim_frame",
        "_facing_from_dto": "facing_from_dto",
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
                # match ursina_units_anim.<target_fn>(self, ...)
                if (
                    isinstance(fn, ast.Attribute)
                    and fn.attr == target_fn
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id == "ursina_units_anim"
                    and call.args
                    and isinstance(call.args[0], ast.Name)
                    and call.args[0].id == "self"
                ):
                    found[node.name] = True

    _Visitor().visit(tree)
    missing = [w for w, ok in found.items() if not ok]
    assert not missing, (
        "wrapper(s) do not call ursina_units_anim.<fn>(self, ...) in source: "
        f"{missing}"
    )


def test_units_anim_has_no_module_top_import_of_renderer() -> None:
    """AST guard: ursina_units_anim must not import ursina_renderer at module top (the
    dependency points one way: renderer -> units_anim). A ``TYPE_CHECKING``-only import
    is allowed and is NOT a runtime import, so we only flag unconditional module-top
    imports."""
    src_path = Path(anim.__file__)
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
        "ursina_units_anim has a module-top (runtime) import of ursina_renderer "
        f"(would risk a cycle): {offenders}"
    )


@pytest.mark.parametrize(
    "first,second",
    [
        ("game.graphics.ursina_units_anim", "game.graphics.ursina_renderer"),
        ("game.graphics.ursina_renderer", "game.graphics.ursina_units_anim"),
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
