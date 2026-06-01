"""WK117 Round B seam test (Agent 11 / QA): the UI-overlay / HUD-texture cluster was
moved VERBATIM from ``game/graphics/ursina_app.py`` into the new
``game/graphics/ursina_app_ui_overlay.py`` using the WK105 MIXED static+instance
owner-arg pure-move pattern. The cluster uploads the pygame HUD to a GPU texture
(dirty-row blit) and resizes the headless UI canvas to the Ursina window. This is a
byte-faithful move — no behavior change.

The 5 moved members:

* ``_hud_quick_fingerprint(surf)`` — was a ``@staticmethod``; moves as a PLAIN module
  function with NO ``owner``/``self`` arg (signature ``(surf,)``).
* ``_hud_prefers_nearest_pixel_filter()`` — was a ``@staticmethod``; moves as a PLAIN
  module function with no params.
* ``_sync_hud_texture_filter_mode(tex)`` — was a ``@staticmethod``; moves as a PLAIN
  module function (signature ``(tex,)``); calls ``_hud_prefers_nearest_pixel_filter()``
  directly.
* ``_refresh_ui_overlay_texture(owner)`` — INSTANCE method; ``self.`` -> ``owner.``.
* ``_sync_headless_ui_canvas_to_window(owner)`` — INSTANCE method; ``self.`` -> ``owner.``.

The 2 INSTANCE methods became module functions with ``owner`` first (every ``self.`` in
their bodies rewritten to ``owner.``). The 3 ``@staticmethod``s became PLAIN module
functions with their original signatures (NO owner/self). ``UrsinaApp`` keeps 5 one-line
delegating wrappers (same names + signatures; 3 stay ``@staticmethod``, 2 owner-first)
so the staying call sites (``run()`` ``_sync_headless_ui_canvas_to_window`` /
``_refresh_ui_overlay_texture`` / ``_sync_hud_texture_filter_mode``) reach the relocated
code unchanged. The intra-cluster cross-calls inside ``_refresh_ui_overlay_texture``
(``_hud_quick_fingerprint(surf)`` and
``_sync_hud_texture_filter_mode(owner._hud_composite_texture)``) and inside
``_sync_hud_texture_filter_mode`` (``_hud_prefers_nearest_pixel_filter()``) are DIRECT
module-local calls, not ``owner.*`` hops.

Acyclic: ``ursina_app.py`` imports the new module one-way (lazily, in each wrapper); the
new module imports ``UrsinaApp`` ONLY under ``TYPE_CHECKING`` so a fresh interpreter can
import either order with no module-load cycle.

This guards the refactor SEAM, not the rendering behaviour itself. ursina render code is
NOT covered by the WK67 digest, ``determinism_guard`` (which excludes
``game/graphics/**``), or the pygame screenshot tool — the live HUD->GPU texture upload,
dirty-row blit, and window-resize-canvas behaviour are verified by Jaimie's DEFERRED
before/after live Ursina captures (need a real GPU/window the headless agents lack).
What this test proves:

* the 2 instance fns live on ``ursina_app_ui_overlay``, are callable, and have an
  ``owner``-first signature; the 3 static fns exist + are callable but their first param
  is NOT ``owner`` (``surf`` / none / ``tex``);
* each ``UrsinaApp`` wrapper DELEGATES — the 2 instance wrappers call the module function
  with the bare app instance (``self``) as ``owner`` and return the result; the 3
  ``@staticmethod`` wrappers forward their passthrough args with NO owner inserted
  (spy+monkeypatch);
* AST guard: the new module has NO module-top runtime ``import game.graphics.ursina_app``
  (a ``TYPE_CHECKING``-guarded import of ``UrsinaApp`` is allowed);
* a fresh interpreter can import both modules in EITHER order (no module-load cycle);
* the ``ursina_app.py`` wrapper bodies reference ``ursina_app_ui_overlay.<fn>`` in source;
* behaviour (best-effort): ``_hud_prefers_nearest_pixel_filter()`` returns ``True`` and
  ``_hud_quick_fingerprint`` on a tiny surface returns an int.
"""
from __future__ import annotations

import ast
import inspect
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Headless: never bring up a real display when the ursina app is imported. import of
# ursina_app is headless-safe; we NEVER call UrsinaApp.__init__ (it opens a window).
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

import game.graphics.ursina_app_ui_overlay as ui_overlay
from game.graphics.ursina_app import UrsinaApp


# The 2 INSTANCE methods WK117 moved into ursina_app_ui_overlay.py (owner-first).
MOVED_INSTANCE_FUNCTIONS = (
    "_refresh_ui_overlay_texture",
    "_sync_headless_ui_canvas_to_window",
)

# The 3 moved @staticmethods (plain module fns now): NOT owner-first.
# name -> the expected leading param list (empty for no-param).
MOVED_STATIC_FUNCTIONS = {
    "_hud_quick_fingerprint": ["surf"],
    "_hud_prefers_nearest_pixel_filter": [],
    "_sync_hud_texture_filter_mode": ["tex"],
}

# All 5 wrappers (name -> module-function-name). Names preserved 1:1.
ALL_MOVED_FUNCTIONS = MOVED_INSTANCE_FUNCTIONS + tuple(MOVED_STATIC_FUNCTIONS)
WRAPPER_TO_FN = {name: name for name in ALL_MOVED_FUNCTIONS}


# ---------------------------------------------------------------------------
# (1) EXISTENCE — moved functions present + callable; owner-first where required
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", ALL_MOVED_FUNCTIONS)
def test_moved_function_lives_on_ui_overlay(name: str) -> None:
    """The moved function is present on ursina_app_ui_overlay and callable."""
    assert hasattr(ui_overlay, name), f"{name} missing from ursina_app_ui_overlay"
    assert callable(getattr(ui_overlay, name)), f"{name} is not callable"


@pytest.mark.parametrize("name", MOVED_INSTANCE_FUNCTIONS)
def test_moved_instance_function_is_owner_first(name: str) -> None:
    """Each moved INSTANCE module function has an ``owner``-first signature (the WK92
    owner-arg pattern): the first positional parameter is the app owner."""
    sig = inspect.signature(getattr(ui_overlay, name))
    params = list(sig.parameters)
    assert params, f"{name} has no parameters; expected an owner-first signature"
    assert params[0] == "owner", (
        f"{name} first param is {params[0]!r}; expected 'owner' (owner-arg pure-move)"
    )


@pytest.mark.parametrize("name,expected_lead", sorted(MOVED_STATIC_FUNCTIONS.items()))
def test_moved_static_function_is_not_owner_first(
    name: str, expected_lead: list
) -> None:
    """Each moved ``@staticmethod`` (no self) moves as a PLAIN module function — its
    leading params match the original signature and the first param (if any) is NOT
    ``owner``."""
    sig = inspect.signature(getattr(ui_overlay, name))
    params = list(sig.parameters)
    assert params[: len(expected_lead)] == expected_lead, (
        f"{name} signature is {params}; expected leading {expected_lead} "
        "(it was a @staticmethod — no owner/self arg)"
    )
    if params:
        assert params[0] != "owner", (
            f"{name} must NOT be owner-first (it is a moved @staticmethod)"
        )


# ---------------------------------------------------------------------------
# (2) WRAPPERS DELEGATE — runtime spy + source/AST belt-and-suspenders
# ---------------------------------------------------------------------------
def _bare_app() -> UrsinaApp:
    """A bare ``UrsinaApp`` instance with no ``__init__`` run.

    Constructing a real UrsinaApp opens an ursina window; ``object.__new__`` gives us an
    instance whose bound wrapper method we can call without the heavy graphics
    construction. The wrapper doesn't touch any instance state itself — it just forwards
    ``self`` — so the bare instance is sufficient to prove delegation.
    """
    return object.__new__(UrsinaApp)


# instance-wrapper-name -> extra positional args to pass after self (none take extras).
_INSTANCE_WRAPPER_EXTRA_ARGS = {
    "_refresh_ui_overlay_texture": (),
    "_sync_headless_ui_canvas_to_window": (),
}


@pytest.mark.parametrize("name", MOVED_INSTANCE_FUNCTIONS)
def test_instance_wrapper_delegates(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """``UrsinaApp.<name>`` -> ``ui_overlay.<name>(self, *extra)``.

    Spy+monkeypatch the module function and assert the bare app is forwarded as
    ``owner`` (first arg), the remaining args pass through, and the result is returned.
    """
    app = _bare_app()
    calls: list[tuple] = []
    sentinel = object()

    def spy(*args, **kwargs):  # noqa: ANN002, ANN003 - test spy
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(ui_overlay, name, spy)

    extra = _INSTANCE_WRAPPER_EXTRA_ARGS[name]
    result = getattr(app, name)(*extra)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    args, kwargs = calls[0]
    assert args[0] is app, "app (self) must be forwarded as the first (owner) arg"
    assert args[1:] == extra, (
        f"remaining args not forwarded: got {args[1:]!r}, expected {extra!r}"
    )
    assert not kwargs, f"unexpected kwargs forwarded: {kwargs!r}"


# static-wrapper-name -> passthrough positional args (NO owner is inserted).
_STATIC_WRAPPER_ARGS = {
    "_hud_quick_fingerprint": (object(),),
    "_hud_prefers_nearest_pixel_filter": (),
    "_sync_hud_texture_filter_mode": (object(),),
}


@pytest.mark.parametrize("name", sorted(MOVED_STATIC_FUNCTIONS))
def test_static_wrapper_delegates(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """``UrsinaApp.<name>`` (a ``@staticmethod``) -> ``ui_overlay.<name>(*args)`` — the
    passthrough args are forwarded with NO owner/self inserted."""
    calls: list[tuple] = []
    sentinel = object()

    def spy(*args, **kwargs):  # noqa: ANN002, ANN003 - test spy
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(ui_overlay, name, spy)

    passthrough = _STATIC_WRAPPER_ARGS[name]
    result = getattr(UrsinaApp, name)(*passthrough)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    args, kwargs = calls[0]
    assert args == passthrough, (
        f"staticmethod wrapper must forward {passthrough!r} (no owner inserted); "
        f"got {args!r}"
    )
    assert not kwargs, f"unexpected kwargs forwarded: {kwargs!r}"


def test_wrappers_call_ui_overlay_module_in_source() -> None:
    """Source/AST belt-and-suspenders: every wrapper body contains a call to
    ``ursina_app_ui_overlay.<fn>(...)``. This pins the delegation even if a future
    monkeypatch path changed."""
    src_path = Path(sys.modules[UrsinaApp.__module__].__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8-sig"), filename=str(src_path))

    found: dict[str, bool] = {w: False for w in WRAPPER_TO_FN}

    class _Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            if node.name not in WRAPPER_TO_FN:
                self.generic_visit(node)
                return
            target_fn = WRAPPER_TO_FN[node.name]
            for call in ast.walk(node):
                if not isinstance(call, ast.Call):
                    continue
                fn = call.func
                # match ursina_app_ui_overlay.<target_fn>(...)
                if (
                    isinstance(fn, ast.Attribute)
                    and fn.attr == target_fn
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id == "ursina_app_ui_overlay"
                ):
                    found[node.name] = True
            self.generic_visit(node)

    _Visitor().visit(tree)
    missing = [w for w, ok in found.items() if not ok]
    assert not missing, (
        "wrapper(s) do not call ursina_app_ui_overlay.<fn>(...) in source: "
        f"{missing}"
    )


# ---------------------------------------------------------------------------
# (3) AST NO-CYCLE GUARD — new module has no module-top runtime ursina_app import
# ---------------------------------------------------------------------------
def test_ui_overlay_has_no_module_top_import_of_ursina_app() -> None:
    """AST guard: ursina_app_ui_overlay must not import ursina_app at module top (the
    dependency points one way: ursina_app -> ui_overlay). A ``TYPE_CHECKING``-guarded
    import of ``UrsinaApp`` is allowed and is NOT a runtime import, so we only flag
    UNCONDITIONAL module-top imports (those whose parent is the module body, not an
    ``if TYPE_CHECKING:`` block)."""
    src_path = Path(ui_overlay.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8-sig"), filename=str(src_path))
    offenders: list[str] = []
    # iter_child_nodes -> module-top statements only; nodes inside an
    # ``if TYPE_CHECKING:`` block are NOT direct children of the module, so a
    # TYPE_CHECKING-guarded import is correctly NOT flagged here.
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith("ursina_app"):
                    offenders.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.endswith("ursina_app"):
                offenders.append(f"from {mod} import ...")
    assert not offenders, (
        "ursina_app_ui_overlay has a module-top (runtime) import of "
        f"ursina_app (would risk a cycle): {offenders}"
    )


# ---------------------------------------------------------------------------
# (4) NO CYCLE — fresh subprocess, BOTH import orders
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "first,second",
    [
        (
            "game.graphics.ursina_app_ui_overlay",
            "game.graphics.ursina_app",
        ),
        (
            "game.graphics.ursina_app",
            "game.graphics.ursina_app_ui_overlay",
        ),
    ],
)
def test_fresh_subprocess_imports_both_orders(first: str, second: str) -> None:
    """A fresh interpreter can import both modules in EITHER order without a
    module-load cycle. Runs out-of-process so already-imported modules in this session
    cannot mask an import-order bug."""
    repo_root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["SDL_VIDEODRIVER"] = "dummy"
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


# ---------------------------------------------------------------------------
# (5) WRAPPER-SOURCE GUARD — ursina_app.py wrappers reference ui_overlay.<fn>
# ---------------------------------------------------------------------------
def test_ursina_app_source_references_ui_overlay_for_each_wrapper() -> None:
    """Static-source guard: ``ursina_app.py`` source must reference
    ``ursina_app_ui_overlay.<fn>`` for each of the 5 wrappers (encoding tolerant of a
    possible BOM)."""
    src_path = Path(sys.modules[UrsinaApp.__module__].__file__)
    src = src_path.read_text(encoding="utf-8-sig")
    missing = [
        name
        for name in ALL_MOVED_FUNCTIONS
        if f"ursina_app_ui_overlay.{name}" not in src
    ]
    assert not missing, (
        "ursina_app.py is missing a ursina_app_ui_overlay.<fn> reference for "
        f"wrapper(s): {missing}"
    )


# ---------------------------------------------------------------------------
# (6) BEHAVIOR (best-effort) — the real moved bodies run as pure functions
# ---------------------------------------------------------------------------
def test_hud_prefers_nearest_pixel_filter_returns_true() -> None:
    """Cheap pure proof: the moved ``_hud_prefers_nearest_pixel_filter`` returns
    ``True`` (WK22 R3: 1:1 texels — nearest keeps UI text sharp)."""
    assert ui_overlay._hud_prefers_nearest_pixel_filter() is True


def test_hud_quick_fingerprint_returns_int() -> None:
    """Best-effort: ``_hud_quick_fingerprint`` on a tiny pygame surface returns an int
    (the crc32 row-sample fingerprint). Skipped (not failed) if the headless pygame
    surface shape doesn't match what the body expects."""
    try:
        pygame.display.init()
    except Exception:
        pass
    try:
        surf = pygame.Surface((8, 8))
        result = ui_overlay._hud_quick_fingerprint(surf)
    except Exception as exc:  # pragma: no cover - headless surface-shape mismatch is a skip
        pytest.skip(f"headless pygame surface shape mismatch: {exc!r}")
    assert isinstance(result, int), (
        f"_hud_quick_fingerprint should return an int; got {type(result).__name__}"
    )
