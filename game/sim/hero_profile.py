"""
Hero Profile read-model contracts (JSON-friendly snapshots).

Live gameplay state stays on `Hero`; UI and future LLM adapters consume these
immutable snapshots only — no pygame/ursina/UI/LLM imports here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable, TypeVar

from config import TILE_SIZE

from game.systems import hero_memory as _hm

_TPlace = TypeVar("_TPlace", bound="KnownPlaceSnapshot")
_TMemory = TypeVar("_TMemory", bound="HeroMemoryEntry")


def safe_percent(current: int | float, maximum: int | float) -> float:
    """Ratio in ``[0.0, 1.0]`` for ``current`` / ``maximum`` (``0.0`` if max <= 0)."""
    try:
        c = float(current)
        m = float(maximum)
    except (TypeError, ValueError):
        return 0.0
    if m <= 0:
        return 0.0
    return max(0.0, min(1.0, c / m))


def sort_known_places(places: Iterable[_TPlace]) -> tuple[_TPlace, ...]:
    """Deterministic order: ``first_seen_ms``, then ``place_id``."""
    return tuple(sorted(places, key=lambda p: (int(p.first_seen_ms), str(p.place_id))))


def sort_memory_entries(entries: Iterable[_TMemory]) -> tuple[_TMemory, ...]:
    """Deterministic order: ``sim_time_ms``, then ``entry_id``."""
    return tuple(sorted(entries, key=lambda e: (int(e.sim_time_ms), int(e.entry_id))))


PROFILE_DISCOVERY_BUILDING_TYPES = frozenset(
    {
        "marketplace",
        "blacksmith",
        "inn",
        "trading_post",
        "library",
        "wizard_tower",
        "guardhouse",
        "ballista_tower",
        "fairgrounds",
        "royal_gardens",
        "palace",
        "gnome_hovel",
        "elven_bungalow",
        "dwarven_settlement",
        "warrior_guild",
        "ranger_guild",
        "rogue_guild",
        "wizard_guild",
    }
)


def format_location_compact(hero: Any) -> str:
    """
    Compact room / overworld label (no pygame/UI deps). Uses duck typing only.
    """
    if getattr(hero, "is_inside_building", False):
        inn = getattr(hero, "inside_building", None)
        bt = getattr(inn, "building_type", None) if inn is not None else None
        label = getattr(bt, "value", bt) if bt is not None else ""
        label = str(label or "building").strip() or "building"
        return f"In:{label}"
    return "Out"


def compact_target_label(hero: Any) -> str:
    """Short HUD string for hunt/pursuit; truncates noisy labels."""
    raw = format_target_label(hero).strip()
    if not raw or raw == "none":
        return "-"
    if len(raw) > 56:
        return raw[:53] + "..."
    return raw


def format_target_label(subject: Any) -> str:
    """
    Compact label for a hero's ``target`` without importing ``Hero`` or UI.

    Uses duck typing only; unknown targets fall back to class name or ``none``.
    """
    t = getattr(subject, "target", subject)
    if t is None:
        return "none"
    if isinstance(t, dict):
        ttype = t.get("type")
        if ttype == "bounty":
            bid = t.get("bounty_id")
            bty = t.get("bounty_type", "explore")
            return f"bounty:{bty}:{bid}"
        if ttype == "shopping":
            item = t.get("item", "")
            return f"marketplace:{item}" if item else "marketplace"
        if ttype == "going_home":
            return "home"
        return f"goal:{ttype}"
    if hasattr(t, "is_alive"):
        et = getattr(t, "enemy_type", None)
        return f"enemy:{et}" if et is not None else "enemy"
    cls = getattr(t, "__class__", type(t)).__name__
    return cls.lower() if cls else "unknown"


@dataclass(frozen=True, slots=True)
class HeroIdentitySnapshot:
    hero_id: str
    name: str
    hero_class: str
    personality: str
    level: int


@dataclass(frozen=True, slots=True)
class HeroProgressionSnapshot:
    xp: int
    xp_to_level: int
    xp_percent: float


@dataclass(frozen=True, slots=True)
class HeroVitalsSnapshot:
    hp: int
    max_hp: int
    health_percent: float
    attack: int
    defense: int
    speed: float


@dataclass(frozen=True, slots=True)
class HeroInventorySnapshot:
    gold: int
    taxed_gold: int
    potions: int
    max_potions: int
    weapon_name: str
    weapon_attack: int
    armor_name: str
    armor_defense: int


@dataclass(frozen=True, slots=True)
class KnownPlaceSnapshot:
    place_id: str
    place_type: str
    display_name: str
    tile: tuple[int, int]
    world_pos: tuple[float, float]
    first_seen_ms: int
    last_seen_ms: int
    visits: int = 0
    last_visited_ms: int | None = None
    is_destroyed: bool = False


@dataclass(frozen=True, slots=True)
class HeroMemoryEntry:
    entry_id: int
    hero_id: str
    event_type: str
    sim_time_ms: int
    summary: str
    subject_type: str = ""
    subject_id: str = ""
    subject_name: str = ""
    tile: tuple[int, int] | None = None
    world_pos: tuple[float, float] | None = None
    tags: tuple[str, ...] = ()
    importance: int = 1


@dataclass(frozen=True, slots=True)
class HeroCareerSnapshot:
    tiles_revealed: int = 0
    places_discovered: int = 0
    enemies_defeated: int = 0
    bounties_claimed: int = 0
    gold_earned: int = 0
    purchases_made: int = 0


@dataclass(frozen=True, slots=True)
class HeroNarrativeSeedSnapshot:
    emotional_state: str = "steady"
    life_stage: str = "adventurer"
    personal_goal: str = "make a name in the kingdom"
    origin_hint: str = ""


@dataclass(frozen=True, slots=True)
class HeroProfileSnapshot:
    identity: HeroIdentitySnapshot
    progression: HeroProgressionSnapshot
    vitals: HeroVitalsSnapshot
    inventory: HeroInventorySnapshot
    career: HeroCareerSnapshot
    narrative: HeroNarrativeSeedSnapshot
    current_state: str
    current_intent: str
    current_location: str
    current_target: str
    last_decision: dict[str, Any] | None = None
    known_places: tuple[KnownPlaceSnapshot, ...] = field(default_factory=tuple)
    recent_memory: tuple[HeroMemoryEntry, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _building_type_slug(building: Any) -> str:
    bt = getattr(building, "building_type", None)
    return str(getattr(bt, "value", bt) or "").strip().lower()


def _iter_building_tiles(building: Any) -> Iterable[tuple[int, int]]:
    gx = int(getattr(building, "grid_x", 0))
    gy = int(getattr(building, "grid_y", 0))
    sz = getattr(building, "size", (1, 1))
    try:
        w, h = int(sz[0]), int(sz[1])
    except (TypeError, ValueError, IndexError):
        w, h = 1, 1
    w = max(1, w)
    h = max(1, h)
    for dx in range(w):
        for dy in range(h):
            yield (gx + dx, gy + dy)


def _building_qualifies_profile_discovery_candidate(building: Any) -> bool:
    """POI filter: shops/lairs/neutral dwellings/temple variants (deterministic taxonomy)."""
    if int(getattr(building, "hp", 1) or 1) <= 0:
        return False
    if getattr(building, "is_constructed", True) is not True:
        return False
    slug = _building_type_slug(building)
    if slug == "castle":
        return False
    if getattr(building, "is_lair", False) or hasattr(building, "stash_gold"):
        return True
    if slug.startswith("temple"):
        return True
    if slug in PROFILE_DISCOVERY_BUILDING_TYPES:
        return True
    if getattr(building, "is_neutral", False) and slug in {"house", "farm", "food_stand"}:
        return True
    return False


def discover_known_buildings_after_fog(
    *,
    buildings: Iterable[Any],
    heroes_world_vision: Iterable[tuple[Any, int, int, int]],
    newly_revealed: Iterable[tuple[int, int]],
    now_ms: int,
    tile_currently_visible: Callable[[int, int], bool] | None = None,
) -> None:
    """
    Credit heroes whose vision overlaps qualifying POIs.

    Paths (deterministic, sorted-building iteration):

    1. **Frontier**: a footprint tile is in ``newly_revealed`` (UNSEEN→VISIBLE) and within the
       hero vision circle — classic exploration.

    2. **Encounter** (optional): when ``tile_currently_visible`` is supplied, first-time credits
       for a place_id not yet in ``Hero.known_places`` may also trigger if any footprint tile
       under the hero circle is ``Visibility.VISIBLE`` on the simulation frame. This catches
       shops/lairs the castle/other revealers uncovered first — still no per-tick spam because
       we skip visibility checks once the place_id is recorded.

    - Dedup / career: ``Hero.remember_known_place`` handles merges; visibility path skips known ids.
    - Memory: emits at most one ``discovered_place`` event per hero per first sight (place_id).
    """
    rev_set = {(int(tx), int(ty)) for tx, ty in newly_revealed}

    cand = tuple(
        sorted(
            (b for b in buildings if _building_qualifies_profile_discovery_candidate(b)),
            key=lambda b: (_building_type_slug(b), int(getattr(b, "grid_x", 0)), int(getattr(b, "grid_y", 0))),
        )
    )

    ms = int(now_ms)

    for hero, hgx, hgy, r in heroes_world_vision:
        r_sq = int(r) * int(r)

        for building in cand:
            kp = getattr(hero, "known_places", None)
            pk_live: dict[Any, Any] = kp if isinstance(kp, dict) else {}

            slug = _building_type_slug(building)
            agx = int(getattr(building, "grid_x", 0))
            agy = int(getattr(building, "grid_y", 0))
            pid = _hm.stable_place_id(slug, agx, agy)
            already = pid in pk_live

            in_hero_sphere = False
            hit_frontier = False
            hit_visible_encounter = False

            for tx, ty in _iter_building_tiles(building):
                dx = int(tx) - int(hgx)
                dy = int(ty) - int(hgy)
                if (dx * dx + dy * dy) > r_sq:
                    continue
                in_hero_sphere = True
                if rev_set and (int(tx), int(ty)) in rev_set:
                    hit_frontier = True
                    continue
                if (
                    tile_currently_visible is not None
                    and not already
                    and tile_currently_visible(int(tx), int(ty))
                ):
                    hit_visible_encounter = True

            if not in_hero_sphere:
                continue
            if not (hit_frontier or hit_visible_encounter):
                continue

            kp2 = getattr(hero, "known_places", None)
            pk2: dict[Any, Any] = kp2 if isinstance(kp2, dict) else {}
            first_discovery = pid not in pk2
            dn = slug.replace("_", " ").strip().title()
            wc = getattr(building, "center_x", None)
            wh = getattr(building, "center_y", None)
            if wc is None or wh is None:
                wc = float(agx * int(TILE_SIZE))
                wh = float(agy * int(TILE_SIZE))
            else:
                wc, wh = float(wc), float(wh)

            rk = getattr(hero, "remember_known_place", None)
            if not callable(rk):
                continue
            rk(
                place_type=str(slug or "building"),
                display_name=dn or "Place",
                tile=(agx, agy),
                world_pos=(wc, wh),
                sim_time_ms=ms,
                building_type=slug,
                grid_x=agx,
                grid_y=agy,
            )
            rm = getattr(hero, "record_profile_memory", None)
            if first_discovery and callable(rm):
                rm(
                    event_type="discovered_place",
                    sim_time_ms=ms,
                    summary=f"Discovered {dn}",
                    subject_type="building",
                    subject_id=str(pid),
                    subject_name=dn,
                    tile=(agx, agy),
                    world_pos=(wc, wh),
                    tags=("discovery", slug),
                    importance=2,
                )


def build_hero_profile_snapshot(
    hero: Any,
    _game_state_or_sim: Any | None = None,
    *,
    now_ms: int | None = None,
) -> HeroProfileSnapshot:
    """
    Build immutable read-model from live ``Hero`` (duck typed). Uses sim time via ``hero`` accessors.
    """
    from game.sim.timebase import now_ms as sim_now_ms

    t = int(now_ms) if now_ms is not None else int(sim_now_ms())

    hid = str(getattr(hero, "hero_id", "") or "").strip() or "?"

    identity = HeroIdentitySnapshot(
        hero_id=hid,
        name=str(getattr(hero, "name", "")),
        hero_class=str(getattr(hero, "hero_class", "unknown")),
        personality=str(getattr(hero, "personality", "")),
        level=int(getattr(hero, "level", 1) or 1),
    )

    xp = int(getattr(hero, "xp", 0) or 0)
    xpto = max(1, int(getattr(hero, "xp_to_level", 100) or 100))
    progression = HeroProgressionSnapshot(
        xp=xp,
        xp_to_level=xpto,
        xp_percent=safe_percent(float(xp), float(xpto)),
    )

    max_hp = max(1, int(getattr(hero, "max_hp", 1) or 1))
    hp = int(getattr(hero, "hp", 0) or 0)

    atk_call = getattr(hero, "attack", None)
    def_call = getattr(hero, "defense", None)
    atk = int(atk_call()) if callable(atk_call) else int(atk_call) if atk_call is not None else 0
    dfs = int(def_call()) if callable(def_call) else int(def_call) if def_call is not None else 0

    vitals = HeroVitalsSnapshot(
        hp=hp,
        max_hp=max_hp,
        health_percent=safe_percent(hp, max_hp),
        attack=atk,
        defense=dfs,
        speed=float(getattr(hero, "speed", 0.0) or 0.0),
    )

    wpn = getattr(hero, "weapon", None)
    arm = getattr(hero, "armor", None)
    inventory = HeroInventorySnapshot(
        gold=int(getattr(hero, "gold", 0) or 0),
        taxed_gold=int(getattr(hero, "taxed_gold", 0) or 0),
        potions=int(getattr(hero, "potions", 0) or 0),
        max_potions=int(getattr(hero, "max_potions", 0) or 0),
        weapon_name=str((wpn or {}).get("name", "") if isinstance(wpn, dict) else ""),
        weapon_attack=int((wpn or {}).get("attack", 0) if isinstance(wpn, dict) else 0),
        armor_name=str((arm or {}).get("name", "") if isinstance(arm, dict) else ""),
        armor_defense=int((arm or {}).get("defense", 0) if isinstance(arm, dict) else 0),
    )

    pc_raw = getattr(hero, "profile_career", None) or {}
    career = HeroCareerSnapshot(
        tiles_revealed=int(pc_raw.get("tiles_revealed", 0)),
        places_discovered=int(pc_raw.get("places_discovered", 0)),
        enemies_defeated=int(pc_raw.get("enemies_defeated", 0)),
        bounties_claimed=int(pc_raw.get("bounties_claimed", 0)),
        gold_earned=int(pc_raw.get("gold_earned", 0)),
        purchases_made=int(pc_raw.get("purchases_made", 0)),
    )

    narrative = HeroNarrativeSeedSnapshot()

    st = getattr(hero, "state", None)
    try:
        if hasattr(st, "name"):
            cur_state = str(st.name)
        else:
            cur_state = str(st)
    except Exception:
        cur_state = "unknown"

    int_snap = getattr(hero, "get_intent_snapshot", None)
    if callable(int_snap):
        isd = int_snap(now_ms=t)
        cur_intent = str(isd.get("intent", getattr(hero, "intent", "idle")))
        ld = isd.get("last_decision")
        last_dec = ld if isinstance(ld, dict) else None
    else:
        cur_intent = str(getattr(hero, "intent", "idle"))
        ld0 = getattr(hero, "last_decision", None)
        if ld0 is not None and hasattr(ld0, "to_dict"):
            last_dec = ld0.to_dict(now_ms=t)
        else:
            last_dec = ld0 if isinstance(ld0, dict) else None

    kp = getattr(hero, "known_places", None)
    kp_vals = tuple(kp.values()) if isinstance(kp, dict) else ()
    sorted_places = sort_known_places(kp_vals)

    mem = getattr(hero, "profile_memory", None) or ()
    sorted_mem = sort_memory_entries(mem)

    return HeroProfileSnapshot(
        identity=identity,
        progression=progression,
        vitals=vitals,
        inventory=inventory,
        career=career,
        narrative=narrative,
        current_state=str(cur_state),
        current_intent=str(cur_intent),
        current_location=format_location_compact(hero),
        current_target=compact_target_label(hero),
        last_decision=last_dec,
        known_places=sorted_places,
        recent_memory=sorted_mem,
    )
