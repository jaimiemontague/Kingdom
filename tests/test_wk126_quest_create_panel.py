"""WK126-T9 — Quest-creation dialog + active-quest board gates (Agent 08, WK133).

Covers the T9 headless gate from the wk126 plan:
- the selected Herald's Post card shows a "Create Quest" button; clicking it
  opens the quest-create modal (open-on-selected-post)
- a valid selection (type -> target -> reward -> confirm) produces a FUNDED
  quest: treasury debited via economy.fund_quest, quest ``is_open``
- over-budget creation is BLOCKED with insufficient-gold feedback (build-menu
  style) and the treasury is untouched
- ESC (real keyboard path) / Cancel / click-outside all close the modal cleanly
  (no quest, no debit) and the modal consumes stray clicks while open
- ``QuestViewPanel.render_active_quests`` lists an active quest (type, target,
  reward, status)

Notes:
- The Herald's Post is constructed DIRECTLY via the base ``Building`` class
  (same as tests/test_wk126_quest_giver_spawn.py) — the build-catalog/factory
  placement path is Agent 07's parallel WK133 lane.
- The raid target uses a real ``GoblinCamp`` (``is_lair=True``); the world is
  revealed so the lair counts as DISCOVERED for the target list.
"""

from __future__ import annotations

import os

# Headless SDL — must be set before pygame is imported by the engine.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from config import QUEST_REWARD_LOW, QUEST_REWARD_MED  # noqa: E402
from game.engine import GameEngine  # noqa: E402
from game.entities.building import Building  # noqa: E402
from game.entities.lair import GoblinCamp  # noqa: E402
from game.entities.quest_giver import QuestGiver  # noqa: E402
from game.input_manager import InputEvent  # noqa: E402
from game.ui.quest_view_panel import QuestViewPanel  # noqa: E402
from game.ui.theme import UITheme  # noqa: E402

# Tall left-column rect: every panel button is inside the viewport (no scroll).
_TALL_LEFT_RECT = pygame.Rect(0, 48, 360, 900)


def _make_engine() -> GameEngine:
    return GameEngine(headless=False, headless_ui=True)


def _bt(building) -> str:
    raw = getattr(building, "building_type", "")
    raw = getattr(raw, "value", raw)
    return str(raw).strip().lower()


def _castle(engine: GameEngine):
    return next(b for b in engine.buildings if _bt(b) == "castle")


def _reveal_world(engine: GameEngine) -> None:
    vis = getattr(engine.world, "visibility", None)
    if not vis:
        return
    for row in vis:
        for x in range(len(row)):
            row[x] = 1  # Visibility.SEEN


def _place_post(engine: GameEngine) -> Building:
    c = _castle(engine)
    post = Building(int(c.grid_x) + 5, int(c.grid_y) + 1, "herald_post")
    post.is_constructed = True
    post.construction_started = True
    engine.buildings.append(post)
    return post


def _add_quest_giver(engine: GameEngine, post: Building) -> QuestGiver:
    giver = QuestGiver(post)
    engine.sim.quest_givers.append(giver)
    return giver


def _place_lair(engine: GameEngine) -> GoblinCamp:
    """Place ONE deterministic lair (drop the world-gen lairs so the target
    list has exactly one candidate)."""
    engine.buildings = [b for b in engine.buildings if not getattr(b, "is_lair", False)]
    c = _castle(engine)
    lair = GoblinCamp(int(c.grid_x) + 14, int(c.grid_y) + 6)
    engine.buildings.append(lair)
    return lair


def _select_and_render(engine: GameEngine, building) -> pygame.Surface:
    engine.selected_building = building
    engine.building_panel.select_building(building, engine.heroes)
    surface = pygame.Surface((1280, 720))
    engine.building_panel.render(surface, engine.heroes, engine.economy, left_rect=_TALL_LEFT_RECT)
    return surface


def _render_panel(engine: GameEngine, surface: pygame.Surface) -> None:
    engine.building_panel.render(surface, engine.heroes, engine.economy, left_rect=_TALL_LEFT_RECT)


def _open_modal(engine: GameEngine, post) -> object:
    """Open the modal through the real button-click path. Returns the modal."""
    surface = _select_and_render(engine, post)
    panel = engine.building_panel
    assert panel.create_quest_button_rect is not None, "Create Quest button missing on herald_post card"
    res = panel.handle_click(panel.create_quest_button_rect.center, engine.economy, engine.get_game_state())
    assert res is True
    qcp = panel.quest_create_panel
    assert qcp.visible is True
    _render_panel(engine, surface)  # populate the modal's hit-rects
    qcp._test_surface = surface  # stash for the click-render loop helpers
    return qcp


def _click(engine: GameEngine, qcp, pos) -> None:
    """Click through the building panel (the real routing) and re-render."""
    engine.building_panel.handle_click(pos, engine.economy, engine.get_game_state())
    _render_panel(engine, qcp._test_surface)


# --------------------------------------------------------------------------------------
# 1. Open-on-selected-post
# --------------------------------------------------------------------------------------
def test_create_quest_button_only_on_constructed_post():
    engine = _make_engine()
    try:
        post = _place_post(engine)
        _select_and_render(engine, post)
        assert engine.building_panel.create_quest_button_rect is not None

        # Not on other buildings.
        _select_and_render(engine, _castle(engine))
        assert engine.building_panel.create_quest_button_rect is None

        # Greyed (no live hit-rect) while under construction.
        post.is_constructed = False
        _select_and_render(engine, post)
        assert engine.building_panel.create_quest_button_rect is None
    finally:
        pygame.quit()


def test_button_click_opens_modal_on_selected_post():
    engine = _make_engine()
    try:
        post = _place_post(engine)
        qcp = _open_modal(engine, post)
        assert qcp.visible is True
        assert qcp.post is post
        assert len(qcp.type_rects) == 4  # all four quest types offered
    finally:
        pygame.quit()


# --------------------------------------------------------------------------------------
# 2. Valid selection -> funded quest (treasury debited, quest is_open)
# --------------------------------------------------------------------------------------
def test_full_flow_creates_funded_raid_quest():
    engine = _make_engine()
    try:
        _reveal_world(engine)
        post = _place_post(engine)
        lair = _place_lair(engine)
        engine.economy.player_gold = 500
        gold_before = int(engine.economy.player_gold)

        qcp = _open_modal(engine, post)
        _click(engine, qcp, qcp.type_rects["raid_lair"].center)
        assert qcp.selected_type == "raid_lair"
        assert len(qcp.target_rects) >= 1, "discovered lair must be listed"
        _click(engine, qcp, qcp.target_rects[0].center)
        assert qcp.target_index == 0
        _click(engine, qcp, qcp.reward_rects["med"].center)
        assert qcp.reward_key == "med"
        _click(engine, qcp, qcp.confirm_rect.center)

        quests = engine.sim.quest_system.get_active_quests()
        assert len(quests) == 1
        q = quests[0]
        assert q.is_open is True and q.funded is True
        assert q.quest_type == "raid_lair" and q.target is lair
        assert q.reward == int(QUEST_REWARD_MED)
        assert q.giver_id == str(post.entity_id)
        assert int(engine.economy.player_gold) == gold_before - int(QUEST_REWARD_MED)
        assert qcp.visible is False  # modal closes on success
    finally:
        pygame.quit()


def test_story_chain_buttons_visible_on_herald_post_modal():
    engine = _make_engine()
    try:
        post = _place_post(engine)
        qcp = _open_modal(engine, post)

        assert set(qcp.story_chain_rects) == {
            "relic_of_the_old_shrine",
            "blackbanners_toll",
            "ashwings_hoard",
        }
        panel_rect = qcp.modal.get_panel_rect()
        assert all(panel_rect.contains(rect) for rect in qcp.story_chain_rects.values())
        assert qcp.cancel_rect is not None and qcp.confirm_rect is not None
        assert all(not rect.colliderect(qcp.cancel_rect) for rect in qcp.story_chain_rects.values())
        assert all(not rect.colliderect(qcp.confirm_rect) for rect in qcp.story_chain_rects.values())
    finally:
        pygame.quit()


def test_story_chain_click_launches_live_chain_and_keeps_modal_open():
    engine = _make_engine()
    try:
        post = _place_post(engine)
        _add_quest_giver(engine, post)

        qcp = _open_modal(engine, post)
        _click(engine, qcp, qcp.story_chain_rects["blackbanners_toll"].center)

        chains = [
            chain
            for chain in engine.sim.quest_chain_system.chains
            if chain.chain_type == "blackbanners_toll"
        ]
        assert len(chains) == 1
        assert chains[0].status == "active"
        assert qcp.visible is True
        assert qcp.feedback == "Blackbanner started."
        snapshots = engine.sim.quest_chain_system.get_active_chain_snapshots()
        assert any(snapshot.chain_type == "blackbanners_toll" for snapshot in snapshots)
    finally:
        pygame.quit()


def test_story_chain_duplicate_and_unavailable_feedback():
    engine = _make_engine()
    try:
        post = _place_post(engine)
        _add_quest_giver(engine, post)

        qcp = _open_modal(engine, post)
        _click(engine, qcp, qcp.story_chain_rects["relic_of_the_old_shrine"].center)
        _click(engine, qcp, qcp.story_chain_rects["relic_of_the_old_shrine"].center)

        chains = [
            chain
            for chain in engine.sim.quest_chain_system.chains
            if chain.chain_type == "relic_of_the_old_shrine"
        ]
        assert len(chains) == 1
        assert qcp.visible is True
        assert qcp.feedback == "Already active."

        engine.sim.quest_givers.clear()
        qcp.close()
        qcp = _open_modal(engine, post)
        _click(engine, qcp, qcp.story_chain_rects["ashwings_hoard"].center)
        assert qcp.visible is True
        assert qcp.feedback == "Story chain unavailable."
        assert [
            chain
            for chain in engine.sim.quest_chain_system.chains
            if chain.chain_type == "ashwings_hoard"
        ] == []
    finally:
        pygame.quit()


def test_slay_flow_uses_count_stepper():
    engine = _make_engine()
    try:
        post = _place_post(engine)
        engine.economy.player_gold = 500
        qcp = _open_modal(engine, post)
        _click(engine, qcp, qcp.type_rects["slay_enemy_type"].center)
        assert len(qcp.target_rects) >= 1
        _click(engine, qcp, qcp.target_rects[0].center)  # goblin
        assert qcp.slay_count == 5  # QUEST_SLAY_DEFAULT_COUNT
        _click(engine, qcp, qcp.count_plus_rect.center)
        _click(engine, qcp, qcp.count_plus_rect.center)
        _click(engine, qcp, qcp.count_minus_rect.center)
        assert qcp.slay_count == 6
        _click(engine, qcp, qcp.confirm_rect.center)

        quests = engine.sim.quest_system.get_active_quests()
        assert len(quests) == 1
        q = quests[0]
        assert q.quest_type == "slay_enemy_type" and q.target == "goblin"
        assert q.count == 6 and q.reward == int(QUEST_REWARD_LOW)
    finally:
        pygame.quit()


# --------------------------------------------------------------------------------------
# 3. Over-budget blocked with feedback
# --------------------------------------------------------------------------------------
def test_over_budget_blocked_with_feedback():
    engine = _make_engine()
    try:
        post = _place_post(engine)
        engine.economy.player_gold = 10
        gold_before = int(engine.economy.player_gold)

        qcp = _open_modal(engine, post)
        _click(engine, qcp, qcp.type_rects["slay_enemy_type"].center)
        _click(engine, qcp, qcp.target_rects[0].center)

        # Clicking an unaffordable tier shows build-menu-style feedback.
        _click(engine, qcp, qcp.reward_rects["high"].center)
        assert qcp.reward_key != "high"
        assert "Need $" in qcp.feedback and "have $10" in qcp.feedback

        # Confirm is blocked too (default Low tier is also unaffordable at 10g).
        qcp.feedback = ""
        _click(engine, qcp, qcp.confirm_rect.center)
        assert engine.sim.quest_system.get_active_quests() == []
        assert int(engine.economy.player_gold) == gold_before
        assert "Need $" in qcp.feedback
        assert qcp.visible is True  # stays open so the player can adjust
    finally:
        pygame.quit()


# --------------------------------------------------------------------------------------
# 4. ESC / Cancel / click-outside close cleanly; modal consumes clicks
# --------------------------------------------------------------------------------------
def test_esc_cancel_and_outside_click_close_clean():
    engine = _make_engine()
    try:
        post = _place_post(engine)
        engine.economy.player_gold = 500
        gold_before = int(engine.economy.player_gold)
        panel = engine.building_panel

        # ESC through the REAL keyboard path (game/input/keyboard.py).
        qcp = _open_modal(engine, post)
        engine.input_handler.handle_keydown(InputEvent(type="KEYDOWN", key="esc"))
        assert qcp.visible is False
        assert getattr(engine.pause_menu, "visible", False) is False  # ESC consumed by the modal

        # Cancel button.
        qcp = _open_modal(engine, post)
        _click(engine, qcp, qcp.cancel_rect.center)
        assert qcp.visible is False

        # Click outside the modal cancels — and is consumed (no world leak).
        qcp = _open_modal(engine, post)
        res = panel.handle_click((5, 715), engine.economy, engine.get_game_state())
        assert res is True
        assert qcp.visible is False

        # Clean: nothing created, nothing debited, panel still on the post.
        assert engine.sim.quest_system.get_active_quests() == []
        assert int(engine.economy.player_gold) == gold_before
        assert panel.visible is True and panel.selected_building is post

        # Deselecting the post closes a dangling modal.
        qcp = _open_modal(engine, post)
        panel.deselect()
        assert qcp.visible is False
    finally:
        pygame.quit()


# --------------------------------------------------------------------------------------
# 5. Active-quest board (quest_view_panel readout)
# --------------------------------------------------------------------------------------
def test_quest_view_panel_lists_active_quest():
    engine = _make_engine()
    try:
        post = _place_post(engine)
        engine.economy.player_gold = 500
        quest = engine.sim.create_quest(post.entity_id, "slay_enemy_type", "goblin", 60, count=5)
        assert quest is not None and quest.is_open

        surface = pygame.Surface((1280, 720))
        qvp = QuestViewPanel(UITheme())
        lines = qvp.render_active_quests(
            surface, pygame.Rect(0, 0, 246, 300), {"sim": engine.sim}
        )
        joined = "\n".join(lines)
        assert "Slay Enemies" in joined
        assert "5x goblin" in joined
        assert "$60" in joined
        assert "Open" in joined

        # Accepted status + n/m progress.
        class _H:
            hero_id = "wk126t9_hero"
            name = "Brina"

        quest.accept(_H())
        quest.progress = 2
        lines = qvp.render_active_quests(
            surface, pygame.Rect(0, 0, 246, 300), {"sim": engine.sim}
        )
        joined = "\n".join(lines)
        assert "Accepted: Brina" in joined and "(2/5)" in joined

        # Empty board renders a friendly placeholder.
        engine.sim.quest_system.quests.clear()
        lines = qvp.render_active_quests(
            surface, pygame.Rect(0, 0, 246, 300), {"sim": engine.sim}
        )
        assert lines == ["No active quests."]
    finally:
        pygame.quit()
