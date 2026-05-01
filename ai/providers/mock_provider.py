"""
Mock LLM provider for testing without API keys.
Uses rule-based decisions that mimic LLM behavior.
"""
import json
import re

from game.sim.determinism import get_rng

from ai.direct_prompt_validator import validate_direct_prompt_output
from ai.prompt_packs import DIRECT_PROMPT_MARK

from .base import BaseLLMProvider

# Deterministic RNG stream for mock decisions (stable across runs with the same seed).
_MOCK_RNG = get_rng("mock_provider")


def _norm_msg(s: str) -> str:
    return str(s or "").strip().lower()


def _hero_ctx_from_prompt_blob(blob: dict) -> dict:
    """Rebuild hero_context shape expected by validate_direct_prompt_output."""
    return {
        "hero": blob.get("hero") or {},
        "situation": blob.get("situation") or {},
        "inventory": blob.get("inventory") or {},
        "current_location": blob.get("current_location", "outdoors"),
        "distances": blob.get("distances") or {},
        "known_places_llm": list(blob.get("known_places_llm") or []),
        "shop_items": list(blob.get("shop_items") or []),
        "market_catalog_items": list(blob.get("market_catalog_items") or []),
        "hero_home_place_id": str(blob.get("hero_home_place_id") or ""),
    }


def _emit_validated_direct(raw: dict, blob: dict) -> str:
    ctx = _hero_ctx_from_prompt_blob(blob)
    msg = str(blob.get("player_message") or "")
    return json.dumps(validate_direct_prompt_output(raw, ctx, msg))


class MockProvider(BaseLLMProvider):
    """
    Mock provider that simulates LLM decisions using rules.
    Useful for testing and development without API costs.
    """
    
    @property
    def name(self) -> str:
        return "mock"
    
    def complete(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        timeout: float = 5.0
    ) -> str:
        """Generate mock response: conversation (in-character text) or decision (JSON)."""
        if DIRECT_PROMPT_MARK in system_prompt:
            return self._mock_direct_prompt(user_prompt)
        # wk14: Detect conversation mode (no JSON in system prompt, or "Sovereign says" in user prompt)
        is_conversation = (
            "JSON" not in system_prompt
            or "Sovereign says" in user_prompt
        )
        if is_conversation:
            return self._mock_conversation_response(system_prompt, user_prompt)
        if "Choose the best next action for this decision moment" in user_prompt:
            return self._mock_autonomous_decision(user_prompt)
        prompt_lower = user_prompt.lower()
        
        # Parse health percentage from prompt
        health_pct = 100
        if "health:" in prompt_lower or "health is at" in prompt_lower:
            try:
                # Try to find health percentage
                import re
                match = re.search(r'(\d+)%', prompt_lower)
                if match:
                    health_pct = int(match.group(1))
            except:
                pass
        
        # Parse personality
        personality = "balanced"
        if "brave and aggressive" in prompt_lower:
            personality = "brave"
        elif "cautious and strategic" in prompt_lower:
            personality = "cautious"
        elif "greedy but cowardly" in prompt_lower:
            personality = "greedy"
        
        # Check situation flags
        in_combat = "in combat" in prompt_lower
        has_potions = "potion(s) available" not in prompt_lower or "0 potion" not in prompt_lower
        can_shop = "can afford" in prompt_lower
        low_health = health_pct < 50
        critical_health = health_pct < 25
        outnumbered = "outnumbered" in prompt_lower
        
        # Decision logic based on personality and situation
        decision = self._make_decision(
            personality, health_pct, in_combat, has_potions,
            can_shop, low_health, critical_health, outnumbered
        )
        
        return json.dumps(decision)

    def _mock_autonomous_decision(self, user_prompt: str) -> str:
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

    def _mock_direct_prompt(self, user_prompt: str) -> str:
        """Deterministic WK50 Phase 2B JSON; mirrors common player phrases from sprint plan."""
        cut = user_prompt.find("\n\nRespond")
        raw = user_prompt[:cut].strip() if cut > 0 else user_prompt.strip()
        try:
            blob = json.loads(raw)
        except json.JSONDecodeError:
            blob = {}
        msg = _norm_msg(blob.get("player_message", ""))
        places = list(blob.get("known_places_llm") or [])

        def find_place(*types: str) -> dict | None:
            tl = {t.lower() for t in types}
            for p in places:
                if str(p.get("place_type", "")).lower() in tl:
                    return p
            return None

        def base(**kwargs: object) -> dict:
            out = {
                "spoken_response": str(kwargs.get("spoken_response", "")),
                "interpreted_intent": str(kwargs.get("interpreted_intent", "no_action_chat_only")),
                "tool_action": kwargs.get("tool_action"),
                "target_kind": str(kwargs.get("target_kind", "")),
                "target_id": str(kwargs.get("target_id", "")),
                "target_description": str(kwargs.get("target_description", "")),
                "obey_defy": str(kwargs.get("obey_defy", "Obey")),
                "refusal_reason": str(kwargs.get("refusal_reason", "")),
                "safety_assessment": str(kwargs.get("safety_assessment", "safe")),
                "confidence": float(kwargs.get("confidence", 0.88)),
            }
            return out

        if re.search(r"attack\b.*\blair\b|\blair\b.*attack", msg) or "attack the lair" in msg:
            return _emit_validated_direct(
                base(
                    spoken_response="Sovereign, I am not commissioned to storm lairs by chat—let the realm place a bounty if we must strike.",
                    interpreted_intent="no_action_chat_only",
                    tool_action=None,
                    safety_assessment="deferred",
                    refusal_reason="mvp_combat_deferred",
                    obey_defy="Defy",
                ),
                blob,
            )

        if "how are you" in msg or "how r you" in msg:
            return _emit_validated_direct(
                base(
                    spoken_response="I stand ready, my liege—wounded or whole, I serve the crown.",
                    interpreted_intent="status_report",
                    tool_action=None,
                    safety_assessment="safe",
                ),
                blob,
            )

        if "go home" in msg or "return home" in msg or "head home" in msg:
            home_bt = _norm_msg((blob.get("hero") or {}).get("home_building_type", ""))
            home = find_place(home_bt) if home_bt else None
            if home is None:
                home = find_place("castle", "inn", "warrior_guild", "ranger_guild", "rogue_guild", "wizard_guild", "temple")
            tid = str(home.get("place_id", "")) if home else ""
            tdesc = str(home.get("display_name", "")) if home else ""
            return _emit_validated_direct(
                base(
                    spoken_response="Aye, Sovereign—I will make for hearth and shelter."
                    if home
                    else "",
                    interpreted_intent="return_home",
                    tool_action="move_to" if home else None,
                    target_kind="known_place" if home else "",
                    target_id=tid,
                    target_description=tdesc or ("Castle" if home else ""),
                ),
                blob,
            )

        if "heal" in msg and "potion" not in msg:
            return _emit_validated_direct(
                base(
                    spoken_response="I'll bind my wounds and find succor—potions or hearth.",
                    interpreted_intent="seek_healing",
                    tool_action="use_potion",
                    target_kind="none",
                    safety_assessment="safe",
                ),
                blob,
            )

        if "buy" in msg and "potion" in msg:
            mart = find_place("marketplace")
            tid = str(mart.get("place_id", "")) if mart else ""
            tdesc = str(mart.get("display_name", "Marketplace")) if mart else ""
            return _emit_validated_direct(
                base(
                    spoken_response=""
                    if not mart
                    else (
                        "The market is known—I will march there and buy what draughts I can afford."
                        if not bool((blob.get("situation") or {}).get("can_shop"))
                        else ""
                    ),
                    interpreted_intent="buy_potions",
                    tool_action="move_to" if mart else None,
                    target_kind="known_place" if mart else "",
                    target_id=tid,
                    target_description=tdesc,
                ),
                blob,
            )

        if re.search(r"(?<![a-z0-9_])inn(?![a-z0-9_])", msg):
            inn = find_place("inn")
            if inn:
                return _emit_validated_direct(
                    base(
                        spoken_response="The inn it is—I know the road.",
                        interpreted_intent="go_to_known_place",
                        tool_action="move_to",
                        target_kind="known_place",
                        target_id=str(inn.get("place_id", "")),
                        target_description=str(inn.get("display_name", "Inn")),
                    ),
                    blob,
                )
            return _emit_validated_direct(
                base(
                    spoken_response="I don't recall an inn yet, Sovereign—I'll need to discover one first.",
                    interpreted_intent="go_to_known_place",
                    tool_action=None,
                    refusal_reason="unknown_place",
                    safety_assessment="unknown_target",
                    obey_defy="Defy",
                ),
                blob,
            )

        if "explore" in msg and any(d in msg for d in ("east", "west", "north", "south")):
            return _emit_validated_direct(
                base(
                    spoken_response="I'll scout that bearing and report what I find.",
                    interpreted_intent="explore_direction",
                    tool_action="explore",
                    target_kind="direction",
                    target_description="",
                ),
                blob,
            )

        if "rest" in msg and "heal" in msg:
            return _emit_validated_direct(
                base(
                    spoken_response="I'll rest until the color returns to my cheeks.",
                    interpreted_intent="rest_until_healed",
                    tool_action=None,
                ),
                blob,
            )

        hero_name = str((blob.get("hero") or {}).get("name", "hero"))
        return _emit_validated_direct(
            base(
                spoken_response=f"I hear you, Sovereign—say again if you need a march, a market-run, or a reckoning of my wounds. ({hero_name})",
                interpreted_intent="no_action_chat_only",
                tool_action=None,
            ),
            blob,
        )

    def _make_decision(
        self, 
        personality: str,
        health_pct: int,
        in_combat: bool,
        has_potions: bool,
        can_shop: bool,
        low_health: bool,
        critical_health: bool,
        outnumbered: bool
    ) -> dict:
        """Make a decision based on the situation."""
        
        # Critical health - everyone considers survival
        if critical_health:
            if has_potions:
                return {
                    "action": "use_potion",
                    "target": "",
                    "reasoning": f"Critical health at {health_pct}%, using potion for survival"
                }
            else:
                return {
                    "action": "retreat",
                    "target": "castle",
                    "reasoning": f"Critical health at {health_pct}% and no potions, must retreat"
                }
        
        # Low health handling varies by personality
        if low_health:
            if personality == "brave":
                # Brave heroes fight longer
                if has_potions and health_pct < 30:
                    return {
                        "action": "use_potion",
                        "target": "",
                        "reasoning": "Getting low, using potion to continue fighting"
                    }
                elif in_combat and not outnumbered:
                    return {
                        "action": "fight",
                        "target": "",
                        "reasoning": "Still got fight left in me!"
                    }
            elif personality == "cautious" or personality == "greedy":
                # Cautious/greedy heroes retreat earlier
                if has_potions:
                    return {
                        "action": "use_potion",
                        "target": "",
                        "reasoning": "Health getting low, using potion"
                    }
                else:
                    return {
                        "action": "retreat",
                        "target": "marketplace",
                        "reasoning": "Low health and no potions, retreating to restock"
                    }
            else:
                # Balanced
                if has_potions and health_pct < 40:
                    return {
                        "action": "use_potion",
                        "target": "",
                        "reasoning": "Using potion at moderate health"
                    }
        
        # Outnumbered handling
        if outnumbered and in_combat:
            if personality == "brave":
                if _MOCK_RNG.random() < 0.3:  # 30% chance to retreat
                    return {
                        "action": "retreat",
                        "target": "castle",
                        "reasoning": "Outnumbered, making tactical retreat"
                    }
            elif personality == "cautious" or personality == "greedy":
                return {
                    "action": "retreat",
                    "target": "castle",
                    "reasoning": "Outnumbered, discretion is the better part of valor"
                }
        
        # Shopping opportunities
        if can_shop and not in_combat:
            if low_health:
                return {
                    "action": "buy_item",
                    "target": "Health Potion",
                    "reasoning": "Buying potion while I can"
                }
            if personality == "greedy":
                # Greedy heroes love shopping
                return {
                    "action": "buy_item",
                    "target": "Health Potion",
                    "reasoning": "Stocking up on supplies"
                }
            elif _MOCK_RNG.random() < 0.4:
                return {
                    "action": "buy_item", 
                    "target": "Health Potion",
                    "reasoning": "Good opportunity to stock up"
                }
        
        # Combat behavior
        if in_combat:
            return {
                "action": "fight",
                "target": "",
                "reasoning": "Engaging the enemy!"
            }
        
        # Default: explore
        return {
            "action": "explore",
            "target": "",
            "reasoning": "Looking for adventure"
        }

    def _mock_conversation_response(self, system_prompt: str, user_prompt: str) -> str:
        """Return a canned in-character response by hero class (wk14). Deterministic RNG."""
        hero_class = "warrior"
        if "ranger" in system_prompt.lower():
            hero_class = "ranger"
        elif "rogue" in system_prompt.lower():
            hero_class = "rogue"
        elif "wizard" in system_prompt.lower():
            hero_class = "wizard"
        templates = {
            "warrior": [
                "Aye, Sovereign. I live to serve. Point me at the next threat.",
                "My blade is yours. Just say where the fight is.",
                "Honored to speak with you. I'll keep the realm safe.",
            ],
            "ranger": [
                "The wilds call, but I hear you. What do you need?",
                "Sovereign. I've seen much from the trails. Ask what you will.",
                "Nature and kingdom both deserve protection. I'm with you.",
            ],
            "rogue": [
                "Gold talks, Sovereign. But so do I. What's the job?",
                "A pleasure. Let's just say we're aligned on profitable outcomes.",
                "You've got my ear. And my skills, when the price is right.",
            ],
            "wizard": [
                "Knowledge serves the realm. I am at your disposal, Sovereign.",
                "The arcane obeys its own laws—but I obey yours. How may I help?",
                "Wise of you to seek counsel. The world holds many secrets.",
            ],
        }
        choices = templates.get(hero_class, templates["warrior"])
        idx = int(_MOCK_RNG.random() * len(choices)) % len(choices)
        return choices[idx]

