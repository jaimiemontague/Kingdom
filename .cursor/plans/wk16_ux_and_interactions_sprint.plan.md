# Sprint Plan: wk16 UX & Interactions Polish

## Goal
Address user feedback from WK15 playtesting to finalize the UI/UX polish. The primary focus is fixing Pause Menu button alignment, making Tax Collectors clickable, and ensuring heroes can be selected globally from any UI context (interiors, chat) to bring up their Left Panel.

## Agent Assignments & Tasks

### Agent 08 (UX/UI Director)
**Assignment:** 16A: Menu Alignment & Hero Selection Contexts
*   **Pause Menu Alignment:** In `game/ui/pause_menu.py`, the "Resume" and "Quit" buttons have their text rendering to the left of the Graphics/Audio/Controls buttons because `icon_play.png` and `icon_quit.png` do not exist. Fix this by passing a blank transparent `pygame.Surface((16, 16), pygame.SRCALPHA)` as the icon for "resume" and "quit" in the `_icon_map` if the cached image fails to load. This will force the text layout math in `Button` to perfectly align all 5 buttons.
    ![Menu Alignment Bug](.cursor/human_provided/v1.4%20menu.JPG)
*   **Hero Global Selection:** Update `game/ui/building_renderers/interior_view_panel.py` and `game/ui/chat_panel.py`. When a player clicks a hero inside a building (interior view) or clicks a hero's name/portrait in the chat panel, it should set `game_state["selected_hero"] = hero` and `game_state["selected_building"] = None`, forcing the Left Menu to open with that hero's details.

### Agent 03 (Technical Director / Architecture)
**Assignment:** 16B: Tax Collector Selection
*   **Tax Collector Clickability:** Ensure that `TaxCollector` entities are clickable. Check `game/engine.py` (mouse click handling) and ensure `TaxCollector` is included in the selection raycast (similar to peasants/heroes). If clicked, set `game_state["selected_hero"] = tax_collector` (or create a unified selection state) so a left panel pops up for them. You may need to create a simple left panel renderer for Tax Collectors in `game/ui/hero_panel.py` (or a dynamic fallback in the HUD) to show their current gold and status.

### Agent 11 (QA/Test Engineering)
**Assignment:** 16D: Verification & Regression
*   Run `python tools/qa_smoke.py --quick`.
*   Take snapshot galleries of the new Pause Menu and the Left Panel targeting a Tax Collector.

## Universal Activation Prompt

When activating the agents, provide them with this prompt template so they understand their exact role in the sprint.

**Universal Prompt:**
> "Please begin the `wk16_ux_and_interactions` sprint. Read the sprint plan at `.cursor/plans/wk16_ux_and_interactions_sprint.plan.md` and read `.cursor/Play Test Results.txt` (only the 'Improvements to make' section) for context. Execute the tasks assigned to you. When complete, update your agent log with your response in the standard JSON format under the sprint ID `wk16-ux-interactions`."
