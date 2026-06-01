"""WK120 Round B seam test (Agent 11 / QA): the per-hero AI decision dispatch was
moved VERBATIM out of ``BasicAI.update_hero`` (HEAD ``ai/basic_ai.py`` L205-335) into a
new module function ``ai/task_router.py::update_hero(ai, hero, dt, view)`` using the
owner-arg pure-move pattern (the BasicAI instance is the ``ai`` param). ``BasicAI`` keeps
a 1-line delegating wrapper (``def update_hero(self, hero, dt, view): from ai import
task_router; return task_router.update_hero(self, hero, dt, view)``); the relocated body
is byte-faithful (the ONLY change is whole-word ``self`` -> ``ai``). ``BasicAI.update``
(the all-heroes loop) is unchanged and still calls ``self.update_hero`` (the wrapper).

This guards the refactor SEAM, not the AI behavior itself. Unlike the ursina render/input
slices, ``update_hero`` IS exactly the path the WK67 AI-decision digest exercises (300
headless ticks, 3 seeded heroes) -- so the load-bearing behavior proof for this move is
the FULL ``tests/test_wk67_ai_boundary.py`` suite staying green with the digest
byte-identical (``b73961340c...d148ded``), run as a DoD gate (NOT in this file). What
this seam test proves:

* ``ai.task_router.update_hero`` exists, is callable, and has the exact owner-first
  signature ``(ai, hero, dt, view)`` (first param ``ai``);
* the ``BasicAI.update_hero`` wrapper DELEGATES -- it calls ``task_router.update_hero``
  with the BasicAI instance forwarded as ``ai`` (first arg), passes ``hero``/``dt``/
  ``view`` through positionally with no kwargs, and returns the module function's result
  (spy+monkeypatch on a bare ``object.__new__(BasicAI)`` instance, called unbound so no
  heavy ``__init__`` runs);
* AST no-cycle guard: ``ai/task_router.py`` has NO module-top runtime import of
  ``ai.basic_ai`` (neither ``import ai.basic_ai`` nor ``from ai.basic_ai import ...`` as
  a direct child of the module body; a ``TYPE_CHECKING``-guarded one would be allowed,
  but there isn't one). ``basic_ai`` imports ``task_router`` LAZILY inside the wrapper,
  so the dependency points one way (basic_ai -> task_router);
* a fresh interpreter can import both modules in EITHER order
  (``ai.task_router`` <-> ``ai.basic_ai``) without a module-load cycle;
* source guard: ``ai/basic_ai.py`` source references ``task_router.update_hero`` (the
  wrapper body), read tolerant of a possible BOM.
"""
from __future__ import annotations

import ast
import inspect
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Headless: the AI path can pull in pygame-touching modules transitively; never bring up
# a real display. We NEVER call BasicAI.__init__ (we use object.__new__).
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import ai.task_router as tr
from ai.basic_ai import BasicAI


# Repo root = one level up from tests/.
_REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# (1) EXISTENCE + SIGNATURE — task_router.update_hero present, callable,
#     exact owner-first signature (ai, hero, dt, view).
# ---------------------------------------------------------------------------
def test_task_router_update_hero_exists_and_callable() -> None:
    assert tr.__name__ == "ai.task_router"
    fn = getattr(tr, "update_hero", None)
    assert fn is not None, "ai.task_router.update_hero is missing"
    assert callable(fn), "ai.task_router.update_hero is not callable"


def test_task_router_update_hero_signature() -> None:
    """The relocated function uses the owner-arg signature: the BasicAI instance is the
    first param ``ai``, followed by ``hero``, ``dt``, ``view``."""
    params = list(inspect.signature(tr.update_hero).parameters)
    assert params == ["ai", "hero", "dt", "view"], (
        f"ai.task_router.update_hero signature is {params!r}; "
        "expected ['ai', 'hero', 'dt', 'view'] (owner-arg pure-move)"
    )


# ---------------------------------------------------------------------------
# (2) WRAPPER DELEGATES — BasicAI.update_hero(self, hero, dt, view) ->
#     task_router.update_hero(self, hero, dt, view).
#
#     Use a bare instance (no __init__) and call the wrapper UNBOUND with that bare
#     instance, monkeypatching tr.update_hero with a recording spy returning a sentinel.
#     The wrapper just forwards self as `ai`; it touches no instance state, so the bare
#     instance is sufficient.
# ---------------------------------------------------------------------------
def test_wrapper_delegates_to_task_router(monkeypatch: pytest.MonkeyPatch) -> None:
    b = object.__new__(BasicAI)  # bare caller, avoids heavy __init__
    hero_marker = object()
    view_marker = object()
    sentinel = object()
    calls: list[tuple] = []

    def spy(*args, **kwargs):  # noqa: ANN002, ANN003 - test spy
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(tr, "update_hero", spy)

    # Unbound call with the bare instance as self.
    result = BasicAI.update_hero(b, hero_marker, 0.05, view_marker)

    assert result is sentinel, "wrapper must return task_router.update_hero's result"
    assert len(calls) == 1, "task_router.update_hero must be called exactly once"
    args, kwargs = calls[0]
    assert args == (b, hero_marker, 0.05, view_marker), (
        "wrapper must forward (self->ai, hero, dt, view) positionally; "
        f"got {args!r}"
    )
    assert not kwargs, f"wrapper forwarded unexpected kwargs: {kwargs!r}"


# ---------------------------------------------------------------------------
# (3) AST NO-CYCLE GUARD — task_router.py has no module-top runtime import of
#     ai.basic_ai (a TYPE_CHECKING-guarded import would be allowed; there is none).
# ---------------------------------------------------------------------------
def test_task_router_has_no_module_top_import_of_basic_ai() -> None:
    src_path = Path(tr.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8"), filename=str(src_path))
    offenders: list[str] = []
    # iter_child_nodes -> module-top statements only; statements inside an
    # ``if TYPE_CHECKING:`` block are NOT direct children of the module, so a
    # TYPE_CHECKING-guarded import is correctly NOT flagged here.
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "ai.basic_ai" or alias.name.startswith("ai.basic_ai."):
                    offenders.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "ai.basic_ai" or mod.startswith("ai.basic_ai."):
                offenders.append(f"from {mod} import ...")
            # also catch `from ai import basic_ai`
            elif mod == "ai":
                for alias in node.names:
                    if alias.name == "basic_ai":
                        offenders.append("from ai import basic_ai")
    assert not offenders, (
        "ai/task_router.py has a module-top (runtime) import of ai.basic_ai "
        f"(would risk a cycle -- basic_ai imports task_router lazily): {offenders}"
    )


# ---------------------------------------------------------------------------
# (4) NO CYCLE — fresh subprocess, BOTH import orders.
#     Run cold so neither module is in sys.modules from this session.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "first,second",
    [
        ("ai.task_router", "ai.basic_ai"),
        ("ai.basic_ai", "ai.task_router"),
    ],
)
def test_fresh_subprocess_imports_both_orders(first: str, second: str) -> None:
    """A fresh interpreter can import both modules in EITHER order without a
    module-load cycle (which a top-level cycle would raise as an ImportError)."""
    env = dict(os.environ)
    env["SDL_VIDEODRIVER"] = "dummy"
    code = (
        "import importlib;"
        f"importlib.import_module({first!r});"
        f"importlib.import_module({second!r});"
        "print('WK120_IMPORT_OK')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert proc.returncode == 0, (
        f"fresh import `{first}` -> `{second}` failed (rc={proc.returncode}).\n"
        f"STDOUT:\n{proc.stdout[-2000:]}\nSTDERR:\n{proc.stderr[-2000:]}"
    )
    assert "WK120_IMPORT_OK" in proc.stdout, (
        f"missing OK marker for `{first}` -> `{second}`.\n"
        f"STDOUT:\n{proc.stdout[-2000:]}\nSTDERR:\n{proc.stderr[-2000:]}"
    )


# ---------------------------------------------------------------------------
# (5) SOURCE GUARD — basic_ai.py wrapper references task_router.update_hero.
# ---------------------------------------------------------------------------
def test_basic_ai_source_references_task_router_update_hero() -> None:
    """Static-source guard: ``ai/basic_ai.py`` source must reference
    ``task_router.update_hero`` (the delegating wrapper body), tolerant of a BOM."""
    src_path = _REPO_ROOT / "ai" / "basic_ai.py"
    assert src_path.exists(), "ai/basic_ai.py missing"
    src = src_path.read_text(encoding="utf-8-sig")
    assert "task_router.update_hero" in src, (
        "ai/basic_ai.py does not reference task_router.update_hero -- the update_hero "
        "wrapper must delegate to the relocated module function"
    )
