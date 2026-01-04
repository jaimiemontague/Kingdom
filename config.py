"""
Configuration settings for the Kingdom Sim game.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Window settings
# WK3 decision: default launch is borderless fullscreen at 1920x1080 (fallback handled in engine).
WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1080
FPS = 60
PROTOTYPE_VERSION = "1.2.7"
GAME_TITLE = f"Kingdom Sim (Prototype v{PROTOTYPE_VERSION}) — The Audio Update"

# Display behavior (Build A): borderless default, with safe fallback to display resolution if smaller.
# Note: pygame flags are applied in `game/engine.py` where we can query display size.
DEFAULT_BORDERLESS = True

# Determinism / simulation settings (future multiplayer enablement)
# - DETERMINISTIC_SIM=1: run simulation with fixed dt (tick-based) and seeded RNG.
# - SIM_SEED: base seed for procedural world + spawns (do not use Python's hash()).
DETERMINISTIC_SIM = os.getenv("DETERMINISTIC_SIM", "0") == "1"
SIM_TICK_HZ = int(os.getenv("SIM_TICK_HZ", str(FPS)))
SIM_SEED = int(os.getenv("SIM_SEED", "1"))

# Tile settings
TILE_SIZE = 32
# Release tuning: smaller map for better performance / faster gameplay loop.
# 25% smaller than 200x200 -> 150x150.
MAP_WIDTH = 150  # tiles
MAP_HEIGHT = 150  # tiles

# Camera / view settings
CAMERA_SPEED_PX_PER_SEC = 900  # world pixels per second (WASD + edge scroll)
CAMERA_EDGE_MARGIN_PX = 40
ZOOM_MIN = 0.5
ZOOM_MAX = 2.5
ZOOM_STEP = 1.15

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

# Hero settings
HERO_HIRE_COST = 50
HERO_BASE_HP = 100
HERO_BASE_ATTACK = 10
HERO_BASE_DEFENSE = 5
HERO_SPEED = 2

# Enemy settings
GOBLIN_HP = 30
GOBLIN_ATTACK = 5
GOBLIN_SPEED = 1.5
GOBLIN_SPAWN_INTERVAL = 5000  # milliseconds

# Safety cap: reduce overall monster density for release stability.
# (~2/3 reduction from 60 -> 20)
MAX_ALIVE_ENEMIES = 20

# Additional enemy types (lairs)
WOLF_HP = 22
WOLF_ATTACK = 4
WOLF_SPEED = 2.3

SKELETON_HP = 55
SKELETON_ATTACK = 7
SKELETON_SPEED = 1.1

# Skeleton Archer (ranged kiter)
SKELETON_ARCHER_HP = 40
SKELETON_ARCHER_ATTACK = 4
SKELETON_ARCHER_SPEED = 1.35
SKELETON_ARCHER_ATTACK_RANGE_TILES = 6.0
SKELETON_ARCHER_MIN_RANGE_TILES = 2.0
SKELETON_ARCHER_ATTACK_COOLDOWN_MS = 1400

# Lair settings (release tuning)
# (~2/3 reduction from 6 -> 2)
LAIR_INITIAL_COUNT = 2
LAIR_MIN_DISTANCE_FROM_CASTLE_TILES = 18
LAIR_STASH_GROWTH_PER_SPAWN = 8
ROGUE_LAIR_GOLD_THRESHOLD = 100
LAIR_BOUNTY_COST = 90

# Bounty reward bands (player-paid; cost == reward). Used by Engine input + early pacing nudge.
BOUNTY_REWARD_LOW = 25
BOUNTY_REWARD_MED = 60
BOUNTY_REWARD_HIGH = 150

# Early pacing guardrail (FS-3 / Build B): deterministic nudge to surface bounties early.
# Values:
# - "auto": default behavior (tip at ~35s if no bounties; starter lair bounty at ~90s if none + affordable)
# - "off": disable entirely
# - "force": fire immediately (for QA verification), still respecting "don't trigger if any bounties exist"
EARLY_PACING_NUDGE_MODE = os.getenv("EARLY_PACING_NUDGE_MODE", "auto")

# Economy settings
STARTING_GOLD = 1500
TAX_RATE = 0.20

# LLM settings
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")  # openai, claude, gemini, grok
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROK_API_KEY = os.getenv("GROK_API_KEY", "")

# LLM decision settings
LLM_DECISION_COOLDOWN = 2000  # milliseconds between LLM calls per hero
LLM_TIMEOUT = 5.0  # seconds
HEALTH_THRESHOLD_FOR_DECISION = 0.5  # 50% health triggers retreat consideration

# WK6: Ranger exploration bias toward black fog
RANGER_EXPLORE_BLACK_FOG_BIAS = 0.7  # 0.0-1.0: probability of picking frontier vs random wander (default 0.7 = 70% frontier)
RANGER_FRONTIER_SCAN_RADIUS_TILES = 10  # Maximum radius (in tiles) to scan for black fog frontier tiles
RANGER_FRONTIER_COMMIT_MS = 4000  # Commitment window (sim-time ms) to prevent rapid re-targeting of exploration goals

# WK6: Bounty targeting in black fog
BOUNTY_BLACK_FOG_DISTANCE_PENALTY = 1.2  # Distance multiplier for bounties in black fog (uncertainty penalty, but never exclusion)

