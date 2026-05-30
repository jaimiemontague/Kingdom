"""
WK71: hero resting behavior extracted from Hero into a mixin.

Mixed into Hero (``class Hero(HeroRestMixin, ...)``). Holds ONLY methods;
all instance state stays initialized in ``Hero.__init__``. Method bodies
moved VERBATIM (they already use ``self.*``, which resolves on the combined
Hero instance), so the MRO and every call site are unchanged.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from config import TILE_SIZE
from game.entities.hero import HeroState

if TYPE_CHECKING:
    from game.entities.buildings.base import Building


class HeroRestMixin:
    """WK71: resting behavior extracted from Hero. Mixed into Hero; accesses self.* set in Hero.__init__."""

    def should_go_home_to_rest(self) -> bool:
        """Check if hero should return home to rest."""
        damage_taken = self.max_hp - self.hp

        # If we've taken more than 10 total damage since last leaving home
        # and we're not already resting
        if self.state == HeroState.RESTING:
            return False

        # First time threshold: took 10+ damage total
        if self.damage_since_left_home >= 10:
            return True

        # If we left home damaged and took 5 more damage
        hp_missing_when_left = self.max_hp - self.hp_when_left_home
        if hp_missing_when_left > 10:
            # We left home still hurt, only return if we've taken 5 more
            additional_damage = self.damage_since_left_home
            if additional_damage >= 5:
                return True

        return False

    def start_resting(self):
        """Start resting at home."""
        return self.start_resting_at_building(self.home_building)

    def start_resting_at_building(
        self,
        building: "Building | None",
        *,
        duration_sec: float | None = None,
    ) -> bool:
        """Start resting in a specific safe building (home guild or inn)."""
        if building is None:
            self.state = HeroState.IDLE
            return False
        if getattr(building, "is_damaged", False):
            self.state = HeroState.IDLE
            return False

        # If switching buildings while already inside, notify the old building first.
        if self.is_inside_building and self.inside_building is not None and self.inside_building is not building:
            old_building = self.inside_building
            if hasattr(old_building, "on_hero_exit"):
                try:
                    old_building.on_hero_exit(self)
                except Exception:
                    pass

        self.is_inside_building = True
        self.inside_building = building
        self.inside_timer = max(0.0, float(duration_sec)) if duration_sec is not None else 0.0
        self.x = building.center_x
        self.y = building.center_y

        if hasattr(building, "on_hero_enter"):
            try:
                building.on_hero_enter(self)
            except Exception:
                pass

        self.state = HeroState.RESTING
        self.hp_healed_this_rest = 0
        self.last_heal_time = 0.0
        self._rest_heal_progress = 0.0
        return True

    def update_resting(self, dt: float) -> bool:
        """Update resting state. Returns True if still resting."""
        if self.state != HeroState.RESTING:
            return False

        rest_building = self.inside_building or self.home_building
        if rest_building is None:
            self.state = HeroState.IDLE
            return False

        # WK18-FEAT-002: Inn loiter fee and eject when broke (resting at Inn)
        if getattr(rest_building, "building_type", None) == "inn":
            from config import INN_LOITER_FEE_GOLD_PER_SEC
            deduct = max(0.0, float(INN_LOITER_FEE_GOLD_PER_SEC)) * dt
            if deduct > 0 and getattr(self, "gold", 0) > 0:
                accum = getattr(self, "_loiter_fee_accum", 0.0) + deduct
                if accum >= 1.0:
                    drop = int(accum)
                    self.gold = max(0, self.gold - drop)
                    self._loiter_fee_accum = accum - drop
                else:
                    self._loiter_fee_accum = accum
            if getattr(self, "gold", 0) < 1:
                self.pop_out_of_building()
                return False

        # Check if building is damaged - must pop out and defend.
        if getattr(rest_building, "is_damaged", False):
            self.pop_out_of_building()
            return False

        # Optional timed rest (used by inn/task-duration flows).
        if self.inside_timer > 0.0:
            self.inside_timer = max(0.0, self.inside_timer - dt)
            if self.inside_timer <= 0.0:
                self.finish_resting()
                return False

        # Default guild rate is 0.01 -> 1 HP per 2s.
        # Inn rate is 0.02 -> 1 HP per 1s.
        recovery_rate = float(getattr(rest_building, "rest_recovery_rate", 0.01))
        self._rest_heal_progress += max(0.0, recovery_rate) * 50.0 * float(dt)
        heal_points = int(self._rest_heal_progress)
        if heal_points > 0:
            self._rest_heal_progress -= float(heal_points)
            if self.hp < self.max_hp:
                applied = min(heal_points, self.max_hp - self.hp)
                self.hp += applied
                self.hp_healed_this_rest += applied

        # Stop resting if fully healed or healed 30 points
        if self.hp >= self.max_hp or self.hp_healed_this_rest >= 30:
            self.finish_resting()
            return False

        return True

    def pop_out_of_building(self) -> "Building | None":
        """Hero pops out of the current building and becomes targetable again."""
        popped_building = self.inside_building or self.home_building
        self.state = HeroState.IDLE
        self.hp_healed_this_rest = 0
        self.last_heal_time = 0.0
        self._rest_heal_progress = 0.0
        self.is_inside_building = False
        self.inside_timer = 0.0
        self.inside_building = None
        if popped_building and hasattr(popped_building, "on_hero_exit"):
            try:
                popped_building.on_hero_exit(self)
            except Exception:
                pass
        # Stay near the building to defend it / continue AI task resolution.
        if popped_building:
            self.x = popped_building.center_x + TILE_SIZE
            self.y = popped_building.center_y
        return popped_building

    def can_rest_at_home(self) -> bool:
        """Check if hero can rest at their home building."""
        if not self.home_building:
            return False
        # Cannot rest in damaged buildings
        return not self.home_building.is_damaged

    def finish_resting(self):
        """Finish resting and leave home."""
        self.state = HeroState.IDLE
        self.hp_when_left_home = self.hp
        self.damage_since_left_home = 0
        self.hp_healed_this_rest = 0
        # Exit building after resting.
        if self.is_inside_building:
            self.pop_out_of_building()

    def enter_building_briefly(self, building: "Building | None", duration_sec: float = 0.6) -> None:
        """Enter a building briefly (e.g. shopping) then auto-exit after duration."""
        if not building:
            return
        if self.is_inside_building and self.inside_building is not None and self.inside_building is not building:
            old_building = self.inside_building
            if hasattr(old_building, "on_hero_exit"):
                try:
                    old_building.on_hero_exit(self)
                except Exception:
                    pass
        self.is_inside_building = True
        self.inside_building = building
        self.inside_timer = max(0.0, float(duration_sec))
        self.x = building.center_x
        self.y = building.center_y
        if hasattr(building, "on_hero_enter"):
            try:
                building.on_hero_enter(self)
            except Exception:
                pass
