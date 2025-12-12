"""
Prompt templates for LLM decision making.
"""

SYSTEM_PROMPT = """You are an AI controlling a hero character in a fantasy kingdom simulation game. 
You must make tactical decisions to help your hero survive, grow stronger, and protect the kingdom.

Your hero has a distinct personality that should influence your decisions:
- "brave and aggressive": Prefers fighting, takes risks, but not suicidal
- "cautious and strategic": Plans ahead, retreats early, values survival
- "greedy but cowardly": Prioritizes gold and items, avoids danger
- "balanced and reliable": Makes sensible decisions, adapts to situations

You will receive context about:
- Your hero's stats, health, gold, and equipment
- Nearby enemies and allies
- Available shop items (if near a marketplace)
- Distances to important locations

You must respond with a JSON object containing your decision. The format is:
{
    "action": "<action_type>",
    "target": "<target_name_or_id>",
    "reasoning": "<brief explanation>"
}

Valid actions:
- "fight": Continue or start fighting (target = enemy type if specific)
- "retreat": Run to safety (castle or marketplace)
- "buy_item": Purchase an item (target = item name)
- "use_potion": Use a healing potion if available
- "explore": Wander and look for enemies or opportunities

IMPORTANT RULES:
1. If health is below 25%, seriously consider retreating or using a potion
2. If you have potions and health is low, use_potion is often better than retreat
3. Don't retreat if you're already near safety and can handle the threat
4. When shopping, prioritize: potions (if hurt) > weapon upgrades > armor upgrades
5. Your personality should influence risk tolerance, not override survival instincts

Respond ONLY with the JSON object, no other text."""


DECISION_PROMPT = """Current Situation for {hero_name}:

{context_summary}

Based on your personality ({personality}) and the current situation, what action should you take?

Remember:
- You have {potions} potion(s) available
- Your health is at {health_percent}%
- {combat_note}
- {shop_note}

Respond with a JSON decision:"""


def build_decision_prompt(context: dict, summary: str) -> str:
    """Build the decision prompt from context."""
    hero = context["hero"]
    sit = context["situation"]
    
    # Combat note
    if sit["in_combat"]:
        enemies = context["nearby_enemies"]
        if sit["outnumbered"]:
            combat_note = f"You are in combat and OUTNUMBERED ({len(enemies)} enemies)"
        else:
            combat_note = f"You are in combat with {len(enemies)} enemy/enemies nearby"
    else:
        combat_note = "No immediate combat threat"
    
    # Shop note
    if sit["can_shop"]:
        affordable = [i["name"] for i in context["shop_items"] if i["can_afford"]]
        if affordable:
            shop_note = f"You can afford: {', '.join(affordable[:3])}"
        else:
            shop_note = "Near shop but can't afford anything"
    else:
        shop_note = "Not near a marketplace"
    
    return DECISION_PROMPT.format(
        hero_name=hero["name"],
        context_summary=summary,
        personality=context["personality"],
        potions=context["inventory"]["potions"],
        health_percent=hero["health_percent"],
        combat_note=combat_note,
        shop_note=shop_note,
    )


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
    }
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
    
    # Low health in combat
    if sit["low_health"] and sit["in_combat"]:
        if inv["potions"] > 0:
            return FALLBACK_DECISIONS["critical_health_with_potion"]
        else:
            return FALLBACK_DECISIONS["low_health_in_combat"]
    
    # Can shop and needs potions
    if sit["can_shop"] and sit["low_health"] and inv["potions"] < 2:
        for item in context["shop_items"]:
            if item["type"] == "potion" and item["can_afford"]:
                return FALLBACK_DECISIONS["can_shop_needs_potion"]
    
    # Enemies nearby and healthy
    if sit["enemies_nearby"] and not sit["low_health"]:
        return FALLBACK_DECISIONS["enemies_nearby"]
    
    # Default: explore
    return FALLBACK_DECISIONS["idle_default"]

