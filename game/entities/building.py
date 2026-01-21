"""
Building entities for the kingdom.
"""
import pygame
from config import (
    TILE_SIZE, BUILDING_SIZES, BUILDING_COLORS, BUILDING_COSTS,
    COLOR_WHITE, COLOR_BLACK
)
from game.graphics.font_cache import get_font, render_text_shadowed_cached
from game.graphics.building_sprites import BuildingSpriteLibrary
from game.graphics.render_context import get_render_zoom
from game.sim.timebase import now_ms as sim_now_ms


#
# Kingdom-wide research unlocks
# -----------------------------
# NOTE: This is intentionally lightweight (in-process) state. Libraries mirror this so
# research behaves like a global tech tree and can't be purchased repeatedly across
# multiple libraries in a single run.
#
RESEARCH_UNLOCKS = {
    "Advanced Healing": False,
    "Fire Magic": False,
    "Defensive Spells": False,
    "Weapon Upgrades": False,
    "Armor Upgrades": False,
}


def is_research_unlocked(name: str) -> bool:
    return bool(RESEARCH_UNLOCKS.get(name, False))


def unlock_research(name: str) -> None:
    if name in RESEARCH_UNLOCKS:
        RESEARCH_UNLOCKS[name] = True


class Building:
    """Base class for all buildings."""
    
    def __init__(self, grid_x: int, grid_y: int, building_type: str):
        self.grid_x = grid_x
        self.grid_y = grid_y
        self.building_type = building_type
        self.size = BUILDING_SIZES.get(building_type, (1, 1))
        self.color = BUILDING_COLORS.get(building_type, (128, 128, 128))
        self.cost = BUILDING_COSTS.get(building_type, 100)
        self.hp = 200
        self.max_hp = 200
        self.last_damage_time_ms = None  # pygame ticks when last damaged (for "under attack" behavior)
        self.placed_time_ms = sim_now_ms()

        # Construction state (used for newly placed buildings).
        # Default: existing/starting buildings are fully constructed and targetable.
        self.is_constructed = True
        self.construction_started = True
        self._work_accum = 0.0  # fractional HP accumulator for build/repair work
        
    @property
    def world_x(self) -> float:
        return self.grid_x * TILE_SIZE
    
    @property
    def world_y(self) -> float:
        return self.grid_y * TILE_SIZE
    
    @property
    def center_x(self) -> float:
        return self.world_x + (self.size[0] * TILE_SIZE) / 2
    
    @property
    def center_y(self) -> float:
        return self.world_y + (self.size[1] * TILE_SIZE) / 2

    # Compatibility: many systems treat "targets" as having x/y coordinates.
    # For buildings, use the center point.
    @property
    def x(self) -> float:
        return self.center_x

    @property
    def y(self) -> float:
        return self.center_y
    
    @property
    def width(self) -> int:
        return self.size[0] * TILE_SIZE
    
    @property
    def height(self) -> int:
        return self.size[1] * TILE_SIZE
    
    def get_rect(self) -> pygame.Rect:
        """Get the building's bounding rectangle."""
        return pygame.Rect(
            self.world_x, self.world_y,
            self.width, self.height
        )
    
    def occupies_tile(self, grid_x: int, grid_y: int) -> bool:
        """Check if building occupies a specific grid tile."""
        return (self.grid_x <= grid_x < self.grid_x + self.size[0] and
                self.grid_y <= grid_y < self.grid_y + self.size[1])
    
    def take_damage(self, amount: int) -> bool:
        """Take damage from an attack. Returns True if destroyed."""
        self.hp = max(0, self.hp - amount)
        self.last_damage_time_ms = sim_now_ms()
        return self.hp <= 0

    @property
    def is_targetable(self) -> bool:
        """Whether enemies can attack this building."""
        if self.hp <= 0:
            return False
        if self.building_type == "castle":
            return True
        return bool(self.construction_started)

    def mark_unconstructed(self):
        """Set this building to its just-placed construction state."""
        self.is_constructed = False
        self.construction_started = False
        self.hp = 1
        self._work_accum = 0.0

    def start_construction(self):
        """Called when a peasant starts building; becomes targetable immediately."""
        self.construction_started = True

    def apply_work(self, dt: float, percent_per_sec: float = 0.01) -> bool:
        """
        Apply build/repair work while a peasant is adjacent.

        Increases HP by (percent_per_sec * max_hp) per second until full.
        Returns True if building is now fully repaired/constructed.
        """
        if self.hp >= self.max_hp:
            self.hp = self.max_hp
            self.is_constructed = True
            return True

        # Accumulate fractional work and apply integer HP increases.
        self._work_accum += self.max_hp * percent_per_sec * dt
        add = int(self._work_accum)
        if add > 0:
            self._work_accum -= add
            self.hp = min(self.max_hp, self.hp + add)

        if self.hp >= self.max_hp:
            self.hp = self.max_hp
            self.is_constructed = True
            return True

        return False
    
    @property
    def is_damaged(self) -> bool:
        """Check if building has taken any damage."""
        return self.hp < self.max_hp

    @property
    def is_under_attack(self) -> bool:
        """True if the building was damaged recently (prevents permanent 'defend forever')."""
        if self.last_damage_time_ms is None:
            return False
        return (sim_now_ms() - self.last_damage_time_ms) < 3000
    
    @property
    def is_fully_repaired(self) -> bool:
        """Check if building is at full health."""
        return self.hp >= self.max_hp
    
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        """Render the building."""
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y

        # Choose a visual state for sprites.
        if getattr(self, "is_constructed", True) is False:
            sprite_state = "construction"
        elif self.hp < self.max_hp:
            sprite_state = "damaged"
        else:
            sprite_state = "built"

        sprite = BuildingSpriteLibrary.get(
            self.building_type,
            sprite_state,
            size_px=(int(self.width), int(self.height)),
        )

        if sprite is not None:
            surface.blit(sprite, (int(screen_x), int(screen_y)))
        else:
            # Fallback to legacy rect rendering
            pygame.draw.rect(surface, self.color, (screen_x, screen_y, self.width, self.height))
            pygame.draw.rect(surface, COLOR_BLACK, (screen_x, screen_y, self.width, self.height), 2)
        
        # Draw health bar if damaged
        if self.hp < self.max_hp:
            bar_width = self.width - 4
            bar_height = 4
            health_pct = self.hp / self.max_hp
            
            # Background
            pygame.draw.rect(
                surface,
                (60, 60, 60),
                (screen_x + 2, screen_y - 8, bar_width, bar_height)
            )
            # Health
            pygame.draw.rect(
                surface,
                (50, 205, 50) if health_pct > 0.5 else (220, 20, 60),
                (screen_x + 2, screen_y - 8, bar_width * health_pct, bar_height)
            )


class Castle(Building):
    """The player's main building. Game over if destroyed."""
    
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "castle")
        self.hp = 500
        self.max_hp = 500
        
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)
        
        # Draw castle icon/text
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        text = render_text_shadowed_cached(20, "CASTLE", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)


class WarriorGuild(Building):
    """Building that allows hiring warrior heroes."""
    
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "warrior_guild")
        self.heroes_hired = 0
        self.stored_tax_gold = 0  # Gold collected from heroes' taxes
        
    def can_hire(self) -> bool:
        """Check if we can hire another hero."""
        return True  # No limit for now
    
    def hire_hero(self):
        """Track that a hero was hired here."""
        self.heroes_hired += 1
    
    def add_tax_gold(self, amount: int):
        """Add gold from hero taxes."""
        self.stored_tax_gold += amount
    
    def collect_taxes(self) -> int:
        """Collect all stored tax gold. Returns the amount collected."""
        amount = self.stored_tax_gold
        self.stored_tax_gold = 0
        return amount
        
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)
        
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        text = render_text_shadowed_cached(16, "WARRIORS", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)
        
        # Show stored tax gold
        if self.stored_tax_gold > 0 and get_render_zoom() >= 1.0:
            gold_text = render_text_shadowed_cached(14, f"Tax: ${self.stored_tax_gold}", (255, 215, 0))
            gold_rect = gold_text.get_rect(center=(
                screen_x + self.width // 2,
                screen_y + self.height + 8
            ))
            surface.blit(gold_text, gold_rect)


class RangerGuild(Building):
    """Building that allows hiring ranger heroes."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "ranger_guild")
        self.heroes_hired = 0
        self.stored_tax_gold = 0  # Gold collected from heroes' taxes

    def can_hire(self) -> bool:
        """Check if we can hire another hero."""
        return True  # No limit for now

    def hire_hero(self):
        """Track that a hero was hired here."""
        self.heroes_hired += 1

    def add_tax_gold(self, amount: int):
        """Add gold from hero taxes."""
        self.stored_tax_gold += amount

    def collect_taxes(self) -> int:
        """Collect all stored tax gold. Returns the amount collected."""
        amount = self.stored_tax_gold
        self.stored_tax_gold = 0
        return amount

    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)

        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y

        text = render_text_shadowed_cached(16, "RANGERS", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)

        # Show stored tax gold
        if self.stored_tax_gold > 0 and get_render_zoom() >= 1.0:
            gold_text = render_text_shadowed_cached(14, f"Tax: ${self.stored_tax_gold}", (255, 215, 0))
            gold_rect = gold_text.get_rect(center=(
                screen_x + self.width // 2,
                screen_y + self.height + 8
            ))
            surface.blit(gold_text, gold_rect)


class RogueGuild(Building):
    """Building that allows hiring rogue heroes."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "rogue_guild")
        self.heroes_hired = 0
        self.stored_tax_gold = 0  # Gold collected from heroes' taxes

    def can_hire(self) -> bool:
        return True

    def hire_hero(self):
        self.heroes_hired += 1

    def add_tax_gold(self, amount: int):
        self.stored_tax_gold += amount

    def collect_taxes(self) -> int:
        amount = self.stored_tax_gold
        self.stored_tax_gold = 0
        return amount

    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)

        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y

        text = render_text_shadowed_cached(16, "ROGUES", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)

        if self.stored_tax_gold > 0 and get_render_zoom() >= 1.0:
            gold_text = render_text_shadowed_cached(14, f"Tax: ${self.stored_tax_gold}", (255, 215, 0))
            gold_rect = gold_text.get_rect(center=(
                screen_x + self.width // 2,
                screen_y + self.height + 8
            ))
            surface.blit(gold_text, gold_rect)


class WizardGuild(Building):
    """Building that allows hiring wizard heroes."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "wizard_guild")
        self.heroes_hired = 0
        self.stored_tax_gold = 0  # Gold collected from heroes' taxes

    def can_hire(self) -> bool:
        return True

    def hire_hero(self):
        self.heroes_hired += 1

    def add_tax_gold(self, amount: int):
        self.stored_tax_gold += amount

    def collect_taxes(self) -> int:
        amount = self.stored_tax_gold
        self.stored_tax_gold = 0
        return amount

    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)

        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y

        text = render_text_shadowed_cached(16, "WIZARDS", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)

        if self.stored_tax_gold > 0 and get_render_zoom() >= 1.0:
            gold_text = render_text_shadowed_cached(14, f"Tax: ${self.stored_tax_gold}", (255, 215, 0))
            gold_rect = gold_text.get_rect(center=(
                screen_x + self.width // 2,
                screen_y + self.height + 8
            ))
            surface.blit(gold_text, gold_rect)


class Marketplace(Building):
    """Building where heroes can buy items."""
    
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "marketplace")
        self.potions_researched = False  # Must research before heroes can buy potions
        self.potion_price = 20

        # Research synergy: if Advanced Healing is unlocked, marketplaces can sell potions
        # immediately and at a reduced price.
        if is_research_unlocked("Advanced Healing"):
            self.potions_researched = True
            self.potion_price = 15
        self.items = [
            {"name": "Dagger", "type": "weapon", "style": "melee", "price": 60, "attack": 4},
            {"name": "Short Bow", "type": "weapon", "style": "ranged", "price": 70, "attack": 4},
            {"name": "Apprentice Staff", "type": "weapon", "style": "magic", "price": 90, "attack": 6},
            {"name": "Iron Sword", "type": "weapon", "price": 80, "attack": 5},
            {"name": "Long Bow", "type": "weapon", "style": "ranged", "price": 140, "attack": 8},
            {"name": "Poison Dagger", "type": "weapon", "style": "melee", "price": 120, "attack": 7},
            {"name": "Steel Sword", "type": "weapon", "price": 150, "attack": 10},
            {"name": "Wizard Staff", "type": "weapon", "style": "magic", "price": 180, "attack": 12},
            {"name": "Leather Armor", "type": "armor", "price": 60, "defense": 3},
            {"name": "Chain Mail", "type": "armor", "price": 120, "defense": 7},
        ]
        
    def get_available_items(self) -> list:
        """Get list of items available for purchase."""
        items = self.items.copy()
        # Add potions if researched
        if self.potions_researched:
            items.insert(0, {"name": "Healing Potion", "type": "potion", "price": self.potion_price, "effect": 50})
        return items
    
    def can_sell_potions(self) -> bool:
        """Check if marketplace can sell potions."""
        return self.potions_researched
    
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)
        
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        text = render_text_shadowed_cached(16, "MARKET", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)


# Phase 1: Economic Buildings

class Blacksmith(Building):
    """Building where heroes can upgrade weapons and armor."""
    
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "blacksmith")
        self.upgrades_sold = 0
        self.researched_items = []
        
        # Research options (similar to Library pattern)
        self.available_research = [
            {"name": "Weapon Upgrades", "cost": 300, "researched": is_research_unlocked("Weapon Upgrades")},
            {"name": "Armor Upgrades", "cost": 300, "researched": is_research_unlocked("Armor Upgrades")},
        ]
        
        # Mirror global unlocks into this instance for display/UX
        for item in self.available_research:
            if item["researched"]:
                self.researched_items.append(item["name"])
        
        # Base items (always available)
        self.base_items = [
            {"name": "Iron Sword", "type": "weapon", "price": 80, "attack": 5},
            {"name": "Leather Armor", "type": "armor", "price": 60, "defense": 3},
        ]
        
        # Upgraded items (gated by research)
        self.upgraded_weapons = [
            {"name": "Steel Sword", "type": "weapon", "price": 150, "attack": 10},
            {"name": "Mithril Blade", "type": "weapon", "price": 250, "attack": 15},
        ]
        
        self.upgraded_armor = [
            {"name": "Chain Mail", "type": "armor", "price": 120, "defense": 7},
            {"name": "Plate Armor", "type": "armor", "price": 200, "defense": 12},
        ]
    
    def can_research(self, research_name: str) -> bool:
        """Check if a research can be performed."""
        if is_research_unlocked(research_name):
            return False
        for item in self.available_research:
            if item["name"] == research_name and not item["researched"]:
                return True
        return False
    
    def research(self, research_name: str, economy, game_state: dict | None = None) -> bool:
        """Perform research if affordable."""
        if hasattr(self, "is_constructed") and not self.is_constructed:
            return False
        if is_research_unlocked(research_name):
            return False
        for item in self.available_research:
            if item["name"] == research_name and not item["researched"]:
                if economy.player_gold >= item["cost"]:
                    economy.player_gold -= item["cost"]
                    item["researched"] = True
                    self.researched_items.append(research_name)
                    unlock_research(research_name)
                    return True
        return False
    
    def get_available_items(self) -> list:
        """Get list of items available for purchase (gated by research)."""
        items = self.base_items.copy()
        
        # Add upgraded weapons if researched
        if is_research_unlocked("Weapon Upgrades"):
            items.extend(self.upgraded_weapons)
        
        # Add upgraded armor if researched
        if is_research_unlocked("Armor Upgrades"):
            items.extend(self.upgraded_armor)
        
        return items
    
    def has_upgrades_available(self) -> bool:
        """Check if any upgrades are available (researched and affordable for heroes)."""
        return is_research_unlocked("Weapon Upgrades") or is_research_unlocked("Armor Upgrades")
        
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)
        
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        text = render_text_shadowed_cached(16, "SMITH", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)


class Inn(Building):
    """Building where heroes can rest and recover HP faster."""
    
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "inn")
        self.heroes_resting = []
        self.rest_recovery_rate = 0.02  # Faster than guilds (0.01)
        
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)
        
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        text = render_text_shadowed_cached(16, "INN", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)


class TradingPost(Building):
    """Building that generates passive income through trade caravans."""
    
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "trading_post")
        self.income_timer = 0.0
        self.income_interval = 10.0  # Generate income every 10 seconds
        self.income_amount = 10  # Gold per interval
        self.total_income_generated = 0
        
    def update(self, dt: float, economy):
        """Update income generation."""
        if not self.is_constructed:
            return
            
        self.income_timer += dt
        if self.income_timer >= self.income_interval:
            self.income_timer = 0.0
            economy.player_gold += self.income_amount
            self.total_income_generated += self.income_amount
        
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)
        
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        text = render_text_shadowed_cached(16, "TRADE", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)


# Phase 2: Temples

class TempleAgrela(Building):
    """Temple to Agrela - recruits Healers."""
    
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "temple_agrela")
        self.heroes_hired = 0
        self.stored_tax_gold = 0
        
    def can_hire(self) -> bool:
        return True
        
    def hire_hero(self):
        self.heroes_hired += 1
        
    def add_tax_gold(self, amount: int):
        self.stored_tax_gold += amount
        
    def collect_taxes(self) -> int:
        amount = self.stored_tax_gold
        self.stored_tax_gold = 0
        return amount
        
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)
        
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        text = render_text_shadowed_cached(14, "AGRELA", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)


class TempleDauros(Building):
    """Temple to Dauros - recruits Monks."""
    
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "temple_dauros")
        self.heroes_hired = 0
        self.stored_tax_gold = 0
        
    def can_hire(self) -> bool:
        return True
        
    def hire_hero(self):
        self.heroes_hired += 1
        
    def add_tax_gold(self, amount: int):
        self.stored_tax_gold += amount
        
    def collect_taxes(self) -> int:
        amount = self.stored_tax_gold
        self.stored_tax_gold = 0
        return amount
        
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)
        
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        text = render_text_shadowed_cached(14, "DAUROS", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)


class TempleFervus(Building):
    """Temple to Fervus - recruits Cultists."""
    
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "temple_fervus")
        self.heroes_hired = 0
        self.stored_tax_gold = 0
        
    def can_hire(self) -> bool:
        return True
        
    def hire_hero(self):
        self.heroes_hired += 1
        
    def add_tax_gold(self, amount: int):
        self.stored_tax_gold += amount
        
    def collect_taxes(self) -> int:
        amount = self.stored_tax_gold
        self.stored_tax_gold = 0
        return amount
        
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)
        
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        text = render_text_shadowed_cached(14, "FERVUS", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)


class TempleKrypta(Building):
    """Temple to Krypta - recruits Priestesses."""
    
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "temple_krypta")
        self.heroes_hired = 0
        self.stored_tax_gold = 0
        
    def can_hire(self) -> bool:
        return True
        
    def hire_hero(self):
        self.heroes_hired += 1
        
    def add_tax_gold(self, amount: int):
        self.stored_tax_gold += amount
        
    def collect_taxes(self) -> int:
        amount = self.stored_tax_gold
        self.stored_tax_gold = 0
        return amount
        
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)
        
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        text = render_text_shadowed_cached(14, "KRYPTA", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)


class TempleKrolm(Building):
    """Temple to Krolm - recruits Barbarians."""
    
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "temple_krolm")
        self.heroes_hired = 0
        self.stored_tax_gold = 0
        
    def can_hire(self) -> bool:
        return True
        
    def hire_hero(self):
        self.heroes_hired += 1
        
    def add_tax_gold(self, amount: int):
        self.stored_tax_gold += amount
        
    def collect_taxes(self) -> int:
        amount = self.stored_tax_gold
        self.stored_tax_gold = 0
        return amount
        
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)
        
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        text = render_text_shadowed_cached(14, "KROLM", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)


class TempleHelia(Building):
    """Temple to Helia - recruits Solarii."""
    
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "temple_helia")
        self.heroes_hired = 0
        self.stored_tax_gold = 0
        
    def can_hire(self) -> bool:
        return True
        
    def hire_hero(self):
        self.heroes_hired += 1
        
    def add_tax_gold(self, amount: int):
        self.stored_tax_gold += amount
        
    def collect_taxes(self) -> int:
        amount = self.stored_tax_gold
        self.stored_tax_gold = 0
        return amount
        
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)
        
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        text = render_text_shadowed_cached(14, "HELIA", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)


class TempleLunord(Building):
    """Temple to Lunord - recruits Adepts."""
    
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "temple_lunord")
        self.heroes_hired = 0
        self.stored_tax_gold = 0
        
    def can_hire(self) -> bool:
        return True
        
    def hire_hero(self):
        self.heroes_hired += 1
        
    def add_tax_gold(self, amount: int):
        self.stored_tax_gold += amount
        
    def collect_taxes(self) -> int:
        amount = self.stored_tax_gold
        self.stored_tax_gold = 0
        return amount
        
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)
        
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        text = render_text_shadowed_cached(14, "LUNORD", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)


# Phase 3: Non-Human Dwellings

class GnomeHovel(Building):
    """Gnome Hovel - recruits Gnomes who assist with building/repairing."""
    
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "gnome_hovel")
        self.heroes_hired = 0
        self.stored_tax_gold = 0
        
    def can_hire(self) -> bool:
        return True
        
    def hire_hero(self):
        self.heroes_hired += 1
        
    def add_tax_gold(self, amount: int):
        self.stored_tax_gold += amount
        
    def collect_taxes(self) -> int:
        amount = self.stored_tax_gold
        self.stored_tax_gold = 0
        return amount
        
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)
        
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        text = render_text_shadowed_cached(14, "GNOMES", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)


class ElvenBungalow(Building):
    """Elven Bungalow - recruits Elves, increases marketplace income."""
    
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "elven_bungalow")
        self.heroes_hired = 0
        self.stored_tax_gold = 0
        
    def can_hire(self) -> bool:
        return True
        
    def hire_hero(self):
        self.heroes_hired += 1
        
    def add_tax_gold(self, amount: int):
        self.stored_tax_gold += amount
        
    def collect_taxes(self) -> int:
        amount = self.stored_tax_gold
        self.stored_tax_gold = 0
        return amount
        
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)
        
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        text = render_text_shadowed_cached(14, "ELVES", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)


class DwarvenSettlement(Building):
    """Dwarven Settlement - recruits Dwarves, unlocks Ballista Tower."""
    
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "dwarven_settlement")
        self.heroes_hired = 0
        self.stored_tax_gold = 0
        
    def can_hire(self) -> bool:
        return True
        
    def hire_hero(self):
        self.heroes_hired += 1
        
    def add_tax_gold(self, amount: int):
        self.stored_tax_gold += amount
        
    def collect_taxes(self) -> int:
        amount = self.stored_tax_gold
        self.stored_tax_gold = 0
        return amount
        
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)
        
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        text = render_text_shadowed_cached(14, "DWARVES", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)


# Phase 4: Defensive Structures

class Guardhouse(Building):
    """Guardhouse - spawns guards to defend the kingdom."""
    
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "guardhouse")
        self.guards_spawned = 0
        self.max_guards = 3
        self.spawn_timer = 0.0
        self.spawn_interval = 30.0  # Spawn a guard every 30 seconds
        
    def update(self, dt: float, guards_list: list):
        """Update guard spawning."""
        if not self.is_constructed:
            return
            
        if len(guards_list) < self.max_guards:
            self.spawn_timer += dt
            if self.spawn_timer >= self.spawn_interval:
                self.spawn_timer = 0.0
                # Guard spawning will be handled by engine
                return True
        return False
        
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)
        
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        text = render_text_shadowed_cached(14, "GUARDS", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)


class BallistaTower(Building):
    """Ballista Tower - provides ranged defense against enemies."""
    
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "ballista_tower")
        self.attack_range = 200  # pixels
        self.attack_damage = 15
        self.attack_cooldown = 0.0
        self.attack_interval = 2.0  # Attack every 2 seconds
        self.target = None
        
        # WK5: Ranged attacker interface
        self.is_ranged_attacker = True
        
        # WK5: Ranged projectile event storage (for engine collection)
        self._last_ranged_event = None

        # Research synergy: defensive spells extend tower range.
        if is_research_unlocked("Defensive Spells"):
            self.attack_range += 50
        
    def update(self, dt: float, enemies: list):
        """Update tower attacks."""
        if not self.is_constructed:
            return
            
        self.attack_cooldown = max(0, self.attack_cooldown - dt)
        
        if self.attack_cooldown <= 0:
            # Find nearest enemy in range
            best_target = None
            best_dist = float('inf')
            
            for enemy in enemies:
                if not enemy.is_alive:
                    continue
                dist = ((self.center_x - enemy.x) ** 2 + (self.center_y - enemy.y) ** 2) ** 0.5
                if dist < self.attack_range and dist < best_dist:
                    best_dist = dist
                    best_target = enemy
            
            if best_target:
                # Attack the enemy
                if best_target.take_damage(self.attack_damage):
                    # Enemy killed
                    pass
                self.attack_cooldown = self.attack_interval
                self.target = best_target
                
                # WK5: Emit ranged projectile event for ranged attackers
                if getattr(self, "is_ranged_attacker", False):
                    spec = None
                    if hasattr(self, "get_ranged_spec"):
                        try:
                            spec = self.get_ranged_spec()
                        except Exception:
                            spec = None
                    
                    kind = (spec or {}).get("kind", "bolt")
                    color = (spec or {}).get("color", (180, 180, 200))
                    size = (spec or {}).get("size_px", 2)
                    
                    # Store event for engine collection (WK5: building attacks happen in update(), not combat system)
                    self._last_ranged_event = {
                        "type": "ranged_projectile",
                        "from_x": float(self.center_x),
                        "from_y": float(self.center_y),
                        "to_x": float(best_target.x),
                        "to_y": float(best_target.y),
                        "projectile_kind": kind,
                        "color": color,
                        "size_px": size,
                    }
                else:
                    # Clear any stale event for non-ranged attackers
                    self._last_ranged_event = None
            else:
                self.target = None
                # Clear any stale event if no target
                self._last_ranged_event = None
        
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)
        
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        text = render_text_shadowed_cached(14, "BALLISTA", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)
        
        # Draw attack range when targeting
        if self.target:
            pygame.draw.circle(
                surface,
                (255, 0, 0, 50),
                (int(screen_x + self.width // 2), int(screen_y + self.height // 2)),
                int(self.attack_range),
                1
            )


class WizardTower(Building):
    """Wizard's Tower - provides magical defense capabilities."""
    
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "wizard_tower")
        self.spell_range = 250  # pixels
        self.spell_cooldown = 0.0
        self.spell_interval = 5.0  # Cast spell every 5 seconds
        self.spell_damage = 25

        # Research synergy: apply any unlocked research to new towers.
        if is_research_unlocked("Fire Magic"):
            self.spell_damage += 5
            self.spell_interval = max(1.0, self.spell_interval * 0.9)
        if is_research_unlocked("Defensive Spells"):
            self.spell_range += 50
        
    def update(self, dt: float, enemies: list):
        """Update spell casting."""
        if not self.is_constructed:
            return
            
        self.spell_cooldown = max(0, self.spell_cooldown - dt)
        
        if self.spell_cooldown <= 0:
            # Find enemies in range
            targets = []
            for enemy in enemies:
                if not enemy.is_alive:
                    continue
                dist = ((self.center_x - enemy.x) ** 2 + (self.center_y - enemy.y) ** 2) ** 0.5
                if dist < self.spell_range:
                    targets.append(enemy)
            
            if targets:
                # Cast spell on all targets in range
                for target in targets:
                    target.take_damage(self.spell_damage)
                self.spell_cooldown = self.spell_interval
        
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)
        
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        text = render_text_shadowed_cached(14, "WIZ TOWER", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)


# Phase 5: Special Buildings

class Fairgrounds(Building):
    """Fairgrounds - hosts tournaments to train heroes and generate income."""
    
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "fairgrounds")
        self.tournament_timer = 0.0
        self.tournament_interval = 60.0  # Tournament every 60 seconds
        self.tournament_income = 50
        self.total_tournaments = 0
        
    def update(self, dt: float, economy, heroes: list):
        """Update tournament system."""
        if not self.is_constructed:
            return
            
        self.tournament_timer += dt
        if self.tournament_timer >= self.tournament_interval:
            self.tournament_timer = 0.0
            # Generate income
            economy.player_gold += self.tournament_income
            self.total_tournaments += 1
            
            # Give XP to nearby heroes
            for hero in heroes:
                if hero.is_alive:
                    dist = ((self.center_x - hero.x) ** 2 + (self.center_y - hero.y) ** 2) ** 0.5
                    if dist < 150:  # Within range
                        hero.add_xp(10)
        
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)
        
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        text = render_text_shadowed_cached(14, "FAIR", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)


class Library(Building):
    """Library - allows research of advanced spells and abilities."""
    
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "library")
        self.researched_items = []
        self.available_research = [
            {"name": "Advanced Healing", "cost": 200, "researched": is_research_unlocked("Advanced Healing")},
            {"name": "Fire Magic", "cost": 250, "researched": is_research_unlocked("Fire Magic")},
            {"name": "Defensive Spells", "cost": 300, "researched": is_research_unlocked("Defensive Spells")},
        ]

        # Mirror global unlocks into this instance for display/UX.
        for item in self.available_research:
            if item["researched"]:
                self.researched_items.append(item["name"])
        
    def can_research(self, research_name: str) -> bool:
        """Check if a research can be performed."""
        if is_research_unlocked(research_name):
            return False
        for item in self.available_research:
            if item["name"] == research_name and not item["researched"]:
                return True
        return False
        
    def research(self, research_name: str, economy, game_state: dict | None = None) -> bool:
        """Perform research if affordable."""
        if hasattr(self, "is_constructed") and not self.is_constructed:
            return False
        if is_research_unlocked(research_name):
            return False
        for item in self.available_research:
            if item["name"] == research_name and not item["researched"]:
                if economy.player_gold >= item["cost"]:
                    economy.player_gold -= item["cost"]
                    item["researched"] = True
                    self.researched_items.append(research_name)
                    unlock_research(research_name)
                    if game_state is not None:
                        self._apply_research_effect(research_name, game_state)
                    return True
        return False

    def _apply_research_effect(self, research_name: str, game_state: dict) -> None:
        """Apply gameplay effects for a completed research unlock."""
        buildings = game_state.get("buildings", []) if isinstance(game_state, dict) else []

        if research_name == "Advanced Healing":
            # Immediate, visible effect: all marketplaces can sell potions and potions are cheaper.
            for b in buildings:
                if getattr(b, "building_type", None) != "marketplace":
                    continue
                b.potions_researched = True
                if hasattr(b, "potion_price"):
                    b.potion_price = min(getattr(b, "potion_price", 20), 15)
                else:
                    b.potion_price = 15

        elif research_name == "Fire Magic":
            for b in buildings:
                if getattr(b, "building_type", None) != "wizard_tower":
                    continue
                # Avoid stacking by relying on the research being one-time.
                b.spell_damage = getattr(b, "spell_damage", 25) + 5
                b.spell_interval = max(1.0, getattr(b, "spell_interval", 5.0) * 0.9)

        elif research_name == "Defensive Spells":
            for b in buildings:
                bt = getattr(b, "building_type", None)
                if bt == "wizard_tower":
                    b.spell_range = getattr(b, "spell_range", 250) + 50
                elif bt == "ballista_tower":
                    b.attack_range = getattr(b, "attack_range", 200) + 50
        
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)
        
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        text = render_text_shadowed_cached(14, "LIBRARY", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)


class RoyalGardens(Building):
    """Royal Gardens - provides place for heroes to relax, boosting morale."""
    
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "royal_gardens")
        self.buff_range = 150  # pixels
        # Aura-style: should drop shortly after leaving range (refreshed while in range).
        self.buff_duration = 1.25  # seconds
        self.buff_attack_bonus = 5
        self.buff_defense_bonus = 3
        
    def get_heroes_in_range(self, heroes: list) -> list:
        """Get heroes within buff range."""
        buffed_heroes = []
        for hero in heroes:
            if hero.is_alive:
                dist = ((self.center_x - hero.x) ** 2 + (self.center_y - hero.y) ** 2) ** 0.5
                if dist < self.buff_range:
                    buffed_heroes.append(hero)
        return buffed_heroes
        
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)
        
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        text = render_text_shadowed_cached(14, "GARDENS", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)


# Phase 6: Palace System

class Palace(Building):
    """Upgradeable Palace - the player's main building."""
    
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "palace")
        self.level = 1
        self.max_level = 3
        self.hp = 500
        self.max_hp = 500
        self.max_peasants = 2
        self.max_tax_collectors = 1
        self.max_palace_guards = 0
        
    def can_upgrade(self) -> bool:
        """Check if palace can be upgraded."""
        return self.level < self.max_level
        
    def get_upgrade_cost(self) -> int:
        """Get cost to upgrade to next level."""
        if self.level == 1:
            return 500
        elif self.level == 2:
            return 1000
        return 0
        
    def upgrade(self, economy) -> bool:
        """Upgrade palace to next level."""
        if not self.can_upgrade():
            return False
            
        cost = self.get_upgrade_cost()
        if economy.player_gold >= cost:
            economy.player_gold -= cost
            self.level += 1
            
            if self.level == 2:
                self.max_peasants = 4
                self.max_tax_collectors = 2
                self.max_palace_guards = 1
                self.max_hp = 750
                self.hp = 750
            elif self.level == 3:
                self.max_peasants = 6
                self.max_tax_collectors = 3
                self.max_palace_guards = 2
                self.max_hp = 1000
                self.hp = 1000
                
            return True
        return False
        
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)
        
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        text = render_text_shadowed_cached(20, f"PALACE L{self.level}", COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)