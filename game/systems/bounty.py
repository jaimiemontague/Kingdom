"""
Bounty system for incentivizing hero behavior.
"""
import pygame
from config import TILE_SIZE, COLOR_GOLD, COLOR_WHITE


class Bounty:
    """A bounty/reward flag placed by the player."""
    
    def __init__(self, x: float, y: float, reward: int, bounty_type: str = "explore"):
        self.x = x
        self.y = y
        self.reward = reward
        self.bounty_type = bounty_type  # "explore", "attack", "defend"
        self.claimed = False
        self.claimed_by = None
        self.target = None  # For attack bounties, could be enemy reference
        
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
            hero.gold += self.reward
            return True
        return False
    
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
        
        # Draw flag pole
        pygame.draw.line(
            surface,
            (139, 90, 43),  # Brown
            (screen_x, screen_y),
            (screen_x, screen_y - 30),
            3
        )
        
        # Draw flag
        flag_color = COLOR_GOLD
        flag_points = [
            (screen_x, screen_y - 30),
            (screen_x + 20, screen_y - 25),
            (screen_x, screen_y - 20),
        ]
        pygame.draw.polygon(surface, flag_color, flag_points)
        
        # Draw reward amount
        font = pygame.font.Font(None, 16)
        text = font.render(f"${self.reward}", True, COLOR_WHITE)
        text_rect = text.get_rect(center=(screen_x + 10, screen_y - 35))
        surface.blit(text, text_rect)


class BountySystem:
    """Manages bounties in the game."""
    
    def __init__(self):
        self.bounties = []
        self.total_claimed = 0
        self.total_spent = 0
        
    def place_bounty(self, x: float, y: float, reward: int, bounty_type: str = "explore") -> Bounty:
        """Place a new bounty."""
        bounty = Bounty(x, y, reward, bounty_type)
        self.bounties.append(bounty)
        self.total_spent += reward
        return bounty
    
    def check_claims(self, heroes: list):
        """Check if any heroes can claim bounties."""
        claimed = []
        for bounty in self.bounties:
            if bounty.claimed:
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
    
    def cleanup(self):
        """Remove claimed bounties."""
        self.bounties = [b for b in self.bounties if not b.claimed]
    
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        """Render all bounties."""
        for bounty in self.bounties:
            bounty.render(surface, camera_offset)

