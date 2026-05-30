"""WK84 Round D-4 seam tests — assign_patrol_zone moved into ai/behaviors/zones.py.

WK84 moved the patrol-zone assignment ``assign_patrol_zone(ai, hero, view)``
VERBATIM out of ``ai/behaviors/exploration.py`` (322 -> 292 LOC) into a new shared
``ai/behaviors/zones.py``. Per the audit it is genuinely shared zone logic
(consumed by ``exploration`` explore/handle_idle, plus ``movement`` and
``stuck_recovery`` via the ``ai.exploration_behavior`` attribute), so it now has a
single home in ``zones.py``.

Unlike WK83 (a delegating *shim*), WK84 keeps the call-sites working via a plain
RE-EXPORT: ``exploration.py`` does ``from ai.behaviors.zones import
assign_patrol_zone`` at module top, so ``exploration.assign_patrol_zone`` is the
SAME object as ``zones.assign_patrol_zone`` (identity-equal). That re-export is
what makes the existing ``ai.exploration_behavior.assign_patrol_zone`` attribute
access (basic_ai sets ``self.exploration_behavior = exploration``;
``movement.py:185`` / ``stuck_recovery.py:166`` read
``ai.exploration_behavior.assign_patrol_zone``) and the test mocks resolve
unchanged.

``zones.py`` imports only leaf deps (``config`` + the ``view_compat`` shim) and
NEVER imports ``ai.behaviors.exploration``, so although ``exploration`` imports
``zones`` there is no import cycle (the dependency is one-directional:
exploration -> zones).

This file is the WAVE-2 (Agent 11 / QA) seam test. It does NOT re-test the
patrol-zone *behavior* — that is covered byte-identically by the full suite and
the WK67 AI-decision digest (whose hero idle/explore decisions ARE driven by this
function). It proves the *seam*:

1. ``ai.behaviors.zones.assign_patrol_zone`` exists + is callable;
2. ``exploration.assign_patrol_zone IS zones.assign_patrol_zone`` (the re-export
   is the SAME object, so explore()/handle_idle(), the
   ``ai.exploration_behavior.assign_patrol_zone`` call-sites, and the test mocks
   all resolve to the one function);
3. NO module-load cycle — in a FRESH subprocess, ``import ai.behaviors.zones``
   then ``import ai.behaviors.exploration`` succeeds, AND the reverse order
   succeeds; PLUS an AST check that ``zones.py`` has NO top-level
   ``import ai.behaviors.exploration`` / ``from ai.behaviors import exploration``.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from ai.behaviors import exploration, zones


# Repo root = two levels up from this test file (tests/ -> repo root).
_REPO_ROOT = Path(__file__).resolve().parent.parent

_ZONES_REL_PATH = "ai/behaviors/zones.py"
_EXPLORATION_TARGET = "ai.behaviors.exploration"


# ---------------------------------------------------------------------------
# 1. zones.assign_patrol_zone exists + is callable, in the new home.
# ---------------------------------------------------------------------------

def test_zones_exposes_assign_patrol_zone():
    assert zones.__name__ == "ai.behaviors.zones"
    fn = getattr(zones, "assign_patrol_zone", None)
    assert fn is not None, "ai.behaviors.zones.assign_patrol_zone missing"
    assert callable(fn), "ai.behaviors.zones.assign_patrol_zone is not callable"


# ---------------------------------------------------------------------------
# 2. The re-export is identity-equal: exploration.assign_patrol_zone IS the
#    zones object. This is the load-bearing seam — every caller that reads
#    assign_patrol_zone off the exploration module (explore/handle_idle directly,
#    and movement.py / stuck_recovery.py via ``ai.exploration_behavior``, plus the
#    test mocks) resolves to the SAME function moved into zones.py.
# ---------------------------------------------------------------------------

def test_exploration_reexports_zones_assign_patrol_zone_identity():
    fn = getattr(exploration, "assign_patrol_zone", None)
    assert fn is not None, (
        "ai.behaviors.exploration must keep re-exporting assign_patrol_zone — "
        "explore()/handle_idle() and the ai.exploration_behavior.assign_patrol_zone "
        "call-sites read it off this module"
    )
    assert fn is zones.assign_patrol_zone, (
        "exploration.assign_patrol_zone is NOT the same object as "
        "zones.assign_patrol_zone — the re-export must be identity-equal so callers "
        "and the test mocks resolve the one moved function "
        f"(exploration={fn!r} vs zones={zones.assign_patrol_zone!r})"
    )


def test_exploration_behavior_attribute_resolves_to_zones_function():
    """The runtime ``ai.exploration_behavior`` attribute path is identity-equal too.

    ``basic_ai`` sets ``self.exploration_behavior = exploration`` (the module), and
    ``movement.py`` / ``stuck_recovery.py`` call
    ``ai.exploration_behavior.assign_patrol_zone(...)``. So the function those
    importers actually invoke must be the moved ``zones`` object. We resolve the
    SAME attribute chain those call-sites use (the exploration module standing in
    for the ``exploration_behavior`` attribute) and assert identity.
    """
    import ai.basic_ai as basic_ai

    # basic_ai binds the exploration *module* as the exploration_behavior attribute.
    assert basic_ai.exploration is exploration, (
        "basic_ai must bind the exploration module as exploration_behavior so the "
        "ai.exploration_behavior.assign_patrol_zone call-sites resolve against it"
    )
    resolved = basic_ai.exploration.assign_patrol_zone
    assert resolved is zones.assign_patrol_zone, (
        "ai.exploration_behavior.assign_patrol_zone (movement.py:185 / "
        "stuck_recovery.py:166) does not resolve to zones.assign_patrol_zone"
    )


# ---------------------------------------------------------------------------
# 3a. AST guard: zones.py has NO module-top import of exploration.
#
#     exploration imports assign_patrol_zone FROM zones; for that to be cycle-free
#     zones.py must never import ai.behaviors.exploration at module load time. This
#     walks the module body's direct children (and the bodies of any top-level
#     non-TYPE_CHECKING ``if`` blocks); a lazy import inside a function body would
#     be runtime-only and is intentionally excluded — but zones currently needs no
#     exploration symbol at all.
# ---------------------------------------------------------------------------

def _module_level_imports_of(path: Path, target: str):
    """Return module-top-level (non-TYPE_CHECKING) imports that reference ``target``.

    ``target`` is matched both as a dotted module name (``import X`` /
    ``from X import ...``) and as a bare leaf (so ``from ai.behaviors import
    exploration`` is caught too).
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
            # Direct `from ai.behaviors.exploration import ...`
            if mod == target or mod.startswith(target + "."):
                found.append(ast.dump(import_node))
            # `from ai.behaviors import exploration`
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


def test_zones_has_no_module_level_exploration_import():
    path = _REPO_ROOT / _ZONES_REL_PATH
    assert path.exists(), f"{_ZONES_REL_PATH} missing"
    offending = _module_level_imports_of(path, _EXPLORATION_TARGET)
    assert not offending, (
        f"{_ZONES_REL_PATH} imports {_EXPLORATION_TARGET} at module load time — "
        f"exploration already imports assign_patrol_zone FROM zones, so a top-level "
        f"zones->exploration import would form a cycle. Offending: {offending}"
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
        "print('WK84_IMPORT_OK')\n"
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
        ("ai.behaviors.zones", "ai.behaviors.exploration"),
        ("ai.behaviors.exploration", "ai.behaviors.zones"),
    ],
)
def test_no_module_load_cycle_fresh_import(first, second):
    proc = _fresh_import_order_ok(first, second)
    assert proc.returncode == 0, (
        f"fresh import order `import {first}; import {second}` failed (a module-load "
        f"cycle would raise here).\nreturncode={proc.returncode}\n"
        f"stdout={proc.stdout[-2000:]}\nstderr={proc.stderr[-2000:]}"
    )
    assert "WK84_IMPORT_OK" in proc.stdout, (
        f"fresh import of {first} then {second} did not complete cleanly.\n"
        f"stdout={proc.stdout[-2000:]}\nstderr={proc.stderr[-2000:]}"
    )


def test_fresh_import_zones_then_assign_patrol_zone_is_reexported_identity():
    """In a FRESH process, after importing both modules, the identity still holds.

    Guards against an import-order-dependent re-export (e.g. if a future edit made
    exploration rebind the name). Done cold in a subprocess so it is independent of
    this session's already-imported modules.
    """
    code = (
        "import ai.behaviors.zones as z\n"
        "import ai.behaviors.exploration as e\n"
        "assert callable(z.assign_patrol_zone), 'zones.assign_patrol_zone not callable'\n"
        "assert e.assign_patrol_zone is z.assign_patrol_zone, 'reexport identity broke'\n"
        "print('WK84_REEXPORT_IDENTITY_OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        timeout=120,
    )
    assert proc.returncode == 0 and "WK84_REEXPORT_IDENTITY_OK" in proc.stdout, (
        "fresh-process re-export identity check failed.\n"
        f"returncode={proc.returncode}\nstdout={proc.stdout[-2000:]}\n"
        f"stderr={proc.stderr[-2000:]}"
    )
