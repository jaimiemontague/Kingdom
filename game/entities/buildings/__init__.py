"""
Building entities package.

Exports all building classes and shared research helpers.
"""

from .base import Building, RESEARCH_UNLOCKS, is_research_unlocked, unlock_research
from .castle import Castle
from .defensive import BallistaTower, Guardhouse, WizardTower
from .dwellings import DwarvenSettlement, ElvenBungalow, GnomeHovel
from .economic import Blacksmith, Inn, Marketplace, TradingPost
from .guilds import RangerGuild, RogueGuild, WarriorGuild, WizardGuild
from .hiring_mixin import HiringBuilding
from .special import Fairgrounds, Library, Palace, RoyalGardens
from .temples import (
    TempleAgrela,
    TempleDauros,
    TempleFervus,
    TempleHelia,
    TempleKrolm,
    TempleKrypta,
    TempleLunord,
)
from .types import BuildingType

__all__ = [
    "BuildingType",
    "RESEARCH_UNLOCKS",
    "is_research_unlocked",
    "unlock_research",
    "Building",
    "HiringBuilding",
    "Castle",
    "WarriorGuild",
    "RangerGuild",
    "RogueGuild",
    "WizardGuild",
    "Marketplace",
    "Blacksmith",
    "Inn",
    "TradingPost",
    "TempleAgrela",
    "TempleDauros",
    "TempleFervus",
    "TempleKrypta",
    "TempleKrolm",
    "TempleHelia",
    "TempleLunord",
    "GnomeHovel",
    "ElvenBungalow",
    "DwarvenSettlement",
    "Guardhouse",
    "BallistaTower",
    "WizardTower",
    "Fairgrounds",
    "Library",
    "RoyalGardens",
    "Palace",
]
