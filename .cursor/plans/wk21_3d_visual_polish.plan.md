# WK21 Sprint Plan: 3D Visual Polish

## Goal
The underlying true 3D perspective is active and interactive (WK20). However, it currently renders everything as basic colored cubes. We need to apply our existing CC0 pixel art assets to this 3D world to make it look like a game again.

## Objectives
1. **Billboarding vs Texturing**: Decide if buildings and lairs look better as 2D pixel-art billboards constantly facing the camera, or as textured 3D objects.
2. **Environment**: Formulate a plan for replacing the flat green map background with a textured plane or an actual grid of tiles corresponding to the simulation coordinates.
3. **Architecture Contract**: Define the implementation scope so `ursina_renderer.py` can cleanly load these assets without destroying performance.

## Team Roster (Round 1)
- **Active Agents**: 
  - `09_ArtDirector_Pixel_Animation_VFX`
- **Consult-Only**: `03_TechnicalDirector_Architecture` (if Agent 09 has questions on rendering math/batching).
- **Silent**: Everyone else.

---

## Universal Prompt (For Jaimie to Copy/Paste)

```text
You are being activated for: WK21 Round 1 (3D Visual Polish)
Please read the sprint plan at `.cursor/plans/wk21_3d_visual_polish.plan.md`.

Our 3D renderer is fully interactive, but it consists solely of colored cubes. It's time to make it pretty.

ROLES FOR THIS ROUND:
- Agent 09 (Art Director): Spec out the visual mapping. Do we use textured 3D primitives, or 2D pixel-art billboards that rotate to face the camera? How will we utilize our existing pixel art from `game/graphics/tile_sprites.py` in the new `ursina_renderer.py`?

INSTRUCTIONS:
Forget prior logging instructions. 
Write your response in your own file under `.cursor/plans/agent_logs/`. 
Format your response exactly matching `.cursor/plans/agent_logs/REPLY_ENTRY_TEMPLATE.json` under `sprints["wk21-3d-visual-polish"].rounds["wk21_r1_kickoff"]`.
Do NOT write or modify code yet—this is Round 1 (Specs & Contracts).
Provide your acceptance criteria and risk assessments based on the plan.
```
