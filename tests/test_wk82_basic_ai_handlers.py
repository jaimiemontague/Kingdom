"""WK82 Round D-2 seam tests — BasicAI inline-handler extraction into ai/behaviors/.

WK82 moved three inline state-machine handler bodies verbatim out of the
~515-LOC ``ai/basic_ai.py`` coordinator into focused behavior modules, using the
WK69/WK75-81 pure-move pattern (functions take the live ``BasicAI`` coordinator
as ``ai``; ``self.`` -> ``ai.``):

* ``ai/behaviors/combat.py``   — ``handle_fighting(ai, hero, view)``
                                  (+ the nested ``_chase_goal_unchanged`` helper)
* ``ai/behaviors/recovery.py`` — ``handle_retreating(ai, hero, view)``
                                  and ``finalize_deferred_task(ai, hero, view)``

``BasicAI`` STAYS in ``ai/basic_ai.py`` as the coordinator — ``update_hero``'s
state-machine dispatch + the WK11 deferred-task path call these by name, so
``BasicAI`` keeps a 1-line delegating wrapper of the same name for each:

* ``handle_fighting``        -> ``combat.handle_fighting``
* ``handle_retreating``      -> ``recovery.handle_retreating``
* ``_finalize_deferred_task``-> ``recovery.finalize_deferred_task``

This file is the WAVE-2 (Agent 11 / QA) seam test. It does NOT re-test the
combat/retreat *behavior* — that is covered byte-identically by the full suite
and the WK67 AI-boundary digest (whose hero combat/retreat decisions ARE these
handlers' output, a PERFECT guard). It proves the *seam*:

1. the two new behavior modules import and expose their public functions;
2. ``BasicAI`` still exposes the three delegating wrappers;
3. each wrapper DELEGATES to its module function, passing the live ``BasicAI``
   as the first positional arg and forwarding ``(hero, view)`` + return value;
4. an AST/import guard: ``combat.py`` + ``recovery.py`` do NOT import
   ``ai.basic_ai`` at module load time (TYPE_CHECKING-only) — i.e. no
   module-level import cycle (the audit warns ``ai.behaviors.__init__`` can pull
   ``llm_bridge``); the wrappers import the behavior module lazily inside the
   method body.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ai.basic_ai import BasicAI
from ai.behaviors import combat, recovery


# Repo root = two levels up from this test file (tests/ -> repo root).
_REPO_ROOT = Path(__file__).resolve().parent.parent

_BASIC_AI_TARGET = "ai.basic_ai"


# ---------------------------------------------------------------------------
# 1. Both new behavior modules import and expose their public function(s).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "module, expected_name, fn_name",
    [
        (combat, "ai.behaviors.combat", "handle_fighting"),
        (recovery, "ai.behaviors.recovery", "handle_retreating"),
        (recovery, "ai.behaviors.recovery", "finalize_deferred_task"),
    ],
)
def test_behavior_module_exposes_public_fn(module, expected_name, fn_name):
    assert module is not None, f"{expected_name} failed to import"
    assert module.__name__ == expected_name
    fn = getattr(module, fn_name, None)
    assert fn is not None, f"{expected_name}.{fn_name} missing"
    assert callable(fn), f"{expected_name}.{fn_name} is not callable"


# ---------------------------------------------------------------------------
# 2. BasicAI still exposes the three delegating wrappers.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "wrapper_name",
    [
        "handle_fighting",
        "handle_retreating",
        "_finalize_deferred_task",
    ],
)
def test_basic_ai_has_wrapper(wrapper_name):
    ai = BasicAI()
    wrapper = getattr(ai, wrapper_name, None)
    assert wrapper is not None, f"BasicAI.{wrapper_name} missing"
    assert callable(wrapper), f"BasicAI.{wrapper_name} is not callable"


# ---------------------------------------------------------------------------
# 3. Each BasicAI wrapper delegates to its behavior-module function,
#    forwarding (ai, hero, view) and returning the module function's result.
#
# Coverage: all three wrappers.
#   combat:   handle_fighting         -> combat.handle_fighting
#   recovery: handle_retreating       -> recovery.handle_retreating
#   recovery: _finalize_deferred_task -> recovery.finalize_deferred_task
#
# The wrappers do a lazy ``from ai.behaviors import combat/recovery`` inside the
# method body and then call ``<module>.<fn>(...)`` — an attribute lookup on the
# module object at call time — so monkeypatching the module attribute is what the
# wrapper resolves.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "module, fn_name, wrapper_name",
    [
        (combat, "handle_fighting", "handle_fighting"),
        (recovery, "handle_retreating", "handle_retreating"),
        (recovery, "finalize_deferred_task", "_finalize_deferred_task"),
    ],
)
def test_wrapper_delegates_to_behavior_function(
    monkeypatch, module, fn_name, wrapper_name
):
    ai = BasicAI()
    hero = object()
    view = object()
    calls = []
    sentinel = object()

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(module, fn_name, spy)

    wrapper = getattr(ai, wrapper_name)
    result = wrapper(hero, view)

    # Wrapper returned exactly what the behavior function returned.
    assert result is sentinel, f"{wrapper_name} did not forward the return value"

    # Behavior function fired exactly once.
    assert len(calls) == 1, (
        f"{module.__name__}.{fn_name} fired {len(calls)} times (want 1)"
    )

    args, kwargs = calls[0]
    # First positional arg is the live BasicAI coordinator instance.
    assert args[0] is ai, f"{wrapper_name} did not pass the BasicAI as first arg"
    # (hero, view) forwarded verbatim (positionally).
    assert args[1] is hero, f"{wrapper_name} did not forward hero"
    assert args[2] is view, f"{wrapper_name} did not forward view"
    assert len(args) == 3, f"{wrapper_name} forwarded extra positional args {args[3:]!r}"
    assert kwargs == {}, f"{wrapper_name} forwarded unexpected kwargs {kwargs!r}"


# ---------------------------------------------------------------------------
# 4a. AST/import guard: combat.py + recovery.py do NOT import ai.basic_ai at
#     module load time (TYPE_CHECKING-only). The behavior modules take the
#     ``ai`` (BasicAI) as a runtime param + import only leaf helpers, so they
#     must never import ai.basic_ai except under ``if TYPE_CHECKING:`` (which is
#     never executed and so cannot create a module-level import cycle).
# ---------------------------------------------------------------------------

_BEHAVIOR_PATHS = [
    "ai/behaviors/combat.py",
    "ai/behaviors/recovery.py",
]


def _module_level_imports_of(path: Path, target: str):
    """Return module-top-level (non-TYPE_CHECKING) imports that reference ``target``.

    Walks only the module body's direct children (and the bodies of any top-level
    ``if`` blocks whose test is NOT ``TYPE_CHECKING``). Imports nested inside
    function or class bodies are *runtime-lazy* and cannot create an import cycle,
    so they are intentionally excluded.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []

    def _scan(import_node):
        if isinstance(import_node, ast.Import):
            for alias in import_node.names:
                if alias.name == target or alias.name.startswith(target + "."):
                    found.append(ast.dump(import_node))
        elif isinstance(import_node, ast.ImportFrom):
            mod = import_node.module or ""
            if mod == target or mod.startswith(target + "."):
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


@pytest.mark.parametrize("rel_path", _BEHAVIOR_PATHS)
def test_no_module_level_basic_ai_import(rel_path):
    path = _REPO_ROOT / rel_path
    assert path.exists(), f"{rel_path} missing"
    offending = _module_level_imports_of(path, _BASIC_AI_TARGET)
    assert not offending, (
        f"{rel_path} imports {_BASIC_AI_TARGET} at module load time (import-cycle "
        f"risk); the BasicAI import must be TYPE_CHECKING-only. Offending: {offending}"
    )


@pytest.mark.parametrize("rel_path", _BEHAVIOR_PATHS)
def test_type_checking_basic_ai_import_present(rel_path):
    """Sanity: the BasicAI import IS present, but only under TYPE_CHECKING."""
    path = _REPO_ROOT / rel_path
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    tc_imports = []
    for node in tree.body:
        if isinstance(node, ast.If):
            test = node.test
            if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
                for sub in node.body:
                    if (
                        isinstance(sub, ast.ImportFrom)
                        and sub.module == _BASIC_AI_TARGET
                    ):
                        tc_imports.append([a.name for a in sub.names])
    assert ["BasicAI"] in tc_imports, (
        f"{rel_path} should TYPE_CHECKING-import BasicAI"
    )
