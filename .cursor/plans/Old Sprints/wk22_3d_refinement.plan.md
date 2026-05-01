# WK22 Sprint Plan: 3D Refinement & Fixes

## Goal
Now that the core 3D visual mapping is complete from WK21, we have several gameplay-breaking and visual bugs that need to be resolved. The goal of this sprint is to polish the renderer visuals, properly obscure unexplored chunks of the map, and re-enable critical keyboard inputs.

## Objectives
1. **Fix Terrain Orientation**: The current terrain maps the trees upside down. UV coordinates or rotation rules need to be corrected so assets appear appropriately upright.
2. **Implement Shadows**: We need directional lights casting shadows off of buildings, units, and environment obstacles, providing depth to the 3D scene without blowing out the FPS budget.
3. **Fix Fog of War Visuals**: Fog of War is hiding entities successfully, but the terrain below remains completely visible. The unobserved tiles must visually obscure the ground so it feels like a genuine Fog of War mechanic.
4. **Restore Hotkeys**: Hotkeys for building matrices, menus, and other interactions are currently non-responsive. The input event pipeline originating in Ursina needs to safely reach our simulation logic/UI systems.

## Team Roster (Round 1: Execution)
- **Active Agents**:
  - `03_TechnicalDirector_Architecture` (Shadows)
  - `08_UX_UI_Director` (Input Event/Hotkey Bridge)
  - `09_ArtDirector_Pixel_Animation_VFX` (Terrain Orientation, Fog Visuals)
- **Consult-Only**: `10_PerformanceStability_Lead` (if shadows tank performance) 
- **Silent**: Everyone else.


## Team Roster (Round 2: Bug Hunt)
R1 caused serious regressions: trees disappeared from the terrain completely, the framerate tanked once heroes spawned, and building sprites are visually duplicating on top of themselves.
- **Active Agents**:
  - `10_PerformanceStability_Lead` (address the FPS tanking on hero spawn)
  - `03_TechnicalDirector_Architecture` (deduplicate building sprites)
  - `09_ArtDirector_Pixel_Animation_VFX` (restore trees to the terrain texture)


### Mid-Sprint Status (Agent 10 Performance Notes)
We are currently mid-way through Round 2 Bug Hunt and the bugs remain stubbornly unresolved. Based on Agent 10's recommendation, our **next steps upon return** are:
1. Increase `URSINA_UI_UPLOAD_INTERVAL_SEC` further to achieve a much cheaper HUD rendering path.
2. Add a temporary hotkey to completely disable the composited Pygame HUD in Ursina. This will allow us to isolate the renderer performance and get the cleanest absolute FPS confirmation without UI overhead interfering.
