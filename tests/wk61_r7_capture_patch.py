"""WK61 R7 — apply UrsinaApp patch for hold-G tax overlay capture (import before main)."""
from __future__ import annotations

from config import TAX_STASH_BUILDING_TYPES


def _building_type_key(building) -> str:
    bt = getattr(building, "building_type", "")
    return str(getattr(bt, "value", bt) or "").strip().lower()


def _seed_tax_gold(engine) -> list[str]:
    seeded: list[str] = []
    for building in list(getattr(engine, "buildings", []) or []):
        bts = _building_type_key(building)
        if bts not in TAX_STASH_BUILDING_TYPES:
            continue
        if hasattr(building, "add_tax_gold"):
            building.add_tax_gold(42)
        else:
            building.stored_tax_gold = 42
        seeded.append(bts)
    return seeded


def _force_g_held(input_manager) -> None:
    orig = input_manager.is_key_pressed

    def _pressed(key: str) -> bool:
        if key == "g":
            return True
        return orig(key)

    input_manager.is_key_pressed = _pressed


def apply_patch() -> None:
    from game.graphics import ursina_app as ua
    from game.graphics.ursina_renderer import set_tax_gold_overlay_held

    orig_init = ua.UrsinaApp.__init__

    def patched_init(self, ai_controller_factory):
        orig_init(self, ai_controller_factory)
        _force_g_held(self.input_manager)
        set_tax_gold_overlay_held(True)
        seeded = _seed_tax_gold(self.engine)
        print(f"[wk61-r7-capture] Seeded tax gold on: {sorted(set(seeded))}", flush=True)

    ua.UrsinaApp.__init__ = patched_init


apply_patch()
