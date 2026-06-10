"""Autonomous-decision mock responder (WK50 prompts). Extracted WK81 from
ai/providers/mock_provider.py via pure move."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai.providers.mock_provider import MockProvider


def mock_autonomous_decision(provider: "MockProvider", user_prompt: str) -> str:
    """Deterministic JSON for WK50 autonomous prompts; only uses allowed_actions."""
    cut = user_prompt.find("\n\nRespond")
    raw = user_prompt[:cut].strip() if cut > 0 else user_prompt.strip()
    try:
        blob = json.loads(raw)
    except json.JSONDecodeError:
        return json.dumps(
            {
                "action": "explore",
                "target": "",
                "reasoning": "mock autonomous parse fallback",
            }
        )
    ctx = blob.get("context", blob)
    allowed = blob.get("allowed_actions") or ctx.get("allowed_actions") or []
    allowed_set = {str(a).strip().lower() for a in allowed if str(a).strip()}
    moment = ctx.get("moment") or {}
    mtype = str(moment.get("type") or "").lower()
    prof = ctx.get("hero_profile") or {}
    vit = prof.get("vitals") or {}
    try:
        hp_frac = float(vit.get("health_percent", 1.0))
    except (TypeError, ValueError):
        hp_frac = 1.0
    inv = prof.get("inventory") or {}
    try:
        pots = int(inv.get("potions", 0))
    except (TypeError, ValueError):
        pots = 0

    def pick(*preferences: str) -> str:
        for p in preferences:
            if p in allowed_set:
                return p
        return next(iter(allowed_set)) if allowed_set else "explore"

    action = "explore"
    target = ""
    if mtype == "quest_offer":
        # WK126-T6 quest-offer responder: deterministic, seeded-RNG-free rule so
        # headless tests can force both verdicts by crafting the reward. The
        # carriers come from the quest_offer.decision_rule contract
        # (ai.decision_moments): 'explore' = accept_quest, 'retreat' =
        # decline_quest. Rule: a mock hero takes any decently funded quest
        # (reward >= 50g) and turns its nose up at miserly offers below that.
        qoffer = ctx.get("quest_offer") or {}
        try:
            reward = int(qoffer.get("reward_gold", 0) or 0)
        except (TypeError, ValueError):
            reward = 0
        if reward >= 50:
            action = pick("explore", "fight")
            reasoning_tag = "accept_quest"
        else:
            action = pick("retreat", "leave_building")
            reasoning_tag = "decline_quest"
        out = {
            "action": action,
            "target": "",
            "reasoning": f"mock quest_offer ({reasoning_tag}, reward={reward})",
            "confidence": 0.8,
            "memory_used": [],
            "personality_influence": "mock",
        }
        return json.dumps(out)
    if mtype == "low_health_combat":
        action = pick("use_potion", "retreat", "fight")
        if action == "retreat":
            target = "castle"
    elif mtype == "post_combat_injured":
        if hp_frac < 0.26:
            action = pick("use_potion", "retreat", "move_to")
        else:
            action = pick("retreat", "move_to", "use_potion", "explore")
        if action == "retreat":
            target = "castle"
        elif action == "move_to":
            target = "castle"
    elif mtype == "rested_and_ready":
        action = pick("leave_building", "explore", "move_to", "buy_item")
        if action == "move_to":
            target = "castle"
    elif mtype == "shopping_opportunity":
        action = pick("buy_item", "leave_building", "move_to", "explore")
        if action == "buy_item":
            target = "Health Potion"
    else:
        action = pick("explore", "retreat", "fight")

    if action == "use_potion" and pots <= 0:
        action = pick("retreat", "fight", "explore")
        if action == "retreat":
            target = "castle"

    if action not in allowed_set and allowed_set:
        action = sorted(allowed_set)[0]
        target = "" if action != "buy_item" else "Health Potion"
        if action == "move_to" and not target:
            target = "castle"

    out = {
        "action": action,
        "target": target,
        "reasoning": f"mock autonomous ({mtype or 'unknown'})",
        "confidence": 0.75,
        "memory_used": [],
        "personality_influence": "mock",
    }
    return json.dumps(out)
