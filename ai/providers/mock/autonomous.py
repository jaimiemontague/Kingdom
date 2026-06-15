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
    if mtype == "quest_chain":
        qchain = ctx.get("quest_chain") or ((ctx.get("current_situation") or {}).get("quest_chains") or [{}])[0]
        status = str(qchain.get("status") or "").lower()
        try:
            reward = int(qchain.get("reward_gold", 0) or 0)
        except (TypeError, ValueError):
            reward = 0
        sit = (ctx.get("current_situation") or {}).get("situation") or ctx.get("situation") or {}
        forced_retreat = bool(
            sit.get("critical_health")
            or (
                sit.get("low_health")
                and pots <= 0
                and (sit.get("enemies_nearby") or not sit.get("near_safety"))
            )
        )
        need_supplies = pots <= 0
        boss_name = str(qchain.get("known_boss_name", "") or "")
        elite_name = str(qchain.get("elite_target_name", "") or "")
        shop_items = list(((ctx.get("current_situation") or {}).get("shop_items") or []))
        if forced_retreat:
            action = pick("retreat_to_heal")
            target = "castle"
            reasoning_tag = "retreat_to_heal"
        elif status == "active":
            if need_supplies:
                action = pick("prepare_supplies", "continue_phase", "retreat_to_heal")
                reasoning_tag = "prepare_supplies"
                if action == "continue_phase":
                    reasoning_tag = "continue_phase"
                elif action == "retreat_to_heal":
                    reasoning_tag = "retreat_to_heal"
                if action == "prepare_supplies":
                    target = "Health Potion"
                    for item in shop_items:
                        if str(item.get("type", "")).strip().lower() == "potion" and bool(item.get("can_afford", False)):
                            target = "Health Potion"
                            break
                    if not any(str(item.get("type", "")).strip().lower() == "potion" for item in shop_items):
                        target = "blacksmith"
                elif action == "retreat_to_heal":
                    target = "castle"
                else:
                    target = str(qchain.get("target_id") or qchain.get("chain_id") or "")
            else:
                action = pick("continue_phase", "prepare_supplies", "retreat_to_heal")
                target = str(qchain.get("target_id") or qchain.get("chain_id") or "")
                reasoning_tag = "continue_phase" if action == "continue_phase" else "prepare_supplies" if action == "prepare_supplies" else "retreat_to_heal"
                if action == "prepare_supplies":
                    target = "Health Potion"
                    if not any(str(item.get("type", "")).strip().lower() == "potion" for item in shop_items):
                        target = "blacksmith"
                if action == "retreat_to_heal":
                    target = "castle"
        else:
            if reward >= 50:
                action = pick("accept_chain", "decline_chain")
                reasoning_tag = "accept_chain"
            else:
                action = pick("decline_chain", "accept_chain")
                reasoning_tag = "decline_chain"
            target = str(qchain.get("chain_id") or "")
        out = {
            "action": action,
            "target": target,
            "reasoning": (
                f"mock quest_chain ({reasoning_tag}, status={status or 'unknown'}"
                + (f", boss={boss_name}" if boss_name else "")
                + (f", elite={elite_name}" if elite_name else "")
                + ")"
            ),
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
