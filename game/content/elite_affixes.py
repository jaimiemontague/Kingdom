"""Deterministic elite affix registry and spawn-time application helpers."""

from __future__ import annotations

from dataclasses import dataclass

from config import TILE_SIZE
from game.sim.determinism import get_rng
from game.sim.timebase import now_ms as sim_now_ms


@dataclass(frozen=True, slots=True)
class EliteAffixDef:
    """Static description of one elite affix."""

    affix_id: str
    display_name: str
    description: str
    tell: str
    counterplay: str
    attack_bonus: int = 0
    defense_bonus: int = 0
    speed_multiplier: float = 1.0
    hp_multiplier: float = 1.0
    aura_attack_bonus: int = 0
    aura_radius_tiles: float = 0.0
    frenzy_threshold: float = 0.0
    frenzy_attack_bonus: int = 0
    courage_bonus: int = 0
    spawn_marker: str = ""


def _elite(
    affix_id: str,
    display_name: str,
    description: str,
    tell: str,
    counterplay: str,
    **kw,
) -> EliteAffixDef:
    return EliteAffixDef(
        affix_id=affix_id,
        display_name=display_name,
        description=description,
        tell=tell,
        counterplay=counterplay,
        **kw,
    )


ELITE_AFFIX_DEFS: dict[str, EliteAffixDef] = {
    "banner_bearer": _elite(
        "banner_bearer",
        "Skull-Banner",
        "A banner lifts the goblins around it into a bolder line.",
        "A skull-banner flutters over the pack.",
        "Focus the banner carrier first.",
        attack_bonus=1,
        aura_attack_bonus=2,
        aura_radius_tiles=4.5,
        courage_bonus=1,
        spawn_marker="banner",
    ),
    "ironhide": _elite(
        "ironhide",
        "Ironhide",
        "A plated hide blunts ordinary blows.",
        "Its skin gleams like dull iron.",
        "Use burst damage or armor-piercing strikes.",
        attack_bonus=0,
        defense_bonus=3,
        speed_multiplier=0.85,
        hp_multiplier=1.2,
        spawn_marker="shield",
    ),
    "frenzied": _elite(
        "frenzied",
        "Frenzied",
        "Once wounded, it fights like it has nothing left to lose.",
        "The creature starts foaming when hurt.",
        "Burst it down before the rage kicks in.",
        attack_bonus=1,
        frenzy_threshold=0.4,
        frenzy_attack_bonus=4,
        spawn_marker="rage",
    ),
}

ELITE_AFFIX_POOL: tuple[str, ...] = tuple(ELITE_AFFIX_DEFS)


def get_elite_affix_def(affix_id: str) -> EliteAffixDef:
    """Look up an elite affix definition by id."""
    return ELITE_AFFIX_DEFS[str(affix_id)]


def elite_title_for_affixes(affix_ids: tuple[str, ...]) -> str:
    """Pick a readable elite title from the rolled affixes."""
    ids = tuple(str(affix_id) for affix_id in affix_ids if str(affix_id).strip())
    if not ids:
        return ""
    if "banner_bearer" in ids:
        return ELITE_AFFIX_DEFS["banner_bearer"].display_name
    return ELITE_AFFIX_DEFS[ids[0]].display_name


def roll_elite_affixes(
    *,
    spawn_key: str = "",
    enemy_type: str = "",
    rng=None,
    min_affixes: int = 1,
    max_affixes: int = 2,
) -> tuple[str, ...]:
    """Roll a deterministic affix bundle for an enemy spawn."""
    if max_affixes <= 0 or not ELITE_AFFIX_POOL:
        return ()
    if rng is None:
        seed_tag = f"boss_encounters:elite:{spawn_key or enemy_type or 'spawn'}"
        rng = get_rng(seed_tag)

    count = max(1, int(min_affixes))
    if max_affixes > count and rng.random() < 0.5:
        count += 1
    count = min(count, max_affixes, len(ELITE_AFFIX_POOL))

    available = list(ELITE_AFFIX_POOL)
    rolled: list[str] = []
    for _ in range(count):
        idx = rng.randrange(len(available))
        rolled.append(available.pop(idx))
    return tuple(rolled)


def _entity_position(entity: object) -> tuple[float, float] | None:
    try:
        return float(getattr(entity, "x")), float(getattr(entity, "y"))
    except Exception:
        return None


def apply_elite_affixes(
    enemy: object,
    affix_ids: tuple[str, ...],
    *,
    nearby_enemies: tuple[object, ...] | list[object] = (),
    now_ms: int | None = None,
    spawn_key: str = "",
) -> tuple[dict[str, object], ...]:
    """Apply a deterministic elite bundle to a spawned enemy."""
    rolled_ids = tuple(str(affix_id) for affix_id in affix_ids if str(affix_id).strip())
    if not rolled_ids:
        return ()

    ts = int(sim_now_ms() if now_ms is None else now_ms)
    base_name = str(getattr(enemy, "name", "") or getattr(enemy, "enemy_type", "enemy")).replace("_", " ").title()
    elite_title = elite_title_for_affixes(rolled_ids)
    elite_name = f"{elite_title} {base_name}".strip()

    enemy.is_elite = True
    enemy.elite_affix_ids = rolled_ids
    enemy.elite_affix_names = tuple(get_elite_affix_def(affix_id).display_name for affix_id in rolled_ids)
    enemy.elite_title = elite_title
    enemy.elite_name = elite_name
    if not getattr(enemy, "is_boss", False):
        enemy.name = elite_name
    enemy.elite_spawned_at_ms = ts
    enemy.elite_spawn_key = str(spawn_key)
    enemy.elite_facts = []
    enemy.elite_banner_targets = ()
    enemy.elite_frenzy_active = False
    enemy.elite_frenzy_threshold = 0.4
    enemy.elite_frenzy_attack_bonus = 0
    enemy.elite_courage_bonus = 0
    enemy.elite_spawn_markers = ()

    fact_records: list[dict[str, object]] = []
    enemy_pos = _entity_position(enemy)

    for affix_id in rolled_ids:
        affix = get_elite_affix_def(affix_id)
        fact: dict[str, object] = {
            "event": "elite_affix_applied",
            "affix_id": affix.affix_id,
            "display_name": affix.display_name,
            "enemy_id": str(getattr(enemy, "entity_id", "")),
            "enemy_type": str(getattr(enemy, "enemy_type", "")),
            "time_ms": ts,
            "detail": affix.description,
        }

        if affix.attack_bonus:
            source = f"elite:{getattr(enemy, 'entity_id', '')}:{affix.affix_id}:self"
            enemy.set_attack_bonus(source, int(affix.attack_bonus))
            fact["attack_bonus"] = int(affix.attack_bonus)
        if affix.defense_bonus:
            enemy.defense = int(getattr(enemy, "defense", 0) or 0) + int(affix.defense_bonus)
            fact["defense_bonus"] = int(affix.defense_bonus)
        if affix.speed_multiplier != 1.0:
            enemy.speed = float(getattr(enemy, "speed", 0.0) or 0.0) * float(affix.speed_multiplier)
            fact["speed_multiplier"] = float(affix.speed_multiplier)
        if affix.hp_multiplier != 1.0:
            enemy.max_hp = max(1, int(round(float(getattr(enemy, "max_hp", 1) or 1) * float(affix.hp_multiplier))))
            enemy.hp = min(enemy.max_hp, max(1, int(round(float(getattr(enemy, "hp", 1) or 1) * float(affix.hp_multiplier)))))
            fact["hp_multiplier"] = float(affix.hp_multiplier)
        if affix.frenzy_threshold > 0.0:
            enemy.elite_frenzy_threshold = float(affix.frenzy_threshold)
            enemy.elite_frenzy_attack_bonus = int(affix.frenzy_attack_bonus)
            fact["frenzy_threshold"] = float(affix.frenzy_threshold)
            fact["frenzy_attack_bonus"] = int(affix.frenzy_attack_bonus)
        if affix.courage_bonus:
            enemy.elite_courage_bonus = int(getattr(enemy, "elite_courage_bonus", 0) or 0) + int(affix.courage_bonus)
            fact["courage_bonus"] = int(affix.courage_bonus)
        if affix.spawn_marker:
            markers = list(getattr(enemy, "elite_spawn_markers", ()) or ())
            markers.append(str(affix.spawn_marker))
            enemy.elite_spawn_markers = tuple(markers)
            fact["spawn_marker"] = str(affix.spawn_marker)
        if affix.aura_attack_bonus and nearby_enemies:
            radius_px = float(affix.aura_radius_tiles) * float(TILE_SIZE)
            buffed_ids: list[str] = []
            if enemy_pos is not None:
                ex, ey = enemy_pos
                for ally in nearby_enemies:
                    if ally is enemy or not getattr(ally, "is_alive", False):
                        continue
                    ally_pos = _entity_position(ally)
                    if ally_pos is None:
                        continue
                    ax, ay = ally_pos
                    dx = ex - ax
                    dy = ey - ay
                    if (dx * dx + dy * dy) > radius_px * radius_px:
                        continue
                    ally_source = f"elite:{getattr(enemy, 'entity_id', '')}:{affix.affix_id}:{getattr(ally, 'entity_id', '')}"
                    ally.set_attack_bonus(ally_source, int(affix.aura_attack_bonus))
                    buffed_ids.append(str(getattr(ally, "entity_id", "")))
            if buffed_ids:
                enemy.elite_banner_targets = tuple(buffed_ids)
                fact["buffed_enemy_ids"] = tuple(buffed_ids)

        fact_records.append(fact)

    enemy.elite_facts = tuple(fact_records)
    return tuple(fact_records)


def spawn_elite_enemy(
    enemy: object,
    *,
    nearby_enemies: tuple[object, ...] | list[object] = (),
    now_ms: int | None = None,
    spawn_key: str = "",
    rng=None,
    min_affixes: int = 1,
    max_affixes: int = 2,
) -> tuple[str, ...]:
    """Roll and apply elite affixes to a just-spawned enemy."""
    rolled = roll_elite_affixes(
        spawn_key=spawn_key or str(getattr(enemy, "entity_id", "")),
        enemy_type=str(getattr(enemy, "enemy_type", "")),
        rng=rng,
        min_affixes=min_affixes,
        max_affixes=max_affixes,
    )
    if rolled:
        apply_elite_affixes(
            enemy,
            rolled,
            nearby_enemies=nearby_enemies,
            now_ms=now_ms,
            spawn_key=spawn_key,
        )
    return rolled
