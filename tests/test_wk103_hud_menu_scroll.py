"""WK103 Round B-20 seam test: hud_menu_scroll.py extraction.

Guards the WK103 split of the mouse-wheel menu-scroll router
(is_mouse_over_menu / scroll_active_menu / handle_menu_scroll) out of
game/ui/hud.py into game/ui/hud_menu_scroll.py behind 1-line delegating
wrappers. Verifies: (1) the 3 module fns exist with the hud-first signature,
(2) the 3 HUD wrappers delegate to the module, (3) no import cycle
(AST + both fresh-subprocess import orders), (4) wheel routing behaves
identically (hero-menu path + building-panel path + early-outs).
"""

import ast
import inspect
import os
import subprocess
import sys
import types

import pygame

# Headless: no real display required.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import game.ui.hud_menu_scroll as hud_menu_scroll  # noqa: E402

_MODULE_FILE = os.path.abspath(hud_menu_scroll.__file__)
_FN_NAMES = ("is_mouse_over_menu", "scroll_active_menu", "handle_menu_scroll")


# ---------------------------------------------------------------------------
# (1) EXISTENCE -- the 3 module fns exist with a hud-first signature.
# ---------------------------------------------------------------------------
def test_module_functions_exist_with_hud_first_signature():
    for name in _FN_NAMES:
        assert hasattr(hud_menu_scroll, name), f"missing module fn {name}"
        fn = getattr(hud_menu_scroll, name)
        assert callable(fn), f"{name} is not callable"
        params = list(inspect.signature(fn).parameters)
        assert params, f"{name} has no parameters"
        assert params[0] == "hud", f"{name} first param is {params[0]!r}, expected 'hud'"


# ---------------------------------------------------------------------------
# (2) WRAPPERS DELEGATE -- the 3 HUD wrappers call the module fns.
# ---------------------------------------------------------------------------
def test_hud_wrappers_delegate_to_module(monkeypatch):
    from game.ui.hud import HUD

    pygame.init()
    hud = HUD(1920, 1080)

    # is_mouse_over_menu wrapper -> module fn
    for name in _FN_NAMES:
        assert hasattr(HUD, name), f"HUD missing wrapper {name}"

    fired = {"is_mouse_over_menu": False, "scroll_active_menu": False, "handle_menu_scroll": False}

    def make_sentinel(key, ret):
        def _sentinel(*args, **kwargs):
            fired[key] = True
            return ret
        return _sentinel

    monkeypatch.setattr(hud_menu_scroll, "is_mouse_over_menu", make_sentinel("is_mouse_over_menu", "IS_SENTINEL"))
    monkeypatch.setattr(hud_menu_scroll, "scroll_active_menu", make_sentinel("scroll_active_menu", "SCROLL_SENTINEL"))
    monkeypatch.setattr(hud_menu_scroll, "handle_menu_scroll", make_sentinel("handle_menu_scroll", "HANDLE_SENTINEL"))

    assert hud.is_mouse_over_menu((0, 0), {}, None) == "IS_SENTINEL"
    assert fired["is_mouse_over_menu"] is True

    assert hud.scroll_active_menu(1, (0, 0), {}, None) == "SCROLL_SENTINEL"
    assert fired["scroll_active_menu"] is True

    # PUBLIC handle_menu_scroll -- the input_handler.py:127 / ursina_app.py:830 entry point.
    assert hud.handle_menu_scroll((0, 0), 1, {}, None) == "HANDLE_SENTINEL"
    assert fired["handle_menu_scroll"] is True


# ---------------------------------------------------------------------------
# (3) AST NO-CYCLE GUARD -- no module-top hud import; both fresh orders import.
# ---------------------------------------------------------------------------
def test_no_module_top_hud_import_ast():
    with open(_MODULE_FILE, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=_MODULE_FILE)

    def _is_type_checking_node(node):
        # Permit `if TYPE_CHECKING:` guarded imports.
        if not isinstance(node, ast.If):
            return False
        test = node.test
        if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
            return True
        if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
            return True
        return False

    offending = []
    for node in tree.body:
        # TYPE_CHECKING-guarded `from game.ui.hud import HUD` is allowed -- skip those.
        if _is_type_checking_node(node):
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "game.ui.hud" or alias.name.startswith("game.ui.hud."):
                    offending.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "game.ui.hud":
                offending.append(node.module)

    assert not offending, f"module-top game.ui.hud import(s) found (cycle risk): {offending}"


def test_both_import_orders_fresh_subprocess():
    order_a = "import game.ui.hud_menu_scroll; import game.ui.hud; print('ok1')"
    order_b = "import game.ui.hud; import game.ui.hud_menu_scroll; print('ok2')"

    # _MODULE_FILE is .../<repo>/game/ui/hud_menu_scroll.py -> climb 3 dirs to repo root.
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(_MODULE_FILE)))
    env = dict(os.environ)
    env.setdefault("SDL_VIDEODRIVER", "dummy")

    res_a = subprocess.run(
        [sys.executable, "-c", order_a],
        cwd=repo_root, env=env, capture_output=True, text=True,
    )
    assert res_a.returncode == 0, f"order A failed: {res_a.stderr}"
    assert "ok1" in res_a.stdout

    res_b = subprocess.run(
        [sys.executable, "-c", order_b],
        cwd=repo_root, env=env, capture_output=True, text=True,
    )
    assert res_b.returncode == 0, f"order B failed: {res_b.stderr}"
    assert "ok2" in res_b.stdout


# ---------------------------------------------------------------------------
# (4) BEHAVIOR -- wheel routing identical (mirrors test_wk52_r10 setup).
# ---------------------------------------------------------------------------
def test_behavior_hero_menu_and_building_panel_paths():
    from game.ui.hud import HUD

    pygame.init()
    hud = HUD(1920, 1080)

    lr = pygame.Rect(0, 48, 224, 400)
    hud._last_left_rect = lr
    gs = {"selected_hero": object(), "selected_peasant": None, "selected_building": None}

    # is_mouse_over_menu: inside the left rect (hero menu) -> True; outside -> False.
    assert hud.is_mouse_over_menu((lr.centerx, lr.centery), gs, None) is True
    assert hud.is_mouse_over_menu((lr.right + 80, lr.centery), gs, None) is False

    # handle_menu_scroll: hero-menu path consumes; outside the rect -> False;
    # wheel_y == 0 -> early-out False.
    assert hud.handle_menu_scroll((lr.centerx, lr.centery), 1, gs, None) is True
    assert hud.handle_menu_scroll((lr.right + 50, lr.centery), 1, gs, None) is False
    assert hud.handle_menu_scroll((lr.centerx, lr.centery), 0, gs, None) is False

    # scroll_active_menu: direction +1 -> wheel_y -1 -> consumes; direction 0 -> False.
    assert hud.scroll_active_menu(1, (lr.centerx, lr.centery), gs, None) is True
    assert hud.scroll_active_menu(0, (lr.centerx, lr.centery), gs, None) is False

    # BUILDING-PANEL path: stub panel that reports a hit + consumes the wheel.
    bp = types.SimpleNamespace(
        visible=True,
        selected_building=object(),
        panel_x=1600,
        panel_y=100,
        panel_width=300,
        panel_height=400,
        apply_menu_scroll=lambda wy: True,
    )
    assert hud.handle_menu_scroll((1750, 300), 1, {}, bp) is True
