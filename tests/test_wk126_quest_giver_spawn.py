"""WK126-T2 (entity + spawn hook) — Quest-Giver NPC lifecycle gates.

Per the wk126 plan T2 headless gate:
- placing + CONSTRUCTING a Herald's Post spawns exactly ONE QuestGiver at the
  expected offset (guardhouse→guard pattern: post center + (TILE_SIZE, 0));
- an unconstructed post spawns nothing;
- the cap holds across many ticks (never a second NPC for the same post);
- destroying the post removes its giver.

Uses the real headless GameEngine so the spawn hook runs through the live
``SimEngine._update_buildings`` / cleanup paths. The Herald's Post building is
created from the base ``Building`` class with ``building_type="herald_post"``
so this gate does not depend on Agent 07's BuildingDef landing first (parallel
Wave-1 lanes; the def only adds catalog/cost/size metadata).
"""
from __future__ import annotations

import os

import pygame

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from config import TILE_SIZE
from game.engine import GameEngine
from game.entities.buildings.base import Building
from game.entities.quest_giver import QuestGiver


def _make_post(engine, *, constructed=True, grid_dx=6, grid_dy=0) -> Building:
    castle = next(b for b in engine.buildings if getattr(b, "building_type", None) == "castle")
    post = Building(int(castle.grid_x) + grid_dx, int(castle.grid_y) + grid_dy, "herald_post")
    post.is_constructed = bool(constructed)
    post.construction_started = True
    engine.sim.buildings.append(post)
    return post


def test_constructed_post_spawns_exactly_one_giver_at_offset():
    engine = GameEngine(headless=True)
    try:
        assert engine.sim.quest_givers == []
        post = _make_post(engine, constructed=True)

        engine.update(1 / 60)

        givers = engine.sim.quest_givers
        assert len(givers) == 1, "a constructed Herald's Post must spawn exactly one QuestGiver"
        giver = givers[0]
        assert isinstance(giver, QuestGiver)
        assert giver.post is post
        assert giver.giver_id == post.entity_id
        # Expected offset: guardhouse→guard pattern (center_x + TILE_SIZE, center_y).
        assert giver.x == float(post.center_x) + TILE_SIZE
        assert giver.y == float(post.center_y)
        assert giver.is_open is False, "no quest armed yet -> '!' off"

        # Cap 1: many more ticks never spawn a second NPC for the same post.
        for _ in range(30):
            engine.update(1 / 60)
        assert len(engine.sim.quest_givers) == 1
    finally:
        pygame.quit()


def test_unconstructed_post_spawns_nothing():
    engine = GameEngine(headless=True)
    try:
        _make_post(engine, constructed=False)
        for _ in range(10):
            engine.update(1 / 60)
        assert engine.sim.quest_givers == []
    finally:
        pygame.quit()


def test_two_posts_get_one_giver_each():
    engine = GameEngine(headless=True)
    try:
        post_a = _make_post(engine, constructed=True, grid_dx=6)
        post_b = _make_post(engine, constructed=True, grid_dx=-6, grid_dy=4)
        engine.update(1 / 60)
        givers = engine.sim.quest_givers
        assert len(givers) == 2
        assert {g.post for g in givers} == {post_a, post_b}
        assert givers[0].giver_id != givers[1].giver_id
    finally:
        pygame.quit()


def test_destroying_post_removes_its_giver():
    engine = GameEngine(headless=True)
    try:
        post = _make_post(engine, constructed=True)
        engine.update(1 / 60)
        assert len(engine.sim.quest_givers) == 1

        post.hp = 0  # destroyed
        engine.update(1 / 60)

        assert post not in engine.sim.buildings, "destroyed post must leave the buildings list"
        assert engine.sim.quest_givers == [], "the post's QuestGiver must be culled with it"
    finally:
        pygame.quit()
