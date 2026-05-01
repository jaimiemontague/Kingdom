# Sprint Plan: wk15 UX Polish & Pacing Tuning

## Goal
Improve game feel and balancing via UI tweaks (Pause menu cleanup, Left panel sizing, Right panel hiding, Research progress bars), economy/difficulty tuning (more monsters, higher gold accumulation/starting gold, building defense priorities), and hero reactivity to castle attacks.

## Agent Assignments & Tasks

### Agent 08 (UX/UI Director)
**Assignment:** 15A: UI Polish & Overhaul
*   **Pause Menu:** In `game/ui/pause_menu.py`, adjust the button spacing and sizes to reduce empty space. Add an icon/symbol mapping to the "Resume" and "Quit" buttons (e.g., using `load_image_cached("assets/ui/icons/play.png")` or similar) so they align with the Graphics, Audio, and Controls buttons that already have icons.
*   **Left Menu / Hero Panel:** Reduce the width of the left-side detail panel (Hero/Building details) by 30% so it's slimmer.
*   **Right Menu / Selection:** In `game/ui/hud.py` or the specific right menu implementation, ensure the right menu completely vanishes (does not render) when nothing is selected, maximizing map view.
*   **Research Button:** In `game/ui/building_view_panel.py` (or similar building detail UX), change the "Research" button render logic: if research is currently active, replace the button with a progress bar (using `HPBar.render` or a custom rect fill) tied to the research progress percentage. 

### Agent 03 (Technical Director / Architecture)
**Assignment:** 15B: Economy, Difficulty & Pacing Configs
*   **Starting Gold:** Increase `starting_gold` in `config.py` (or `EconomyConfig`) by 40% (e.g., from 1500 to 2100).
*   **Debt Collection / Tax Rate:** Increase the rate at which tax/debt collectors gather gold, or increase the tax yield. This can be done by bumping the tax rate percentage, lowering the cooldown between tax ticks, or increasing the bounds on bounty turn-ins. 
*   **Monster Density:** Lower the spawn intervals or increase the `max_alive_enemies` / `initial_count` limits for Lairs and wave generators in `config.py` so that waves are larger and more aggressive.

### Agent 06 (AI Behavior Director)
**Assignment:** 15C: Hero Defense & Research Systems
*   **Castle Defense Urgent Priority:** Update `game/entities/hero.py` State Machine: if the `castle.is_under_attack` is true, heroes should immediately drop what they're doing (including popping out of buildings) and move to defend the castle. This overrides normal workflow/resting.
*   **Farming/Building Defense:** Update warrior behavior logic. If nearby economic buildings (Farms, Mills) are taking damage (`is_under_attack`), warriors should prioritize moving to and defending them instead of wandering past.
*   **Timed Research System:** Introduce a time delay to `Marketplace` (potions) and `Blacksmith` / `Library` research functions. Instead of instant unlocks upon clicking, clicking "Research" should start a timer (e.g., 30s for potions, scaled for others based on cost). This will hold state that Agent 08's progress bar reads from. 

### Agent 11 (QA/Test Engineering)
**Assignment:** 15D: Verification & Regression
*   Ensure the new research timers don't break determinism or cause crashes during headless runs. 
*   Run `python tools/qa_smoke.py --quick`.
*   Take snapshot galleries of the new Pause Menu and slim Left panel.

## Universal Activation Prompt

When activating the agents, provide them with this prompt template so they understand their exact role in the sprint.

**Universal Prompt:**
> "Please begin the `wk15_ux_and_pacing` sprint. Read the sprint plan at `.cursor/plans/wk15_ux_and_pacing_sprint.plan.md`. Execute the tasks assigned to you. When complete, update your agent log with your response in the standard JSON format under the sprint ID `wk15-ux-pacing`."
