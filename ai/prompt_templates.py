"""
Prompt templates for LLM decision making.
"""

from ai.vocab import ToolAction

# WK110: derived from the canonical ``ai.vocab.ToolAction`` enum. ``VALID_ACTIONS`` and
# ``TOOL_ACTIONS`` are both sets of the same seven tool-action strings (byte-identical
# membership to the pre-WK110 literals); the set comprehension reproduces that exactly.
VALID_ACTIONS = {a.value for a in ToolAction}

# WK18: Tool-use schema for Obey/Defy and physical actions (LLM agency).
TOOL_ACTIONS = {a.value for a in ToolAction}
OBEY_DEFY_VALUES = ("Obey", "Defy")

# WK134: actions valid ONLY on the autonomous decision-moment path (offered via
# DecisionMoment.allowed_actions, e.g. IDLE_SEEKING_ACTIVITY's accept_bounty).
# Deliberately NOT added to ToolAction/TOOL_ACTIONS: the direct-prompt (chat)
# validator must keep rejecting them — the Sovereign cannot order a bounty
# accept by chat — while ai.llm_brain._parse_response must let them through so
# decision_output_validator can check them against the moment's allowlist.
AUTONOMOUS_ONLY_ACTIONS = frozenset({"accept_bounty"})


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
    # WK127-T2: threshold re-aligned to <2 — do_shopping only buys at potions<2,
    # so <3 sent heroes on guaranteed zero-purchase trips (marketplace orbit).
    if sit["can_shop"] and inv["potions"] < 2:
        for item in context["shop_items"]:
            if item["type"] == "potion" and item["can_afford"]:
                return FALLBACK_DECISIONS["can_shop_needs_potion"]
    
    # Enemies nearby and healthy
    if sit["enemies_nearby"] and not sit["low_health"]:
        return FALLBACK_DECISIONS["enemies_nearby"]
    
    # Default: explore
    return FALLBACK_DECISIONS["idle_default"]

