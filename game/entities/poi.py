"""
Points of Interest: discoverable map features that extend the Building system.

POIs are placed procedurally during world generation and sit hidden until a hero
walks within discovery range. Each POI carries a frozen definition (type, rarity,
interaction style) and mutable runtime state (discovered, interacted, depleted).
"""

from __future__ import annotations

from dataclasses import dataclass

from game.entities.buildings.base import Building


@dataclass(frozen=True)
class POIDefinition:
    """Immutable blueprint for a single POI type."""

    poi_type: str              # "poi_shrine", "poi_treasure_cache", etc.
    display_name: str          # "Shrine / Altar"
    building_type: str         # same as poi_type — maps to prefab system
    size: tuple[int, int]      # footprint in tiles
    difficulty_tier: int       # 1-5
    rarity: str                # "common", "uncommon", "rare", "legendary"
    interaction_type: str      # "shrine", "loot", "npc", "knowledge", "combat", "dungeon", "boss"
    is_persistent: bool        # True = stays after interaction
    vision_radius: int         # how far this POI reveals fog (0 for hidden)
    description: str           # LLM flavor text
    zone_affinity: tuple[str, ...]   # zone_ids where this can spawn
    elevation_preference: str  # "high", "mid", "low", "any"


class PointOfInterest(Building):
    """A discoverable map feature — hidden until a hero explores nearby."""

    is_poi = True  # duck-type flag for renderer

    def __init__(self, grid_x: int, grid_y: int, definition: POIDefinition):
        super().__init__(grid_x, grid_y, definition.building_type)
        self.poi_def = definition
        self.is_discovered = False
        self.is_interacted = False
        self.is_depleted = False
        self.discoverer_hero_id = None
        self.interaction_count = 0
        self.cooldown_remaining = 0.0
        # WK55: tick stamp of last interaction (renderer can flash/glow for ~1s)
        self.last_interaction_tick: int = 0
        # WK132: set True when a cleared POI (e.g. Ruined Outpost) becomes a
        # permanent fog-of-war revealer (radius = poi_def.vision_radius).
        self.grants_vision: bool = False

        # POIs are always fully "constructed" — they exist as world features
        self.is_constructed = True
        self.construction_started = True

    @property
    def is_targetable(self) -> bool:
        """POIs are not attackable by enemies."""
        return False


# ---------------------------------------------------------------------------
# POI definitions — one per type (12 Phase 1 + 5 WK132 round-out = 17 total)
# ---------------------------------------------------------------------------

POI_DEFINITIONS: dict[str, POIDefinition] = {
    "poi_shrine": POIDefinition(
        poi_type="poi_shrine",
        display_name="Shrine / Altar",
        building_type="poi_shrine",
        size=(1, 1),
        difficulty_tier=1,
        rarity="common",
        interaction_type="shrine",
        is_persistent=True,
        vision_radius=0,
        description=(
            "A moss-covered stone altar flanked by weathered pillars. "
            "Candles flicker in the still air, and a faint warmth radiates "
            "from the carved runes."
        ),
        zone_affinity=("castle_town", "darkwood", "mountains", "canyon_land"),
        elevation_preference="mid",
    ),
    "poi_treasure_cache": POIDefinition(
        poi_type="poi_treasure_cache",
        display_name="Treasure Cache",
        building_type="poi_treasure_cache",
        size=(1, 1),
        difficulty_tier=1,
        rarity="common",
        interaction_type="loot",
        is_persistent=False,
        vision_radius=0,
        description=(
            "A half-buried crate and a pair of barrels, their lids pried "
            "loose. Someone stashed supplies here and never came back."
        ),
        zone_affinity=("castle_town", "darkwood", "mountains", "canyon_land"),
        elevation_preference="any",
    ),
    "poi_hermit_hut": POIDefinition(
        poi_type="poi_hermit_hut",
        display_name="Hermit Hut",
        building_type="poi_hermit_hut",
        size=(1, 1),
        difficulty_tier=1,
        rarity="uncommon",
        interaction_type="npc",
        is_persistent=True,
        vision_radius=0,
        description=(
            "A ramshackle tent beside a cold campfire. Tools lie scattered "
            "around the clearing. Whoever lives here values solitude."
        ),
        zone_affinity=("darkwood", "canyon_land"),
        elevation_preference="low",
    ),
    "poi_gravestone": POIDefinition(
        poi_type="poi_gravestone",
        display_name="Overgrown Gravestone",
        building_type="poi_gravestone",
        size=(1, 1),
        difficulty_tier=1,
        rarity="common",
        interaction_type="knowledge",
        is_persistent=True,
        vision_radius=0,
        description=(
            "A cracked headstone barely visible beneath creeping vines. "
            "The inscription is faded but still legible."
        ),
        zone_affinity=("canyon_land", "darkwood"),
        elevation_preference="any",
    ),
    "poi_abandoned_camp": POIDefinition(
        poi_type="poi_abandoned_camp",
        display_name="Abandoned Camp",
        building_type="poi_abandoned_camp",
        size=(2, 2),
        difficulty_tier=2,
        rarity="common",
        interaction_type="combat",
        is_persistent=False,
        vision_radius=0,
        description=(
            "Two collapsed tents surround a dead campfire. Broken barrels "
            "and scattered tools suggest a hasty departure — or an ambush."
        ),
        zone_affinity=("darkwood", "canyon_land"),
        elevation_preference="low",
    ),
    "poi_druid_grove": POIDefinition(
        poi_type="poi_druid_grove",
        display_name="Druid Grove",
        building_type="poi_druid_grove",
        size=(3, 3),
        difficulty_tier=1,
        rarity="uncommon",
        interaction_type="shrine",
        is_persistent=True,
        vision_radius=0,
        description=(
            "Ancient oaks form a perfect circle around a mossy stone ring. "
            "Mushrooms and wildflowers carpet the ground. The air hums with "
            "old magic."
        ),
        zone_affinity=("darkwood",),
        elevation_preference="low",
    ),
    "poi_wizard_tower": POIDefinition(
        poi_type="poi_wizard_tower",
        display_name="Wizard's Tower",
        building_type="poi_wizard_tower",
        size=(2, 2),
        difficulty_tier=3,
        rarity="rare",
        interaction_type="knowledge",
        is_persistent=True,
        vision_radius=0,
        description=(
            "A slender tower of grey stone rises above the ridgeline. "
            "Blue light flickers behind narrow windows. The door is ajar."
        ),
        zone_affinity=("mountains", "canyon_land"),
        elevation_preference="high",
    ),
    "poi_graveyard": POIDefinition(
        poi_type="poi_graveyard",
        display_name="Overgrown Graveyard",
        building_type="poi_graveyard",
        size=(4, 4),
        difficulty_tier=4,
        rarity="rare",
        interaction_type="combat",
        is_persistent=True,
        vision_radius=0,
        description=(
            "Rows of headstones lean at odd angles behind a rusted iron "
            "fence. A small crypt squats at the centre. The ground is "
            "freshly disturbed."
        ),
        zone_affinity=("canyon_land",),
        elevation_preference="any",
    ),
    "poi_bandit_fortress": POIDefinition(
        poi_type="poi_bandit_fortress",
        display_name="Bandit Fortress",
        building_type="poi_bandit_fortress",
        size=(5, 5),
        difficulty_tier=5,
        rarity="legendary",
        interaction_type="boss",
        is_persistent=True,
        vision_radius=0,
        description=(
            "Wooden palisades ring a crude stronghold of tents, watch-towers "
            "and campfires. Armed figures patrol the walls. A banner bearing "
            "a skull flaps in the wind."
        ),
        zone_affinity=("canyon_land", "darkwood"),
        elevation_preference="any",
    ),
    "poi_cave_entrance": POIDefinition(
        poi_type="poi_cave_entrance",
        display_name="Cave Entrance",
        building_type="poi_cave_entrance",
        size=(2, 2),
        difficulty_tier=3,
        rarity="uncommon",
        interaction_type="dungeon",
        is_persistent=True,
        vision_radius=0,
        description=(
            "A dark opening in the cliff face, framed by jagged rock. "
            "Cold air seeps outward, carrying the faint echo of dripping "
            "water."
        ),
        zone_affinity=("mountains",),
        elevation_preference="high",
    ),
    "poi_mine_entrance": POIDefinition(
        poi_type="poi_mine_entrance",
        display_name="Mine Entrance",
        building_type="poi_mine_entrance",
        size=(2, 2),
        difficulty_tier=2,
        rarity="uncommon",
        interaction_type="dungeon",
        is_persistent=True,
        vision_radius=0,
        description=(
            "Rough-hewn timber braces the mouth of an old mine shaft. "
            "A pickaxe leans against the wall and ore barrels sit "
            "beside the entrance."
        ),
        zone_affinity=("mountains",),
        elevation_preference="high",
    ),
    "poi_demon_portal": POIDefinition(
        poi_type="poi_demon_portal",
        display_name="Demon Portal",
        building_type="poi_demon_portal",
        size=(2, 2),
        difficulty_tier=5,
        rarity="legendary",
        interaction_type="boss",
        is_persistent=True,
        vision_radius=0,
        description=(
            "Four obsidian pillars surround a ring of guttering candles. "
            "The air shimmers with heat and the ground is scorched black. "
            "Something watches from the other side."
        ),
        zone_affinity=("canyon_land",),
        elevation_preference="any",
    ),
    # -----------------------------------------------------------------
    # WK132: POIs round-out — 5 remaining types from pois_proposal §4.
    # Prefabs authored in parallel by Agent 15 as
    # assets/prefabs/buildings/poi_<id>_v1.json (renderer falls back to
    # "<building_type>_v1.json" automatically).
    # -----------------------------------------------------------------
    "poi_mysterious_well": POIDefinition(
        poi_type="poi_mysterious_well",
        display_name="Mysterious Well",
        building_type="poi_mysterious_well",
        size=(1, 1),
        difficulty_tier=2,
        rarity="uncommon",
        interaction_type="well",
        is_persistent=False,
        vision_radius=0,
        description=(
            "A dark stone well ringed by smooth rocks. The water far below "
            "is black and perfectly still — until you lean over the edge."
        ),
        zone_affinity=("castle_town", "darkwood", "mountains", "canyon_land"),
        elevation_preference="any",
    ),
    "poi_ruined_outpost": POIDefinition(
        poi_type="poi_ruined_outpost",
        display_name="Ruined Outpost",
        building_type="poi_ruined_outpost",
        size=(3, 3),
        difficulty_tier=3,  # proposal band 2-3; 3 picked for skeleton/goblin mix
        rarity="uncommon",
        interaction_type="outpost",
        is_persistent=True,
        vision_radius=5,  # permanent fog reveal radius once cleared
        description=(
            "Crumbled walls and a single intact watchtower mark an old "
            "frontier outpost. Something has made its nest in the rubble, "
            "but the tower still commands the surrounding land."
        ),
        zone_affinity=("mountains", "canyon_land"),
        elevation_preference="any",
    ),
    "poi_windmill_ruin": POIDefinition(
        poi_type="poi_windmill_ruin",
        display_name="Windmill Ruin",
        building_type="poi_windmill_ruin",
        size=(2, 2),
        difficulty_tier=1,
        rarity="rare",
        interaction_type="windmill",
        is_persistent=True,
        vision_radius=0,
        description=(
            "A leaning windmill with tattered sails creaks in the wind. "
            "Broken fence posts trace the outline of a farmstead long "
            "abandoned to the frontier."
        ),
        zone_affinity=("frontier",),  # placed via the unzoned frontier palette
        elevation_preference="any",
    ),
    "poi_ancient_ruins": POIDefinition(
        poi_type="poi_ancient_ruins",
        display_name="Ancient Ruins",
        building_type="poi_ancient_ruins",
        size=(5, 5),
        difficulty_tier=3,  # proposal band 3-4; 3 keeps loot in the uncommon pool
        rarity="rare",
        interaction_type="ruins",
        is_persistent=True,
        vision_radius=0,
        description=(
            "Toppled columns and moss-eaten walls of an elder civilisation. "
            "Carvings on the central altar map the surrounding lands — and "
            "hint at treasures the ages have not yet claimed."
        ),
        zone_affinity=("darkwood", "mountains", "canyon_land"),
        elevation_preference="any",
    ),
    "poi_dragon_cave": POIDefinition(
        poi_type="poi_dragon_cave",
        display_name="Dragon Cave",
        building_type="poi_dragon_cave",
        size=(3, 3),
        difficulty_tier=5,
        rarity="legendary",
        interaction_type="boss",
        is_persistent=True,
        vision_radius=0,
        description=(
            "A vast cave mouth framed by scorched rock and scattered bones. "
            "Smoke curls from the darkness within, and the ground trembles "
            "with a slow, enormous breathing."
        ),
        zone_affinity=("mountains",),
        elevation_preference="high",
    ),
}
