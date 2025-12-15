# Kingdom Sim

A Majesty-inspired fantasy kingdom simulation game where heroes are controlled by AI powered by Large Language Models (LLMs).

## Prototype Version

This repository is currently stamped as **Prototype v1.0.0** (see `config.py`).

## Overview

In this game, you play as a ruler who builds a kingdom and hires heroes to defend it. Unlike traditional RTS games, you don't directly control the heroes - instead, they make their own decisions based on their AI personalities. The twist? Important decisions (when to retreat, what to buy, which bounties to pursue) are made by calling LLM APIs like OpenAI, Claude, Gemini, or Grok.

## Features

- **Indirect Control**: Place buildings and bounties, but heroes decide their own actions
- **LLM-Powered Decisions**: Heroes consult AI for strategic choices
- **Multiple LLM Providers**: Support for OpenAI, Claude, Gemini, Grok, or mock AI
- **Hero Personalities**: Each hero has a unique personality affecting decisions
- **Economic System**: Build, hire, and tax your way to kingdom prosperity
- **Wave-Based Combat**: Defend against goblin invasions
- **Peasants + Construction**: Newly placed buildings start at 1 HP and must be built; peasants also repair and prioritize castle repairs

## Requirements

- Python 3.8+
- Pygame 2.5+
- (Optional) API keys for LLM providers

## Installation

1. Clone or download this repository

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. (Optional) Set up your LLM API key:
   - Create a `.env` file in the project root
   - Add your API key:
```
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-key-here
```

## Running the Game

```bash
# Run with mock AI (no API key needed)
python main.py

# Run with OpenAI
python main.py --provider openai

# Run with Claude
python main.py --provider claude

# Run with Gemini
python main.py --provider gemini

# Run with Grok
python main.py --provider grok

# Run without LLM (basic AI only)
python main.py --no-llm

# (Dev) Headless observer runner
python tools/observe_sync.py --seconds 20 --heroes 10 --seed 3 --log-every 120 --realtime
```

## Controls

| Key | Action |
|-----|--------|
| 1 | Build Warrior Guild ($150) |
| 2 | Build Marketplace ($100) |
| H | Hire a Hero ($50) |
| B | Place a Bounty ($50) |
| Left Click | Select hero / Place building |
| Right Click | Command selected hero to move |
| P | Use potion (selected hero) |
| Space/ESC | Pause game |
| F1 | Toggle debug panel |
| Mouse Edge | Scroll camera |

## Gameplay

1. **Start**: Your castle is automatically placed in the center
2. **Build**: Press 1 or 2 to select a building, then click to place it
3. **Hire**: Build a Warrior Guild, then press H to hire heroes
4. **Defend**: Heroes will automatically fight goblins that spawn
5. **Economy**: Heroes earn gold from kills, spend at marketplace (you get 20% tax)
6. **Bounties**: Press B to place bounty flags that attract heroes

## LLM Integration

The game uses LLMs for "important" hero decisions:

- **Retreat**: When health is low, should the hero run or fight on?
- **Shopping**: What should the hero buy at the marketplace?
- **Risk Assessment**: Is this bounty worth pursuing given the danger?

The LLM receives context about the hero's stats, nearby enemies, inventory, and personality, then returns a JSON decision that the game executes.

### Context Example
```json
{
    "hero": {"name": "Brock", "class": "warrior", "hp": 35, "max_hp": 100},
    "inventory": {"weapon": "Iron Sword", "potions": 1},
    "nearby_enemies": [{"type": "goblin", "distance": 3}],
    "personality": "brave and aggressive"
}
```

### Response Example
```json
{
    "action": "use_potion",
    "target": "",
    "reasoning": "Health is critical at 35%, using potion to survive"
}
```

## Project Structure

```
kingdom/
├── main.py              # Entry point
├── config.py            # Game configuration
├── requirements.txt     # Python dependencies
├── game/
│   ├── engine.py        # Main game loop
│   ├── world.py         # Tile map system
│   ├── entities/        # Hero, Enemy, Building classes
│   ├── systems/         # Combat, Economy, Pathfinding
│   └── ui/              # HUD, Menus, Debug panel
├── ai/
│   ├── basic_ai.py      # State machine AI
│   ├── llm_brain.py     # LLM coordinator
│   ├── context_builder.py
│   ├── prompt_templates.py
│   └── providers/       # OpenAI, Claude, Gemini, Grok
└── assets/              # Sprites and maps (placeholder)
```

## Customization

### Adding New Hero Classes

1. Create a new class in `game/entities/hero.py`
2. Add personality traits and stats
3. Update the Warrior Guild to allow hiring different types

### Changing LLM Behavior

Edit `ai/prompt_templates.py` to modify the system prompt and decision format.

### Adjusting Difficulty

Edit `config.py` to change:
- `GOBLIN_SPAWN_INTERVAL`: Time between enemy waves
- `STARTING_GOLD`: Initial player gold
- `HERO_HIRE_COST`: Cost to hire heroes
- `HEALTH_THRESHOLD_FOR_DECISION`: When heroes consult the LLM

## Credits

Inspired by "Majesty: The Fantasy Kingdom Sim" by Cyberlore Studios.

## License

MIT License - Feel free to modify and distribute.

