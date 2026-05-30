"""WK81 Round D-1 seam tests — MockProvider split into the ``ai/providers/mock/`` package.

WK81 moved the 4 mock LLM responder bodies verbatim out of the 519-LOC
``ai/providers/mock_provider.py`` god-file into focused modules, using the
WK69/WK75-79 pure-move pattern (functions take the live ``MockProvider`` as
``provider``; ``self.`` -> ``provider.``):

* ``ai/providers/mock/autonomous.py``      — ``mock_autonomous_decision(provider, user_prompt)``
* ``ai/providers/mock/direct_prompt.py``   — ``mock_direct_prompt(provider, user_prompt)``
                                             (+ the module helpers ``_hero_ctx_from_prompt_blob`` /
                                             ``_emit_validated_direct`` used only here)
* ``ai/providers/mock/legacy_decision.py`` — ``make_decision(provider, ...)``
* ``ai/providers/mock/conversation.py``    — ``mock_conversation_response(provider, system_prompt, user_prompt)``

``MockProvider`` STAYS in ``ai/providers/mock_provider.py`` as the facade — the
provider registry (``ai/llm_brain.py``) imports it from that path — keeping
``name`` / ``complete`` (the prompt-sniffing dispatcher, unchanged) / ``_norm_msg``
plus a 1-line delegating wrapper of the same name+signature for each moved
responder.

This file is the WAVE-2 (Agent 11 / QA) seam test. It does NOT re-test mock
responder *behavior* — that is covered byte-identically by the full suite, the
WK67 AI-boundary digest (whose hero decisions ARE this mock's output, a PERFECT
guard), and qa_smoke's direct_prompt/conversation scenarios. It proves the *seam*:

1. all four new package modules import and expose their public function;
2. ``MockProvider`` is still importable from ``ai.providers.mock_provider`` (the
   registry path) and exposes ``name`` + ``complete`` + the 4 responder wrappers;
3. each ``MockProvider`` responder wrapper DELEGATES to its package function,
   passing the live ``MockProvider`` as the first positional arg and forwarding the
   call args + return value;
4. an AST/import guard: the package submodules do NOT import
   ``ai.providers.mock_provider`` at module load time (TYPE_CHECKING-only) — i.e.
   no module-level import cycle — AND importing ``ai.providers.mock_provider`` in a
   fresh interpreter does NOT eagerly pull in the ``ai.providers.mock`` submodules
   (the wrappers import the package lazily inside the method body).
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from ai.providers.mock import (  # noqa: E402
    autonomous,
    conversation,
    direct_prompt,
    legacy_decision,
)
from ai.providers.mock_provider import MockProvider  # noqa: E402


# Repo root = two levels up from this test file (tests/ -> repo root).
_REPO_ROOT = Path(__file__).resolve().parent.parent

_MOCK_PROVIDER_TARGET = "ai.providers.mock_provider"


# ---------------------------------------------------------------------------
# 1. All four new package modules import and expose their public function.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "module, expected_name, fn_name",
    [
        (autonomous, "ai.providers.mock.autonomous", "mock_autonomous_decision"),
        (direct_prompt, "ai.providers.mock.direct_prompt", "mock_direct_prompt"),
        (legacy_decision, "ai.providers.mock.legacy_decision", "make_decision"),
        (conversation, "ai.providers.mock.conversation", "mock_conversation_response"),
    ],
)
def test_package_module_exposes_public_fn(module, expected_name, fn_name):
    assert module is not None, f"{expected_name} failed to import"
    assert module.__name__ == expected_name
    fn = getattr(module, fn_name, None)
    assert fn is not None, f"{expected_name}.{fn_name} missing"
    assert callable(fn), f"{expected_name}.{fn_name} is not callable"


# ---------------------------------------------------------------------------
# 2. MockProvider still imports from the registry path and exposes the facade
#    surface: name + complete + the 4 responder wrappers.
# ---------------------------------------------------------------------------

def test_mockprovider_importable_from_registry_path():
    # The provider registry (ai/llm_brain.py) does exactly this import; it must
    # keep working after the split.
    from ai.providers.mock_provider import MockProvider as MP

    provider = MP()
    assert provider.name == "mock"
    assert callable(provider.complete)


@pytest.mark.parametrize(
    "wrapper_name",
    [
        "_mock_autonomous_decision",
        "_mock_direct_prompt",
        "_make_decision",
        "_mock_conversation_response",
    ],
)
def test_mockprovider_has_responder_wrapper(wrapper_name):
    provider = MockProvider()
    wrapper = getattr(provider, wrapper_name, None)
    assert wrapper is not None, f"MockProvider.{wrapper_name} missing"
    assert callable(wrapper), f"MockProvider.{wrapper_name} is not callable"


# ---------------------------------------------------------------------------
# 3. Each MockProvider responder wrapper delegates to its package function,
#    forwarding (provider, *args) and returning the package function's result.
#
# Coverage: all four responder wrappers.
#   autonomous:      _mock_autonomous_decision    -> autonomous.mock_autonomous_decision
#   direct_prompt:   _mock_direct_prompt          -> direct_prompt.mock_direct_prompt
#   legacy_decision: _make_decision               -> legacy_decision.make_decision
#   conversation:    _mock_conversation_response  -> conversation.mock_conversation_response
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "module, fn_name, wrapper_name, call_args",
    [
        (autonomous, "mock_autonomous_decision", "_mock_autonomous_decision", ("PROMPT",)),
        (direct_prompt, "mock_direct_prompt", "_mock_direct_prompt", ("PROMPT",)),
        (
            legacy_decision,
            "make_decision",
            "_make_decision",
            ("brave", 42, True, True, False, True, False, True),
        ),
        (
            conversation,
            "mock_conversation_response",
            "_mock_conversation_response",
            ("SYS", "USER"),
        ),
    ],
)
def test_wrapper_delegates_to_package_function(
    monkeypatch, module, fn_name, wrapper_name, call_args
):
    provider = MockProvider()
    calls = []
    sentinel = object()

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(module, fn_name, spy)

    wrapper = getattr(provider, wrapper_name)
    result = wrapper(*call_args)

    # Wrapper returned exactly what the package function returned.
    assert result is sentinel, f"{wrapper_name} did not forward the return value"

    # Package function fired exactly once.
    assert len(calls) == 1, f"{module.__name__}.{fn_name} fired {len(calls)} times (want 1)"

    args, kwargs = calls[0]
    # First positional arg is the live MockProvider instance.
    assert args[0] is provider, f"{wrapper_name} did not pass the MockProvider as first arg"
    # Remaining args forwarded verbatim (positionally).
    assert args[1:] == call_args, (
        f"{wrapper_name} forwarded {args[1:]!r}, expected {call_args!r}"
    )
    assert kwargs == {}, f"{wrapper_name} forwarded unexpected kwargs {kwargs!r}"


# ---------------------------------------------------------------------------
# 4a. AST/import guard: the package submodules do NOT import
#     ai.providers.mock_provider at module load time (TYPE_CHECKING-only).
#
#     NOTE: legacy_decision.py and conversation.py legitimately lazy-import the
#     shared ``_MOCK_RNG`` singleton from mock_provider *inside* their function
#     bodies (a runtime-lazy import that cannot create a module-level cycle and is
#     the documented WK70 pattern). The AST scan below intentionally only inspects
#     module-top-level imports, so those function-body imports are not flagged.
# ---------------------------------------------------------------------------

_SUBMODULE_PATHS = [
    "ai/providers/mock/autonomous.py",
    "ai/providers/mock/direct_prompt.py",
    "ai/providers/mock/legacy_decision.py",
    "ai/providers/mock/conversation.py",
]


def _module_level_imports_of(path: Path, target: str):
    """Return module-top-level (non-TYPE_CHECKING) imports that reference ``target``.

    Walks only the module body's direct children (and the bodies of any top-level
    ``if`` blocks whose test is NOT ``TYPE_CHECKING``). Imports nested inside function
    or class bodies are *runtime-lazy* and cannot create an import cycle, so they are
    intentionally excluded.
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


@pytest.mark.parametrize("rel_path", _SUBMODULE_PATHS)
def test_no_module_level_mock_provider_import(rel_path):
    path = _REPO_ROOT / rel_path
    assert path.exists(), f"{rel_path} missing"
    offending = _module_level_imports_of(path, _MOCK_PROVIDER_TARGET)
    assert not offending, (
        f"{rel_path} imports {_MOCK_PROVIDER_TARGET} at module load time (import-cycle "
        f"risk); the MockProvider import must be TYPE_CHECKING-only. Offending: {offending}"
    )


@pytest.mark.parametrize("rel_path", _SUBMODULE_PATHS)
def test_type_checking_import_present(rel_path):
    """Sanity: the MockProvider import IS present, but only under TYPE_CHECKING."""
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
                        and sub.module == _MOCK_PROVIDER_TARGET
                    ):
                        tc_imports.append([a.name for a in sub.names])
    assert ["MockProvider"] in tc_imports, (
        f"{rel_path} should TYPE_CHECKING-import MockProvider"
    )


# ---------------------------------------------------------------------------
# 4b. Runtime guard: importing ai.providers.mock_provider in a FRESH interpreter
#     does NOT eagerly import the ai.providers.mock.* responder submodules.
#     (The 4 wrappers import the package lazily inside the method body, so the
#     submodules only load on first responder call.)
# ---------------------------------------------------------------------------

def test_importing_mock_provider_does_not_eagerly_load_submodules():
    code = (
        "import sys\n"
        "import ai.providers.mock_provider as mp\n"
        "assert hasattr(mp, 'MockProvider'), 'MockProvider missing after import'\n"
        "eager = sorted(\n"
        "    m for m in sys.modules\n"
        "    if m == 'ai.providers.mock.autonomous'\n"
        "    or m == 'ai.providers.mock.direct_prompt'\n"
        "    or m == 'ai.providers.mock.legacy_decision'\n"
        "    or m == 'ai.providers.mock.conversation'\n"
        ")\n"
        "assert not eager, 'eagerly imported responder submodules: ' + repr(eager)\n"
        "print('OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        "fresh-import subprocess failed:\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    assert "OK" in proc.stdout, f"unexpected subprocess stdout: {proc.stdout!r}"
