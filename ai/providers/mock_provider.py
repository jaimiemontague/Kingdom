"""
Mock LLM provider for testing without API keys.
Uses rule-based decisions that mimic LLM behavior.

WK81 Round D-1: the 4 responder bodies live in the ai/providers/mock/ package
(autonomous, direct_prompt, legacy_decision, conversation). MockProvider stays
here as the facade -- the provider registry imports it from this path -- with
`complete()`'s prompt-sniffing/format-detection dispatch unchanged and a 1-line
delegating wrapper for each responder.
"""
import json

from game.sim.determinism import get_rng

from ai.prompt_packs import DIRECT_PROMPT_MARK

from .base import BaseLLMProvider

# Deterministic RNG stream for mock decisions (stable across runs with the same seed).
# Shared singleton: the legacy_decision / conversation responders in
# ai/providers/mock/ import THIS instance (not a fresh get_rng) so the stream
# advances as one and output stays byte-identical.
_MOCK_RNG = get_rng("mock_provider")


def _norm_msg(s: str) -> str:
    return str(s or "").strip().lower()


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

    # ------------------------------------------------------------------
    # WK81: responder bodies moved to ai/providers/mock/*. These 1-line
    # wrappers keep complete()'s dispatch (and the public method names)
    # unchanged; the package is imported lazily to avoid an import cycle.
    # ------------------------------------------------------------------
    def _mock_autonomous_decision(self, user_prompt):
        from ai.providers.mock import autonomous
        return autonomous.mock_autonomous_decision(self, user_prompt)

    def _mock_direct_prompt(self, user_prompt):
        from ai.providers.mock import direct_prompt
        return direct_prompt.mock_direct_prompt(self, user_prompt)

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
        from ai.providers.mock import legacy_decision
        return legacy_decision.make_decision(
            self, personality, health_pct, in_combat, has_potions,
            can_shop, low_health, critical_health, outnumbered
        )

    def _mock_conversation_response(self, system_prompt, user_prompt):
        from ai.providers.mock import conversation
        return conversation.mock_conversation_response(self, system_prompt, user_prompt)
