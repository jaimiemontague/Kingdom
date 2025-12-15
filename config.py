"""
Configuration settings for the Kingdom Sim game.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Window settings
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
FPS = 60
PROTOTYPE_VERSION = "1.0.0"
GAME_TITLE = f"Kingdom Sim (Prototype v{PROTOTYPE_VERSION})"

# Tile settings
TILE_SIZE = 32
MAP_WIDTH = 40  # tiles
MAP_HEIGHT = 22  # tiles

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
    "marketplace": 100,
}

BUILDING_SIZES = {
    "castle": (3, 3),
    "warrior_guild": (2, 2),
    "marketplace": (2, 2),
}

BUILDING_COLORS = {
    "castle": (139, 69, 19),
    "warrior_guild": (178, 34, 34),
    "marketplace": (218, 165, 32),
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

# Economy settings
STARTING_GOLD = 500
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

