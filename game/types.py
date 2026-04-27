"""
Core gameplay enums that remain string-compatible.
"""
from enum import Enum


class HeroClass(str, Enum):
    WARRIOR = "warrior"
    RANGER = "ranger"
    ROGUE = "rogue"
    WIZARD = "wizard"
    CLERIC = "cleric"


class EnemyType(str, Enum):
    GOBLIN = "goblin"
    WOLF = "wolf"
    SKELETON = "skeleton"
    SKELETON_ARCHER = "skeleton_archer"
    SPIDER = "spider"
    BANDIT = "bandit"


class BountyType(str, Enum):
    EXPLORE = "explore"
    ATTACK_LAIR = "attack_lair"
    DEFEND_BUILDING = "defend_building"
    HUNT_ENEMY_TYPE = "hunt_enemy_type"
