"""
Bounty system for incentivizing hero behavior.
"""
import pygame
import math
from config import TILE_SIZE, COLOR_GOLD, COLOR_WHITE
from game.graphics.font_cache import get_font
from game.sim.timebase import now_ms as sim_now_ms


class Bounty:
    """A bounty/reward flag placed by the player."""

    # Simple monotonic id generator (kept local to this module; good enough for a prototype).
    _NEXT_ID = 1

    def __init__(self, x: float, y: float, reward: int, bounty_type: str = "explore", target=None):
        self.x = x
        self.y = y
        self.reward = reward
        # Types:
        # - explore: go to location and claim
        # - attack_lair: attack a lair target (requires target)
        # - defend_building: defend/repair a building target (requires target)
        # - hunt_enemy_type: optional; target should be an enemy_type string
        self.bounty_type = bounty_type
        self.claimed = False
        self.claimed_by = None
        self.target = target  # For non-explore bounties: building/enemy_type/etc

        # Metadata for AI coordination
        self.bounty_id = Bounty._NEXT_ID
        Bounty._NEXT_ID += 1

        self.created_time_ms = sim_now_ms()
        self.claimed_time_ms = None
        self.assigned_to = None
        self.assigned_time_ms = None

        # Contract metrics (computed by BountySystem; safe fallbacks if never set)
        # NOTE: Keep these names stable; QA + UI rely on them.
        self.responders = 0
        # Back-compat alias for QA tooling (some checks look for this specifically)
        self.responder_count = 0
        self.attractiveness_score = 0.0
        self.attractiveness_tier = "low"  # "low" | "med" | "high"

        # UI metrics (legacy/cache-friendly mirrors; keep in sync with contract fields)
        self.ui_responders = 0
        self.ui_attractiveness = "low"  # "low" | "med" | "high"
        self.ui_score = 0.0

        # Cached text surfaces (avoid per-frame allocations for static/slow-changing labels)
        self._ui_cache_reward_value = None
        self._ui_cache_reward_surf = None
        self._ui_cache_reward_rect = None
        self._ui_cache_meta_key = None  # (responders:int, tier:str)
        self._ui_cache_r_surf = None
        self._ui_cache_a_surf = None
        self._ui_cache_r_w = 0
        
    @property
    def grid_x(self) -> int:
        return int(self.x // TILE_SIZE)
    
    @property
    def grid_y(self) -> int:
        return int(self.y // TILE_SIZE)
    
    def claim(self, hero):
        """Claim this bounty."""
        if not self.claimed:
            self.claimed = True
            self.claimed_by = hero.name
            # Use normal hero gold flow so taxes apply consistently.
            if hasattr(hero, "add_gold"):
                hero.add_gold(self.reward)
            else:
                hero.gold += self.reward
            self.claimed_time_ms = sim_now_ms()
            return True
        return False

    def assign(self, hero_name: str):
        """Mark this bounty as assigned to a hero (best-effort coordination to avoid dogpiles)."""
        self.assigned_to = hero_name
        self.assigned_time_ms = sim_now_ms()
        # Ensure responder fields become >0 as soon as a hero explicitly takes the bounty.
        # This avoids missing short-lived targeting windows due to UI metric cadencing.
        try:
            self.responder_count = max(int(getattr(self, "responder_count", 0) or 0), 1)
        except Exception:
            self.responder_count = 1
        try:
            # Contract field `responders` is currently stored as an int count in this prototype.
            self.responders = max(int(getattr(self, "responders", 0) or 0), 1)
        except Exception:
            self.responders = 1

    def unassign(self):
        self.assigned_to = None
        self.assigned_time_ms = None

    def is_assigned_active(self, now_ms: int, ttl_ms: int) -> bool:
        if not self.assigned_to or self.assigned_time_ms is None:
            return False
        return (now_ms - int(self.assigned_time_ms)) < int(ttl_ms)

    def is_available_for(self, hero_name: str, now_ms: int, ttl_ms: int) -> bool:
        """Whether this bounty is free to be taken by the given hero."""
        if self.claimed:
            return False
        if not self.assigned_to:
            return True
        if self.assigned_to == hero_name:
            return True
        # Allow "stealing" if the assignment is stale.
        return not self.is_assigned_active(now_ms, ttl_ms)

    def is_valid(self, buildings: list) -> bool:
        """
        Whether the bounty still makes sense.

        Note: This is intentionally lightweight; other systems can add richer validity checks.
        """
        if self.claimed:
            return False

        if self.bounty_type == "explore":
            return True

        # Targeted bounties must have a target that still exists.
        if self.target is None:
            return False

        if self.bounty_type == "attack_lair":
            # If target object is still in buildings and has HP, it is valid.
            return (self.target in buildings) and getattr(self.target, "hp", 1) > 0

        if self.bounty_type == "defend_building":
            if self.target not in buildings:
                return False
            # Only valid while damaged or under attack (or unconstructed).
            if getattr(self.target, "is_damaged", False) or getattr(self.target, "is_under_attack", False):
                return True
            if hasattr(self.target, "is_constructed") and not getattr(self.target, "is_constructed", True):
                return True
            return False

        if self.bounty_type == "hunt_enemy_type":
            # Valid if target is a non-empty string.
            return isinstance(self.target, str) and bool(self.target.strip())

        # Unknown types default to valid (prototype friendliness)
        return True

    def estimate_risk(self, enemies: list, radius_px: float = TILE_SIZE * 10) -> float:
        """
        Simple risk heuristic: weighted count of nearby enemies.
        Returns a float where higher == riskier.
        """
        if not enemies:
            return 0.0
        r2 = float(radius_px) * float(radius_px)
        risk = 0.0
        for e in enemies:
            if not getattr(e, "is_alive", True):
                continue
            dx = float(e.x) - float(self.x)
            dy = float(e.y) - float(self.y)
            if (dx * dx + dy * dy) <= r2:
                hp_pct = 1.0
                try:
                    hp_pct = float(e.hp) / float(e.max_hp) if getattr(e, "max_hp", 0) else 1.0
                except Exception:
                    hp_pct = 1.0
                atk = float(getattr(e, "attack_power", 5))
                # A small heuristic: high-attack and high-hp enemies contribute more.
                risk += 0.25 + 0.02 * atk + 0.5 * max(0.0, min(1.0, hp_pct))
        return risk

    def get_goal_position(self, buildings: list) -> tuple[float, float]:
        """
        Resolve where a hero should walk to for this bounty.
        For targeted bounties, use the target's center if available.
        """
        if self.bounty_type in ("attack_lair", "defend_building") and self.target is not None:
            if hasattr(self.target, "center_x") and hasattr(self.target, "center_y"):
                return float(self.target.center_x), float(self.target.center_y)
        return float(self.x), float(self.y)
    
    def is_near(self, x: float, y: float, distance: float = TILE_SIZE * 2) -> bool:
        """Check if a position is near this bounty."""
        dx = self.x - x
        dy = self.y - y
        return (dx * dx + dy * dy) <= distance * distance
    
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        """Render the bounty flag."""
        if self.claimed:
            return
        
        cam_x, cam_y = camera_offset
        screen_x = self.x - cam_x
        screen_y = self.y - cam_y
        
        # WK6: Draw flag pole with stronger outline for black fog visibility
        # Pole outline (darker brown for contrast)
        pygame.draw.line(
            surface,
            (80, 50, 25),  # Dark brown outline
            (screen_x, screen_y),
            (screen_x, screen_y - 30),
            5
        )
        # Pole core
        pygame.draw.line(
            surface,
            (139, 90, 43),  # Brown
            (screen_x, screen_y),
            (screen_x, screen_y - 30),
            3
        )
        
        # Draw flag with outline for black fog visibility
        flag_color = COLOR_GOLD
        flag_points = [
            (screen_x, screen_y - 30),
            (screen_x + 20, screen_y - 25),
            (screen_x, screen_y - 20),
        ]
        # WK6: Add dark outline for black fog contrast
        pygame.draw.polygon(surface, (100, 80, 0), flag_points)  # Dark gold outline
        pygame.draw.polygon(surface, flag_color, flag_points)
        
        # Draw reward amount
        font = get_font(16)
        reward_val = int(getattr(self, "reward", 0) or 0)
        if self._ui_cache_reward_value != reward_val or self._ui_cache_reward_surf is None:
            self._ui_cache_reward_value = reward_val
            self._ui_cache_reward_surf = font.render(f"${reward_val}", True, COLOR_WHITE)
            self._ui_cache_reward_rect = self._ui_cache_reward_surf.get_rect(center=(0, 0))
        if self._ui_cache_reward_surf is not None and self._ui_cache_reward_rect is not None:
            # Position per-frame, but reuse surface/rect template
            rect = self._ui_cache_reward_rect.copy()
            rect.center = (screen_x + 10, screen_y - 35)
            surface.blit(self._ui_cache_reward_surf, rect)

        # Draw responders + attractiveness (compact, readable)
        responders = int(getattr(self, "responders", getattr(self, "ui_responders", 0)) or 0)
        tier = str(getattr(self, "attractiveness_tier", getattr(self, "ui_attractiveness", "low")) or "low").lower()
        tier_label = {"low": "Low", "med": "Med", "high": "High"}.get(tier, "Low")
        tier_color = {"low": (150, 150, 150), "med": (240, 210, 90), "high": (110, 230, 140)}.get(tier, (150, 150, 150))

        meta_font = get_font(14)
        meta_key = (int(responders), str(tier))
        if self._ui_cache_meta_key != meta_key or self._ui_cache_r_surf is None or self._ui_cache_a_surf is None:
            self._ui_cache_meta_key = meta_key
            self._ui_cache_r_surf = meta_font.render(f"R:{responders}", True, COLOR_WHITE)
            self._ui_cache_r_w = int(self._ui_cache_r_surf.get_width()) if self._ui_cache_r_surf else 0
            self._ui_cache_a_surf = meta_font.render(tier_label, True, tier_color)

        if self._ui_cache_r_surf is not None:
            surface.blit(self._ui_cache_r_surf, (screen_x + 24, screen_y - 18))
        if self._ui_cache_a_surf is not None:
            surface.blit(self._ui_cache_a_surf, (screen_x + 24 + self._ui_cache_r_w + 6, screen_y - 18))


class BountySystem:
    """Manages bounties in the game."""
    
    def __init__(self):
        self.bounties = []
        self.total_claimed = 0
        self.total_spent = 0

        # UI metric cadence (avoid per-frame O(H*B) scans and allocations)
        self._ui_last_update_ms = 0
        self._ui_update_interval_ms = 250
        
    def place_bounty(self, x: float, y: float, reward: int, bounty_type: str = "explore", target=None) -> Bounty:
        """Place a new bounty."""
        bounty = Bounty(x, y, reward, bounty_type, target=target)
        self.bounties.append(bounty)
        self.total_spent += reward
        return bounty
    
    def check_claims(self, heroes: list):
        """Check if any heroes can claim bounties."""
        claimed = []
        for bounty in self.bounties:
            if bounty.claimed:
                continue

            # Only "explore" bounties are proximity-claimed.
            # Typed bounties (e.g. attack_lair) are completed by their owning system (ex: lair_cleared).
            if getattr(bounty, "bounty_type", "explore") != "explore":
                continue
            
            for hero in heroes:
                if hero.is_alive and bounty.is_near(hero.x, hero.y):
                    if bounty.claim(hero):
                        claimed.append((bounty, hero))
                        self.total_claimed += 1
                        break
        
        return claimed
    
    def get_unclaimed_bounties(self) -> list:
        """Get list of unclaimed bounties."""
        return [b for b in self.bounties if not b.claimed]

    def summarize_for_hero(self, hero, game_state: dict, limit: int = 5) -> list[dict]:
        """
        Build a JSON-friendly list of bounty candidates for a hero.
        Includes distance/risk/validity/assignment so AI/LLM can reason about them.
        """
        buildings = game_state.get("buildings", [])
        enemies = game_state.get("enemies", [])
        now_ms = sim_now_ms()

        summaries = []
        for b in self.get_unclaimed_bounties():
            try:
                goal_x, goal_y = b.get_goal_position(buildings)
                dist_px = float(hero.distance_to(goal_x, goal_y)) if hasattr(hero, "distance_to") else 0.0
            except Exception:
                goal_x, goal_y = float(b.x), float(b.y)
                dist_px = 0.0

            summaries.append(
                {
                    "id": getattr(b, "bounty_id", None),
                    "type": getattr(b, "bounty_type", "explore"),
                    "reward": int(getattr(b, "reward", 0)),
                    "goal": {"x": goal_x, "y": goal_y},
                    "distance_tiles": round(dist_px / TILE_SIZE, 1) if TILE_SIZE else 0.0,
                    "risk": round(float(b.estimate_risk(enemies)), 2),
                    "valid": bool(b.is_valid(buildings)),
                    "assigned_to": getattr(b, "assigned_to", None),
                    "assigned_active": bool(b.is_assigned_active(now_ms, ttl_ms=15000)),
                }
            )

        # Sort: valid first, then closer, then higher reward
        summaries.sort(key=lambda s: (not s["valid"], s["distance_tiles"], -s["reward"]))
        return summaries[: max(0, int(limit))]

    def update_ui_metrics(self, heroes: list, enemies: list, buildings: list):
        """
        Compute lightweight UI-only bounty metrics:
        - responders: count of living heroes currently targeting this bounty
        - attractiveness tier: based on reward vs local risk (deterministic)

        This avoids importing AI modules (keeps boundaries clean).
        """
        now_ms = int(sim_now_ms())
        interval_ms = int(getattr(self, "_ui_update_interval_ms", 250) or 250)
        last_ms = getattr(self, "_ui_last_update_ms", None)
        if last_ms is not None:
            try:
                if (now_ms - int(last_ms)) < interval_ms:
                    return
            except Exception:
                # If stored value is weird, fall through and recompute.
                pass
        self._ui_last_update_ms = now_ms

        alive_heroes = [h for h in heroes if getattr(h, "is_alive", True)]

        for b in self.get_unclaimed_bounties():
            # responders
            responders = 0
            bid = getattr(b, "bounty_id", None)
            for h in alive_heroes:
                t = getattr(h, "target", None)
                if isinstance(t, dict) and t.get("type") == "bounty":
                    if bid is not None and t.get("bounty_id") == bid:
                        responders += 1
                    elif bid is None and t.get("bounty_ref") is b:
                        responders += 1

            # If assigned, ensure at least 1 responder (best-effort coordination signal).
            if getattr(b, "assigned_to", None):
                responders = max(responders, 1)

            # attractiveness (reward vs risk, small deterministic heuristic)
            reward = float(getattr(b, "reward", 0) or 0.0)
            risk = float(b.estimate_risk(enemies)) if hasattr(b, "estimate_risk") else 0.0
            valid = True
            if hasattr(b, "is_valid"):
                try:
                    valid = bool(b.is_valid(buildings))
                except Exception:
                    valid = True

            # Score: higher reward helps, risk hurts. Clamp to >= 0 for sanity.
            score = max(0.0, (reward / 50.0) - (1.25 * risk))
            tier = "low"
            if valid and score >= 2.0:
                tier = "high"
            elif valid and score >= 1.0:
                tier = "med"

            # Contract fields (stable)
            prev = int(getattr(b, "responder_count", 0) or 0)
            responders_int = int(responders)
            # Never drop to 0 due to cadencing; keep the max seen until claim/cleanup.
            responders_int = max(prev, responders_int)
            b.responders = int(responders_int)
            b.responder_count = int(responders_int)
            b.attractiveness_score = float(score)
            b.attractiveness_tier = str(tier)

            # UI mirrors (legacy)
            b.ui_responders = int(responders_int)
            b.ui_score = float(score)
            b.ui_attractiveness = str(tier)
    
    def cleanup(self):
        """Remove claimed bounties."""
        self.bounties = [b for b in self.bounties if not b.claimed]
    
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        """Render all bounties."""
        for bounty in self.bounties:
            bounty.render(surface, camera_offset)

