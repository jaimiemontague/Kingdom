"""
Main game engine - handles the game loop, input, and coordination.
"""
import time
import pygame
from config import (
    WINDOW_WIDTH, WINDOW_HEIGHT, FPS, GAME_TITLE, TILE_SIZE,
    MAP_WIDTH, MAP_HEIGHT, COLOR_BLACK,
    CAMERA_SPEED_PX_PER_SEC, CAMERA_EDGE_MARGIN_PX,
    ZOOM_MIN, ZOOM_MAX, ZOOM_STEP,
    MAX_ALIVE_ENEMIES,
    LAIR_BOUNTY_COST,
    BOUNTY_REWARD_LOW,
    BOUNTY_REWARD_MED,
    BOUNTY_REWARD_HIGH,
    EARLY_PACING_NUDGE_MODE,
    DETERMINISTIC_SIM,
    SIM_TICK_HZ,
    SIM_SEED,
)
from game.graphics.vfx import VFXSystem
from game.world import World, Visibility
 
from game.entities import (
    Castle, WarriorGuild, RangerGuild, RogueGuild, WizardGuild, Marketplace,
    Blacksmith, Inn, TradingPost,
    TempleAgrela, TempleDauros, TempleFervus, TempleKrypta, TempleKrolm, TempleHelia, TempleLunord,
    GnomeHovel, ElvenBungalow, DwarvenSettlement,
    Guardhouse, BallistaTower, WizardTower,
    Fairgrounds, Library, RoyalGardens,
    Palace, Hero, Goblin, TaxCollector, Peasant, Guard
)
from game.systems import CombatSystem, EconomySystem, EnemySpawner, BountySystem, LairSystem, NeutralBuildingSystem
from game.systems.buffs import BuffSystem
from game.ui import HUD, BuildingMenu, DebugPanel, BuildingPanel
from game.graphics.font_cache import get_font
from game.systems import perf_stats
from game.sim.determinism import set_sim_seed
from game.sim.timebase import set_sim_now_ms



class GameEngine:
    """Main game engine class."""
    
    def __init__(self, early_nudge_mode: str | None = None):
        pygame.init()
        pygame.font.init()

        # Determinism knobs (future multiplayer enablement).
        # Seed early so world gen + initial lairs are reproducible when enabled.
        set_sim_seed(SIM_SEED)
        self._sim_now_ms = 0

        # Early pacing guardrail (ContentScenarioDirector, wk1 broad sweep):
        # Within the first few minutes, surface a clear prompt and optionally place
        # a starter bounty using existing systems. Driven by sim-time (dt), not wall-clock.
        self._early_nudge_elapsed_s = 0.0
        self._early_nudge_tip_shown = False
        self._early_nudge_starter_bounty_done = False
        self._early_nudge_mode = (early_nudge_mode or EARLY_PACING_NUDGE_MODE or "auto").strip().lower()
        
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption(GAME_TITLE)
        self.clock = pygame.time.Clock()
        self.running = True
        self.paused = False

        # Perf overlay
        self.show_perf = True
        self._perf_last_ms = 0
        self._perf_pf_calls = 0
        self._perf_pf_failures = 0
        self._perf_pf_total_ms = 0.0
        # Cached overlay panel (avoid per-frame Surface allocations)
        self._perf_overlay_next_update_ms = 0
        self._perf_overlay_panel = None
        self._perf_overlay_dirty = True
        self._perf_snapshot = {
            "fps": 0.0,
            "heroes": 0,
            "enemies": 0,
            "peasants": 0,
            "guards": 0,
        }
        # Loop timings (diagnostic only; EMA smoothing)
        self._perf_events_ms = 0.0
        self._perf_update_ms = 0.0
        self._perf_render_ms = 0.0
        
        # Initialize game world
        self.world = World()
        
        # Camera
        self.camera_x = 0
        self.camera_y = 0
        self.zoom = 1.0
        self.default_zoom = 1.0

        # Render surfaces (avoid per-frame allocations).
        self._view_surface = None
        self._view_surface_size = (0, 0)
        self._scaled_surface = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
        self._pause_overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        self._pause_overlay.fill((0, 0, 0, 128))
        
        # Game objects
        self.buildings = []
        self.heroes = []
        self.enemies = []
        self.bounties = []
        self.peasants = []
        self.guards = []
        self.peasant_spawn_timer = 0.0
        
        # Systems
        self.combat_system = CombatSystem()
        self.economy = EconomySystem()
        self.spawner = EnemySpawner(self.world)
        self.lair_system = LairSystem(self.world)
        self.neutral_building_system = NeutralBuildingSystem(self.world)
        self.buff_system = BuffSystem()
        
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

        # VFX system (lightweight particles for hits/kills).
        # Expected interface:
        # - update(dt: float) -> None
        # - render(surface: pygame.Surface, camera_offset: tuple[int,int]) -> None
        # - emit_from_events(events: list[dict]) -> None
        self.vfx_system = VFXSystem()
        
        # Tax collector (created after castle is placed)
        self.tax_collector = None
        
        # Initialize starting buildings
        self.setup_initial_state()

    def _update_fog_of_war(self):
        """Update fog-of-war visibility around the castle and living heroes."""
        # Tunables (tile radius). Kept local to avoid cross-agent config conflicts.
        CASTLE_VISION_TILES = 10
        HERO_VISION_TILES = 7

        castle = next((b for b in self.buildings if getattr(b, "building_type", None) == "castle"), None)
        revealers = []
        if castle is not None:
            revealers.append((castle.center_x, castle.center_y, CASTLE_VISION_TILES))

        for hero in self.heroes:
            if getattr(hero, "is_alive", True):
                revealers.append((hero.x, hero.y, HERO_VISION_TILES))

        if revealers:
            self.world.update_visibility(revealers)
        
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
        self.center_on_castle(reset_zoom=True, castle=castle)

        # Spawn initial monster lairs (hostile world-structures).
        self.lair_system.spawn_initial_lairs(self.buildings, castle)
        self.clamp_camera()

        # Initialize fog-of-war reveal around the starting castle.
        self._update_fog_of_war()
        
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

            # Pygame 2 mouse wheel event
            elif hasattr(pygame, "MOUSEWHEEL") and event.type == pygame.MOUSEWHEEL:
                # event.y: +1 scroll up, -1 scroll down
                if event.y > 0:
                    self.zoom_by(ZOOM_STEP)
                elif event.y < 0:
                    self.zoom_by(1.0 / ZOOM_STEP)
    
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
        # Phase 1: Economic Buildings
        elif event.key == pygame.K_6:
            if self.economy.can_afford_building("blacksmith"):
                self.building_menu.select_building("blacksmith")
            else:
                self.hud.add_message("Not enough gold!", (255, 100, 100))
        elif event.key == pygame.K_7:
            if self.economy.can_afford_building("inn"):
                self.building_menu.select_building("inn")
            else:
                self.hud.add_message("Not enough gold!", (255, 100, 100))
        elif event.key == pygame.K_8:
            if self.economy.can_afford_building("trading_post"):
                self.building_menu.select_building("trading_post")
            else:
                self.hud.add_message("Not enough gold!", (255, 100, 100))
        # Phase 2: Temples (using letters)
        elif event.key == pygame.K_t:
            # Cycle through temples or use T for first temple
            if self.economy.can_afford_building("temple_agrela"):
                self.building_menu.select_building("temple_agrela")
            else:
                self.hud.add_message("Not enough gold!", (255, 100, 100))
        # Phase 3: Non-Human Dwellings
        elif event.key == pygame.K_g:
            if self.economy.can_afford_building("gnome_hovel"):
                self.building_menu.select_building("gnome_hovel")
            else:
                self.hud.add_message("Not enough gold!", (255, 100, 100))
        elif event.key == pygame.K_e:
            if self.economy.can_afford_building("elven_bungalow"):
                self.building_menu.select_building("elven_bungalow")
            else:
                self.hud.add_message("Not enough gold!", (255, 100, 100))
        elif event.key == pygame.K_v:
            if self.economy.can_afford_building("dwarven_settlement"):
                self.building_menu.select_building("dwarven_settlement")
            else:
                self.hud.add_message("Not enough gold!", (255, 100, 100))
        # Phase 4: Defensive Structures
        elif event.key == pygame.K_u:
            if self.economy.can_afford_building("guardhouse"):
                self.building_menu.select_building("guardhouse")
            else:
                self.hud.add_message("Not enough gold!", (255, 100, 100))
        elif event.key == pygame.K_y:
            # Y for ballista tower (B is used for bounties)
            if self.economy.can_afford_building("ballista_tower"):
                self.building_menu.select_building("ballista_tower")
            else:
                self.hud.add_message("Not enough gold!", (255, 100, 100))
        elif event.key == pygame.K_o:
            if self.economy.can_afford_building("wizard_tower"):
                self.building_menu.select_building("wizard_tower")
            else:
                self.hud.add_message("Not enough gold!", (255, 100, 100))
        # Phase 5: Special Buildings
        elif event.key == pygame.K_f:
            if self.economy.can_afford_building("fairgrounds"):
                self.building_menu.select_building("fairgrounds")
            else:
                self.hud.add_message("Not enough gold!", (255, 100, 100))
        elif event.key == pygame.K_i:
            if self.economy.can_afford_building("library"):
                self.building_menu.select_building("library")
            else:
                self.hud.add_message("Not enough gold!", (255, 100, 100))
        elif event.key == pygame.K_r:
            if self.economy.can_afford_building("royal_gardens"):
                self.building_menu.select_building("royal_gardens")
            else:
                self.hud.add_message("Not enough gold!", (255, 100, 100))
                
        elif event.key == pygame.K_h:
            # Hire a hero
            self.try_hire_hero()
            
        elif event.key == pygame.K_SPACE:
            # Center view on castle and reset to starting zoom
            self.center_on_castle(reset_zoom=True)
        
        elif event.key == pygame.K_F1:
            # Toggle debug panel
            self.debug_panel.toggle()
        elif event.key == pygame.K_F2:
            # Toggle perf overlay
            self.show_perf = not self.show_perf
        elif event.key == pygame.K_F3:
            # Toggle HUD help/controls overlay
            if hasattr(self.hud, "toggle_help"):
                self.hud.toggle_help()
        
        elif event.key == pygame.K_b:
            # Place a bounty at mouse position
            self.place_bounty()
            
        elif event.key == pygame.K_p:
            # Use potion for selected hero
            if self.selected_hero and self.selected_hero.is_alive:
                if self.selected_hero.use_potion():
                    self.hud.add_message(f"{self.selected_hero.name} used a potion!", (100, 255, 100))

        # Zoom controls (+/- and keypad)
        elif event.key in (pygame.K_EQUALS, pygame.K_KP_PLUS):
            self.zoom_by(ZOOM_STEP)
        elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self.zoom_by(1.0 / ZOOM_STEP)
    
    def handle_mousedown(self, event):
        """Handle mouse clicks."""
        # Mouse wheel zoom (older pygame uses buttons 4/5)
        if event.button == 4:
            self.zoom_by(ZOOM_STEP)
            return
        if event.button == 5:
            self.zoom_by(1.0 / ZOOM_STEP)
            return

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
                (self.camera_x, self.camera_y),
                zoom=self.zoom
            )
        
        # Update building panel hover state
        self.building_panel.update_hover(event.pos)
    
    def try_select_hero(self, screen_pos: tuple) -> bool:
        """Try to select a hero at the given screen position. Returns True if selected."""
        world_x, world_y = self.screen_to_world(screen_pos[0], screen_pos[1])
        
        for hero in self.heroes:
            if hero.is_alive and hero.distance_to(world_x, world_y) < hero.size:
                self.selected_hero = hero
                return True
        
        return False
    
    def try_select_building(self, screen_pos: tuple) -> bool:
        """Try to select a building at the given screen position. Returns True if selected."""
        world_x, world_y = self.screen_to_world(screen_pos[0], screen_pos[1])
        
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
        building = None
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
        # Phase 1: Economic Buildings
        elif building_type == "blacksmith":
            building = Blacksmith(grid_x, grid_y)
        elif building_type == "inn":
            building = Inn(grid_x, grid_y)
        elif building_type == "trading_post":
            building = TradingPost(grid_x, grid_y)
        # Phase 2: Temples
        elif building_type == "temple_agrela":
            building = TempleAgrela(grid_x, grid_y)
        elif building_type == "temple_dauros":
            building = TempleDauros(grid_x, grid_y)
        elif building_type == "temple_fervus":
            building = TempleFervus(grid_x, grid_y)
        elif building_type == "temple_krypta":
            building = TempleKrypta(grid_x, grid_y)
        elif building_type == "temple_krolm":
            building = TempleKrolm(grid_x, grid_y)
        elif building_type == "temple_helia":
            building = TempleHelia(grid_x, grid_y)
        elif building_type == "temple_lunord":
            building = TempleLunord(grid_x, grid_y)
        # Phase 3: Non-Human Dwellings
        elif building_type == "gnome_hovel":
            building = GnomeHovel(grid_x, grid_y)
        elif building_type == "elven_bungalow":
            building = ElvenBungalow(grid_x, grid_y)
        elif building_type == "dwarven_settlement":
            building = DwarvenSettlement(grid_x, grid_y)
        # Phase 4: Defensive Structures
        elif building_type == "guardhouse":
            building = Guardhouse(grid_x, grid_y)
        elif building_type == "ballista_tower":
            building = BallistaTower(grid_x, grid_y)
        elif building_type == "wizard_tower":
            building = WizardTower(grid_x, grid_y)
        # Phase 5: Special Buildings
        elif building_type == "fairgrounds":
            building = Fairgrounds(grid_x, grid_y)
        elif building_type == "library":
            building = Library(grid_x, grid_y)
        elif building_type == "royal_gardens":
            building = RoyalGardens(grid_x, grid_y)
        # Phase 6: Palace
        elif building_type == "palace":
            building = Palace(grid_x, grid_y)
        
        if building is None:
            return

        # Newly placed buildings start unconstructed (1 HP, non-targetable) until a peasant begins building.
        if hasattr(building, "mark_unconstructed"):
            building.mark_unconstructed()
        
        self.buildings.append(building)
        self.building_menu.cancel_selection()
        self.hud.add_message(f"Placed: {building_type.replace('_', ' ').title()} (awaiting construction)", (100, 255, 100))
    
    def place_bounty(self):
        """Place a bounty at the current mouse position."""
        mouse_pos = pygame.mouse.get_pos()
        world_x, world_y = self.screen_to_world(mouse_pos[0], mouse_pos[1])
        
        # Bounty reward tiers (player-paid; cost == reward).
        mods = pygame.key.get_mods()
        if mods & pygame.KMOD_CTRL:
            reward = int(BOUNTY_REWARD_HIGH)
        elif mods & pygame.KMOD_SHIFT:
            reward = int(BOUNTY_REWARD_MED)
        else:
            reward = int(BOUNTY_REWARD_LOW)
        
        if not self.economy.add_bounty(reward):
            self.hud.add_message("Not enough gold for bounty!", (255, 100, 100))
            return
        
        self.bounty_system.place_bounty(world_x, world_y, reward, "explore")
        self.hud.add_message(f"Bounty placed (${reward}). Heroes will respond.", (255, 215, 0))

    def _nearest_lair_to(self, x: float, y: float):
        """Return nearest living lair to (x,y) or None."""
        lairs = getattr(self.lair_system, "lairs", []) or []
        best = None
        best_d2 = None
        for lair in lairs:
            if getattr(lair, "hp", 1) <= 0:
                continue
            lx = float(getattr(lair, "center_x", getattr(lair, "x", 0.0)))
            ly = float(getattr(lair, "center_y", getattr(lair, "y", 0.0)))
            dx = lx - float(x)
            dy = ly - float(y)
            d2 = dx * dx + dy * dy
            if best is None or (best_d2 is not None and d2 < best_d2):
                best = lair
                best_d2 = d2
        return best

    def _maybe_apply_early_pacing_nudge(self, dt: float, castle):
        """
        Deterministic-ish early-session pacing hook:
        - show a short HUD prompt early if the player hasn't placed a bounty
        - later, optionally place a starter 'attack_lair' bounty on the nearest lair
          (only if the player can afford it and hasn't placed any bounties yet)
        """
        if not castle:
            return

        mode = getattr(self, "_early_nudge_mode", "auto")
        if mode == "off":
            return
        if mode not in ("auto", "force"):
            mode = "auto"

        # Only relevant in the early game window.
        self._early_nudge_elapsed_s += float(dt)
        if self._early_nudge_elapsed_s > 180.0:
            return

        unclaimed = self.bounty_system.get_unclaimed_bounties()
        has_any_bounty = bool(unclaimed)

        tip_time_s = 0.0 if mode == "force" else 35.0
        starter_time_s = 0.0 if mode == "force" else 90.0

        # 1) Tip prompt: show once.
        if (not self._early_nudge_tip_shown) and (self._early_nudge_elapsed_s >= tip_time_s) and (not has_any_bounty):
            self._early_nudge_tip_shown = True
            self.hud.add_message("Tip: Press B to place a bounty and guide heroes.", (220, 220, 255))
            self.hud.add_message("Try targeting a lair for big stash payouts.", (220, 220, 255))

        # 2) Optional starter bounty: show player a clear lever if they haven't engaged.
        if self._early_nudge_starter_bounty_done:
            return
        if self._early_nudge_elapsed_s < starter_time_s:
            return
        if has_any_bounty:
            # Player already engaged with the bounty system; don't interfere.
            self._early_nudge_starter_bounty_done = True
            return

        lair = self._nearest_lair_to(float(castle.center_x), float(castle.center_y))
        if lair is None:
            self._early_nudge_starter_bounty_done = True
            return

        reward = int(LAIR_BOUNTY_COST) if LAIR_BOUNTY_COST else 75
        if not self.economy.add_bounty(reward):
            # Can't afford; keep it non-spammy and don't keep retrying.
            self._early_nudge_starter_bounty_done = True
            self.hud.add_message("Tip: Earn more gold to place bounties that guide heroes.", (220, 220, 255))
            return

        bx = float(getattr(lair, "center_x", getattr(lair, "x", 0.0)))
        by = float(getattr(lair, "center_y", getattr(lair, "y", 0.0)))
        self.bounty_system.place_bounty(bx, by, reward, "attack_lair", target=lair)
        self._early_nudge_starter_bounty_done = True
        self.hud.add_message(f"Starter bounty placed: Clear the lair (+${reward})", (255, 215, 0))
    
    def update(self, dt: float):
        """Update game state."""
        if DETERMINISTIC_SIM:
            # Drive gameplay timing off simulation time (not wall-clock).
            self._sim_now_ms += int(round(float(dt) * 1000.0))
            set_sim_now_ms(self._sim_now_ms)
        else:
            set_sim_now_ms(None)

        # Allow camera movement even while paused.
        self.update_camera(dt)
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

        # Fog-of-war reveal (castle + heroes).
        self._update_fog_of_war()

        # Apply/refresh buffs (auras) once per tick so ATK/DEF stays dynamic and stable.
        self.buff_system.update(self.heroes, self.buildings)

        # Spawn peasants from the castle (1 every 5s) until there are 2 alive.
        castle = game_state.get("castle")

        # Content pacing guardrail: nudge player toward a clear early decision.
        self._maybe_apply_early_pacing_nudge(dt, castle)

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
            enemy.update(dt, self.heroes, self.peasants, self.buildings, guards=self.guards, world=self.world)

        # Update guards
        for guard in self.guards:
            guard.update(dt, self.enemies, world=self.world, buildings=self.buildings)
        
        # Spawn new enemies (with a safety cap to prevent runaway slowdown if enemies accumulate)
        alive_enemy_count = len([e for e in self.enemies if getattr(e, "is_alive", False)])
        remaining_slots = max(0, int(MAX_ALIVE_ENEMIES) - alive_enemy_count)
        if remaining_slots > 0:
            new_enemies = self.spawner.update(dt)
            if new_enemies:
                self.enemies.extend(new_enemies[:remaining_slots])

            # Spawn enemies from lairs (in addition to wave spawns)
            alive_enemy_count = len([e for e in self.enemies if getattr(e, "is_alive", False)])
            remaining_slots = max(0, int(MAX_ALIVE_ENEMIES) - alive_enemy_count)
            if remaining_slots > 0:
                lair_enemies = self.lair_system.update(dt, self.buildings)
                if lair_enemies:
                    self.enemies.extend(lair_enemies[:remaining_slots])
        
        # Process combat
        events = self.combat_system.process_combat(
            self.heroes, self.enemies, self.buildings
        )

        # Feed combat events into optional VFX system (non-blocking, best-effort).
        if self.vfx_system is not None and hasattr(self.vfx_system, "emit_from_events"):
            try:
                self.vfx_system.emit_from_events(events)
            except Exception:
                # VFX should never crash the simulation.
                pass
        
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
            elif event["type"] == "lair_cleared":
                lair_name = event.get("lair_type", "lair").replace("_", " ").title()
                gold = event.get("gold", 0)
                hero_name = event.get("hero", "A hero")
                self.hud.add_message(
                    f"{hero_name} cleared {lair_name}! (+{gold}g)",
                    (255, 215, 0),
                )
                lair_obj = event.get("lair_obj")

                # Completion-based lair bounty payout (do NOT allow proximity-claim).
                # If there is an active attack_lair bounty targeting this lair, pay it to the clearing hero now.
                try:
                    hero_obj = next((h for h in self.heroes if getattr(h, "name", None) == hero_name), None)
                    if hero_obj is not None and lair_obj is not None:
                        for b in list(getattr(self.bounty_system, "bounties", []) or []):
                            if getattr(b, "claimed", False):
                                continue
                            if getattr(b, "bounty_type", None) != "attack_lair":
                                continue
                            if getattr(b, "target", None) is lair_obj:
                                b.claim(hero_obj)
                except Exception:
                    # Bounty payout should never crash the sim.
                    pass

                if lair_obj in self.buildings:
                    self.buildings.remove(lair_obj)
                if lair_obj in getattr(self.lair_system, "lairs", []):
                    self.lair_system.lairs.remove(lair_obj)
        
        # Clean up dead enemies
        self.enemies = [e for e in self.enemies if e.is_alive]

        # Clean up dead guards
        self.guards = [g for g in self.guards if getattr(g, "is_alive", False)]
        
        # Process bounties
        claimed = self.bounty_system.check_claims(self.heroes)
        for bounty, hero in claimed:
            self.hud.add_message(
                f"{hero.name} claimed bounty: +${bounty.reward}!",
                (255, 215, 0)
            )
        self.bounty_system.cleanup()

        # Neutral buildings: auto-spawn + passive tax
        self.neutral_building_system.update(dt, self.buildings, self.heroes, castle)
        
        # Update tax collector
        if self.tax_collector:
            self.tax_collector.update(dt, self.buildings, self.economy, world=self.world)
        
        # Update buildings that need periodic updates
        for building in self.buildings:
            if building.building_type == "trading_post" and hasattr(building, "update"):
                building.update(dt, self.economy)
            elif building.building_type == "ballista_tower" and hasattr(building, "update"):
                building.update(dt, self.enemies)
            elif building.building_type == "wizard_tower" and hasattr(building, "update"):
                building.update(dt, self.enemies)
            elif building.building_type == "fairgrounds" and hasattr(building, "update"):
                building.update(dt, self.economy, self.heroes)
            elif building.building_type == "guardhouse" and hasattr(building, "update"):
                # Guard spawning handled here so guards become real entities.
                should_spawn = building.update(dt, [g for g in self.guards if g.home_building == building])
                if should_spawn:
                    # Spawn a guard near the guardhouse.
                    g = Guard(building.center_x + TILE_SIZE, building.center_y, home_building=building)
                    self.guards.append(g)
                    if hasattr(building, "guards_spawned"):
                        building.guards_spawned += 1

            # Palace guards (if palace building exists)
            elif building.building_type == "palace":
                max_guards = getattr(building, "max_palace_guards", 0)
                if max_guards > 0 and getattr(building, "is_constructed", True):
                    current = len([g for g in self.guards if g.home_building == building])
                    if current < max_guards:
                        g = Guard(building.center_x + TILE_SIZE, building.center_y, home_building=building)
                        self.guards.append(g)
        
        # Update HUD
        self.hud.update()

        # Update VFX (after simulation state is updated).
        if self.vfx_system is not None and hasattr(self.vfx_system, "update"):
            try:
                self.vfx_system.update(dt)
            except Exception:
                pass
        
        # Camera already updated at top of update()
    
    def screen_to_world(self, screen_x: float, screen_y: float) -> tuple[float, float]:
        """Convert screen-space pixels to world-space pixels, accounting for zoom."""
        z = self.zoom if self.zoom else 1.0
        return self.camera_x + (screen_x / z), self.camera_y + (screen_y / z)

    def clamp_camera(self):
        """Clamp camera to world bounds given current zoom."""
        view_w = max(1, int(WINDOW_WIDTH / (self.zoom if self.zoom else 1.0)))
        view_h = max(1, int(WINDOW_HEIGHT / (self.zoom if self.zoom else 1.0)))
        world_w = MAP_WIDTH * TILE_SIZE
        world_h = MAP_HEIGHT * TILE_SIZE

        max_x = max(0, world_w - view_w)
        max_y = max(0, world_h - view_h)

        self.camera_x = max(0, min(max_x, self.camera_x))
        self.camera_y = max(0, min(max_y, self.camera_y))

    def center_on_castle(self, reset_zoom: bool = True, castle=None):
        """Center camera on the castle; optionally reset zoom to the starting zoom."""
        if reset_zoom:
            self.zoom = float(getattr(self, "default_zoom", 1.0))

        if castle is None:
            castle = next(
                (b for b in self.buildings if getattr(b, "building_type", None) == "castle" and getattr(b, "hp", 0) > 0),
                None,
            )
        if not castle:
            return

        self.camera_x = castle.center_x - WINDOW_WIDTH // 2
        self.camera_y = castle.center_y - WINDOW_HEIGHT // 2
        self.clamp_camera()

    def set_zoom(self, new_zoom: float):
        """Set zoom with clamping."""
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, float(new_zoom)))
        self.clamp_camera()

    def zoom_by(self, factor: float):
        """Zoom in/out around the mouse cursor."""
        if factor is None:
            return
        factor = float(factor)
        if factor <= 0:
            return

        mouse_x, mouse_y = pygame.mouse.get_pos()
        before_x, before_y = self.screen_to_world(mouse_x, mouse_y)

        self.set_zoom(self.zoom * factor)

        # Keep the same world point under the cursor after zooming.
        after_zoom = self.zoom if self.zoom else 1.0
        self.camera_x = before_x - (mouse_x / after_zoom)
        self.camera_y = before_y - (mouse_y / after_zoom)
        self.clamp_camera()

    def update_camera(self, dt: float):
        """Update camera position based on WASD + mouse edge scrolling."""
        keys = pygame.key.get_pressed()
        speed = float(CAMERA_SPEED_PX_PER_SEC) * float(dt)

        dx = 0.0
        dy = 0.0

        # WASD pan (world-space pixels)
        if keys[pygame.K_a]:
            dx -= speed
        if keys[pygame.K_d]:
            dx += speed
        if keys[pygame.K_w]:
            dy -= speed
        if keys[pygame.K_s]:
            dy += speed

        # Mouse edge scroll (still in world-space pixels)
        mouse_x, mouse_y = pygame.mouse.get_pos()
        if mouse_x < CAMERA_EDGE_MARGIN_PX:
            dx -= speed
        elif mouse_x > WINDOW_WIDTH - CAMERA_EDGE_MARGIN_PX:
            dx += speed

        if mouse_y < CAMERA_EDGE_MARGIN_PX:
            dy -= speed
        elif mouse_y > WINDOW_HEIGHT - CAMERA_EDGE_MARGIN_PX:
            dy += speed

        if dx or dy:
            self.camera_x += dx
            self.camera_y += dy
            self.clamp_camera()
    
    def get_game_state(self) -> dict:
        """Get current game state for AI and UI."""
        castle = next((b for b in self.buildings if b.building_type == "castle"), None)
        return {
            "gold": self.economy.player_gold,
            "heroes": self.heroes,
            "peasants": self.peasants,
            "guards": self.guards,
            "enemies": self.enemies,
            "buildings": self.buildings,
            "bounties": self.bounty_system.get_unclaimed_bounties(),
            "bounty_system": self.bounty_system,
            "wave": self.spawner.wave_number,
            "selected_hero": self.selected_hero,
            "castle": castle,
            "economy": self.economy,
            "world": self.world,
            # UI helper: placement mode info for HUD
            "placing_building_type": getattr(self.building_menu, "selected_building", None),
        }
    
    def render(self):
        """Render the game."""
        # Clear screen
        self.screen.fill(COLOR_BLACK)

        # Pixel art: quantize camera to integer pixels to reduce shimmer.
        camera_offset = (int(self.camera_x), int(self.camera_y))

        # If not zoomed, render directly to the screen to avoid an expensive smoothscale.
        if abs((self.zoom if self.zoom else 1.0) - 1.0) < 1e-6:
            view_surface = self.screen
        else:
            # Render world + entities to a zoomed "camera view" surface, then scale to window.
            view_w = max(1, int(WINDOW_WIDTH / (self.zoom if self.zoom else 1.0)))
            view_h = max(1, int(WINDOW_HEIGHT / (self.zoom if self.zoom else 1.0)))
            if self._view_surface is None or self._view_surface_size != (view_w, view_h):
                self._view_surface = pygame.Surface((view_w, view_h))
                self._view_surface_size = (view_w, view_h)
            view_surface = self._view_surface
            view_surface.fill(COLOR_BLACK)

        # Render world
        self.world.render(view_surface, camera_offset)

        # Render buildings
        for building in self.buildings:
            building.render(view_surface, camera_offset)

        # Render enemies
        for enemy in self.enemies:
            # Fog-of-war: enemies should only be visible when currently in vision (VISIBLE),
            # not in explored-but-dim (SEEN) tiles.
            gx, gy = self.world.world_to_grid(getattr(enemy, "x", 0.0), getattr(enemy, "y", 0.0))
            if 0 <= gx < self.world.width and 0 <= gy < self.world.height:
                if self.world.visibility[gy][gx] != Visibility.VISIBLE:
                    continue
            else:
                continue
            enemy.render(view_surface, camera_offset)

        # Render heroes
        for hero in self.heroes:
            hero.render(view_surface, camera_offset)

        # Render guards
        for guard in self.guards:
            guard.render(view_surface, camera_offset)

        # Render peasants
        for peasant in self.peasants:
            peasant.render(view_surface, camera_offset)

        # Render tax collector
        if self.tax_collector:
            self.tax_collector.render(view_surface, camera_offset)

        # Render bounties
        # Precompute lightweight UI metrics (responders/attractiveness) so bounty markers can display them.
        if hasattr(self.bounty_system, "update_ui_metrics"):
            try:
                self.bounty_system.update_ui_metrics(self.heroes, self.enemies, self.buildings)
            except Exception:
                pass
        self.bounty_system.render(view_surface, camera_offset)

        # Render building preview
        self.building_menu.render(view_surface, camera_offset)

        # Render VFX overlay (world-space) if present.
        if self.vfx_system is not None and hasattr(self.vfx_system, "render"):
            try:
                self.vfx_system.render(view_surface, camera_offset)
            except Exception:
                pass

        # Fog-of-war overlay (covers world + entities/markers in unrevealed areas)
        # Draw AFTER world/entities/VFX so hidden areas remain hidden.
        if hasattr(self.world, "render_fog"):
            self.world.render_fog(view_surface, camera_offset)

        # Scale the world to the actual window (reusing a destination surface)
        if view_surface is not self.screen:
            # Pixel art: nearest-neighbor scaling (no blur).
            pygame.transform.scale(view_surface, (WINDOW_WIDTH, WINDOW_HEIGHT), self._scaled_surface)
            self.screen.blit(self._scaled_surface, (0, 0))
        
        # Render HUD
        self.hud.render(self.screen, self.get_game_state())
        
        # Render debug panel
        self.debug_panel.render(self.screen, self.get_game_state())
        
        # Render building panel
        self.building_panel.render(self.screen, self.heroes, self.economy)

        # Perf overlay (helps diagnose lag spikes)
        if self.show_perf:
            self.render_perf_overlay(self.screen)
        
        # Pause overlay
        if self.paused:
            self.screen.blit(self._pause_overlay, (0, 0))
            
            font = pygame.font.Font(None, 72)
            text = font.render("PAUSED", True, (255, 255, 255))
            text_rect = text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2))
            self.screen.blit(text, text_rect)
        
        pygame.display.flip()

    def render_perf_overlay(self, surface: pygame.Surface):
        now_ms = pygame.time.get_ticks()
        if self._perf_last_ms == 0:
            self._perf_last_ms = now_ms

        # Update snapshot ~1x/sec (pathfinding stats) and ~4x/sec (counts + timings).
        if self._perf_overlay_next_update_ms == 0:
            self._perf_overlay_next_update_ms = now_ms

        if now_ms >= self._perf_overlay_next_update_ms:
            self._perf_overlay_next_update_ms = now_ms + 250
            self._perf_snapshot["fps"] = float(self.clock.get_fps())
            self._perf_snapshot["heroes"] = len([h for h in self.heroes if getattr(h, "is_alive", True)])
            self._perf_snapshot["enemies"] = len([e for e in self.enemies if getattr(e, "is_alive", False)])
            self._perf_snapshot["peasants"] = len([p for p in self.peasants if getattr(p, "is_alive", True)])
            self._perf_snapshot["guards"] = len([g for g in self.guards if getattr(g, "is_alive", False)])
            self._perf_overlay_dirty = True

        if now_ms - self._perf_last_ms >= 1000:
            self._perf_last_ms = now_ms
            self._perf_pf_calls = perf_stats.pathfinding.calls
            self._perf_pf_failures = perf_stats.pathfinding.failures
            self._perf_pf_total_ms = perf_stats.pathfinding.total_ms
            perf_stats.reset_pathfinding()
            self._perf_overlay_dirty = True

        # Rebuild panel only when sampled values change.
        if self._perf_overlay_panel is None or self._perf_overlay_dirty:
            self._perf_overlay_dirty = False

            fps = float(self._perf_snapshot.get("fps", 0.0))
            enemies_alive = int(self._perf_snapshot.get("enemies", 0))
            heroes_alive = int(self._perf_snapshot.get("heroes", 0))
            peasants_alive = int(self._perf_snapshot.get("peasants", 0))
            guards_alive = int(self._perf_snapshot.get("guards", 0))

            lines = [
                f"FPS: {fps:0.1f}",
                f"Entities: heroes={heroes_alive} peasants={peasants_alive} guards={guards_alive} enemies={enemies_alive} (cap={MAX_ALIVE_ENEMIES})",
                f"Loop ms (ema): events={self._perf_events_ms:0.2f} update={self._perf_update_ms:0.2f} render={self._perf_render_ms:0.2f}",
                f"PF calls/s: {self._perf_pf_calls}  fails/s: {self._perf_pf_failures}  ms/s: {self._perf_pf_total_ms:0.1f}",
            ]

            font = get_font(16)
            pad = 6
            w = 0
            h = 0
            rendered = []
            for line in lines:
                s = font.render(line, True, (255, 255, 255))
                rendered.append(s)
                w = max(w, s.get_width())
                h += s.get_height()

            panel = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
            panel.fill((0, 0, 0, 140))
            yy = pad
            for s in rendered:
                panel.blit(s, (pad, yy))
                yy += s.get_height()
            self._perf_overlay_panel = panel

        surface.blit(self._perf_overlay_panel, (10, 10))
    
    def run(self):
        """Main game loop."""
        while self.running:
            if DETERMINISTIC_SIM:
                # Keep realtime pacing, but do not use wall-clock delta for simulation.
                self.clock.tick(FPS)
                dt = 1.0 / max(1, int(SIM_TICK_HZ))
            else:
                dt = self.clock.tick(FPS) / 1000.0  # Delta time in seconds

            t0 = time.perf_counter()
            self.handle_events()
            t1 = time.perf_counter()
            self.update(dt)
            t2 = time.perf_counter()
            self.render()
            t3 = time.perf_counter()

            # Perf timings (EMA). Diagnostic only: must not affect simulation state.
            if self.show_perf:
                evt_ms = (t1 - t0) * 1000.0
                upd_ms = (t2 - t1) * 1000.0
                rnd_ms = (t3 - t2) * 1000.0

                alpha = 0.12
                self._perf_events_ms = evt_ms if self._perf_events_ms <= 0 else (self._perf_events_ms * (1 - alpha) + evt_ms * alpha)
                self._perf_update_ms = upd_ms if self._perf_update_ms <= 0 else (self._perf_update_ms * (1 - alpha) + upd_ms * alpha)
                self._perf_render_ms = rnd_ms if self._perf_render_ms <= 0 else (self._perf_render_ms * (1 - alpha) + rnd_ms * alpha)
        
        pygame.quit()

