"""
Prompt templates for LLM decision making.
"""

from ai.vocab import ToolAction
from ai.quest_chain_context import quest_chain_status_allowed_actions

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
AUTONOMOUS_ONLY_ACTIONS = frozenset({
    "accept_bounty",
    "accept_chain",
    "decline_chain",
    "continue_phase",
    "prepare_supplies",
    "retreat_to_heal",
})


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
    "quest_chain_continue_phase": {
        "action": "continue_phase",
        "target": "",
        "reasoning": "Fallback: continue the current quest-chain phase",
    },
    "quest_chain_prepare_supplies": {
        "action": "prepare_supplies",
        "target": "Health Potion",
        "reasoning": "Fallback: quest chain needs supplies before pressing on",
    },
    "quest_chain_retreat_to_heal": {
        "action": "retreat_to_heal",
        "target": "castle",
        "reasoning": "Fallback: quest chain is too risky right now, retreating to heal",
    },
    "quest_chain_accept": {
        "action": "accept_chain",
        "target": "",
        "reasoning": "Fallback: accepting the offered quest chain",
    },
    "quest_chain_decline": {
        "action": "decline_chain",
        "target": "",
        "reasoning": "Fallback: declining the offered quest chain",
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

    quest_chains = list(context.get("quest_chains") or [])
    if quest_chains:
        focus = quest_chains[0]
        status = str(focus.get("status", "") or "").lower()
        chain_target = str(
            focus.get("target_id")
            or focus.get("target_name")
            or focus.get("current_phase_id")
            or ""
        )
        chain_id = str(focus.get("chain_id", "") or "")
        boss_name = str(focus.get("known_boss_name", "") or "")
        elite_name = str(focus.get("elite_target_name", "") or "")
        forced_retreat = bool(
            sit.get("critical_health")
            or (
                sit.get("low_health")
                and int(inv.get("potions", 0) or 0) <= 0
                and (sit.get("enemies_nearby") or not sit.get("near_safety"))
            )
        )
        allowed = quest_chain_status_allowed_actions(
            focus,
            survival_forced=forced_retreat,
            needs_supplies=int(inv.get("potions", 0) or 0) <= 0,
        )
        if "retreat_to_heal" in allowed and forced_retreat:
            decision = dict(FALLBACK_DECISIONS["quest_chain_retreat_to_heal"])
            decision["target"] = "castle"
            return decision
        if (
            status == "active"
            and "prepare_supplies" in allowed
            and int(inv.get("potions", 0) or 0) <= 0
        ):
            decision = dict(FALLBACK_DECISIONS["quest_chain_prepare_supplies"])
            potion_available = False
            for item in list(context.get("shop_items") or []) + list(context.get("market_catalog_items") or []):
                if str(item.get("type", "")).strip().lower() == "potion" and bool(item.get("can_afford", False)):
                    potion_available = True
                    break
            decision["target"] = "Health Potion" if potion_available else "blacksmith"
            if boss_name:
                decision["reasoning"] = f"Fallback: resupply before facing {boss_name}"
            elif elite_name:
                decision["reasoning"] = f"Fallback: resupply before intercepting {elite_name}"
            return decision
        if status == "active" and "continue_phase" in allowed:
            decision = dict(FALLBACK_DECISIONS["quest_chain_continue_phase"])
            decision["target"] = chain_target
            decision["reasoning"] = (
                f"Fallback: continue quest chain {focus.get('name', chain_id)}"
            )
            return decision
        if status == "offered" and "accept_chain" in allowed:
            reward = int(focus.get("reward_gold", 0) or 0)
            key = "quest_chain_accept" if reward >= 50 else "quest_chain_decline"
            decision = dict(FALLBACK_DECISIONS[key])
            decision["target"] = chain_id
            return decision

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

