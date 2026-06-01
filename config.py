"""
Configuration settings for the Kingdom Sim game.
"""
from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


# WK60: Starting Buildings (Feature 6 — Make It Fun)
# Pre-constructed buildings placed around castle at game start.
# Each entry: (building_type, grid_x, grid_y)
# Castle is at (124, 124) 3x3 footprint, occupying tiles (124-126, 124-126).
# All starting buildings are 2x2.
STARTING_BUILDINGS = [
    ("warrior_guild", 128, 124),   # East of castle
    ("ranger_guild", 119, 124),    # West of castle (2 tiles gap)
    ("marketplace", 124, 128),     # South of castle
    ("food_stand", 127, 128),      # WK61-R11: east of marketplace (>=2 tile gap)
    ("guardhouse", 124, 131),      # Further south
]

# WK60: Guild Hero Cap (Feature 3 — Make It Fun)
GUILD_MAX_HEROES = 8

# WK60: Guardhouse Arrow Config (Feature 5 — Make It Fun)
GUARDHOUSE_ARROW_RANGE_TILES = 8.0
GUARDHOUSE_ARROW_DAMAGE = 12
GUARDHOUSE_ARROW_COOLDOWN = 2.0
GUARDHOUSE_ARROWS_PER_SHOT = 2  # WK61-TUNE-002: fire 2 arrows per volley
GUARDHOUSE_MAX_HP = 250  # WK61-R4-BUG-006: defensive structure HP for combat/UI state

# WK61-R4-BUG-005: heroes shop when mostly healthy (not only at 100% after WK61 HP tuning).
SHOP_MIN_HEALTH_FRACTION = 0.85

# WK61-TUNE-003: Hero rest recovery rates (5x guild, 7x inn from WK60 baseline)
GUILD_REST_RECOVERY_RATE = 0.05   # was 0.01 default (~2.5 HP/sec)
INN_REST_RECOVERY_RATE = 0.14     # was 0.02 (~7.0 HP/sec)

# WK61-FEAT-007: Enemy building priority range (enemies within this many tiles of a
# building strongly prefer attacking buildings over chasing heroes)
ENEMY_BUILDING_PRIORITY_RANGE_TILES = 10


@dataclass(frozen=True)
class DifficultyConfig:
    """WK60: Difficulty system tuning knobs (Feature 8 — Make It Fun)."""
    default_difficulty: str = "normal"  # easy, normal, hard
    easy_spawn_interval_mult: float = 1.5
    easy_enemy_count_mult: float = 0.6
    easy_enemy_hp_mult: float = 0.7
    easy_enemy_damage_mult: float = 0.7
    hard_spawn_interval_mult: float = 0.7
    hard_enemy_count_mult: float = 1.5
    hard_enemy_hp_mult: float = 1.3
    hard_enemy_damage_mult: float = 1.3


@dataclass(frozen=True)
class WaveEventConfig:
    """WK60: Wave events system tuning knobs (Feature 1 — Make It Fun)."""
    first_event_minute: float = 2.0   # WK61-R10: was 3.0
    interval_minutes: float = 1.75    # WK61-R10: was 2.5
    warning_seconds: float = 10.0
    max_enemy_cap_overflow: float = 1.5  # wave events can temporarily exceed MAX_ALIVE_ENEMIES by this factor


DIFFICULTY = DifficultyConfig()
WAVE_EVENT = WaveEventConfig()

# WK61-R10: economy pacing (playtest polish)
NEUTRAL_TAX_PER_MINUTE = {"house": 9.0, "farm": 12.0, "food_stand": 10.0}
ECONOMY_TAX_RATE_MULT = 1.4  # optional shop-sale multiplier; not applied to global TAX_RATE

# WK61-R10: spawner pacing
SPAWNER_INITIAL_NO_SPAWN_MS = 1500
SPAWNER_FIRST_WAVE_INTERVAL_MS = 3500
SPAWNER_EXTRA_SPAWN_DELAY_MS = 5000
SPAWNER_GOBLIN_INTERVAL_MULT = 2

# WK61-R10: hero hunger meals at food stands
HUNGER_INTERVAL_MS = 60_000  # WK61-R12: 1 min for faster playtest feedback
FOOD_MEAL_COST_GOLD = 5
FOOD_MEAL_HUNGER_RESET = True

# WK61-R11: marketplace passive taxable income (hold-G stash, not player treasury)
MARKETPLACE_PASSIVE_TAX_INTERVAL_MS = 120_000
MARKETPLACE_PASSIVE_TAX_MIN = 100
MARKETPLACE_PASSIVE_TAX_MAX = 400


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


# Research timer (wk15: timed research for Marketplace/Blacksmith/Library)
RESEARCH_POTIONS_DURATION_MS = 30_000  # 30s for potions
RESEARCH_DURATION_MS_PER_100_GOLD = 10_000  # e.g. 200 cost = 20s, 300 = 30s

# Flat module-level config constants (the canonical surface consumers import).
# Window settings
WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1080
FPS = 60
PROTOTYPE_VERSION = "1.5.8"
GAME_TITLE = "Kingdom Sim (Prototype v1.5.8) — Major FPS Leap with Tree Instancing, Terrain Fog Shading, and Batching"
DEFAULT_BORDERLESS = True

# Determinism / simulation settings (env-driven; read at import time)
DETERMINISTIC_SIM = os.getenv("DETERMINISTIC_SIM", "0") == "1"
SIM_TICK_HZ = int(os.getenv("SIM_TICK_HZ", str(FPS)))
SIM_SEED = int(os.getenv("SIM_SEED", "1"))
EARLY_PACING_NUDGE_MODE = os.getenv("EARLY_PACING_NUDGE_MODE", "auto")

# Map settings
TILE_SIZE = 32
MAP_WIDTH = 250
MAP_HEIGHT = 250

# 2D unit sprite raster size (PNG scale for heroes/enemies/workers). Simulation grid stays TILE_SIZE px/tile.
UNIT_SPRITE_PIXELS = int(os.getenv("KINGDOM_UNIT_SPRITE_PX", "48"))

# Ursina 3D: worker billboards (see ``ursina_renderer.PEASANT_SCALE_*``).
# ``BASE`` scales X/Z; ``Y_SCALE_MUL`` squashes quad height so tall Legacy Vania sprites match
# hero silhouette without blurring textures in the exporter. Env: KINGDOM_URSINA_WORKER_SCALE,
# KINGDOM_URSINA_WORKER_Y_MUL.
# Default 0.42 ≈ 1.5× the prior 0.28 pass (readability vs heroes); tune with env / Y_MUL as needed.
URSINA_WORKER_BILLBOARD_BASE = float(os.getenv("KINGDOM_URSINA_WORKER_SCALE", "0.42"))
URSINA_WORKER_BILLBOARD_Y_SCALE_MUL = float(os.getenv("KINGDOM_URSINA_WORKER_Y_MUL", "0.55"))

# WK46 Stage 3: Lumberjack builders (local wood, per BuilderPeasant).
BUILDER_CHOP_DURATION_S = 5.0
BUILDER_HARVEST_DURATION_S = 5.0
BUILDER_WOOD_COST_HOUSE = 10
BUILDER_WOOD_COST_FOOD_STAND = 10
BUILDER_WOOD_COST_FARM = 20
BUILDER_MIN_CHOP_GROWTH = 0.50

# Camera / view settings
CAMERA_SPEED_PX_PER_SEC = 900
CAMERA_EDGE_MARGIN_PX = 40
ZOOM_MIN = 0.3
ZOOM_MAX = 5.0
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
# WK70 Round C-1 (Move 10 / kills L7): these 4 maps are now DERIVED back-compat views of
# the single source of truth `game.content.buildings.BUILDING_DEFS`. They are byte-identical
# (keys + values) to the pre-WK70 hand-authored dicts (guarded by
# tests/test_wk70_building_registry.py). Edit BUILDING_DEFS, not these. Membership rules:
#   COSTS/MAX_OCCUPANTS  -> exclude lairs (they hit Building.__init__ defaults), include POIs
#   SIZES/COLORS         -> include lairs + POIs
# Import is safe: BUILDING_DEFS imports nothing from game.entities at load time (config is a
# leaf imported by ~152 files, including the game.entities/game.systems graph, so it must not
# import that graph back). The BuildingType-coverage assert lives in game.content.buildings,
# which validates against a standalone load of game/entities/buildings/types.py (a pure enum,
# no config dependency) — see assert_building_type_coverage() there, run at its import.
from game.content.buildings import BUILDING_DEFS

BUILDING_COSTS = {k: d.cost for k, d in BUILDING_DEFS.items() if not d.is_lair}
BUILDING_SIZES = {k: d.size for k, d in BUILDING_DEFS.items()}          # incl. lairs + POIs
BUILDING_COLORS = {k: d.color for k, d in BUILDING_DEFS.items()}       # incl. lairs + POIs

# Building constraints (mutually exclusive buildings)
BUILDING_CONSTRAINTS = {}

# Building prerequisites (required buildings)
BUILDING_PREREQUISITES = {
    "temple": [],
}

# Inn economy (WK18): entry and loiter fees; heroes with gold < 1 are ejected
INN_ENTRY_FEE = 2
INN_LOITER_FEE_GOLD_PER_SEC = 0.5

# Max heroes that can be inside a building at once (0 = not enterable in this sprint)
# WK70: derived view of BUILDING_DEFS (excludes lairs, which hit Building.__init__ default 8).
BUILDING_MAX_OCCUPANTS = {
    k: d.max_occupants for k, d in BUILDING_DEFS.items() if not d.is_lair
}

# Fog: player building line-of-sight (WK34; SimEngine `GameEngine` / `SimEngine._update_fog_of_war`)
# All constructed player buildings (excl. castle, neutrals, lairs) get a revealer at the
# building center. Guild hiring halls use 3D prefabs that often read slightly past the
# logical 2×2 sim footprint in Ursina, so fog can look "hugged" to the mesh; the extra
# is additive and tunable.
PLAYER_BUILDING_VISION_TILES = 3
PLAYER_GUILD_TYPES = frozenset({"warrior_guild", "ranger_guild", "rogue_guild", "wizard_guild"})
PLAYER_GUILD_EXTRA_VISION_TILES = 2

# Hero settings
HERO_HIRE_COST = 100  # WK60: doubled from 50 (Feature 4 — Make It Fun)
HERO_BASE_HP = 60  # WK61-TUNE-004: reduced from 100 (heroes fragile early, tough with levels)
HERO_BASE_ATTACK = 10
HERO_BASE_DEFENSE = 5
HERO_SPEED = 120.0  # px/sec (baked: old 2 * 60)

# Enemy settings
GOBLIN_HP = 30
GOBLIN_ATTACK = 5
GOBLIN_SPEED = 90.0  # px/sec (baked: old 1.5 * 60)
GOBLIN_SPAWN_INTERVAL = 3500   # wk15: lower = more frequent waves (was 5000)

# Safety cap: reduce overall monster density for release stability.
# (~2/3 reduction from 60 -> 20)
MAX_ALIVE_ENEMIES = 80         # WK61-R12: raised from 48 for doubled wave counts

# Additional enemy types (lairs)
WOLF_HP = 22
WOLF_ATTACK = 4
WOLF_SPEED = 138.0  # px/sec (baked: old 2.3 * 60)

SKELETON_HP = 55
SKELETON_ATTACK = 7
SKELETON_SPEED = 66.0  # px/sec (baked: old 1.1 * 60)

# Skeleton Archer (ranged kiter)
SKELETON_ARCHER_HP = 40
SKELETON_ARCHER_ATTACK = 4
SKELETON_ARCHER_SPEED = 81.0  # px/sec (baked: old 1.35 * 60)
SKELETON_ARCHER_ATTACK_RANGE_TILES = 6.0
SKELETON_ARCHER_MIN_RANGE_TILES = 2.0
SKELETON_ARCHER_ATTACK_COOLDOWN_MS = 1400

# Lair settings (release tuning)
# (~2/3 reduction from 6 -> 2)
LAIR_INITIAL_COUNT = 5   # WK60: raised from 4 for more early pressure
LAIR_MIN_DISTANCE_FROM_CASTLE_TILES = 15  # WK60: reduced from 18 (lairs feel closer, more threatening)
LAIR_STASH_GROWTH_PER_SPAWN = 8
ROGUE_LAIR_GOLD_THRESHOLD = 100

# --- WK22 Ursina 3D viewer (directional shadows; lower = faster GPU) ---
# Shadow maps + lit_with_shadows_shader are expensive; default off for playable FPS (WK31).
# Enable for screenshots: KINGDOM_URSINA_DIRECTIONAL_SHADOWS=1 (or set True here for local dev).
URSINA_DIRECTIONAL_SHADOWS = False
_ursina_shadow_env = os.environ.get("KINGDOM_URSINA_DIRECTIONAL_SHADOWS", "").strip().lower()
if _ursina_shadow_env in ("1", "true", "yes", "on"):
    URSINA_DIRECTIONAL_SHADOWS = True
elif _ursina_shadow_env in ("0", "false", "no", "off"):
    URSINA_DIRECTIONAL_SHADOWS = False
# When shadows are on, smaller maps cost less GPU (128–2048). Default a step down from 512 (WK31).
URSINA_SHADOW_MAP_SIZE = 384
_ursina_sm_env = os.environ.get("KINGDOM_URSINA_SHADOW_MAP_SIZE", "").strip()
if _ursina_sm_env.isdigit():
    URSINA_SHADOW_MAP_SIZE = max(128, min(2048, int(_ursina_sm_env)))
# Grass/path scatter: 1 = legacy (every tile), 2 = place small grass doodad on a coarse grid (~4x fewer props).
URSINA_TERRAIN_SCATTER_STRIDE = 2
_ts_env = os.environ.get("KINGDOM_URSINA_TERRAIN_SCATTER_STRIDE", "").strip()
if _ts_env.isdigit():
    URSINA_TERRAIN_SCATTER_STRIDE = max(1, min(8, int(_ts_env)))

# --- WK33 terrain readability tuning (Ursina renderer) ---
# Lift environment scatter (trees/grass/rocks) after the WK32 "dark pass".
URSINA_ENV_SCATTER_BRIGHTNESS = 1.2
try:
    _sb_env = float(os.environ.get("KINGDOM_URSINA_ENV_SCATTER_BRIGHTNESS", "").strip() or "0")
except Exception:
    _sb_env = 0.0
if _sb_env > 0:
    # Clamp to avoid blowing out white materials.
    URSINA_ENV_SCATTER_BRIGHTNESS = max(0.5, min(2.0, _sb_env))

# Explored (SEEN) fog tuning knobs.
URSINA_FOG_SEEN_ALPHA = 0x80  # WK53: ~0.5 alpha (was 0xAA); darker grey mist over explored tiles
_seen_a_env = os.environ.get("KINGDOM_URSINA_FOG_SEEN_ALPHA", "").strip()
try:
    _seen_a_i = int(_seen_a_env) if _seen_a_env else -1
except Exception:
    _seen_a_i = -1
if 0 <= _seen_a_i <= 255:
    URSINA_FOG_SEEN_ALPHA = _seen_a_i

# How much to darken vertical props (trees/rocks/grass clumps) in explored-but-not-visible fog.
URSINA_SEEN_PROP_FOG_MULT = 0.5
try:
    _spf_env = float(os.environ.get("KINGDOM_URSINA_SEEN_PROP_FOG_MULT", "").strip() or "0")
except Exception:
    _spf_env = 0.0
if _spf_env > 0:
    URSINA_SEEN_PROP_FOG_MULT = max(0.1, min(1.0, _spf_env))
# Legacy (WK23): Ursina fog no longer throttles on this — stale 3D fog desynced from minimap/pygame.
URSINA_FOG_MIN_UPDATE_INTERVAL_SEC = 0.12
# Legacy: Ursina HUD GPU upload is now skipped via row-sampled CRC when pixels are unchanged (ursina_app).
URSINA_UI_UPLOAD_INTERVAL_SEC = 0.10
LAIR_BOUNTY_COST = 90

# Bounty reward bands (player-paid; cost == reward). Used by Engine input + early pacing nudge.
BOUNTY_REWARD_LOW = 25
BOUNTY_REWARD_MED = 60
BOUNTY_REWARD_HIGH = 150

# Economy settings
STARTING_GOLD = 2100   # wk15: +40% from 1500 for pacing
TAX_RATE = 0.25      # 25% (hero/lair gold uses this; monster gold increased separately for pacing)
TAX_COLLECTION_INTERVAL_SEC = 45.0  # wk15: collector runs more often (was 60s hardcoded)
# WK61-R6: building types with ``stored_tax_gold`` / ``has_tax_stash_data`` for hold-G overlay.
TAX_STASH_BUILDING_TYPES = frozenset({
    "marketplace",
    "blacksmith",
    "warrior_guild",
    "ranger_guild",
    "rogue_guild",
    "wizard_guild",
    "temple",
    "temple_agrela",
    "temple_dauros",
    "temple_fervus",
    "temple_krypta",
    "temple_krolm",
    "temple_helia",
    "temple_lunord",
    "house",
    "farm",
    "food_stand",
})
# WK61-R6: player buildings without tax stash (overlay should skip / return None).
NON_TAX_STASH_BUILDING_TYPES = frozenset({
    "castle",
    "palace",
    "inn",
    "trading_post",
    "guardhouse",
})
TAX_COLLECTOR_REST_AFTER_RETURN_SEC = 10.0  # Rest at castle 10s after returning a nice haul
TAX_COLLECTOR_NICE_HAUL_GOLD = 20  # Gold deposited >= this triggers the short rest

# LLM settings (env-driven; read at import time)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")  # openai, claude, gemini, grok, mock
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROK_API_KEY = os.getenv("GROK_API_KEY", "")

# LLM decision settings
LLM_DECISION_COOLDOWN = 2000
LLM_TIMEOUT = 5.0
HEALTH_THRESHOLD_FOR_DECISION = 0.5

# wk14 Persona and Presence: conversation mode
CONVERSATION_COOLDOWN_MS = 2000
CONVERSATION_HISTORY_LIMIT = 20
CONVERSATION_TIMEOUT = 8.0

# WK6: Ranger exploration bias toward black fog
RANGER_EXPLORE_BLACK_FOG_BIAS = 0.7  # 0.0-1.0: probability of picking frontier vs random wander (default 0.7 = 70% frontier)
RANGER_FRONTIER_SCAN_RADIUS_TILES = 10  # Maximum radius (in tiles) to scan for black fog frontier tiles
RANGER_FRONTIER_COMMIT_MS = 4000  # Commitment window (sim-time ms) to prevent rapid re-targeting of exploration goals

# --- WK53 Terrain Elevation (Agent 03: terrain_height.py + heightmap generation) ---
# Maximum terrain elevation in world units (Ursina Y).
# WK53 R3: reduced from 8.0 to 5.0 for less extreme peaks after flatness bias.
TERRAIN_HEIGHT_SCALE = 5.0
# Perlin noise frequency for large rolling hills.
TERRAIN_HILL_FREQUENCY = 0.04
# Perlin noise frequency for medium mountain ridges.
TERRAIN_MOUNTAIN_FREQUENCY = 0.10
# Perlin noise frequency for fine rocky detail.
TERRAIN_DETAIL_FREQUENCY = 0.25
# Slope angle (degrees) that counts as a cliff (future: pathfinding impassable).
TERRAIN_CLIFF_THRESHOLD = 45.0
# Fixed Y for water tile surfaces (world units). Water tiles clamp to this height.
TERRAIN_WATER_LEVEL = 1.0
# Radius (in tiles) around castle center that is flattened to a plateau.
TERRAIN_CASTLE_FLAT_RADIUS = 4
# WK53 R3: Flatness exponent — power curve applied to raw [0,1] noise before scaling.
# Values > 1.0 push low noise toward zero (flat). 2.5 gives ~60-70% flat terrain.
TERRAIN_FLATNESS_EXPONENT = 2.5

# ---------- Underground / Vertical Stacking (WK57) ----------
UNDERGROUND_DEPTH = 10.0
UNDERGROUND_CEILING_Y = -2.0
UNDERGROUND_CAVE_NOISE_AMP = 1.5
UNDERGROUND_CAVE_NOISE_FREQ = 0.3
UNDERGROUND_HOLE_RADIUS_TILES = 2.5
UNDERGROUND_HOLE_EDGE_TILES = 1.0
UNDERGROUND_TORCH_COLOR = (1.0, 0.75, 0.4)
UNDERGROUND_TORCH_INTENSITY = 0.8
UNDERGROUND_TORCH_ATTENUATION = (1.0, 0.22, 0.08)
UNDERGROUND_AMBIENT_COLOR = (0.08, 0.06, 0.1)
UNDERGROUND_AMBIENT_ALPHA = 1.0
UNDERGROUND_FOG_DENSITY = 0.015
UNDERGROUND_CAMERA_TRANSITION_SPEED = 8.0
UNDERGROUND_MAX_ENTRANCES_SHADER = 8
UNDERGROUND_HERO_DESCENT_SPEED = 4.0
UNDERGROUND_CHAMBER_SPACING = 3
UNDERGROUND_CORRIDOR_WIDTH = 2
UNDERGROUND_ROCK_TEXTURE = "assets/textures/rock_ground.png"

# WK55: POI Discovery range (tiles). Slightly less than hero vision (7) so the
# hero sees the mystery marker before the POI flips to discovered.
POI_DISCOVERY_RANGE_TILES = 5

# WK6: Bounty targeting in black fog
BOUNTY_BLACK_FOG_DISTANCE_PENALTY = 1.2  # Distance multiplier for bounties in black fog (uncertainty penalty, but never exclusion)

# ---------- WK60: Dev Mode (Feature 9 — Make It Fun) ----------
DEV_MODE = os.getenv("KINGDOM_DEV_MODE", "0") == "1"
if DEV_MODE:
    HERO_HIRE_COST = 0
    STARTING_GOLD = 999_999
    GUILD_MAX_HEROES = 999
    print("*** DEV MODE ACTIVE — free heroes, infinite gold ***")

