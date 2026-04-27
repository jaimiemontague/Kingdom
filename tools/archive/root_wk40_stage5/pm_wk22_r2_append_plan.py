import os

plan_path = 'c:\\Users\\Jaimie Montague\\OneDrive\\Documents\\Kingdom\\.cursor\\plans\\wk22_3d_refinement.plan.md'
with open(plan_path, 'a', encoding='utf-8') as f:
    f.write("\n\n## Team Roster (Round 2: Bug Hunt)\n")
    f.write("R1 caused serious regressions: trees disappeared from the terrain completely, the framerate tanked once heroes spawned, and building sprites are visually duplicating on top of themselves.\n")
    f.write("- **Active Agents**:\n")
    f.write("  - `10_PerformanceStability_Lead` (address the FPS tanking on hero spawn)\n")
    f.write("  - `03_TechnicalDirector_Architecture` (deduplicate building sprites)\n")
    f.write("  - `09_ArtDirector_Pixel_Animation_VFX` (restore trees to the terrain texture)\n")
