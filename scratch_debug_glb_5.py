from ursina import *
from pathlib import Path
import gltf
import sys
import panda3d.core as p3d

def test():
    app = Ursina(borderless=False, size=(800, 600))
    EditorCamera()
    
    # Ground
    Entity(model='plane', scale=10, color=color.gray)
    
    p = Path("assets/models/Models/GLB format/signpost.glb").resolve()
    gs = gltf.GltfSettings()
    root = gltf.load_model(str(p), gltf_settings=gs)
    np = p3d.NodePath(root)
    
    # We will spawn 3: one at 0, one at 90, one at -90
    e1 = Entity(model=np, position=(-2, 0, 0), scale=2)
    e1.rotation_x = 0
    Text(text="0", parent=e1, y=2)
    
    e2 = Entity(model=np, position=(0, 0, 0), scale=2)
    e2.rotation_x = 90
    Text(text="+90", parent=e2, y=2)
    
    e3 = Entity(model=np, position=(2, 0, 0), scale=2)
    e3.rotation_x = -90
    Text(text="-90", parent=e3, y=2)

    def input(k):
        if k == 'escape':
            sys.exit(0)

    # Let's take a screenshot programmatically after 1 second?
    # Or I can just run it without visuals and inspect bounds?
    # No, I can't take a screenshot with `run_command` inside the agent easily unless I use the browser_subagent?
    # Wait, the browser_subagent is for URLs.
    
    # I'll just check the bounds of the Ursina Entity!
    app.step()
    
    print("e1 (0)   bounds:", e1.bounds)
    print("e2 (90)  bounds:", e2.bounds)
    print("e3 (-90) bounds:", e3.bounds)
    
    sys.exit(0)

if __name__ == "__main__":
    test()
