# Sprint WK17: Quality, Logic, & Immersion

This sprint focuses on critical quality-of-life improvements, AI logic stability, and performance hardening derived from the latest play test results. 

The objective is to make the world feel more cohesive and responsive. If an LLM character decides to buy a dagger, they need the conviction to complete that task. If the player builds a farm, they deserve to see it. If the game runs for 5 minutes, it should not choke on memory leaks.

## User Review Required
> [!IMPORTANT]
> The assignments below dictate how the other agents will operate. Please review the division of labor and the strict acceptance criteria. Once approved, I will generate the PM Hub tickets and the universal prompt for you to distribute.

## Proposed Changes

We are dividing this sprint into four major tracks, assigned to the appropriate directors.

### 1. Fog of War & Line of Sight Vision (Agent 05 & 03)
**Problem:** Auto-spawned player buildings (farms, houses) and guards are getting swallowed by the fog of war. The player is left blind to their own domain.
**Visionary Approach:** The kingdom's presence naturally extends vision. Any structure flying the player's banner inherently pushes back the darkness. Guards, as active defenders, must have dynamic vision cones/radii. 
- **Agent 05 (Gameplay Systems):** Define the visibility radii for auto-spawned buildings (Farms, Houses) and Guards. Determine how this ties into the existing `FogOfWar` or visibility matrix.
- **Agent 03 (Technical Director):** Implement the systemic hooks so that when an auto-spawned building is created, it registers a vision source. Ensure the engine dynamically updates Guard vision without tanking performance.

### 2. The Hero Conviction System - AI Behavior (Agent 06)
**Problem:** Heroes declare intent (e.g., "I will go buy a dagger at the blacksmith") but suffer from immediate ADHD/task-churn, turning right back around to re-enter the inn. 
**Visionary Approach:** Heroes need *hysteresis* (conviction). When a decision is made via the LLM to pursue a specific actionable target (like a blacksmith), that intent must be locked in with a higher priority or inertia until the destination is reached or heavily interrupted. 
- **Agent 06 (AI Behavior):** Audit the hero simulation loop. When an LLM dictates a journey to a specific building, lock that transition state. The hero should not re-evaluate "what should I do?" every tick if they are already executing an LLM-directed errand, unless attacked. 
- **Acceptance:** Play testing must confirm that a hero leaving a building with a stated goal actually completes the walk to the destination building >95% of the time.

### 3. Clickable Peasants & Immersion (Agent 08)
**Problem:** Peasants exist in the world but feel like background noise because they cannot be clicked.
**Visionary Approach:** Every entity in Majesty-style games feels alive if you can inspect them. Peasants must have a click hitbox that registers them as the active selection, bringing up a minimal yet flavorful UI panel (showing their current simple task, e.g., "Carrying Wood", "Fleeing").
- **Agent 08 (UX/UI):** Hook peasants into the entity selection system. Design and implement a simple, tasteful info panel for them. It must not clutter the screen but must definitively confirm to the player "Yes, this is a working citizen of your kingdom."

### 4. Memory Leak & Lag Annihilation (Agent 10 & 03)
**Problem:** The game lags out and potentially leaks memory after a few minutes of play.
**Visionary Approach:** We cannot ship a simulation that chokes on its own history. This is likely tied to pathfinding caches not clearing, dead entities lingering in memory, or surfaces not being released. 
- **Agent 10 (Performance/Stability):** Profile the game over a 5-minute `--no-llm` simulation. Identify the exact objects leaking (using `tracemalloc` or object graphs). 
- **Agent 03 (Technical Director):** Fix the root cause identified by Agent 10. Ensure dead entities are fully garbage collected and caches are bounded.

---

## Verification Plan

### Automated Tests
- **QA Smoke:** `python tools/qa_smoke.py --quick` must remain strictly PASS across all merges.
- **Asset Validator:** `python tools/validate_assets.py --strict` must PASS.
- **Determinism Guard:** We will run `python tools/determinism_guard.py` to ensure the new peasant selection and vision rules do not introduce wall-clock non-determinism.

### Manual Verification
- **Stress Test (Memory):** Run `python main.py --no-llm` and let it idle for 10 minutes at 3x speed. Memory must plateau, and FPS must remain > 50 on standard hardware.
- **Vision Check:** Spawn a guard and let them walk; verify the fog clears dynamically around them. Wait for a farm to auto-spawn; verify it clears the fog around it.
- **Behavior Check:** Use `python main.py --provider mock` and watch a hero leave the inn. Ensure they walk uninterrupted to their next building destination without immediately turning back.
- **UX Check:** Click a peasant walking on a road. Verify the selection ring appears and the UI panel accurately reflects their state.

*Awaiting PM/Human approval before cutting these into `agent_01_ExecutiveProducer_PM.json` tickets and drafting the activation prompt.*
