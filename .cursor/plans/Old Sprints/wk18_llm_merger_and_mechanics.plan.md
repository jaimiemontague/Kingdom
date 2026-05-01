# Sprint WK18: The LLM-AI Merger, Physicality, & Dev Tools

This sprint represents a massive leap forward in the simulation's depth. We are granting the LLM direct physical agency over its character, grounded by its stats and the emergent economy. We are also enhancing the physical constraints of the world (collisions and building destruction) and surfacing the "brain" of the game via new monitoring tools.

## Proposed Changes

### Track 1: The LLM-AI Merger & Agency (Agent 06 & Agent 03)
**Problem:** The LLM's responses are currently just text. If the Lord (player) says "leave the inn," the LLM might agree, but lacks the mechanical hook to actually walk out the door.
**Visionary Approach:** The LLM prompt must be injected with the hero's *exact* current stats to ground its persona. When a conversation occurs, the LLM must be provided a strict JSON schema or function-calling toolset allowing it to output mechanical intents alongside its dialogue.

- **Agent 06 (AI Behavior):** 
  - **Context Injection:** In `game/ai/behaviors/llm_bridge.py` (or where the prompt is built), inject the hero's physical stats (`hp`, `max_hp`, `gold`, `state`, `intent`, `target`) into the system prompt so the AI identifies as that specific entity.
  - **Tool Schema Definitions:** Define an `ActionTool` JSON schema that the LLM is instructed to output when deciding to physically act. The schema should include fields for `action` (e.g., `leave_building`, `move_to`, `attack`) and `target`.
  - **Obey vs Defy:** Explicitly prompt the LLM to make a conscious choice when commanded by the player: to either "Obey" the lord or "Defy" them based on their personality and current stats (e.g. low HP), outputting this reasoning alongside their tool action.
- **Agent 03 (Engine/Architecture) [Round 2]:** 
  - Build the parsing bridge in the main simulation loop that reads these LLM JSON tool-outputs and forcibly injects them into the hero's state machine (overriding standard Idle/Bounty logic).

### Track 2: The Panopticon - AI Monitoring Dev Tools (Agent 12 & Agent 08)
**Problem:** The human cannot see what the LLMs are thinking in real-time, making debugging and tuning the AI Merger impossible.
**Visionary Approach:** We need a sleek, Matrix-style developer overlay that streams the raw consciousness of the kingdom.

- **Agent 12 (Tools/DevEx):** 
  - **EventBus Hooks:** In `game/events.py`, add new `GameEventType` enums: `LLM_PROMPT_SENT` and `LLM_RESPONSE_RECEIVED`.
  - **Provider Instrumentation:** In `ai/providers/openai_provider.py`, fire these events to the `EventBus` when a request goes out and when the response text comes back. We want the raw payload broadcasted globally.
- **Agent 08 (UX/UI):** 
  - **DevOverlay Class:** Create a new `game/ui/dev_overlay.py` containing a `DevOverlay` UI widget.
  - **HUD Integration:** In `game/ui/hud.py`, instantiate the `DevOverlay`. Subscribe to the new `LLM_*` events from the EventBus to populate a scrolling buffer of recent LLM thoughts.
  - **Toggle:** Bind a hotkey (e.g., `F3` or backtick `` ` `` if free) in `input_handler.py` to toggle `HUD.show_dev_overlay`, rendering a semi-transparent black panel with color-coded, monospace text showing real-time AI API activity.

### Track 3: Physical Constraints (Agent 03 & Agent 05)
**Problem:** Heroes clip through each other, they don't seem to step *into* the blacksmith, and destroying a building with people inside leaves them in a weird state.
**Visionary Approach:** Bodies must take up space, and buildings are physical containers. 

- **Agent 03 (Technical Director) [Round 2]:** 
  - **Soft Collisions:** In `game/systems/movement.py` or the core entity loop, implement a soft separation/flocking steer so heroes push away from each other if their distance `< 15` pixels. They can no longer occupy the exact same coordinate.
- **Agent 05 (Gameplay Systems):**
  - **Blacksmith Entrance:** Update `game/entities/buildings/economic.py` (or similar). When a hero arrives at the Blacksmith to buy gear, they must transition to `is_inside_building = True` and disappear from the map, executing their internal transaction timer, exactly mirroring the Inn logic.
  - **Building Destruction Ejection:** In `game/engine.py` (combat resolution), when a building's HP hits 0 or it is demolished by the player: 
    1. Iterate its `occupants` or query heroes where `target_building == this_building`.
    2. Forcibly set their `is_inside_building = False` and relocate their physical `pos` to an adjacent tile outside the footprint of the destroyed building so they pop out.

### Track 4: The Inn Economy (Agent 05)
**Problem:** The Inn is too comfortable. Broke heroes loiter indefinitely.
**Visionary Approach:** Capitalism must drive the heroes back to the wilderness. 

- **Agent 05 (Gameplay Systems):** 
  - **Entry/Loiter Fee:** In `game/entities/buildings/economic.py` (the Inn logic), implement a gold deduction whenever a hero enters or spends a tick inside.
  - **The Bounce:** If a hero's `gold` drops to `< 1` while inside the Inn, forcefully evict them (`is_inside_building = False`). This ensures broke heroes must return to hunting monsters or bounties instead of hiding.

---

## Verification Plan

### Automated Tests
- **QA Smoke:** `python tools/qa_smoke.py --quick` must remain strictly PASS.
- **Determinism:** The `determinism_guard` must not be violated by the new physical collision soft-push vectors.

### Manual Verification
- **LLM Merger:** Tell a hero to leave the inn. Verify they actually leave based on the LLM tool JSON processing.
- **Dev Tool Check:** Press the Dev Tool hotkey and observe the real-time LLM requests scrolling.
- **Collision Check:** Spawn 5 heroes in a tight cluster; verify they push each other apart.
- **Blacksmith Visual:** Watch a hero buy a sword; they must physically disappear from the map.
- **Economy & Destruction:** Set a hero's gold to 0 and watch them get bounced from the Inn. Destroy the Inn while heroes are inside; they should instantly appear on the grass.
