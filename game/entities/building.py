"""
Building entities for the kingdom.
"""
import pygame
from config import (
    TILE_SIZE, BUILDING_SIZES, BUILDING_COLORS, BUILDING_COSTS,
    COLOR_WHITE, COLOR_BLACK
)


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
    
    def take_damage(self, amount: int):
        """Take damage from an attack."""
        self.hp = max(0, self.hp - amount)
        return self.hp <= 0
    
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        """Render the building."""
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        # Draw building
        pygame.draw.rect(
            surface,
            self.color,
            (screen_x, screen_y, self.width, self.height)
        )
        
        # Draw border
        pygame.draw.rect(
            surface,
            COLOR_BLACK,
            (screen_x, screen_y, self.width, self.height),
            2
        )
        
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
        
        font = pygame.font.Font(None, 20)
        text = font.render("CASTLE", True, COLOR_WHITE)
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
        
        font = pygame.font.Font(None, 16)
        text = font.render("WARRIORS", True, COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)
        
        # Show stored tax gold
        if self.stored_tax_gold > 0:
            gold_font = pygame.font.Font(None, 14)
            gold_text = gold_font.render(f"Tax: ${self.stored_tax_gold}", True, (255, 215, 0))
            gold_rect = gold_text.get_rect(center=(
                screen_x + self.width // 2,
                screen_y + self.height + 8
            ))
            surface.blit(gold_text, gold_rect)


class Marketplace(Building):
    """Building where heroes can buy items."""
    
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "marketplace")
        self.items = [
            {"name": "Health Potion", "type": "potion", "price": 30, "effect": 50},
            {"name": "Iron Sword", "type": "weapon", "price": 80, "attack": 5},
            {"name": "Steel Sword", "type": "weapon", "price": 150, "attack": 10},
            {"name": "Leather Armor", "type": "armor", "price": 60, "defense": 3},
            {"name": "Chain Mail", "type": "armor", "price": 120, "defense": 7},
        ]
        
    def get_available_items(self) -> list:
        """Get list of items available for purchase."""
        return self.items.copy()
    
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)
        
        cam_x, cam_y = camera_offset
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        
        font = pygame.font.Font(None, 16)
        text = font.render("MARKET", True, COLOR_WHITE)
        text_rect = text.get_rect(center=(
            screen_x + self.width // 2,
            screen_y + self.height // 2
        ))
        surface.blit(text, text_rect)

