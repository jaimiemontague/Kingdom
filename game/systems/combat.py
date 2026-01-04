"""
Combat system for handling attacks and damage.
"""
import math
from config import TILE_SIZE


class CombatSystem:
    """Manages combat between heroes and enemies."""
    
    def __init__(self):
        self.combat_log = []

    def _hero_can_attack(self, hero) -> bool:
        """
        WK2 contract: combat must hard-gate attack execution when hero.can_attack is False.
        Fallback for older heroes: do not allow attacks while inside buildings.
        """
        if hasattr(hero, "can_attack"):
            try:
                return bool(getattr(hero, "can_attack"))
            except Exception:
                return not bool(getattr(hero, "is_inside_building", False))
        return not bool(getattr(hero, "is_inside_building", False))
        
    def process_combat(self, heroes: list, enemies: list, buildings: list) -> list:
        """
        Process all combat interactions.
        Returns list of events (kills, damage, etc.)
        """
        events = []
        
        # Heroes attacking enemies
        for hero in heroes:
            if not hero.is_alive:
                continue
            if hero.attack_cooldown > 0:
                continue

            # P0 hard gate: no damage while hero is inside a building.
            if not self._hero_can_attack(hero):
                # Optional breadcrumb for debug/QA counters (kept internal; non-contract).
                try:
                    hero.attack_blocked_reason = getattr(hero, "attack_blocked_reason", "") or "inside_building"
                    hero._inside_attack_blocks = int(getattr(hero, "_inside_attack_blocks", 0) or 0) + 1
                except Exception:
                    pass
                continue
                
            # Find closest enemy in range
            closest_enemy = None
            closest_dist = float('inf')
            
            for enemy in enemies:
                if not enemy.is_alive:
                    continue
                dist = hero.distance_to(enemy.x, enemy.y)
                if dist <= hero.attack_range and dist < closest_dist:
                    closest_dist = dist
                    closest_enemy = enemy
            
            if closest_enemy:
                # If the enemy is currently targeting a building, being attacked should make it retarget the attacker.
                # This prevents enemies from mindlessly chewing on buildings while a hero hits them.
                if getattr(closest_enemy, "target", None) is not None and hasattr(closest_enemy.target, "building_type"):
                    closest_enemy.target = hero

                # Register this hero as an attacker for gold distribution
                if hasattr(closest_enemy, 'register_attacker'):
                    closest_enemy.register_attacker(hero)
                
                # Attack!
                damage = hero.attack
                if hasattr(hero, "compute_attack_damage"):
                    try:
                        damage = hero.compute_attack_damage(closest_enemy)
                    except TypeError:
                        damage = hero.compute_attack_damage()
                killed = closest_enemy.take_damage(damage)
                hero.attack_cooldown = hero.attack_cooldown_max

                # Allow hero to trigger visuals/audio (animations, etc.)
                if hasattr(hero, "on_attack_landed"):
                    try:
                        hero.on_attack_landed(closest_enemy, damage, killed)
                    except TypeError:
                        # Backwards-compatible signature
                        hero.on_attack_landed()
                
                events.append({
                    "type": "hero_attack",
                    "attacker": hero.name,
                    "target": closest_enemy.enemy_type,
                    "damage": damage,
                    "x": closest_enemy.x,
                    "y": closest_enemy.y,
                })
                
                # WK5: Emit ranged projectile event for ranged attackers
                if getattr(hero, "is_ranged_attacker", False):
                    spec = None
                    if hasattr(hero, "get_ranged_spec"):
                        try:
                            spec = hero.get_ranged_spec()
                        except Exception:
                            spec = None
                    
                    kind = (spec or {}).get("kind", "arrow")
                    color = (spec or {}).get("color", (200, 200, 200))
                    size = (spec or {}).get("size_px", 2)  # Build B: default 2px for readability
                    
                    events.append({
                        "type": "ranged_projectile",
                        "from_x": float(hero.x),
                        "from_y": float(hero.y),
                        "to_x": float(closest_enemy.x),
                        "to_y": float(closest_enemy.y),
                        "projectile_kind": kind,
                        "color": color,
                        "size_px": size,
                    })
                
                if killed:
                    # Distribute gold among all heroes who participated or are nearby
                    gold_recipients = self.get_gold_recipients(
                        closest_enemy, heroes
                    )
                    
                    if gold_recipients:
                        gold_per_hero = closest_enemy.gold_reward // len(gold_recipients)
                        remainder = closest_enemy.gold_reward % len(gold_recipients)
                        
                        for i, recipient in enumerate(gold_recipients):
                            # First recipient gets any remainder
                            gold_share = gold_per_hero + (1 if i == 0 and remainder > 0 else 0)
                            recipient.add_gold(gold_share)
                        
                        events.append({
                            "type": "enemy_killed",
                            "hero": hero.name,
                            "enemy": closest_enemy.enemy_type,
                            "gold": closest_enemy.gold_reward,
                            "xp": closest_enemy.xp_reward,
                            "gold_split": len(gold_recipients),
                            "x": closest_enemy.x,
                            "y": closest_enemy.y,
                        })
                    
                    # XP goes to the killer only
                    hero.add_xp(closest_enemy.xp_reward)

        # Heroes attacking lairs (only if explicitly targeting one)
        for hero in heroes:
            if not getattr(hero, "is_alive", False):
                continue
            if getattr(hero, "attack_cooldown", 0) > 0:
                continue
            if not self._hero_can_attack(hero):
                try:
                    hero.attack_blocked_reason = getattr(hero, "attack_blocked_reason", "") or "inside_building"
                    hero._inside_attack_blocks = int(getattr(hero, "_inside_attack_blocks", 0) or 0) + 1
                except Exception:
                    pass
                continue

            lair = getattr(hero, "target", None)
            if not getattr(lair, "is_lair", False):
                continue
            if getattr(lair, "hp", 0) <= 0:
                continue

            # Use center distance with a small slack for footprint.
            dist = hero.distance_to(lair.center_x, lair.center_y)
            if dist > (hero.attack_range + TILE_SIZE):
                continue

            damage = hero.attack
            if hasattr(hero, "compute_attack_damage"):
                try:
                    damage = hero.compute_attack_damage(lair)
                except TypeError:
                    damage = hero.compute_attack_damage()

            # Record attacker if supported.
            killed = False
            if hasattr(lair, "take_damage"):
                try:
                    killed = lair.take_damage(damage, attacker=hero)
                except TypeError:
                    killed = lair.take_damage(damage)

            hero.attack_cooldown = hero.attack_cooldown_max

            # WK6 Mid-Sprint: Add position for visibility-gated audio
            lair_x = float(getattr(lair, "center_x", getattr(lair, "x", 0.0)))
            lair_y = float(getattr(lair, "center_y", getattr(lair, "y", 0.0)))
            
            events.append({
                "type": "hero_attack_lair",
                "attacker": hero.name,
                "target": getattr(lair, "building_type", "lair"),
                "damage": damage,
                "x": lair_x,  # WK6 Mid-Sprint: Position for visibility gating
                "y": lair_y,  # WK6 Mid-Sprint: Position for visibility gating
            })
            
            # WK5: Emit ranged projectile event for ranged attackers attacking lairs
            if getattr(hero, "is_ranged_attacker", False):
                spec = None
                if hasattr(hero, "get_ranged_spec"):
                    try:
                        spec = hero.get_ranged_spec()
                    except Exception:
                        spec = None
                
                kind = (spec or {}).get("kind", "arrow")
                color = (spec or {}).get("color", (200, 200, 200))
                size = (spec or {}).get("size_px", 1)
                
                events.append({
                    "type": "ranged_projectile",
                    "from_x": float(hero.x),
                    "from_y": float(hero.y),
                    "to_x": float(lair.center_x),
                    "to_y": float(lair.center_y),
                    "projectile_kind": kind,
                    "color": color,
                    "size_px": size,
                })

            if killed and not getattr(lair, "_cleared_emitted", False):
                setattr(lair, "_cleared_emitted", True)
                summary = {}
                if hasattr(lair, "on_cleared"):
                    summary = lair.on_cleared(hero)

                # WK6 Mid-Sprint: Add position for visibility-gated audio
                lair_x = float(getattr(lair, "center_x", getattr(lair, "x", 0.0)))
                lair_y = float(getattr(lair, "center_y", getattr(lair, "y", 0.0)))
                
                events.append({
                    "type": "lair_cleared",
                    "hero": hero.name,
                    "lair_type": getattr(lair, "building_type", "lair"),
                    "gold": summary.get("gold", 0),
                    "threat_level": summary.get("threat_level", 1),
                    "lair_obj": lair,
                    "x": lair_x,  # WK6 Mid-Sprint: Position for visibility gating
                    "y": lair_y,  # WK6 Mid-Sprint: Position for visibility gating
                })
        
        # Enemies attacking (handled in enemy update, but we track deaths here)
        for enemy in enemies:
            if not enemy.is_alive:
                continue
            
            # Enemy attacks are processed in enemy.update()
            # Here we just check for hero deaths
            pass
        
        # Check for building destruction
        for building in buildings:
            if building.hp <= 0 and building.building_type == "castle":
                events.append({
                    "type": "castle_destroyed",
                })
        
        return events
    
    def get_enemies_in_range(self, x: float, y: float, range_dist: float, enemies: list) -> list:
        """Get all enemies within range of a position."""
        in_range = []
        for enemy in enemies:
            if enemy.is_alive:
                dist = math.sqrt((x - enemy.x) ** 2 + (y - enemy.y) ** 2)
                if dist <= range_dist:
                    in_range.append((enemy, dist))
        return sorted(in_range, key=lambda e: e[1])
    
    def get_nearest_enemy(self, x: float, y: float, enemies: list):
        """Get the nearest living enemy to a position."""
        nearest = None
        nearest_dist = float('inf')
        
        for enemy in enemies:
            if enemy.is_alive:
                dist = math.sqrt((x - enemy.x) ** 2 + (y - enemy.y) ** 2)
                if dist < nearest_dist:
                    nearest_dist = dist
                    nearest = enemy
        
        return nearest, nearest_dist if nearest else None
    
    def get_gold_recipients(self, enemy, heroes: list) -> list:
        """
        Get list of heroes who should receive gold from a kill.
        Includes heroes who attacked the enemy OR are within the same tile.
        """
        recipients = []
        attacker_names = getattr(enemy, 'attackers', set())
        
        for hero in heroes:
            if not hero.is_alive:
                continue
            
            # Check if hero attacked this enemy
            if hero.name in attacker_names:
                recipients.append(hero)
                continue
            
            # Check if hero is within the same tile (TILE_SIZE distance)
            dist = math.sqrt((hero.x - enemy.x) ** 2 + (hero.y - enemy.y) ** 2)
            if dist <= TILE_SIZE:
                recipients.append(hero)
        
        return recipients

