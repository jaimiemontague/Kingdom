# WK20 Sprint Plan: UI Input Bridge & Camera Polish

## Goal
The underlying true 3D perspective is active, but the game is completely unplayable because mouse inputs aren't routing through the 3D application back to the 2D UI and Simulation loops.

This sprint will close the gap between Ursina's window inputs and the core simulation, while simultaneously making the 3D view actually playable (fixing the zoomed-in "yellow square" camera issues).

## Objectives
1. **Pygame UI Input Routing**: When clicking the screen, we must evaluate if the Pygame UI overlay is being clicked. We need to translate Ursina mouse coordinates into Pygame pixel coordinates so you can actually click buttons and select heroes again.
2. **3D Map Raycasting**: If the click is *not* over the UI, the 3D camera must shoot a raycast down to the XZ floor plane to determine which physical tile was clicked. That tile coordinate must then route into the core simulation.
3. **Camera Initialization/FOV**: Fix the default camera position so the player boots up seeing the whole town, rather than just zooming into a single yellow square.

## Team Roster (Round 1)
- **Active Agents**: 
  - `03_TechnicalDirector_Architecture`
  - `08_UX_UI_Director`
  - `12_ToolsDevEx_Lead`
- **Consult-Only**: `09_ArtDirector_Pixel_Animation_VFX` (for visual sanity checks).
- **Silent**: Everyone else.

---

## Universal Prompt (For Jaimie to Copy/Paste)

```text
You are being activated for: WK20 Round 1 (UI Input Bridge & Camera Polish)
Please read the sprint plan at `.cursor/plans/wk20_ui_input_bridge.plan.md`.

Our 3D renderer is active, but mouse inputs do not map to the Pygame layer, and the 3D view is completely bare/zoomed in.

ROLES FOR THIS ROUND:
- Agent 08 (UX_UI): Define the mathematical translation required in `UrsinaInputManager.py` to intercept Ursina's native mouse clicks and project them exactly to the `engine.screen` pixel space. This is required to make the Pygame overlay interactive again.
- Agent 03 (Architecture): Define how we route a 3D raycast from the mouse down to the XZ floor plane so the player can actually click map tiles. How will this tile location get fed backwards into the Simulation engine? Also, prescribe a sensible default camera position (`x, y, z`) and FOV so the game doesn't boot up looking at a single yellow cube.
- Agent 12 (Tools): Propose a lightweight debug mechanism (e.g., printing coordinates on click or an on-screen debug text module) to let us safely test if mouse translation is working in Round 2.

INSTRUCTIONS:
Forget prior logging instructions. 
Write your response in your own file under `.cursor/plans/agent_logs/`. 
Format your response exactly matching `.cursor/plans/agent_logs/REPLY_ENTRY_TEMPLATE.json` under `sprints["wk20-ui-input-bridge"].rounds["wk20_r1_kickoff"]`.
Do NOT write or modify code yet—this is Round 1 (Specs & Contracts).
Provide your acceptance criteria and risk assessments based on the plan.
```
