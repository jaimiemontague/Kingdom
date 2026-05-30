"""WK67 Round A-2 — AI-boundary characterization pins.

These pins are written in **Wave 0, before any production-code change**, and are
the contract that proves the WK67 moves (4 presentation-split, 5 AiGameView /
WorldView, 6 HeroCommand) are *behavior-preserving*. Two of them MUST be GREEN
on the current unmodified code (the keystone AI-decision digest + the
shopping-purchase parity); the other two are written now but ``xfail`` until the
wave that introduces the new contract surface flips them green.

Pin map (see ``.cursor/plans/wk67_round_a2_ai_boundary.plan.md`` "Wave 0 — Agent 11"):

1. ``test_ai_decision_digest_is_stable`` — **THE keystone**. A deterministic
   (``DETERMINISTIC_SIM=1``, seed 3) headless ``GameEngine`` with three seeded
   heroes runs a fixed 300 ticks; a sha256 over every hero's
   ``(hero_id, x, y, state, intent, target-type, gold)`` plus the economy
   transaction-log length / total-spent / wave each tick is asserted equal to a
   recorded constant. This digest MUST stay byte-identical through Move 5
   (AiGameView read swap) and Move 6 (HeroCommand write swap). A changed digest
   means the boundary change altered AI behavior — STOP and report.

2. ``test_shopping_purchase_parity`` — **GREEN on current code**. Drives
   ``ai.behaviors.shopping.do_shopping`` for a real ``Hero`` with known gold at a
   shop with known items, against a real ``EconomySystem``, and pins the
   resulting hero gold / potions / weapon / armor + the full
   ``economy.transaction_log`` (hero/item/price/tax) + ``total_spent_by_heroes``.
   This is the exact multi-item gold-gating contract Move 6 (HeroCommand) must
   preserve, since the applier mutates synchronously between purchases.

3. ``test_ai_view_purity`` — **xfail until Wave 2 (Move 5)**. After Move 5 the
   sim hands the AI an ``AiGameView`` that (a) carries no economy/sim/engine,
   (b) exposes ``world`` as a read-only ``WorldView`` (not the live ``World``),
   (c) is constructible from a headless engine via ``build_ai_view``. Flip to
   GREEN (remove the xfail) when ``game.sim.ai_view`` lands and 03/06 migrate.

4. ``test_frame_state_split`` — **xfail until Wave 1 (Move 4)**. After Move 4,
   ``build_snapshot()`` takes no presentation kwargs and returns a
   ``RenderSnapshot`` (sim truth: live tuples + DTO tuples), and the engine
   builds a ``PresentationFrameState`` carrying camera/zoom/paused/selection.
   Flip to GREEN when ``RenderSnapshot``/``PresentationFrameState`` land.

WK66/WK65 cross-check: ``test_wk66_render_boundary.py`` and
``test_wk65_snapshot_no_mutation.py`` must still pass after every WK67 wave; they
are run, not duplicated, here (see the module docstring of each).

Style mirrors ``tests/test_engine.py`` / ``tests/test_wk66_render_boundary.py``:
``GameEngine(headless=True)`` + ``pygame.quit()`` in a finally, plus the WK66
per-test render-cache hygiene fixture (the parity pin constructs a real ``Hero``,
which touches the same global sprite/font caches).

----------------------------------------------------------------------------
WK67-W0 PM NOTE — pre-existing nondeterminism (RECORDED, NOT masked)
----------------------------------------------------------------------------
The AI patrol/wander stream is the module-level shared RNG
``ai.basic_ai._AI_RNG = get_rng("ai_basic")``, created once at import time and
assigned to every ``BasicAI`` instance (``self._ai_rng = _AI_RNG``). It is
**never re-seeded** when a new ``GameEngine``/``BasicAI`` is built, so across
repeated *in-process* engine constructions its sequence keeps advancing from
where the previous build's tick loop left it. Result: with seeded heroes, the
AI-decision digest drifts build-to-build within one process (observed three
distinct digests over three back-to-back builds; first-build value is stable).
This is the SAME family as the WK66 ``_fog_revision`` ±1 carry-over and the
WK65 ``tests/test_spawner.py`` order-dependent global-rebind. The keystone
digest helper therefore **explicitly re-seeds ``_AI_RNG`` (and the controller's
``_ai_rng``) to the sim seed** at the start of each build so the digest is a
byte-stable guardrail; this lives entirely in the test and touches no production
code. Agent 04/03 should be aware of this carry-over when re-running the digest
at the AI gates, and PM may want to file the ``_AI_RNG`` non-reseed as a
follow-up determinism fix (it is independent of the WK67 boundary moves).

A SECOND global leak in the same family: ``RESEARCH_UNLOCKS`` (a module-level
dict in ``game/entities/buildings/base.py``) is mutated by ``unlock_research()``
and is never reset between tests. When a *prior* suite test unlocks
"Weapon Upgrades"/"Armor Upgrades", the blacksmith's ``get_available_items()``
catalogue changes, which shifts hero shopping/decisions and drifts this digest
by suite order (observed: the keystone passed in isolation but failed in the
full suite until reset). ``_build_digest_engine`` therefore also resets
``RESEARCH_UNLOCKS`` to all-False. Both resets live entirely in the test and
touch no production code. PM follow-up candidates: re-seed ``_AI_RNG`` per
``BasicAI`` build, and add a research-state reset fixture / per-engine research
state (both are latent test-isolation gaps, independent of WK67).

A THIRD, process-level vector (the one that actually broke the full suite, vs
isolated runs): ``tests/perf_ursina_stress.py`` and ``tests/perf_stress_test.py``
set ``os.environ["SIM_SEED"] = "42"`` at *import* time. pytest collection imports
those modules, so by the time the keystone runs, the parent process env has
``SIM_SEED=42``. Because ``config.SIM_SEED`` is read from the env at import and
``SimEngine`` re-applies it during construction (overriding any in-test
``set_sim_seed``), the digest would shift by collection order. The keystone is
therefore computed in a fresh subprocess whose env pins ``SIM_SEED`` (and
``DETERMINISTIC_SIM=1``) explicitly to the digest seed — see
``_compute_digest_in_subprocess``. This is the load-bearing reason the keystone
uses a subprocess rather than an in-process build. PM follow-up: those perf
modules should set ``SIM_SEED`` inside their fixtures/tests, not at module top,
so collection no longer mutates the shared process env (latent isolation gap,
independent of WK67).
"""

from __future__ import annotations

import hashlib
import os

import pygame
import pytest

# Headless-friendly drivers so sprite/font loads (real Hero construction) work
# without a real display — mirrors tools/capture_screenshots.py and the WK66 pins.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from config import TILE_SIZE
from game.engine import GameEngine


# ---------------------------------------------------------------------------
# Per-test render/font cache hygiene (shared with WK66 — see that file's note)
# ---------------------------------------------------------------------------
#
# Constructing a real Hero (parity pin) and running the engine populates
# module-global pygame.Surface/Font caches that, if left across a pygame.quit(),
# can be reused by a later suite test on a torn-down SDL session and corrupt the
# heap. Drop them after every test in this module. Adds cleanup only; touches no
# assertion or scenario.


def _clear_global_render_caches() -> None:
    try:
        from game.graphics import font_cache as _fc

        _fc._FONT_CACHE.clear()
        _fc._TEXT_CACHE.clear()
        _fc._TEXT_SHADOW_CACHE.clear()
    except Exception:
        pass
    import importlib

    for module_name, cls_name in (
        ("game.graphics.hero_sprites", "HeroSpriteLibrary"),
        ("game.graphics.enemy_sprites", "EnemySpriteLibrary"),
        ("game.graphics.worker_sprites", "WorkerSpriteLibrary"),
        ("game.graphics.building_sprites", "BuildingSpriteLibrary"),
    ):
        try:
            cache = getattr(getattr(importlib.import_module(module_name), cls_name), "_cache")
            cache.clear()
        except Exception:
            pass
    try:
        from game.graphics import ui_icons as _icons

        _icons._type_cache.clear()
        _icons._tier_cache.clear()
        _icons._badge_cache.clear()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _render_resource_hygiene():
    yield
    _clear_global_render_caches()
    try:
        if pygame.display.get_init():
            pygame.display.quit()
    except Exception:
        pass
    try:
        pygame.quit()
    except Exception:
        pass


# ===========================================================================
# Pin 1 — AI-decision digest (THE keystone; GREEN on current code)
# ===========================================================================
#
# Golden captured from current HEAD code (seed 3, DETERMINISTIC_SIM=1, 300 ticks,
# three seeded heroes, with the shared AI RNG re-seeded — see the PM NOTE above).
# This MUST stay byte-identical through Move 5 (AiGameView) and Move 6
# (HeroCommand). If it changes, the boundary change altered AI behavior.
_AI_DECISION_DIGEST = "b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded"
_AI_DIGEST_TICKS = 300
_AI_DIGEST_SEED = 3


def _seed_digest_heroes(engine: GameEngine) -> None:
    """Add three deterministic heroes of distinct classes near the castle.

    The base headless engine spawns buildings but no heroes (heroes require a
    guild + the player loop), so the per-hero portion of the digest would be
    empty without this. Seeding three classes exercises the patrol/idle/journey
    decision paths the digest is meant to guard.
    """
    from game.entities.hero import Hero

    castle = next(b for b in engine.buildings if getattr(b, "building_type", None) == "castle")
    cx = float(castle.center_x)
    cy = float(castle.center_y)
    engine.heroes.append(
        Hero(cx + 2 * TILE_SIZE, cy, hero_class="warrior", hero_id="wk67_digest_h1", name="Aldous")
    )
    engine.heroes.append(
        Hero(cx - 2 * TILE_SIZE, cy + TILE_SIZE, hero_class="ranger", hero_id="wk67_digest_h2", name="Brina")
    )
    engine.heroes.append(
        Hero(cx, cy - 3 * TILE_SIZE, hero_class="cleric", hero_id="wk67_digest_h3", name="Cora")
    )


def _build_digest_engine() -> GameEngine:
    """A seeded headless engine with a deterministic AI controller and heroes.

    Re-seeds BOTH the gameplay RNG (``set_sim_seed``) and the shared module-level
    AI RNG (``ai.basic_ai._AI_RNG`` + the controller's ``_ai_rng``) so the patrol
    stream is independent of import time and prior in-process builds (see the PM
    NOTE in the module docstring). This re-seed is the only thing that makes the
    keystone digest byte-stable across builds; it lives in the test, not in
    production code, so Move 5/6 do not change it.
    """
    import ai.basic_ai as basic_ai
    import game.entities.buildings.base as buildings_base
    from ai.basic_ai import BasicAI
    from game.sim.determinism import set_sim_seed

    set_sim_seed(_AI_DIGEST_SEED)
    basic_ai._AI_RNG.seed(_AI_DIGEST_SEED)
    # Reset the module-level research-unlock dict. It is global mutable state
    # (game/entities/buildings/base.py:RESEARCH_UNLOCKS); a *prior* suite test
    # that calls unlock_research() and never resets it would otherwise change the
    # blacksmith catalogue and shift hero shopping/decisions, drifting this
    # digest by suite order. This is the SAME class of pre-existing global-state
    # leak as the _AI_RNG carry-over (see the module docstring PM NOTE).
    for _research_key in buildings_base.RESEARCH_UNLOCKS:
        buildings_base.RESEARCH_UNLOCKS[_research_key] = False
    engine = GameEngine(headless=True)
    engine.ai_controller = BasicAI(llm_brain=None)
    engine.ai_controller._ai_rng.seed(_AI_DIGEST_SEED)
    _seed_digest_heroes(engine)
    return engine


def _ai_digest(engine: GameEngine, ticks: int = _AI_DIGEST_TICKS) -> str:
    """Hash the per-tick AI-decision state of every hero + economy + wave.

    Per hero: (hero_id, round(x,3), round(y,3), state, intent, target-type, gold).
    Plus: economy transaction-log length, total_spent_by_heroes, and wave number.
    This is the exact shape the WK67 plan locks (plan "Wave 0 — Agent 11").
    """
    h = hashlib.sha256()
    for _ in range(ticks):
        engine.update(1 / 60)
        for hero in sorted(engine.sim.heroes, key=lambda x: getattr(x, "hero_id", "")):
            target = getattr(hero, "target", None)
            target_type = target.get("type") if isinstance(target, dict) else str(target)
            h.update(
                repr(
                    (
                        getattr(hero, "hero_id", ""),
                        round(hero.x, 3),
                        round(hero.y, 3),
                        str(getattr(hero, "state", None)),
                        str(getattr(hero, "current_intent", "")),
                        str(target_type),
                        int(getattr(hero, "gold", 0)),
                    )
                ).encode()
            )
        econ = engine.sim.economy
        h.update(
            repr(
                (
                    len(econ.transaction_log),
                    econ.total_spent_by_heroes,
                    engine.sim.spawner.wave_number,
                )
            ).encode()
        )
    return h.hexdigest()


_DIGEST_STDOUT_MARKER = "WK67_AI_DECISION_DIGEST="


def _compute_digest_in_subprocess() -> str:
    """Run the digest in a FRESH interpreter and return it.

    WHY A SUBPROCESS (not just in-process re-seeds): the AI decision path reads
    several pieces of module-level mutable global state that other suite tests
    mutate and never reset (``_AI_RNG``, ``RESEARCH_UNLOCKS``, and at least one
    more — see the PM NOTE). ``_build_digest_engine`` resets the known ones, but
    making the keystone *bulletproof against arbitrary suite ordering* means
    computing it in a clean process where NO prior test has run. The subprocess
    runs THIS file as ``python -m`` (its ``__main__`` block prints the digest),
    so 03/06 reproduce it verbatim and the constant cannot flap by test order.
    """
    import subprocess
    import sys

    env = dict(os.environ)
    env["DETERMINISTIC_SIM"] = "1"
    # Pin SIM_SEED explicitly. config.SIM_SEED is read from the env at import and
    # SimEngine re-applies it during construction (sim_engine.py), so it OVERRIDES
    # any in-test set_sim_seed(). Some suite modules (tests/perf_*stress*.py) set
    # os.environ["SIM_SEED"]="42" at import time, which the subprocess would
    # otherwise inherit and shift the digest. Pin it to the digest seed so the
    # keystone is byte-stable regardless of suite ordering.
    env["SIM_SEED"] = str(_AI_DIGEST_SEED)
    env.setdefault("SDL_VIDEODRIVER", "dummy")
    env.setdefault("SDL_AUDIODRIVER", "dummy")
    proc = subprocess.run(
        [sys.executable, "-m", "tests.test_wk67_ai_boundary"],
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    for line in proc.stdout.splitlines():
        if line.startswith(_DIGEST_STDOUT_MARKER):
            return line[len(_DIGEST_STDOUT_MARKER):].strip()
    raise AssertionError(
        "subprocess did not print the AI-decision digest.\n"
        f"returncode={proc.returncode}\nstdout(tail)={proc.stdout[-2000:]}\n"
        f"stderr(tail)={proc.stderr[-2000:]}"
    )


def test_ai_decision_digest_is_stable():
    """The AI-decision digest equals the golden captured from current code.

    THE keystone guardrail for Moves 5 & 6. If this goes red, the AI/render
    boundary change was NOT inert — the AI decided something different. Computed
    in a fresh subprocess so it is byte-stable regardless of suite ordering.
    """
    digest = _compute_digest_in_subprocess()
    assert digest == _AI_DECISION_DIGEST, (
        "AI-decision digest changed — a WK67 boundary move altered AI behavior. "
        f"got={digest} golden={_AI_DECISION_DIGEST}"
    )


def test_ai_decision_digest_is_reproducible():
    """Two FRESH-process builds must produce the same digest.

    Proves the scenario is internally deterministic in a clean interpreter (the
    guardrail Moves 5/6 are diffed against). It is run as two subprocesses — NOT
    two in-process builds — because the AI decision path reads module-level
    mutable global state that does not fully reset between in-process engine
    constructions (``_AI_RNG``, ``RESEARCH_UNLOCKS``, and at least one more
    unidentified global; see the PM NOTE). The in-process drift is itself the
    pre-existing leak, so a fresh process is the correct reproducibility unit and
    matches how the keystone is computed.
    """
    d1 = _compute_digest_in_subprocess()
    d2 = _compute_digest_in_subprocess()
    assert d1 == d2, (
        "AI-decision digest is not reproducible across fresh subprocesses — the "
        f"scenario itself is nondeterministic. d1={d1} d2={d2}"
    )


# ===========================================================================
# Pin 2 — Shopping-purchase parity (pins Move 6; GREEN on current code)
# ===========================================================================
#
# Reference captured from current HEAD code: a warrior with 200 gold shops a
# marketplace offering a 20-gold potion, an 80-gold attack-6 weapon, and a
# 60-gold defense-4 armor. do_shopping's priority order buys: potion (P1),
# second potion (P2, gold>=50 & potions<2), weapon (P3, beats attack 0), armor
# (P4, beats defense 0). Final gold 200-20-20-80-60 = 20. Tax is 25% per item
# (config.TAX_RATE). total_spent_by_heroes = 180. This is the exact multi-item
# gold-gating + economy-log contract Move 6's synchronous applier must preserve.
_SHOP_REF_GOLD = 20
_SHOP_REF_POTIONS = 2
_SHOP_REF_WEAPON = {"name": "Iron Sword", "attack": 6}
_SHOP_REF_ARMOR = {"name": "Leather Armor", "defense": 4}
_SHOP_REF_TOTAL_SPENT = 180
_SHOP_REF_TXN_LOG = (
    {"type": "hero_purchase", "hero": "Buyer", "item": "Healing Potion", "price": 20, "tax": 5},
    {"type": "hero_purchase", "hero": "Buyer", "item": "Healing Potion", "price": 20, "tax": 5},
    {"type": "hero_purchase", "hero": "Buyer", "item": "Iron Sword", "price": 80, "tax": 20},
    {"type": "hero_purchase", "hero": "Buyer", "item": "Leather Armor", "price": 60, "tax": 15},
)


class _ParityShop:
    """A minimal shop offering a fixed catalogue.

    Exposes ``get_available_items`` (the only method ``do_shopping`` requires) and
    ``add_tax_gold`` so the ``Hero.buy_item`` tax-stash branch can run if it is
    ever reached. ``do_shopping`` calls ``hero.buy_item(item)`` WITHOUT passing
    ``shop_building=``, so the live code routes tax to ``inside_building`` /
    pending — which this isolated hero has none of; the tax therefore lands only
    in the economy log, exactly as the current code behaves.
    """

    building_type = "marketplace"

    def __init__(self, items):
        self._items = items
        self.stashed_tax = 0

    def get_available_items(self):
        return list(self._items)

    def add_tax_gold(self, amount):
        self.stashed_tax += int(amount)


class _StubJourney:
    def _maybe_start_journey(self, _ai, _hero, _game_state, purchased_types):
        self.received_purchased_types = set(purchased_types)
        return False


class _StubAI:
    def __init__(self):
        self.journey_behavior = _StubJourney()


class _ParitySimStub:
    """Minimal sim the real ``SimCommandSink`` resolves the shopping write against.

    Move 6 routes the purchase through a sim-owned synchronous ``SimCommandSink``:
    ``do_shopping`` proposes ``HeroPurchaseCommand(hero.hero_id, item)`` and the
    sink runs ``apply_hero_command`` → ``find_hero_by_id(id).buy_item(item)`` +
    ``economy.hero_purchase(name, item_name, price)`` — the EXACT effect the old
    inline ``do_shopping`` had. This stub exposes those two surfaces over the
    parity hero + a real ``EconomySystem`` so the recorded gold/inventory/economy
    reference still holds, now proven through the command path (the synchronous
    applier updates ``hero.gold`` between purchases, preserving the multi-item
    priority gating).
    """

    def __init__(self, hero, economy):
        self._hero = hero
        self.economy = economy

    def find_hero_by_id(self, hero_id):
        return self._hero if str(getattr(self._hero, "hero_id", "")) == str(hero_id) else None


def _parity_sink_view(hero, economy):
    """AiGameView-shaped object whose ``.commands`` is a real ``SimCommandSink``.

    Carries ``.commands`` (read by ``do_shopping``) plus the legacy-context read
    fields (projected for the journey trigger); NO economy/sim/engine on the view
    itself — the economy is reached only inside the sim-owned applier.
    """
    from types import SimpleNamespace

    from game.sim.hero_commands import SimCommandSink

    return SimpleNamespace(
        commands=SimCommandSink(_ParitySimStub(hero, economy)),
        world=None,
        buildings=[],
        enemies=[],
        heroes=[hero],
        bounties=[],
        pois=[],
        player_gold=0,
        castle=None,
    )


def test_shopping_purchase_parity():
    """do_shopping's multi-item gold gating + economy logging match the reference.

    The contract Move 6 (HeroCommand) must reproduce EXACTLY — the synchronous
    applier must keep updating ``hero.gold`` between purchases so the priority
    branches gate identically.
    """
    from ai.behaviors import shopping
    from game.entities.hero import Hero
    from game.systems.economy import EconomySystem

    pygame.init()
    pygame.display.set_mode((1, 1))
    try:
        items = [
            {"name": "Healing Potion", "type": "potion", "price": 20, "effect": 50},
            {"name": "Iron Sword", "type": "weapon", "price": 80, "attack": 6},
            {"name": "Leather Armor", "type": "armor", "price": 60, "defense": 4},
        ]
        hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="wk67_shop_hero", name="Buyer")
        hero.gold = 200
        hero.potions = 0
        hero.weapon = None
        hero.armor = None
        shop = _ParityShop(items)
        economy = EconomySystem()
        ai = _StubAI()

        started_journey = shopping.do_shopping(ai, hero, shop, _parity_sink_view(hero, economy))

        # Journey is not triggered for this scenario (full-HP gating not met here).
        assert started_journey is False

        # Hero inventory + spendable gold after the multi-item priority loop.
        assert hero.gold == _SHOP_REF_GOLD, f"hero gold {hero.gold} != {_SHOP_REF_GOLD}"
        assert hero.potions == _SHOP_REF_POTIONS, f"hero potions {hero.potions} != {_SHOP_REF_POTIONS}"
        assert hero.weapon == _SHOP_REF_WEAPON, f"hero weapon {hero.weapon} != {_SHOP_REF_WEAPON}"
        assert hero.armor == _SHOP_REF_ARMOR, f"hero armor {hero.armor} != {_SHOP_REF_ARMOR}"

        # Economy ledger: every hero purchase logged with the correct tax (25%).
        assert economy.total_spent_by_heroes == _SHOP_REF_TOTAL_SPENT
        assert tuple(economy.transaction_log) == _SHOP_REF_TXN_LOG, (
            "economy transaction log diverged from the recorded shopping reference"
        )
    finally:
        pygame.quit()


# ===========================================================================
# Pin 3 — AiGameView purity (pins Move 5; GREEN — Move 5 landed)
# ===========================================================================
#
# WK67 Wave 2 (Move 5) landed ``game/sim/ai_view.py`` (AiGameView + WorldView) and
# ``SimEngine.build_ai_view``, and 06 migrated the AI consumers. The xfail was
# removed at Gate 3 (Wave 3) once this pin XPASSed. The contract: the object the
# sim hands the AI must (a) carry NO economy/sim/engine, (b) expose ``world`` as a
# WorldView (a read-only facade, NOT the live World), (c) be constructible from a
# headless engine without a live presentation/window.


def test_ai_view_purity():
    """After Move 5 the AI consumes a read-only AiGameView, not the live dict."""
    from game.sim.ai_view import AiGameView, WorldView  # exists only after Move 5

    engine = GameEngine(headless=True)
    try:
        view = engine.sim.build_ai_view()

        # (a) NO live mutable sim services on the view.
        for forbidden in ("economy", "sim", "engine"):
            assert not hasattr(view, forbidden), (
                f"AiGameView must not expose '{forbidden}' — that is the L3 leak Move 5 closes"
            )

        # (b) world is a read-only WorldView wrapping the live World, not the World.
        assert isinstance(view, AiGameView)
        assert isinstance(view.world, WorldView)
        assert view.world is not engine.world
        # WorldView must be a drop-in for the AI's read surface.
        assert hasattr(view.world, "width") and hasattr(view.world, "height")
        assert hasattr(view.world, "world_to_grid") and hasattr(view.world, "is_walkable")

        # (c) immutable facts present (was the live economy / spawner).
        assert isinstance(view.player_gold, int)
        assert isinstance(view.wave, int)
    finally:
        pygame.quit()


# ===========================================================================
# Pin 4 — Frame-state split (pins Move 4; GREEN — Move 4 landed)
# ===========================================================================
#
# WK67 Wave 1 (Move 4) landed ``RenderSnapshot`` + ``PresentationFrameState`` in
# ``game/sim/snapshot.py`` and ``build_snapshot`` dropped its presentation kwargs.
# The xfail was removed at Gate 3 (Wave 3) once this pin XPASSed. The contract:
# the RenderSnapshot carries sim truth (live entity tuples + WK66 DTO tuples) and
# the PresentationFrameState carries camera/zoom/screen/paused/selection.


def test_frame_state_split():
    """After Move 4 presentation state is out of the sim snapshot."""
    import inspect

    from game.sim.snapshot import PresentationFrameState, RenderSnapshot  # post-Move 4

    engine = GameEngine(headless=True)
    try:
        snap = engine.build_snapshot()
        assert isinstance(snap, RenderSnapshot)

        # RenderSnapshot carries sim truth: live entity tuples...
        assert isinstance(snap.heroes, tuple)
        assert isinstance(snap.enemies, tuple)
        assert isinstance(snap.buildings, tuple)
        # ...AND the WK66 DTO tuples (live tuples are NOT deleted this sprint).
        assert hasattr(snap, "hero_dtos") and hasattr(snap, "building_dtos")
        # Presentation fields are GONE from the sim snapshot.
        for presentation_field in (
            "camera_x", "camera_y", "zoom", "paused", "selected_hero", "selected_building",
        ):
            assert not hasattr(snap, presentation_field), (
                f"'{presentation_field}' must move off the sim snapshot to PresentationFrameState"
            )

        # build_snapshot no longer takes presentation kwargs.
        sig = inspect.signature(engine.sim.build_snapshot)
        for presentation_kwarg in (
            "camera_x", "camera_y", "zoom", "paused", "screen_w", "selected_hero",
        ):
            assert presentation_kwarg not in sig.parameters, (
                f"SimEngine.build_snapshot must not accept presentation kwarg '{presentation_kwarg}'"
            )

        # PresentationFrameState carries the presentation fields.
        frame = PresentationFrameState()
        for presentation_field in ("camera_x", "camera_y", "zoom", "paused", "selected_hero"):
            assert hasattr(frame, presentation_field)
    finally:
        pygame.quit()


# ===========================================================================
# WK67 Wave 5 — determinism / capture pins (Gate 5 FINAL)
# ===========================================================================
#
# Wave 5 landed three determinism/capture items; these three pins certify they
# stay pinned and cannot silently regress. All three are HEADLESS-SAFE — none
# requires an Ursina display (the byte-identical Ursina capture itself is a
# tool/display artifact proven manually by Agent 12, NOT run inside pytest;
# Pin 5c only guards that the scenario stays registered/importable).


# ---------------------------------------------------------------------------
# Pin 5a — anim frame is tick-derived (not wall-clock) under DETERMINISTIC_SIM
# ---------------------------------------------------------------------------
#
# Wave 5a (Agent 10) added the single-source-of-truth helper
# ``game.graphics.ursina_units_anim.anim_clock_seconds(frame_tick_id)``: under
# ``config.DETERMINISTIC_SIM`` it returns ``int(frame_tick_id) * (1/20)`` (a pure
# function of the sim tick), else ``time.perf_counter()`` for live play. Both unit
# renderers (UrsinaRenderer._compute_anim_frame and
# InstancedUnitRenderer._resolve_unit_anim_clip_frame) read it, so a given sim tick
# ALWAYS selects the same within-clip frame index → byte-reproducible captures.
# Agent 10's manual proof: per-(tick,clip,idx) digest
# ``cbecc2e6356b4475a1d293ad42825d6e7b74f69c0726798b85245cb87808cbd6`` identical
# across two runs. This pin asserts the *tick-derived* contract headlessly: the
# clock is a pure function of the tick (same tick → same value; monotonic in tick;
# equals tick*(1/20)), and the per-(tick,clip,frame) selection — which is what the
# renderers actually choose — is identical across two independent passes.
_SIM_TICK_SECONDS = 1.0 / 20.0


def _representative_clips():
    """A small, display-independent representative clip set.

    Plain ``pygame.Surface`` frames need no display; ``_frame_index_for_clip`` only
    reads ``len(frames)``/``frame_time_sec``/``loop``. Covers a looping idle, a
    faster looping walk, and a NON-looping attack one-shot (the strike pose the
    combat capture freezes), so the pin exercises both the loop and finish branches.
    """
    from game.graphics.animation import AnimationClip

    def _clip(n_frames, ft, loop):
        return AnimationClip(
            frames=[pygame.Surface((4, 4)) for _ in range(n_frames)],
            frame_time_sec=ft,
            loop=loop,
        )

    return {
        "idle": _clip(4, 0.15, True),
        "walk": _clip(6, 0.08, True),
        "attack": _clip(3, 0.06, False),
    }


def _anim_frame_pass(clips, ticks):
    """One pass: for each tick, the (tick, clip, frame-index, finished) the renderer
    would pick, using the SAME tick-derived clock both unit renderers use."""
    from game.graphics.ursina_units_anim import _frame_index_for_clip, anim_clock_seconds

    out = []
    for t in range(ticks):
        elapsed = anim_clock_seconds(t)
        for clip_name, clip in sorted(clips.items()):
            out.append((t, clip_name, _frame_index_for_clip(clip, elapsed)))
    return out


def test_anim_clock_is_tick_derived_under_deterministic_sim(monkeypatch):
    """Under DETERMINISTIC_SIM the anim clock is a pure function of the sim tick.

    Pins Wave 5a: the within-clip anim clock is derived from the sim tick id, NOT
    wall-clock, so the renderers select the same frame for a given tick → captures
    are byte-reproducible. Asserts (a) same tick → same value across calls, (b)
    strictly monotonic increasing with tick, (c) equals tick*(1/20) exactly, and
    (d) the per-(tick,clip,frame) selection is identical across two independent
    passes for a representative clip set (the actual renderer-facing contract).
    """
    import config

    monkeypatch.setattr(config, "DETERMINISTIC_SIM", True, raising=False)
    from game.graphics.ursina_units_anim import anim_clock_seconds

    # (a) pure function of the tick — same tick yields the same value across calls.
    for tick in (0, 1, 7, 100, 1234):
        assert anim_clock_seconds(tick) == anim_clock_seconds(tick)

    # (b) strictly monotonic increasing with tick.
    prev = None
    for tick in range(0, 200):
        val = anim_clock_seconds(tick)
        if prev is not None:
            assert val > prev, f"anim clock not monotonic at tick {tick}: {val} <= {prev}"
        prev = val

    # (c) equals tick * (1/20) exactly (the deterministic 20 Hz sim basis).
    for tick in (0, 1, 7, 20, 100, 999):
        assert anim_clock_seconds(tick) == float(tick) * _SIM_TICK_SECONDS

    # (d) per-(tick,clip,frame) selection identical across two independent passes —
    # this is what the unit renderers actually pick for each unit each frame.
    clips = _representative_clips()
    pass_a = _anim_frame_pass(clips, ticks=120)
    pass_b = _anim_frame_pass(clips, ticks=120)
    assert pass_a == pass_b, (
        "tick-derived anim frame selection drifted across two passes — the anim "
        "frame is not a pure function of the sim tick under DETERMINISTIC_SIM"
    )
    # Sanity: the non-looping 'attack' clip actually reaches its finished pose
    # (so the pin exercises the one-shot strike branch the combat capture freezes),
    # and the looping clips actually advance (not stuck on frame 0 forever).
    attack_finished = any(name == "attack" and frame[1] is True for _, name, frame in pass_a)
    walk_advanced = any(name == "walk" and frame[0] > 0 for _, name, frame in pass_a)
    assert attack_finished, "representative non-looping clip never finished — clock not advancing"
    assert walk_advanced, "representative looping clip never advanced — clock not advancing"


# ---------------------------------------------------------------------------
# Pin 5b — fog_revision is stable across two same-seed builds
# ---------------------------------------------------------------------------
#
# Wave 5b (Agent 03) root-caused the in-process ``_fog_revision`` ±1 drift to the
# class-global ``Peasant._spawn_counter`` carrying over between builds (it shifted
# a peasant idle offset → a fog revealer's grid tile → the revision increment
# COUNT); the fix resets it in ``SimEngine.__init__`` next to the seed reset. Two
# same-seed in-process builds now give an IDENTICAL ``_fog_revision`` sequence.
#
# This pin computes the sequence in TWO FRESH SUBPROCESSES with a pinned env
# (DETERMINISTIC_SIM=1, SIM_SEED=3) — the SAME bulletproofing the keystone digest
# uses — so the known process-level env pollution (perf_*stress* modules set
# os.environ["SIM_SEED"]="42" at import; config.SIM_SEED is read at import and
# SimEngine re-applies it, OVERRIDING in-test set_sim_seed) cannot shift the
# sequence by suite ordering. It asserts the two sequences are byte-identical.
_FOG_SEQ_STDOUT_MARKER = "WK67_FOG_REVISION_SEQ="
_FOG_SEQ_TICKS = 600
_FOG_SEQ_SEED = 3


def _run_fog_revision_sequence(ticks: int = _FOG_SEQ_TICKS) -> tuple[int, ...]:
    """Deterministic headless reveal: a ranger walks two legs across the map.

    Mirrors the WK66 fog scenario (tests/test_wk66_render_boundary.py): no AI
    controller (so movement is fully scripted) + fixed seed ⇒ the visibility grid
    evolves identically, and (post Wave-5b ``Peasant._spawn_counter`` reset) so does
    the ``_fog_revision`` increment sequence. Returns the per-tick revision values.
    """
    from game.entities.hero import Hero, HeroState
    from game.sim.determinism import set_sim_seed
    from game.sim.timebase import set_sim_now_ms

    set_sim_seed(_FOG_SEQ_SEED)
    engine = GameEngine(headless=True)
    try:
        set_sim_now_ms(0)
        castle = next(b for b in engine.buildings if getattr(b, "building_type", None) == "castle")
        hero = Hero(
            float(castle.center_x), float(castle.center_y),
            hero_class="ranger", hero_id="wk67_fog_pin", name="Scout",
        )
        engine.heroes.append(hero)
        hero.set_target_position(castle.center_x + 30 * TILE_SIZE, castle.center_y + 20 * TILE_SIZE)
        hero.state = HeroState.MOVING

        seq: list[int] = []
        for t in range(ticks):
            set_sim_now_ms(int(t * (1 / 60) * 1000.0))
            if hero.state != HeroState.MOVING and hero.target_position is None and t < ticks - 60:
                hero.set_target_position(
                    castle.center_x - 20 * TILE_SIZE, castle.center_y - 25 * TILE_SIZE
                )
                hero.state = HeroState.MOVING
            engine.update(1 / 60)
            seq.append(int(getattr(engine.sim, "_fog_revision", 0)))
        return tuple(seq)
    finally:
        pygame.quit()


def _compute_fog_sequence_in_subprocess() -> str:
    """Run the fog-revision sequence in a FRESH interpreter; return its repr.

    Same load-bearing rationale as ``_compute_digest_in_subprocess``: pin SIM_SEED
    and DETERMINISTIC_SIM explicitly so the sequence is byte-stable regardless of
    pytest collection order (which can leave SIM_SEED=42 in the parent env)."""
    import subprocess
    import sys

    env = dict(os.environ)
    env["DETERMINISTIC_SIM"] = "1"
    env["SIM_SEED"] = str(_FOG_SEQ_SEED)
    env.setdefault("SDL_VIDEODRIVER", "dummy")
    env.setdefault("SDL_AUDIODRIVER", "dummy")
    proc = subprocess.run(
        [sys.executable, "-m", "tests.test_wk67_ai_boundary", "--fog-revision"],
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    for line in proc.stdout.splitlines():
        if line.startswith(_FOG_SEQ_STDOUT_MARKER):
            return line[len(_FOG_SEQ_STDOUT_MARKER):].strip()
    raise AssertionError(
        "subprocess did not print the fog-revision sequence.\n"
        f"returncode={proc.returncode}\nstdout(tail)={proc.stdout[-2000:]}\n"
        f"stderr(tail)={proc.stderr[-2000:]}"
    )


def test_fog_revision_sequence_is_stable_across_builds():
    """Two same-seed fresh-process builds give a byte-identical _fog_revision seq.

    Pins Wave 5b: the ``Peasant._spawn_counter`` reset in ``SimEngine.__init__``
    makes the per-tick ``_fog_revision`` increment sequence reproducible build to
    build. If a future change re-introduces the carry-over (or otherwise perturbs
    when ``update_visibility`` runs), the two sequences diverge and this goes red.
    """
    seq1 = _compute_fog_sequence_in_subprocess()
    seq2 = _compute_fog_sequence_in_subprocess()
    assert seq1 == seq2, (
        "_fog_revision sequence is not byte-identical across two same-seed builds — "
        "Wave 5b determinism (Peasant._spawn_counter reset) regressed."
    )
    # Sanity: the sequence is non-trivial (the scout actually triggered many
    # reveals, so the pin guards a real evolving sequence, not a constant).
    parsed = eval(seq1)  # noqa: S307 — our own repr of a tuple of ints, fixed env
    assert isinstance(parsed, tuple) and len(parsed) == _FOG_SEQ_TICKS
    assert parsed[-1] > 1, f"fog revision did not advance past 1 (final={parsed[-1]})"


# ---------------------------------------------------------------------------
# Pin 5c — combat capture scenario stays registered / importable
# ---------------------------------------------------------------------------
#
# Wave 5c (Agent 12) added ``tools/screenshot_scenarios.py::ursina_melee_combat``
# (+ ``tools/wk67_combat_capture_patch.py``); the Ursina one-shot capture
# ``python tools/run_ursina_capture_once.py --scenario ursina_melee_combat ...``
# is byte-identical across two DETERMINISTIC_SIM runs (Agent 12 manual proof:
# SHA256 ``2DE5D5F4...``). That capture needs a real display, so it is NOT run
# inside headless pytest. This pin is the lightweight guard that the scenario
# cannot silently disappear: it asserts the scenario is REGISTERED in BOTH
# registries (the Ursina capture registry consumed by run_ursina_capture_once.py,
# and the pygame ``get_scenario`` dispatch) and is importable headlessly.
def test_combat_capture_scenario_is_registered():
    """The ursina_melee_combat capture scenario stays registered + importable.

    Headless guard for Wave 5c — the actual byte-identical Ursina PNG capture
    (Agent 12 manual proof SHA256 2DE5D5F4...) needs a display and is NOT run here.
    """
    from tools.screenshot_scenarios import (
        URSINA_CAPTURE_SCENARIOS,
        get_ursina_capture_scenario,
        scenario_ursina_melee_combat,
    )

    # (1) Present in the Ursina capture registry consumed by run_ursina_capture_once.py.
    assert "ursina_melee_combat" in URSINA_CAPTURE_SCENARIOS, (
        "ursina_melee_combat vanished from URSINA_CAPTURE_SCENARIOS — Wave 5c "
        "byte-identical combat capture coverage would silently disappear"
    )
    cfg = get_ursina_capture_scenario("ursina_melee_combat")
    assert cfg.get("patch_path") == "tools/wk67_combat_capture_patch.py"
    assert int(cfg.get("default_ticks", 0)) > 0
    assert cfg.get("stem") == "ursina_melee_combat"

    # (2) The pygame-path builder is importable and dispatched by get_scenario.
    assert callable(scenario_ursina_melee_combat)


# ===========================================================================
# __main__ — fresh-process digest / fog-revision printer (subprocess entrypoints)
# ===========================================================================
#
# Run as ``python -m tests.test_wk67_ai_boundary`` with DETERMINISTIC_SIM=1 to
# print the AI-decision digest on a clean interpreter; pass ``--fog-revision`` to
# print the deterministic ``_fog_revision`` sequence instead (Pin 5b subprocess).
# The keystone (and Pin 5b) invoke these so they never flap by suite ordering;
# 03/06/10 can run these lines directly to re-confirm at the AI/determinism gates.
if __name__ == "__main__":
    import sys

    if "--fog-revision" in sys.argv[1:]:
        _seq = _run_fog_revision_sequence(_FOG_SEQ_TICKS)
        print(f"{_FOG_SEQ_STDOUT_MARKER}{_seq!r}")
    else:
        _engine = _build_digest_engine()
        try:
            _digest = _ai_digest(_engine, _AI_DIGEST_TICKS)
        finally:
            pygame.quit()
        print(f"{_DIGEST_STDOUT_MARKER}{_digest}")
