"""
WK131: Item registry — the single authoritative catalogue of items.

Design constraints (hard rails):
- The shop-stock dicts in ``game/entities/buildings/economic.py`` are now
  GENERATED from this registry via :func:`to_shop_dict` and must stay
  byte-compatible with the pre-WK131 hardcoded lists (same names, types,
  styles, prices, attack/defense/effect values) so existing saves, tests
  and the WK67 AI-decision digest see the identical stock.
- This module draws NO RNG and reads NO sim time — it is pure data, safe to
  import anywhere (including the digest scenario).
- Item tuning constants live HERE, not in config.py (per WK131 scope rails).
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------

SLOTS = ("weapon", "armor", "accessory", "consumable")
RARITIES = ("common", "uncommon", "rare", "legendary")

# Legacy shop-dict "type" values per slot (hero.buy_item / do_shopping read these).
_LEGACY_TYPE_BY_SLOT = {
    "weapon": "weapon",
    "armor": "armor",
    "accessory": "accessory",
    "consumable": "potion",
}

# Blacksmith sells its catalogue 40% below marketplace price (pre-WK131 behavior:
# Iron Sword 80 -> 48, Leather Armor 60 -> 36, Steel Sword 150 -> 90,
# Chain Mail 120 -> 72, Mithril Blade 250 -> 150, Plate Armor 200 -> 120).
BLACKSMITH_DISCOUNT = 0.40


@dataclass(frozen=True, slots=True)
class ItemDef:
    """Immutable item definition. Stat mods are additive."""

    item_id: str
    name: str
    slot: str                 # weapon | armor | accessory | consumable
    rarity: str = "common"    # common | uncommon | rare | legendary
    buy_price: int = 0        # marketplace (base) price
    sell_price: int = 0       # what a hero gets when selling (gross, pre-tax)
    attack: int = 0
    defense: int = 0
    speed: float = 0.0
    max_hp: int = 0
    style: str = ""           # weapon style: melee | ranged | magic | "" (legacy compat)
    effect: int = 0           # consumable heal amount (legacy "effect" key)
    flavor: str = ""

    @property
    def blacksmith_price(self) -> int:
        return int(round(self.buy_price * (1.0 - BLACKSMITH_DISCOUNT)))


def _i(item_id: str, name: str, slot: str, rarity: str, buy: int, **kw) -> ItemDef:
    sell = kw.pop("sell_price", max(1, buy // 2))
    return ItemDef(
        item_id=item_id, name=name, slot=slot, rarity=rarity,
        buy_price=int(buy), sell_price=int(sell), **kw,
    )


# ---------------------------------------------------------------------------
# Registry (~22 items)
# ---------------------------------------------------------------------------

_ALL_ITEMS: tuple[ItemDef, ...] = (
    # --- Weapons (the first 8 subsume the old Marketplace.items weapon dicts;
    #     names/styles/prices/attack MUST NOT change) -------------------------
    _i("dagger", "Dagger", "weapon", "common", 60, attack=4, style="melee",
       flavor="A plain blade for desperate work."),
    _i("short_bow", "Short Bow", "weapon", "common", 70, attack=4, style="ranged",
       flavor="Light, quick, and forgiving of poor aim."),
    _i("apprentice_staff", "Apprentice Staff", "weapon", "common", 90, attack=6, style="magic",
       flavor="Still smells faintly of classroom chalk."),
    _i("iron_sword", "Iron Sword", "weapon", "common", 80, attack=5,
       flavor="The honest backbone of every militia."),
    _i("long_bow", "Long Bow", "weapon", "uncommon", 140, attack=8, style="ranged",
       flavor="Yew-cut and waxed; sings when drawn."),
    _i("poison_dagger", "Poison Dagger", "weapon", "uncommon", 120, attack=7, style="melee",
       flavor="The green sheen is not decorative."),
    _i("steel_sword", "Steel Sword", "weapon", "uncommon", 150, attack=10,
       flavor="Folded steel, guild-stamped."),
    _i("wizard_staff", "Wizard Staff", "weapon", "rare", 180, attack=12, style="magic",
       flavor="Hums softly near ley lines."),
    # Blacksmith research tier (price 150 at the smith = 250 * 0.6).
    _i("mithril_blade", "Mithril Blade", "weapon", "rare", 250, attack=15,
       flavor="Lighter than doubt, sharper than rumor."),
    # Loot-only legendary.
    _i("runed_warhammer", "Runed Warhammer", "weapon", "legendary", 400, attack=18, style="melee",
       flavor="The runes glow when monsters are near."),

    # --- Armor (first 3 subsume the old shop armor dicts) -------------------
    _i("leather_armor", "Leather Armor", "armor", "common", 60, defense=3,
       flavor="Boiled, oiled, and only slightly chewed."),
    _i("chain_mail", "Chain Mail", "armor", "uncommon", 120, defense=7,
       flavor="A thousand patient rings."),
    _i("plate_armor", "Plate Armor", "armor", "rare", 200, defense=12,
       flavor="Walking fortress, slight echo."),
    # Loot-only legendary.
    _i("dragonscale_armor", "Dragonscale Armor", "armor", "legendary", 450, defense=16,
       flavor="Still warm to the touch."),

    # --- Accessories (new slot; loot-only in WK131) --------------------------
    _i("ring_of_strength", "Ring of Strength", "accessory", "uncommon", 90, attack=3,
       flavor="Tightens pleasantly before a brawl."),
    _i("iron_amulet", "Iron Amulet", "accessory", "uncommon", 90, defense=3,
       flavor="Cold iron turns ill intent."),
    _i("swift_boots", "Swift Boots", "accessory", "uncommon", 100, speed=0.35,
       flavor="The cobbler swore they were 'barely cursed'."),
    _i("vitality_pendant", "Vitality Pendant", "accessory", "rare", 140, max_hp=25,
       flavor="Beats faintly, like a second heart."),
    _i("hawk_signet", "Hawk Signet", "accessory", "rare", 160, attack=2, defense=2,
       flavor="Sigil of a long-dead border lord."),

    # --- Consumables ---------------------------------------------------------
    _i("healing_potion", "Healing Potion", "consumable", "common", 15, effect=50,
       flavor="Tastes of mint and regret."),
    _i("greater_healing_potion", "Greater Healing Potion", "consumable", "uncommon", 40, effect=100,
       flavor="Twice the mint, twice the regret."),
    _i("swiftness_draught", "Swiftness Draught", "consumable", "common", 30,
       flavor="Fizzes alarmingly. Sells well to the impatient."),
)

ITEMS: dict[str, ItemDef] = {item.item_id: item for item in _ALL_ITEMS}

# --- Shop stock lists (order matters: mirrors the pre-WK131 hardcoded lists) ---

MARKETPLACE_STOCK: tuple[str, ...] = (
    "dagger", "short_bow", "apprentice_staff", "iron_sword", "long_bow",
    "poison_dagger", "steel_sword", "wizard_staff", "leather_armor", "chain_mail",
)

BLACKSMITH_BASE_STOCK: tuple[str, ...] = ("iron_sword", "leather_armor")
BLACKSMITH_WEAPON_RESEARCH_STOCK: tuple[str, ...] = ("steel_sword", "mithril_blade")
BLACKSMITH_ARMOR_RESEARCH_STOCK: tuple[str, ...] = ("chain_mail", "plate_armor")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def get_item(item_id: str) -> ItemDef:
    """Look up an item by id. Raises KeyError for unknown ids."""
    return ITEMS[item_id]


def all_items() -> tuple[ItemDef, ...]:
    return _ALL_ITEMS


def to_shop_dict(item_id: str, *, price: int | None = None) -> dict:
    """Project an item into the legacy shop-dict shape.

    Byte-compatible with the pre-WK131 hardcoded dicts for every key the game
    reads (name/type/style/price/attack/defense/effect), plus an ``id`` key so
    downstream code can map a purchased dict back to its :class:`ItemDef`.
    The ``style`` key is present only when the legacy dict carried one.
    """
    item = ITEMS[item_id]
    d: dict = {"name": item.name, "type": _LEGACY_TYPE_BY_SLOT[item.slot]}
    if item.style:
        d["style"] = item.style
    d["price"] = int(price) if price is not None else int(item.buy_price)
    if item.slot == "weapon":
        d["attack"] = int(item.attack)
    elif item.slot == "armor":
        d["defense"] = int(item.defense)
    elif item.slot == "consumable" and item.effect:
        d["effect"] = int(item.effect)
    d["id"] = item.item_id
    return d


def find_by_name(name: str) -> ItemDef | None:
    """Reverse lookup by display name (legacy dicts carry only names)."""
    for item in _ALL_ITEMS:
        if item.name == name:
            return item
    return None
