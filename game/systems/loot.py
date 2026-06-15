"""
WK131: seeded loot tables — item drops from enemy kills and POI loot caches.

Determinism / digest rails:
- ALL randomness flows through one ``get_rng("loot")`` stream owned by the
  :class:`LootSystem` instance (injectable for tests).
- RNG is drawn ONLY inside ``roll_enemy_drop`` / ``roll_poi_drop``, which are
  called ONLY from kill events (``ENEMY_KILLED`` routing in ``sim_engine``) and
  POI loot interactions (``poi_interaction._handle_loot``). The WK67 digest
  scenario has no enemies and no POIs, so this module never draws RNG there —
  constructing a ``LootSystem`` performs zero draws.
- No ground-item entities in this MVP: drops go straight to the killer/looter
  hero via ``hero.receive_item`` (auto-equip if better, else backpack).
"""

from __future__ import annotations

from game.content.items import ItemDef, get_item
from game.sim.determinism import get_rng

# ---------------------------------------------------------------------------
# Tunables (item constants live in content/items.py + here, NOT config.py)
# ---------------------------------------------------------------------------

# Regular enemies: small chance of a common drop on kill.
ENEMY_DROP_CHANCE = 0.07

# Bosses always drop, from the rare+ pool.
# WK132: "dragon" (Dragon Cave boss) added — the guaranteed rare+/legendary
# drop rides the existing kill-event pipeline, so no extra cave-completion
# loot hook is needed (single drop path, no double-dipping).
BOSS_ENEMY_TYPES = ("bandit_lord", "demon_overlord", "dragon", "goblin_warchief")

# POI loot caches: chance of an item IN ADDITION to the existing gold roll.
POI_ITEM_DROP_CHANCE = 0.35

# Drop pools by rarity band (item ids; stable ordering = deterministic choice).
COMMON_DROP_POOL: tuple[str, ...] = (
    "dagger", "short_bow", "iron_sword", "leather_armor",
    "healing_potion", "swiftness_draught",
)
UNCOMMON_DROP_POOL: tuple[str, ...] = (
    "long_bow", "poison_dagger", "steel_sword", "chain_mail",
    "ring_of_strength", "iron_amulet", "swift_boots", "greater_healing_potion",
)
RARE_PLUS_DROP_POOL: tuple[str, ...] = (
    "wizard_staff", "mithril_blade", "plate_armor",
    "vitality_pendant", "hawk_signet",
    "runed_warhammer", "dragonscale_armor",
)


class LootSystem:
    """Seeded loot roller. One instance per sim engine (plus one inside the
    POI interaction system); independent instances share the same derived
    seed but draw from independent streams, which is fine because each is
    advanced only by its own event source."""

    def __init__(self, rng=None):
        # No draws happen here — get_rng(tag) only seeds a fresh stream.
        self._rng = rng if rng is not None else get_rng("loot")

    # ------------------------------------------------------------------
    # Rolls (the ONLY methods that draw RNG)
    # ------------------------------------------------------------------

    def roll_enemy_drop(self, enemy_type: str) -> ItemDef | None:
        """Roll a drop for a killed enemy. Bosses always drop rare+;
        regular enemies have a small chance of a common drop."""
        if str(enemy_type) in BOSS_ENEMY_TYPES:
            return get_item(self._rng.choice(RARE_PLUS_DROP_POOL))
        if self._rng.random() < ENEMY_DROP_CHANCE:
            return get_item(self._rng.choice(COMMON_DROP_POOL))
        return None

    def roll_poi_drop(self, tier: int) -> ItemDef | None:
        """Roll an item for a POI loot cache (in addition to gold).
        Pool scales with the POI difficulty tier.

        WK132: the existing tier mapping already realises the per-type loot
        spec, so no new pools were added: caches (t1) and wells (t2) hit the
        common pool, Ancient Ruins (t3) the uncommon pool, and t4+ rare+.
        Dragon Cave legendary loot comes from the dragon's guaranteed boss
        kill drop (BOSS_ENEMY_TYPES), not from a poi drop roll."""
        if self._rng.random() >= POI_ITEM_DROP_CHANCE:
            return None
        tier = int(tier)
        if tier <= 2:
            pool = COMMON_DROP_POOL
        elif tier == 3:
            pool = UNCOMMON_DROP_POOL
        else:
            pool = RARE_PLUS_DROP_POOL
        return get_item(self._rng.choice(pool))

    # ------------------------------------------------------------------
    # Delivery
    # ------------------------------------------------------------------

    @staticmethod
    def grant_item(hero, item: ItemDef) -> str:
        """Hand a rolled item to a hero. Returns 'equipped' | 'stored' | 'dropped'."""
        receive = getattr(hero, "receive_item", None)
        if callable(receive):
            return str(receive(item))
        return "dropped"
