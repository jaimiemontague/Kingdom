"""WK83 Round D-3 seam tests — handle_moving moved into ai/behaviors/movement.py.

WK83 moved the global MOVING-state dispatcher ``handle_moving(ai, hero, view)``
VERBATIM out of ``ai/behaviors/bounty_pursuit.py`` (368 -> 236 LOC) into
``ai/behaviors/movement.py``. It is NOT bounty code — it is the per-frame router
that drives bounty claim/abandon, the arrival dispatch, the chase zone-limit, and
enter-FIGHTING; it is exactly the MOVING-state behavior the 300-tick WK67
AI-decision digest hashes (a PERFECT guard).

``bounty_pursuit.handle_moving`` is now a 1-line delegating shim so
``basic_ai``'s ``self.bounty_behavior.handle_moving(self, hero, view)`` caller
(basic_ai.py) is UNCHANGED. ``movement.handle_moving`` still needs two
``bounty_pursuit`` helpers (``_seed_direct_prompt_explore_bearing`` /
``_resolve_bounty_from_target``), so to avoid a module-load cycle:

* ``movement.py`` imports ``bounty_pursuit`` LAZILY, inside ``handle_moving``
  (never at module top), and
* the ``bounty_pursuit.handle_moving`` shim imports ``movement`` LAZILY too.

This file is the WAVE-2 (Agent 11 / QA) seam test. It does NOT re-test the
MOVING-dispatch *behavior* — that is covered byte-identically by the full suite
and the WK67 AI-boundary digest (whose hero movement decisions ARE this
dispatcher's output). It proves the *seam*:

1. ``ai.behaviors.movement.handle_moving`` exists + is callable;
2. ``ai.behaviors.bounty_pursuit.handle_moving`` is a delegating shim — spying on
   ``movement.handle_moving`` and calling ``bounty_pursuit.handle_moving(ai, hero,
   view)`` with sentinels fires ``movement.handle_moving`` with the SAME
   ``(ai, hero, view)`` (and forwards its return);
3. NO module-load cycle — in a FRESH subprocess, ``import ai.behaviors.movement``
   then ``import ai.behaviors.bounty_pursuit`` succeeds, AND the reverse order
   succeeds; PLUS an AST check that ``movement.py`` has NO top-level
   ``import bounty_pursuit`` / ``from ai.behaviors import bounty_pursuit`` (the
   bounty_pursuit import must be lazy, inside ``handle_moving``).
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from ai.behaviors import bounty_pursuit, movement


# Repo root = two levels up from this test file (tests/ -> repo root).
_REPO_ROOT = Path(__file__).resolve().parent.parent

_MOVEMENT_REL_PATH = "ai/behaviors/movement.py"
_BOUNTY_PURSUIT_TARGET = "ai.behaviors.bounty_pursuit"


# ---------------------------------------------------------------------------
# 1. movement.handle_moving exists + is callable.
# ---------------------------------------------------------------------------

def test_movement_exposes_handle_moving():
    assert movement.__name__ == "ai.behaviors.movement"
    fn = getattr(movement, "handle_moving", None)
    assert fn is not None, "ai.behaviors.movement.handle_moving missing"
    assert callable(fn), "ai.behaviors.movement.handle_moving is not callable"


def test_bounty_pursuit_still_exposes_handle_moving():
    """bounty_pursuit.handle_moving must remain present (the basic_ai caller name)."""
    fn = getattr(bounty_pursuit, "handle_moving", None)
    assert fn is not None, "ai.behaviors.bounty_pursuit.handle_moving missing"
    assert callable(fn), "ai.behaviors.bounty_pursuit.handle_moving is not callable"


# ---------------------------------------------------------------------------
# 2. bounty_pursuit.handle_moving is a delegating shim to movement.handle_moving.
#
#    The shim does a lazy ``from ai.behaviors import movement`` inside its body
#    then calls ``movement.handle_moving(ai, hero, view)`` — an attribute lookup
#    on the module object at call time — so monkeypatching the module attribute is
#    what the shim resolves.
# ---------------------------------------------------------------------------

def test_shim_delegates_to_movement_handle_moving(monkeypatch):
    calls = []
    sentinel = object()

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(movement, "handle_moving", spy)

    ai = object()
    hero = object()
    view = object()
    result = bounty_pursuit.handle_moving(ai, hero, view)

    # The shim returned exactly what movement.handle_moving returned.
    assert result is sentinel, "bounty_pursuit.handle_moving did not forward the return value"

    # movement.handle_moving fired exactly once.
    assert len(calls) == 1, (
        f"movement.handle_moving fired {len(calls)} times (want 1)"
    )

    args, kwargs = calls[0]
    # Same (ai, hero, view) forwarded verbatim, positionally, with no extras.
    assert args[0] is ai, "shim did not forward ai"
    assert args[1] is hero, "shim did not forward hero"
    assert args[2] is view, "shim did not forward view"
    assert len(args) == 3, f"shim forwarded extra positional args {args[3:]!r}"
    assert kwargs == {}, f"shim forwarded unexpected kwargs {kwargs!r}"


# ---------------------------------------------------------------------------
# 3a. AST guard: movement.py has NO module-top import of bounty_pursuit.
#
#     movement.handle_moving needs two bounty_pursuit helpers, but it must import
#     them LAZILY inside the function body (never at module top), so there is no
#     module-load cycle (movement <-> bounty_pursuit). This walks only the module
#     body's direct children (and the bodies of any top-level non-TYPE_CHECKING
#     ``if`` blocks); imports nested inside the function are runtime-lazy and so
#     are intentionally excluded.
# ---------------------------------------------------------------------------

def _module_level_imports_of(path: Path, target: str):
    """Return module-top-level (non-TYPE_CHECKING) imports that reference ``target``.

    ``target`` is matched both as a dotted module name (for ``import X`` /
    ``from X import ...``) and as a bare leaf (so ``from ai.behaviors import
    bounty_pursuit`` is caught too).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    leaf = target.rsplit(".", 1)[-1]
    parent = target.rsplit(".", 1)[0] if "." in target else ""

    def _scan(import_node):
        if isinstance(import_node, ast.Import):
            for alias in import_node.names:
                if alias.name == target or alias.name.startswith(target + "."):
                    found.append(ast.dump(import_node))
        elif isinstance(import_node, ast.ImportFrom):
            mod = import_node.module or ""
            # Direct `from ai.behaviors.bounty_pursuit import ...`
            if mod == target or mod.startswith(target + "."):
                found.append(ast.dump(import_node))
            # `from ai.behaviors import bounty_pursuit`
            elif mod == parent:
                for alias in import_node.names:
                    if alias.name == leaf:
                        found.append(ast.dump(import_node))

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            _scan(node)
        elif isinstance(node, ast.If):
            test = node.test
            is_type_checking = isinstance(test, ast.Name) and test.id == "TYPE_CHECKING"
            if is_type_checking:
                continue  # TYPE_CHECKING-only imports are allowed (never executed)
            for sub in node.body + node.orelse:
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    _scan(sub)

    return found


def test_movement_has_no_module_level_bounty_pursuit_import():
    path = _REPO_ROOT / _MOVEMENT_REL_PATH
    assert path.exists(), f"{_MOVEMENT_REL_PATH} missing"
    offending = _module_level_imports_of(path, _BOUNTY_PURSUIT_TARGET)
    assert not offending, (
        f"{_MOVEMENT_REL_PATH} imports {_BOUNTY_PURSUIT_TARGET} at module load time "
        f"(import-cycle risk); the bounty_pursuit import must be lazy, inside "
        f"handle_moving. Offending: {offending}"
    )


def test_movement_handle_moving_imports_bounty_pursuit_lazily():
    """Sanity: the bounty_pursuit import IS present, but only inside handle_moving.

    Proves the lazy import is real (so movement.handle_moving can reach the
    bounty_pursuit helpers), not that it was simply dropped — which would mean a
    NameError at runtime, not a missing dependency.
    """
    path = _REPO_ROOT / _MOVEMENT_REL_PATH
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    handle_moving = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "handle_moving"
        ),
        None,
    )
    assert handle_moving is not None, "movement.py has no top-level handle_moving def"

    lazy_imports = []
    for sub in ast.walk(handle_moving):
        if isinstance(sub, ast.ImportFrom):
            mod = sub.module or ""
            if mod == _BOUNTY_PURSUIT_TARGET:
                lazy_imports.append([a.name for a in sub.names])
            elif mod == "ai.behaviors" and any(a.name == "bounty_pursuit" for a in sub.names):
                lazy_imports.append(["bounty_pursuit"])
        elif isinstance(sub, ast.Import):
            for alias in sub.names:
                if alias.name == _BOUNTY_PURSUIT_TARGET:
                    lazy_imports.append([alias.name])

    assert lazy_imports, (
        "movement.handle_moving does not lazily import bounty_pursuit — it needs "
        "bounty_pursuit helpers (_seed_direct_prompt_explore_bearing / "
        "_resolve_bounty_from_target); a missing import would NameError at runtime."
    )


# ---------------------------------------------------------------------------
# 3b. No module-load cycle: a FRESH interpreter can import the two modules in
#     EITHER order without an ImportError (which a top-level cycle would raise).
#
#     Run in a subprocess so the import truly happens cold (neither module is in
#     sys.modules from this test session). One subprocess per order.
# ---------------------------------------------------------------------------

def _fresh_import_order_ok(first: str, second: str) -> subprocess.CompletedProcess:
    code = (
        f"import {first}\n"
        f"import {second}\n"
        "print('WK83_IMPORT_OK')\n"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        timeout=120,
    )


@pytest.mark.parametrize(
    "first, second",
    [
        ("ai.behaviors.movement", "ai.behaviors.bounty_pursuit"),
        ("ai.behaviors.bounty_pursuit", "ai.behaviors.movement"),
    ],
)
def test_no_module_load_cycle_fresh_import(first, second):
    proc = _fresh_import_order_ok(first, second)
    assert proc.returncode == 0, (
        f"fresh import order `import {first}; import {second}` failed (a module-load "
        f"cycle would raise here).\nreturncode={proc.returncode}\n"
        f"stdout={proc.stdout[-2000:]}\nstderr={proc.stderr[-2000:]}"
    )
    assert "WK83_IMPORT_OK" in proc.stdout, (
        f"fresh import of {first} then {second} did not complete cleanly.\n"
        f"stdout={proc.stdout[-2000:]}\nstderr={proc.stderr[-2000:]}"
    )
