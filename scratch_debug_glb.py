import os
from pathlib import Path
import gltf
from panda3d.core import NodePath

def test_load(rel_path):
    p = Path(rel_path).resolve()
    print(f"Loading {p}")
    if not p.exists():
        print("  - File does not exist!")
        return

    try:
        gs = gltf.GltfSettings()
        gs.no_srgb = False
        model_root = gltf.load_model(str(p), gltf_settings=gs)
        if model_root is None:
            print("  - model_root is None")
        else:
            np = NodePath(model_root)
            print("  - Loaded successfully.")
            tb = np.getTightBounds()
            if tb:
                print(f"  - Tight Bounds: {tb[0]} to {tb[1]}")
            else:
                print("  - Tight Bounds: None (Geometry might be empty or invalid)")
            
            # Count geom nodes
            geom_nodes = np.findAllMatches("**/+GeomNode")
            print(f"  - GeomNodes found: {geom_nodes.getNumPaths()}")
    except Exception as e:
        print(f"  - Exception: {e}")

if __name__ == "__main__":
    test_load("assets/models/Models/GLB format/fence.glb")
    test_load("assets/models/Models/GLB format/barrel.glb")
    test_load("assets/models/Models/GLB format/workbench.glb")
