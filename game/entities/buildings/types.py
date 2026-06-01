"""
Canonical building type identifiers.
"""

from enum import Enum


class BuildingType(str, Enum):
    CASTLE = "castle"
    WARRIOR_GUILD = "warrior_guild"
    RANGER_GUILD = "ranger_guild"
    ROGUE_GUILD = "rogue_guild"
    WIZARD_GUILD = "wizard_guild"
    MARKETPLACE = "marketplace"
    BLACKSMITH = "blacksmith"
    INN = "inn"
    TRADING_POST = "trading_post"
    TEMPLE = "temple"
    TEMPLE_AGRELA = "temple_agrela"
    TEMPLE_DAUROS = "temple_dauros"
    TEMPLE_FERVUS = "temple_fervus"
    TEMPLE_KRYPTA = "temple_krypta"
    TEMPLE_KROLM = "temple_krolm"
    TEMPLE_HELIA = "temple_helia"
    TEMPLE_LUNORD = "temple_lunord"
    GUARDHOUSE = "guardhouse"
    PALACE = "palace"
    HOUSE = "house"
    FARM = "farm"
    FOOD_STAND = "food_stand"
