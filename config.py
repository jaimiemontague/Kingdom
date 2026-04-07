"""
Configuration settings for the Kingdom Sim game.
"""
from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class WindowConfig:
    width: int = 1920
    height: int = 1080
    fps: int = 60
    prototype_version: str = "1.4.7"
    game_title: str = "Kingdom Sim (Prototype v1.4.7) — 3D Visual Polish"
    default_borderless: bool = True


@dataclass(frozen=True)
class SimConfig:
    deterministic_sim: bool
    tick_hz: int
    seed: int
    early_pacing_nudge_mode: str


@dataclass(frozen=True)
class MapConfig:
    tile_size: int = 32
    width: int = 150
    height: int = 150


@dataclass(frozen=True)
class CameraConfig:
    speed_px_per_sec: int = 900
    edge_margin_px: int = 40
    zoom_min: float = 0.5
    zoom_max: float = 2.5
    zoom_step: float = 1.15


@dataclass(frozen=True)
class HeroConfig:
    hire_cost: int = 50
    base_hp: int = 100
    base_attack: int = 10
    base_defense: int = 5
    speed: int = 2


@dataclass(frozen=True)
class EnemyConfig:
    goblin_hp: int = 30
    goblin_attack: int = 5
    goblin_speed: float = 1.5
    goblin_spawn_interval: int = 3500   # wk15: lower = more frequent waves (was 5000)
    max_alive_enemies: int = 32         # wk15: higher cap for more aggressive waves (was 20)
    wolf_hp: int = 22
    wolf_attack: int = 4
    wolf_speed: float = 2.3
    skeleton_hp: int = 55
    skeleton_attack: int = 7
    skeleton_speed: float = 1.1
    skeleton_archer_hp: int = 40
    skeleton_archer_attack: int = 4
    skeleton_archer_speed: float = 1.35
    skeleton_archer_attack_range_tiles: float = 6.0
    skeleton_archer_min_range_tiles: float = 2.0
    skeleton_archer_attack_cooldown_ms: int = 1400


@dataclass(frozen=True)
class LairConfig:
    initial_count: int = 4   # wk15: more lairs = more monster density (was 2)
    min_distance_from_castle_tiles: int = 18
    stash_growth_per_spawn: int = 8
    rogue_lair_gold_threshold: int = 100
    bounty_cost: int = 90


@dataclass(frozen=True)
class BountyConfig:
    reward_low: int = 25
    reward_med: int = 60
    reward_high: int = 150
    black_fog_distance_penalty: float = 1.2


@dataclass(frozen=True)
class EconomyConfig:
    starting_gold: int = 2100   # wk15: +40% from 1500 for pacing
    tax_rate: float = 0.25      # 25% (hero/lair gold uses this; monster gold increased separately for pacing)
    tax_collection_interval_sec: float = 45.0  # wk15: collector runs more often (was 60s hardcoded)
    tax_collector_rest_after_return_sec: float = 10.0  # Rest at castle 10s after returning a nice haul
    tax_collector_nice_haul_gold: int = 20  # Gold deposited >= this triggers the short rest


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    openai_api_key: str
    openai_model: str
    anthropic_api_key: str
    gemini_api_key: str
    grok_api_key: str
    decision_cooldown: int = 2000
    timeout: float = 5.0
    health_threshold_for_decision: float = 0.5


@dataclass(frozen=True)
class RangerConfig:
    explore_black_fog_bias: float = 0.7
    frontier_scan_radius_tiles: int = 10
    frontier_commit_ms: int = 4000


# Speed tiers (wk12 Chronos: 5-tier player-facing speed control)
SPEED_PAUSE = 0.0
SPEED_SUPER_SLOW = 0.1
SPEED_SLOW = 0.25
SPEED_NORMAL = 0.5
SPEED_FAST = 1.0
DEFAULT_SPEED_TIER = SPEED_NORMAL
SPEED_TIER_NAMES = {
    SPEED_PAUSE: "Paused",
    SPEED_SUPER_SLOW: "Super Slow",
    SPEED_SLOW: "Slow",
    SPEED_NORMAL: "Normal",
    SPEED_FAST: "Fast",
}


# Grouped config objects (frozen dataclasses)
WINDOW = WindowConfig()
SIM = SimConfig(
    deterministic_sim=os.getenv("DETERMINISTIC_SIM", "0") == "1",
    tick_hz=int(os.getenv("SIM_TICK_HZ", str(WINDOW.fps))),
    seed=int(os.getenv("SIM_SEED", "1")),
    early_pacing_nudge_mode=os.getenv("EARLY_PACING_NUDGE_MODE", "auto"),
)
MAP = MapConfig()
CAMERA = CameraConfig()
HERO = HeroConfig()
ENEMY = EnemyConfig()
LAIR = LairConfig()
BOUNTY = BountyConfig()
ECONOMY = EconomyConfig()
LLM = LLMConfig(
    provider=os.getenv("LLM_PROVIDER", "openai"),
    openai_api_key=os.getenv("OPENAI_API_KEY", ""),
    openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
    gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
    grok_api_key=os.getenv("GROK_API_KEY", ""),
)
RANGER = RangerConfig()

# Research timer (wk15: timed research for Marketplace/Blacksmith/Library)
RESEARCH_POTIONS_DURATION_MS = 30_000  # 30s for potions
RESEARCH_DURATION_MS_PER_100_GOLD = 10_000  # e.g. 200 cost = 20s, 300 = 30s

# Backward-compatible module-level aliases (consumers unchanged)
# Window settings
WINDOW_WIDTH = WINDOW.width
WINDOW_HEIGHT = WINDOW.height
FPS = WINDOW.fps
PROTOTYPE_VERSION = WINDOW.prototype_version
GAME_TITLE = WINDOW.game_title
DEFAULT_BORDERLESS = WINDOW.default_borderless

# Determinism / simulation settings
DETERMINISTIC_SIM = SIM.deterministic_sim
SIM_TICK_HZ = SIM.tick_hz
SIM_SEED = SIM.seed
EARLY_PACING_NUDGE_MODE = SIM.early_pacing_nudge_mode

# Map settings
TILE_SIZE = MAP.tile_size
MAP_WIDTH = MAP.width
MAP_HEIGHT = MAP.height

# Camera / view settings
CAMERA_SPEED_PX_PER_SEC = CAMERA.speed_px_per_sec
CAMERA_EDGE_MARGIN_PX = CAMERA.edge_margin_px
ZOOM_MIN = CAMERA.zoom_min
ZOOM_MAX = CAMERA.zoom_max
ZOOM_STEP = CAMERA.zoom_step

# Colors
COLOR_GRASS = (34, 139, 34)
COLOR_WATER = (65, 105, 225)
COLOR_PATH = (139, 119, 101)
COLOR_TREE = (0, 100, 0)
COLOR_UI_BG = (40, 40, 50)
COLOR_UI_BORDER = (80, 80, 100)
COLOR_GOLD = (255, 215, 0)
COLOR_WHITE = (255, 255, 255)
COLOR_BLACK = (0, 0, 0)
COLOR_RED = (220, 20, 60)
COLOR_GREEN = (50, 205, 50)
COLOR_BLUE = (70, 130, 180)

# Building settings
BUILDING_COSTS = {
    "castle": 0,  # Free, placed at start
    "warrior_guild": 150,
    "ranger_guild": 175,
    "rogue_guild": 160,
    "wizard_guild": 220,
    "marketplace": 100,
    # Phase 1: Economic Buildings
    "blacksmith": 200,
    "inn": 150,
    "trading_post": 250,
    # Phase 2: Temples
    "temple_agrela": 400,
    "temple_dauros": 400,
    "temple_fervus": 400,
    "temple_krypta": 400,
    "temple_krolm": 400,
    "temple_helia": 400,
    "temple_lunord": 400,
    # Phase 3: Non-Human Dwellings
    "gnome_hovel": 300,
    "elven_bungalow": 350,
    "dwarven_settlement": 300,
    # Phase 4: Defensive Structures
    "guardhouse": 200,
    "ballista_tower": 300,
    "wizard_tower": 500,
    # Phase 5: Special Buildings
    "fairgrounds": 400,
    "library": 350,
    "royal_gardens": 250,
    # Phase 6: Palace
    "palace": 0,
    # Neutral auto-spawn buildings (not player-placeable)
    "house": 0,
    "farm": 0,
    "food_stand": 0,
}

BUILDING_SIZES = {
    "castle": (3, 3),
    "warrior_guild": (2, 2),
    "ranger_guild": (2, 2),
    "rogue_guild": (2, 2),
    "wizard_guild": (2, 2),
    "marketplace": (2, 2),
    # Phase 1: Economic Buildings
    "blacksmith": (2, 2),
    "inn": (2, 2),
    "trading_post": (2, 2),
    # Phase 2: Temples
    "temple_agrela": (3, 3),
    "temple_dauros": (3, 3),
    "temple_fervus": (3, 3),
    "temple_krypta": (3, 3),
    "temple_krolm": (3, 3),
    "temple_helia": (3, 3),
    "temple_lunord": (3, 3),
    # Phase 3: Non-Human Dwellings
    "gnome_hovel": (2, 2),
    "elven_bungalow": (2, 2),
    "dwarven_settlement": (2, 2),
    # Phase 4: Defensive Structures
    "guardhouse": (2, 2),
    "ballista_tower": (1, 1),
    "wizard_tower": (2, 2),
    # Phase 5: Special Buildings
    "fairgrounds": (3, 3),
    "library": (2, 2),
    "royal_gardens": (2, 2),
    # Phase 6: Palace
    "palace": (3, 3),
    # Neutral auto-spawn buildings
    "house": (1, 1),
    "farm": (2, 2),
    "food_stand": (1, 1),
    # Lairs
    "goblin_camp": (2, 2),
    "wolf_den": (2, 2),
    "skeleton_crypt": (3, 3),
    "spider_nest": (2, 2),
    "bandit_camp": (3, 3),
}

BUILDING_COLORS = {
    "castle": (139, 69, 19),
    "warrior_guild": (178, 34, 34),
    "ranger_guild": (46, 139, 87),
    "rogue_guild": (75, 0, 130),
    "wizard_guild": (147, 112, 219),
    "marketplace": (218, 165, 32),
    # Phase 1: Economic Buildings
    "blacksmith": (105, 105, 105),  # Dark gray
    "inn": (160, 82, 45),  # Sienna
    "trading_post": (255, 140, 0),  # Dark orange
    # Phase 2: Temples
    "temple_agrela": (255, 192, 203),  # Pink (healing)
    "temple_dauros": (255, 255, 224),  # Light yellow (monks)
    "temple_fervus": (50, 205, 50),  # Lime green (nature)
    "temple_krypta": (75, 0, 130),  # Indigo (death)
    "temple_krolm": (139, 0, 0),  # Dark red (rage)
    "temple_helia": (255, 165, 0),  # Orange (sun)
    "temple_lunord": (176, 196, 222),  # Light steel blue (wind)
    # Phase 3: Non-Human Dwellings
    "gnome_hovel": (128, 128, 0),  # Olive
    "elven_bungalow": (34, 139, 34),  # Forest green
    "dwarven_settlement": (101, 67, 33),  # Brown
    # Phase 4: Defensive Structures
    "guardhouse": (128, 128, 128),  # Gray
    "ballista_tower": (64, 64, 64),  # Dark gray
    "wizard_tower": (138, 43, 226),  # Blue violet
    # Phase 5: Special Buildings
    "fairgrounds": (255, 20, 147),  # Deep pink
    "library": (25, 25, 112),  # Midnight blue
    "royal_gardens": (124, 252, 0),  # Lawn green
    # Phase 6: Palace
    "palace": (184, 134, 11),  # Dark goldenrod
    # Neutral auto-spawn buildings
    "house": (120, 100, 80),  # warm brown
    "farm": (200, 170, 90),  # wheat
    "food_stand": (210, 120, 60),  # orange/brown
    # Lairs
    "goblin_camp": (120, 80, 40),
    "wolf_den": (90, 90, 90),
    "skeleton_crypt": (70, 60, 90),
    "spider_nest": (20, 20, 20),
    "bandit_camp": (110, 70, 40),
}

# Building constraints (mutually exclusive buildings)
BUILDING_CONSTRAINTS = {
    "gnome_hovel": ["elven_bungalow", "dwarven_settlement"],
    "elven_bungalow": ["gnome_hovel", "dwarven_settlement"],
    "dwarven_settlement": ["gnome_hovel", "elven_bungalow"],
}

# Building prerequisites (required buildings)
BUILDING_PREREQUISITES = {
    "ballista_tower": ["dwarven_settlement"],
}

# Inn economy (WK18): entry and loiter fees; heroes with gold < 1 are ejected
INN_ENTRY_FEE = 2
INN_LOITER_FEE_GOLD_PER_SEC = 0.5

# Max heroes that can be inside a building at once (0 = not enterable in this sprint)
BUILDING_MAX_OCCUPANTS = {
    "castle": 0,
    "warrior_guild": 4,
    "ranger_guild": 4,
    "rogue_guild": 4,
    "wizard_guild": 4,
    "marketplace": 3,
    "blacksmith": 2,
    "inn": 6,
    "trading_post": 0,
    "temple_agrela": 4,
    "temple_dauros": 4,
    "temple_fervus": 4,
    "temple_krypta": 4,
    "temple_krolm": 4,
    "temple_helia": 4,
    "temple_lunord": 4,
    "gnome_hovel": 0,
    "elven_bungalow": 0,
    "dwarven_settlement": 0,
    "guardhouse": 0,
    "ballista_tower": 0,
    "wizard_tower": 0,
    "fairgrounds": 0,
    "library": 0,
    "royal_gardens": 0,
    "palace": 0,
    "house": 0,
    "farm": 0,
    "food_stand": 0,
}

# Hero settings
HERO_HIRE_COST = HERO.hire_cost
HERO_BASE_HP = HERO.base_hp
HERO_BASE_ATTACK = HERO.base_attack
HERO_BASE_DEFENSE = HERO.base_defense
HERO_SPEED = HERO.speed

# Enemy settings
GOBLIN_HP = ENEMY.goblin_hp
GOBLIN_ATTACK = ENEMY.goblin_attack
GOBLIN_SPEED = ENEMY.goblin_speed
GOBLIN_SPAWN_INTERVAL = ENEMY.goblin_spawn_interval

# Safety cap: reduce overall monster density for release stability.
# (~2/3 reduction from 60 -> 20)
MAX_ALIVE_ENEMIES = ENEMY.max_alive_enemies

# Additional enemy types (lairs)
WOLF_HP = ENEMY.wolf_hp
WOLF_ATTACK = ENEMY.wolf_attack
WOLF_SPEED = ENEMY.wolf_speed

SKELETON_HP = ENEMY.skeleton_hp
SKELETON_ATTACK = ENEMY.skeleton_attack
SKELETON_SPEED = ENEMY.skeleton_speed

# Skeleton Archer (ranged kiter)
SKELETON_ARCHER_HP = ENEMY.skeleton_archer_hp
SKELETON_ARCHER_ATTACK = ENEMY.skeleton_archer_attack
SKELETON_ARCHER_SPEED = ENEMY.skeleton_archer_speed
SKELETON_ARCHER_ATTACK_RANGE_TILES = ENEMY.skeleton_archer_attack_range_tiles
SKELETON_ARCHER_MIN_RANGE_TILES = ENEMY.skeleton_archer_min_range_tiles
SKELETON_ARCHER_ATTACK_COOLDOWN_MS = ENEMY.skeleton_archer_attack_cooldown_ms

# Lair settings (release tuning)
# (~2/3 reduction from 6 -> 2)
LAIR_INITIAL_COUNT = LAIR.initial_count
LAIR_MIN_DISTANCE_FROM_CASTLE_TILES = LAIR.min_distance_from_castle_tiles
LAIR_STASH_GROWTH_PER_SPAWN = LAIR.stash_growth_per_spawn
ROGUE_LAIR_GOLD_THRESHOLD = LAIR.rogue_lair_gold_threshold

# --- WK22 Ursina 3D viewer (directional shadows; lower = faster GPU) ---
# Shadow maps are expensive; keep off by default for playable FPS (set True for screenshots).
URSINA_DIRECTIONAL_SHADOWS = False
URSINA_SHADOW_MAP_SIZE = 512
# Min seconds between full-map fog texture rebuilds (heroes exploring can thrash visibility).
URSINA_FOG_MIN_UPDATE_INTERVAL_SEC = 0.12
# Legacy: Ursina HUD GPU upload is now skipped via row-sampled CRC when pixels are unchanged (ursina_app).
URSINA_UI_UPLOAD_INTERVAL_SEC = 0.10
LAIR_BOUNTY_COST = LAIR.bounty_cost

# Bounty reward bands (player-paid; cost == reward). Used by Engine input + early pacing nudge.
BOUNTY_REWARD_LOW = BOUNTY.reward_low
BOUNTY_REWARD_MED = BOUNTY.reward_med
BOUNTY_REWARD_HIGH = BOUNTY.reward_high

# Economy settings
STARTING_GOLD = ECONOMY.starting_gold
TAX_RATE = ECONOMY.tax_rate
TAX_COLLECTION_INTERVAL_SEC = ECONOMY.tax_collection_interval_sec
TAX_COLLECTOR_REST_AFTER_RETURN_SEC = ECONOMY.tax_collector_rest_after_return_sec
TAX_COLLECTOR_NICE_HAUL_GOLD = ECONOMY.tax_collector_nice_haul_gold

# LLM settings
LLM_PROVIDER = LLM.provider  # openai, claude, gemini, grok, mock
OPENAI_API_KEY = LLM.openai_api_key
OPENAI_MODEL = LLM.openai_model
ANTHROPIC_API_KEY = LLM.anthropic_api_key
GEMINI_API_KEY = LLM.gemini_api_key
GROK_API_KEY = LLM.grok_api_key

# LLM decision settings
LLM_DECISION_COOLDOWN = LLM.decision_cooldown
LLM_TIMEOUT = LLM.timeout
HEALTH_THRESHOLD_FOR_DECISION = LLM.health_threshold_for_decision

# wk14 Persona and Presence: conversation mode
CONVERSATION_COOLDOWN_MS = 2000
CONVERSATION_HISTORY_LIMIT = 20
CONVERSATION_TIMEOUT = 8.0

# WK6: Ranger exploration bias toward black fog
RANGER_EXPLORE_BLACK_FOG_BIAS = RANGER.explore_black_fog_bias  # 0.0-1.0: probability of picking frontier vs random wander (default 0.7 = 70% frontier)
RANGER_FRONTIER_SCAN_RADIUS_TILES = RANGER.frontier_scan_radius_tiles  # Maximum radius (in tiles) to scan for black fog frontier tiles
RANGER_FRONTIER_COMMIT_MS = RANGER.frontier_commit_ms  # Commitment window (sim-time ms) to prevent rapid re-targeting of exploration goals

# WK6: Bounty targeting in black fog
BOUNTY_BLACK_FOG_DISTANCE_PENALTY = BOUNTY.black_fog_distance_penalty  # Distance multiplier for bounties in black fog (uncertainty penalty, but never exclusion)

