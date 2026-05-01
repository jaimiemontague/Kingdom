# WK19 Sprint Plan: True 3D Ursina Transition

## Goal
Transition the "Phase 2.1" 2D orthographic Ursina MVP into a genuine 3D visual experience without breaking the underlying robust headless simulation or the hybrid Pygame UI layer.

## Objectives
1. **Perspective Camera**: Swap the orthographic camera to a fixed perspective isometric/top-down camera angle (e.g., pitched down ~45-60 degrees).
2. **Volumetric Primitives**: Replace flat `quad` and `circle` models with 3D primitives (`cube`, `cylinder`, `sphere`) scaling along the Z/Y axes so structures and heroes have visible height and volume.
3. **Preserve Hybrid UI**: Ensure the UI overlay (rendered via Pygame texturing on `camera.ui`) is completely unaffected by the 3D camera shifts.
4. **Preserve Simulation**: The `GameEngine` logic and determinism MUST remain completely untouched. All changes must be strictly isolated to `game/graphics/ursina_app.py` and `game/graphics/ursina_renderer.py`.

## Team Roster (Round 1)
- **Active Agents**: 
  - `03_TechnicalDirector_Architecture`
  - `08_UX_UI_Director`
  - `09_ArtDirector_Pixel_Animation_VFX`
- **Consult-Only**: `11_QA`, `12_Tools`
- **Silent**: Everyone else.

---

## Universal Prompt (For Jaimie to Copy/Paste)

```text
You are being activated for: WK19 Round 1 (True 3D Ursina Transition)
Please read the sprint plan at `.cursor/plans/wk19_ursina_true_3d.plan.md`.

We are converting our flat orthographic Ursina renderer into a true 3D perspective viewpoint with primitive volumes.

ROLES FOR THIS ROUND:
- **Agent 03 (Architecture)**: Define the code contract for `UrsinaRenderer`. We need to properly scale X/Z (world floor) and map Y to vertical height. The underlying Pygame logic still simulates in 2D (X/Y). Outline the math scaling and translation required to map 2D pixel coordinates to a 3D X/Z floor plane.
- **Agent 09 (Art/VFX)**: Define the visual volumetric mapping using Ursina's built-in primitives. (e.g., Hero = Capsule/Cylinder, Castle = Large Gold Cube, Enemy = Red Cube). Pick sizes/scales that look good from a 45-degree angle.
- **Agent 08 (UX/UI)**: Verify that shifting the main camera to perspective will not break our `camera.ui` full-screen quad Pygame overlay. Propose any scaling/parenting guardrails if needed.

INSTRUCTIONS:
Forget prior logging instructions. 
Write your response in your own file under `.cursor/plans/agent_logs/`. 
Format your response exactly matching `.cursor/plans/agent_logs/REPLY_ENTRY_TEMPLATE.json` under `sprints["wk19-ursina-true-3d"].rounds["wk19_r1_kickoff"]`.
Do NOT write or modify code yet—this is Round 1 (Specs & Contracts).
Provide your acceptance criteria and risk assessments based on the plan.
```
