"""
Building factory for runtime placement.
"""
from game.entities import (
    WarriorGuild,
    RangerGuild,
    RogueGuild,
    WizardGuild,
    Marketplace,
    Blacksmith,
    Inn,
    TradingPost,
    Temple,
    TempleAgrela,
    TempleDauros,
    TempleFervus,
    TempleKrypta,
    TempleKrolm,
    TempleHelia,
    TempleLunord,
    GnomeHovel,
    ElvenBungalow,
    DwarvenSettlement,
    Guardhouse,
    BallistaTower,
    WizardTower,
    Fairgrounds,
    Library,
    RoyalGardens,
    Palace,
)


class BuildingFactory:
    """Create building instances from placement type keys."""

    BUILDING_REGISTRY = {
        "warrior_guild": WarriorGuild,
        "ranger_guild": RangerGuild,
        "rogue_guild": RogueGuild,
        "wizard_guild": WizardGuild,
        "marketplace": Marketplace,
        "blacksmith": Blacksmith,
        "inn": Inn,
        "trading_post": TradingPost,
        "temple": Temple,
        "temple_agrela": TempleAgrela,
        "temple_dauros": TempleDauros,
        "temple_fervus": TempleFervus,
        "temple_krypta": TempleKrypta,
        "temple_krolm": TempleKrolm,
        "temple_helia": TempleHelia,
        "temple_lunord": TempleLunord,
        "gnome_hovel": GnomeHovel,
        "elven_bungalow": ElvenBungalow,
        "dwarven_settlement": DwarvenSettlement,
        "guardhouse": Guardhouse,
        "ballista_tower": BallistaTower,
        "wizard_tower": WizardTower,
        "fairgrounds": Fairgrounds,
        "library": Library,
        "royal_gardens": RoyalGardens,
        "palace": Palace,
    }

    def create(self, building_type: str, grid_x: int, grid_y: int):
        """Return a placed building instance, or None for unknown type."""
        cls = self.BUILDING_REGISTRY.get(str(building_type))
        if cls is None:
            return None
        return cls(grid_x, grid_y)
