"""
Prompt templates for LLM decision making.
"""

VALID_ACTIONS = {
    "fight",
    "retreat",
    "buy_item",
    "use_potion",
    "explore",
    "leave_building",
    "move_to",
}

# WK18: Tool-use schema for Obey/Defy and physical actions (LLM agency).
TOOL_ACTIONS = {
    "leave_building",
    "move_to",
    "fight",
    "retreat",
    "buy_item",
    "use_potion",
    "explore",
}
OBEY_DEFY_VALUES = ("Obey", "Defy")


# Fallback decisions for when LLM is unavailable or times out
FALLBACK_DECISIONS = {
    "critical_health_with_potion": {
        "action": "use_potion",
        "target": "",
        "reasoning": "Fallback: Critical health, using potion"
    },
    "critical_health_no_potion": {
        "action": "retreat",
        "target": "castle",
        "reasoning": "Fallback: Critical health, retreating"
    },
    "low_health_in_combat": {
        "action": "retreat",
        "target": "marketplace",
        "reasoning": "Fallback: Low health in combat, retreating"
    },
    "can_shop_needs_potion": {
        "action": "buy_item",
        "target": "Health Potion",
        "reasoning": "Fallback: Low on health, buying potion"
    },
    "idle_default": {
        "action": "explore",
        "target": "",
        "reasoning": "Fallback: Nothing to do, exploring"
    },
    "enemies_nearby": {
        "action": "fight",
        "target": "",
        "reasoning": "Fallback: Enemies nearby, engaging"
    },
    "hunger_seek_meal": {
        "action": "seek_meal",
        "target": "food_stand",
        "reasoning": "Fallback: Hunger urgent, seeking meal at food stand",
    },
}


def get_fallback_decision(context: dict) -> dict:
    """Get a fallback decision based on context when LLM is unavailable."""
    sit = context["situation"]
    hero = context["hero"]
    inv = context["inventory"]
    
    # Critical health
    if sit["critical_health"]:
        if inv["potions"] > 0:
            return FALLBACK_DECISIONS["critical_health_with_potion"]
        else:
            return FALLBACK_DECISIONS["critical_health_no_potion"]
    
    # V1.3 Extension: Prefer using potions before retreating
    # Low health in combat - use potion if available, only retreat if no potions
    if sit["low_health"] and sit["in_combat"]:
        if inv["potions"] > 0:
            # Use potion instead of retreating when available
            return FALLBACK_DECISIONS["critical_health_with_potion"]
        else:
            return FALLBACK_DECISIONS["low_health_in_combat"]
    
    # WK61-R11: hungry heroes seek food before discretionary shop/explore.
    if sit.get("hunger_urgent") and sit.get("can_afford_meal") and not sit["critical_health"]:
        return FALLBACK_DECISIONS["hunger_seek_meal"]

    # V1.3 Extension: More aggressive potion buying
    # Can shop and needs potions (lowered threshold from <2 to <3, and removed low_health requirement)
    if sit["can_shop"] and inv["potions"] < 3:
        for item in context["shop_items"]:
            if item["type"] == "potion" and item["can_afford"]:
                return FALLBACK_DECISIONS["can_shop_needs_potion"]
    
    # Enemies nearby and healthy
    if sit["enemies_nearby"] and not sit["low_health"]:
        return FALLBACK_DECISIONS["enemies_nearby"]
    
    # Default: explore
    return FALLBACK_DECISIONS["idle_default"]

