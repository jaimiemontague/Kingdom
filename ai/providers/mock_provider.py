"""
Mock LLM provider for testing without API keys.
Uses rule-based decisions that mimic LLM behavior.
"""
from game.sim.determinism import get_rng

# Deterministic RNG stream for mock decisions (stable across runs with the same seed).
_MOCK_RNG = get_rng("mock_provider")
import json
from .base import BaseLLMProvider


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
        """Generate a mock decision based on keywords in the prompt."""
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

