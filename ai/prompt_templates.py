"""
Prompt templates for LLM decision making.
"""

VALID_ACTIONS = {
    "fight",
    "retreat",
    "buy_item",
    "use_potion",
    "explore",
}

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

# wk14 Persona and Presence: conversational mode (in-building chat with Sovereign)
CONVERSATION_SYSTEM_PROMPT = """You are {hero_name}, a level {level} {hero_class} in a fantasy kingdom.
Personality: {personality}.

The Sovereign (the player who rules this kingdom) is speaking with you directly.
Respond in character. You are loyal to the Sovereign but have your own personality.
Keep responses to 2-3 sentences. Be colorful and in-world.

Current location: {location}. {building_context}
{occupants_note}
"""

CONVERSATION_USER_PROMPT = """Recent adventures:
{recent_decisions}

Conversation so far:
{conversation_history}

The Sovereign says: "{player_message}"

Respond in character as {hero_name}:"""


DECISION_PROMPT = """Current Situation for {hero_name}:

{context_summary}

Based on your personality ({personality}) and the current situation, what action should you take?

Remember:
- You have {potions} potion(s) available
- Your health is at {health_percent}%
- {combat_note}
- {shop_note}

Respond with a JSON decision:"""


def build_conversation_prompt(
    hero_context: dict,
    conversation_history: list,
    player_message: str,
) -> tuple[str, str]:
    """Build (system_prompt, user_prompt) for conversational LLM mode. Returns (system_prompt, user_prompt)."""
    hero = hero_context["hero"]
    location = hero_context.get("current_location", "outdoors")
    building_context = hero_context.get("building_context", "") or ""
    occupants = hero_context.get("building_occupants", []) or []
    occupants_note = f"Others here: {', '.join(occupants)}." if occupants else "You are alone here."

    system_prompt = CONVERSATION_SYSTEM_PROMPT.format(
        hero_name=hero["name"],
        level=hero["level"],
        hero_class=hero["class"],
        personality=hero_context.get("personality", "balanced and reliable"),
        location=location,
        building_context=building_context,
        occupants_note=occupants_note,
    )

    recent_decisions = ""
    if hero_context.get("hero") and hasattr(hero_context.get("hero"), "last_decision"):
        # If context was built from a hero object we might have last_decision; here we have dict.
        pass
    last_dec = hero_context.get("last_decision")
    if last_dec and isinstance(last_dec, dict):
        action = last_dec.get("action", "")
        reason = last_dec.get("reasoning", last_dec.get("reason", ""))
        recent_decisions = f"Last action: {action}. {reason}" if action else "No recent action."
    else:
        recent_decisions = "No recent action."

    conv_lines = []
    for msg in (conversation_history or [])[-10:]:
        role = msg.get("role", "")
        text = msg.get("text", "")
        if role == "player":
            conv_lines.append(f"Sovereign: {text}")
        else:
            conv_lines.append(f"{hero['name']}: {text}")
    conversation_history_str = "\n".join(conv_lines) if conv_lines else "(No messages yet.)"

    user_prompt = CONVERSATION_USER_PROMPT.format(
        recent_decisions=recent_decisions,
        conversation_history=conversation_history_str,
        player_message=player_message.strip() or "(nothing)",
        hero_name=hero["name"],
    )
    return (system_prompt, user_prompt)


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
    
    # V1.3 Extension: Prefer using potions before retreating
    # Low health in combat - use potion if available, only retreat if no potions
    if sit["low_health"] and sit["in_combat"]:
        if inv["potions"] > 0:
            # Use potion instead of retreating when available
            return FALLBACK_DECISIONS["critical_health_with_potion"]
        else:
            return FALLBACK_DECISIONS["low_health_in_combat"]
    
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

