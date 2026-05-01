# Plan: Direct Prompt Integration Tests & Fixes

**Goal:** Create end-to-end integration tests for every direct prompt command (`buy potions`, `go home`, `explore east`, `status_report`, etc.) to ensure the mock provider and validator produce the correct executable intent and physical action without false refusals. After tests are created, fix the underlying validation/context bugs that cause false refusals.

**Context / Known Bugs:**
- "Buy potions": Hero refuses, claiming the market is too far, that they haven't discovered it (even when they have), or that they can't afford it (even when they have 20+ gold).
- This indicates the `hero_context` (specifically `known_places_llm`, `shop_items`, `can_afford`, or `can_shop`) is either not being populated correctly by `ContextBuilder`, or `direct_prompt_validator.py` is misinterpreting it.

**Scope:**
1. **Agent 11 (QA):** Write comprehensive integration tests (e.g., `tests/test_direct_prompt_integration.py`). Set up a simulation with a hero (e.g., a Ranger), give them 20+ gold, have them discover the market, prompt them to buy a potion, and assert that the prompt correctly resolves to a committed `move_to` or `buy_item` action. Write a test for every supported command.
2. **Agent 06 (AI/LLM):** Fix `ai/direct_prompt_validator.py` and `ai/context_builder.py` so the tests pass. Ensure memory of places works and gold checks correctly compute affordability even if the hero is not currently *at* the shop.
3. **Agent 11 (QA):** Re-run tests to confirm.

**Execution Order (Automation DAG):**
- Step 1: Agent 11 (write tests)
- Step 2: Agent 06 (fix bugs based on tests)
- Step 3: Agent 11 (verify tests pass)
