"""
Main game engine - handles the game loop, input, and coordination.
"""
import pygame
from config import (
    WINDOW_WIDTH, WINDOW_HEIGHT, FPS, GAME_TITLE, TILE_SIZE,
    MAP_WIDTH, MAP_HEIGHT, COLOR_BLACK
)
from game.world import World
from game.entities import (
    Castle, WarriorGuild, RangerGuild, RogueGuild, WizardGuild,
    Marketplace, Hero, Goblin, TaxCollector, Peasant
)
from game.systems import CombatSystem, EconomySystem, EnemySpawner, BountySystem
from game.ui import HUD, BuildingMenu, DebugPanel, BuildingPanel


class GameEngine:
    """Main game engine class."""
    
    def __init__(self):
        pygame.init()
        pygame.font.init()
        
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption(GAME_TITLE)
        self.clock = pygame.time.Clock()
        self.running = True
        self.paused = False
        
        # Initialize game world
        self.world = World()
        
        # Camera
        self.camera_x = 0
        self.camera_y = 0
        
        # Game objects
        self.buildings = []
        self.heroes = []
        self.enemies = []
        self.bounties = []
        self.peasants = []
        self.peasant_spawn_timer = 0.0
        
        # Systems
        self.combat_system = CombatSystem()
        self.economy = EconomySystem()
        self.spawner = EnemySpawner(self.world)
        
        # UI
        self.hud = HUD(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.building_menu = BuildingMenu()
        self.debug_panel = DebugPanel(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.building_panel = BuildingPanel(WINDOW_WIDTH, WINDOW_HEIGHT)
        
        # Selection
        self.selected_building = None
        
        # Bounty system
        self.bounty_system = BountySystem()
        
        # Selection
        self.selected_hero = None
        
        # AI controller (will be set from main.py)
        self.ai_controller = None
        
        # Tax collector (created after castle is placed)
        self.tax_collector = None
        
        # Initialize starting buildings
        self.setup_initial_state()
        
    def setup_initial_state(self):
        """Set up the initial game state."""
        # Place castle in center
        center_x = MAP_WIDTH // 2 - 1
        center_y = MAP_HEIGHT // 2 - 1
        
        castle = Castle(center_x, center_y)
        # Starting castle is fully built and targetable.
        if hasattr(castle, "is_constructed"):
            castle.is_constructed = True
        if hasattr(castle, "construction_started"):
            castle.construction_started = True
        self.buildings.append(castle)
        
        # Create tax collector at castle
        self.tax_collector = TaxCollector(castle)
        
        # Clear tiles under castle for path
        for dy in range(castle.size[1]):
            for dx in range(castle.size[0]):
                self.world.set_tile(center_x + dx, center_y + dy, 2)  # PATH
        
        # Center camera on castle
        self.camera_x = castle.center_x - WINDOW_WIDTH // 2
        self.camera_y = castle.center_y - WINDOW_HEIGHT // 2
        
    def handle_events(self):
        """Process input events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                
            elif event.type == pygame.KEYDOWN:
                self.handle_keydown(event)
                
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self.handle_mousedown(event)
                
            elif event.type == pygame.MOUSEMOTION:
                self.handle_mousemove(event)
    
    def handle_keydown(self, event):
        """Handle keyboard input."""
        if event.key == pygame.K_ESCAPE:
            if self.building_menu.selected_building:
                self.building_menu.cancel_selection()
            else:
                self.paused = not self.paused
                
        elif event.key == pygame.K_1:
            # Select warrior guild for placement
            if self.economy.can_afford_building("warrior_guild"):
                self.building_menu.select_building("warrior_guild")
            else:
                self.hud.add_message("Not enough gold!", (255, 100, 100))
                
        elif event.key == pygame.K_2:
            # Select marketplace for placement
            if self.economy.can_afford_building("marketplace"):
                self.building_menu.select_building("marketplace")
            else:
                self.hud.add_message("Not enough gold!", (255, 100, 100))

        elif event.key == pygame.K_3:
            # Select ranger guild for placement
            if self.economy.can_afford_building("ranger_guild"):
                self.building_menu.select_building("ranger_guild")
            else:
                self.hud.add_message("Not enough gold!", (255, 100, 100))

        elif event.key == pygame.K_4:
            # Select rogue guild for placement
            if self.economy.can_afford_building("rogue_guild"):
                self.building_menu.select_building("rogue_guild")
            else:
                self.hud.add_message("Not enough gold!", (255, 100, 100))

        elif event.key == pygame.K_5:
            # Select wizard guild for placement
            if self.economy.can_afford_building("wizard_guild"):
                self.building_menu.select_building("wizard_guild")
            else:
                self.hud.add_message("Not enough gold!", (255, 100, 100))
                
        elif event.key == pygame.K_h:
            # Hire a hero
            self.try_hire_hero()
            
        elif event.key == pygame.K_SPACE:
            # Toggle pause
            self.paused = not self.paused
        
        elif event.key == pygame.K_F1:
            # Toggle debug panel
            self.debug_panel.toggle()
        
        elif event.key == pygame.K_b:
            # Place a bounty at mouse position
            self.place_bounty()
            
        elif event.key == pygame.K_p:
            # Use potion for selected hero
            if self.selected_hero and self.selected_hero.is_alive:
                if self.selected_hero.use_potion():
                    self.hud.add_message(f"{self.selected_hero.name} used a potion!", (100, 255, 100))
    
    def handle_mousedown(self, event):
        """Handle mouse clicks."""
        if event.button == 1:  # Left click
            # Check if clicking on building panel first
            if self.building_panel.visible:
                if self.building_panel.handle_click(event.pos, self.economy, self.get_game_state()):
                    return
            
            if self.building_menu.selected_building:
                # Try to place building
                pos = self.building_menu.get_placement()
                if pos:
                    self.place_building(pos[0], pos[1])
            else:
                # Try to select a hero first
                if self.try_select_hero(event.pos):
                    self.building_panel.deselect()
                    self.selected_building = None
                # Then try to select a building
                elif self.try_select_building(event.pos):
                    self.selected_hero = None
                else:
                    # Clicked on empty space
                    self.selected_hero = None
                    self.building_panel.deselect()
                    self.selected_building = None
                
        elif event.button == 3:  # Right click
            # Indirect-control game: no direct hero commands.
            pass
    
    def handle_mousemove(self, event):
        """Handle mouse movement."""
        if self.building_menu.selected_building:
            self.building_menu.update_preview(
                event.pos, 
                self.world, 
                self.buildings,
                (self.camera_x, self.camera_y)
            )
        
        # Update building panel hover state
        self.building_panel.update_hover(event.pos)
    
    def try_select_hero(self, screen_pos: tuple) -> bool:
        """Try to select a hero at the given screen position. Returns True if selected."""
        world_x = screen_pos[0] + self.camera_x
        world_y = screen_pos[1] + self.camera_y
        
        for hero in self.heroes:
            if hero.is_alive and hero.distance_to(world_x, world_y) < hero.size:
                self.selected_hero = hero
                return True
        
        return False
    
    def try_select_building(self, screen_pos: tuple) -> bool:
        """Try to select a building at the given screen position. Returns True if selected."""
        world_x = screen_pos[0] + self.camera_x
        world_y = screen_pos[1] + self.camera_y
        
        for building in self.buildings:
            rect = building.get_rect()
            if rect.collidepoint(world_x, world_y):
                self.selected_building = building
                self.building_panel.select_building(building, self.heroes)
                return True
        
        return False
    
    def try_hire_hero(self):
        """Try to hire a hero from the selected guild building."""
        guild = self.selected_building

        allowed = ["warrior_guild", "ranger_guild", "rogue_guild", "wizard_guild"]
        if not guild or not hasattr(guild, "building_type") or guild.building_type not in allowed:
            self.hud.add_message("Select a constructed guild (Warrior/Ranger/Rogue/Wizard) to hire from!", (255, 100, 100))
            return

        # Guild must be constructed before it can be used.
        if hasattr(guild, "is_constructed") and not guild.is_constructed:
            self.hud.add_message("Guild is under construction!", (255, 100, 100))
            return
        
        if not self.economy.can_afford_hero():
            self.hud.add_message("Not enough gold to hire!", (255, 100, 100))
            return
        
        # Hire the hero
        self.economy.hire_hero()
        guild.hire_hero()
        
        # Spawn hero near guild
        class_by_guild = {
            "warrior_guild": "warrior",
            "ranger_guild": "ranger",
            "rogue_guild": "rogue",
            "wizard_guild": "wizard",
        }
        hero_class = class_by_guild.get(guild.building_type, "warrior")
        hero = Hero(
            guild.center_x + TILE_SIZE,
            guild.center_y,
            hero_class=hero_class
        )
        # Set the hero's home building to this guild
        hero.home_building = guild
        
        self.heroes.append(hero)
        self.hud.add_message(f"{hero.name} the {hero_class.title()} joins your kingdom!", (100, 255, 100))
    
    def place_building(self, grid_x: int, grid_y: int):
        """Place the selected building."""
        building_type = self.building_menu.selected_building
        
        if not self.economy.buy_building(building_type):
            self.hud.add_message("Not enough gold!", (255, 100, 100))
            return
        
        # Create the building
        if building_type == "warrior_guild":
            building = WarriorGuild(grid_x, grid_y)
        elif building_type == "ranger_guild":
            building = RangerGuild(grid_x, grid_y)
        elif building_type == "rogue_guild":
            building = RogueGuild(grid_x, grid_y)
        elif building_type == "wizard_guild":
            building = WizardGuild(grid_x, grid_y)
        elif building_type == "marketplace":
            building = Marketplace(grid_x, grid_y)
        else:
            return

        # Newly placed buildings start unconstructed (1 HP, non-targetable) until a peasant begins building.
        if hasattr(building, "mark_unconstructed"):
            building.mark_unconstructed()
        
        self.buildings.append(building)
        self.building_menu.cancel_selection()
        self.hud.add_message(f"{building_type.replace('_', ' ').title()} placed (needs building)", (100, 255, 100))
    
    def place_bounty(self):
        """Place a bounty at the current mouse position."""
        mouse_pos = pygame.mouse.get_pos()
        world_x = mouse_pos[0] + self.camera_x
        world_y = mouse_pos[1] + self.camera_y
        
        # Default bounty reward
        reward = 50
        
        if not self.economy.add_bounty(reward):
            self.hud.add_message("Not enough gold for bounty!", (255, 100, 100))
            return
        
        self.bounty_system.place_bounty(world_x, world_y, reward, "explore")
        self.hud.add_message(f"Bounty placed: ${reward}", (255, 215, 0))
    
    def update(self, dt: float):
        """Update game state."""
        if self.paused:
            return
        
        # Build game state for AI
        game_state = self.get_game_state()
        
        # Update AI for heroes
        if self.ai_controller:
            self.ai_controller.update(dt, self.heroes, game_state)
        
        # Update heroes
        for hero in self.heroes:
            hero.update(dt, game_state)

        # Spawn peasants from the castle (1 every 5s) until there are 2 alive.
        castle = game_state.get("castle")
        self.peasant_spawn_timer += dt
        alive_peasants = [p for p in self.peasants if p.is_alive]
        if castle and len(alive_peasants) < 2 and self.peasant_spawn_timer >= 5.0:
            self.peasant_spawn_timer = 0.0
            self.peasants.append(Peasant(castle.center_x, castle.center_y))

        # Update peasants
        for peasant in self.peasants:
            peasant.update(dt, game_state)
        
        # Update enemies
        for enemy in self.enemies:
            enemy.update(dt, self.heroes, self.peasants, self.buildings)
        
        # Spawn new enemies
        new_enemies = self.spawner.update(dt)
        self.enemies.extend(new_enemies)
        
        # Process combat
        events = self.combat_system.process_combat(
            self.heroes, self.enemies, self.buildings
        )
        
        # Handle combat events
        for event in events:
            if event["type"] == "enemy_killed":
                self.hud.add_message(
                    f"{event['hero']} slew a {event['enemy']}! (+{event['gold']}g, +{event['xp']}xp)",
                    (255, 215, 0)
                )
            elif event["type"] == "castle_destroyed":
                self.hud.add_message("GAME OVER - Castle Destroyed!", (255, 0, 0))
                self.paused = True
        
        # Clean up dead enemies
        self.enemies = [e for e in self.enemies if e.is_alive]
        
        # Process bounties
        claimed = self.bounty_system.check_claims(self.heroes)
        for bounty, hero in claimed:
            self.hud.add_message(
                f"{hero.name} claimed bounty: +${bounty.reward}!",
                (255, 215, 0)
            )
        self.bounty_system.cleanup()
        
        # Update tax collector
        if self.tax_collector:
            self.tax_collector.update(dt, self.buildings, self.economy)
        
        # Update HUD
        self.hud.update()
        
        # Update camera (edge scrolling)
        self.update_camera()
    
    def update_camera(self):
        """Update camera position based on mouse position."""
        mouse_x, mouse_y = pygame.mouse.get_pos()
        scroll_speed = 10
        edge_margin = 50
        
        if mouse_x < edge_margin:
            self.camera_x = max(0, self.camera_x - scroll_speed)
        elif mouse_x > WINDOW_WIDTH - edge_margin:
            max_x = MAP_WIDTH * TILE_SIZE - WINDOW_WIDTH
            self.camera_x = min(max_x, self.camera_x + scroll_speed)
        
        if mouse_y < edge_margin:
            self.camera_y = max(0, self.camera_y - scroll_speed)
        elif mouse_y > WINDOW_HEIGHT - edge_margin:
            max_y = MAP_HEIGHT * TILE_SIZE - WINDOW_HEIGHT
            self.camera_y = min(max_y, self.camera_y + scroll_speed)
    
    def get_game_state(self) -> dict:
        """Get current game state for AI and UI."""
        castle = next((b for b in self.buildings if b.building_type == "castle"), None)
        return {
            "gold": self.economy.player_gold,
            "heroes": self.heroes,
            "peasants": self.peasants,
            "enemies": self.enemies,
            "buildings": self.buildings,
            "bounties": self.bounty_system.get_unclaimed_bounties(),
            "wave": self.spawner.wave_number,
            "selected_hero": self.selected_hero,
            "castle": castle,
            "economy": self.economy,
        }
    
    def render(self):
        """Render the game."""
        # Clear screen
        self.screen.fill(COLOR_BLACK)
        
        camera_offset = (self.camera_x, self.camera_y)
        
        # Render world
        self.world.render(self.screen, camera_offset)
        
        # Render buildings
        for building in self.buildings:
            building.render(self.screen, camera_offset)
        
        # Render enemies
        for enemy in self.enemies:
            enemy.render(self.screen, camera_offset)
        
        # Render heroes
        for hero in self.heroes:
            hero.render(self.screen, camera_offset)

        # Render peasants
        for peasant in self.peasants:
            peasant.render(self.screen, camera_offset)
        
        # Render tax collector
        if self.tax_collector:
            self.tax_collector.render(self.screen, camera_offset)
        
        # Render bounties
        self.bounty_system.render(self.screen, camera_offset)
        
        # Render building preview
        self.building_menu.render(self.screen, camera_offset)
        
        # Render HUD
        self.hud.render(self.screen, self.get_game_state())
        
        # Render debug panel
        self.debug_panel.render(self.screen, self.get_game_state())
        
        # Render building panel
        self.building_panel.render(self.screen, self.heroes, self.economy)
        
        # Pause overlay
        if self.paused:
            overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 128))
            self.screen.blit(overlay, (0, 0))
            
            font = pygame.font.Font(None, 72)
            text = font.render("PAUSED", True, (255, 255, 255))
            text_rect = text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2))
            self.screen.blit(text, text_rect)
        
        pygame.display.flip()
    
    def run(self):
        """Main game loop."""
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0  # Delta time in seconds
            
            self.handle_events()
            self.update(dt)
            self.render()
        
        pygame.quit()

