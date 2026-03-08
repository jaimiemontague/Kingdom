"""
Basic 3D Viewer application using Ursina.
Wraps the core headless simulation and visualizes it.
"""
from ursina import Ursina, window, camera, color, time, scene
import pygame
import os

from game.engine import GameEngine
from game.ursina_input_manager import UrsinaInputManager
from game.graphics.ursina_renderer import UrsinaRenderer

class UrsinaApp:
    def __init__(self, ai_controller_factory):
        # We still need Pygame hidden in the background for font/audio subsystems
        # that the engine expects. We init it safely so it doesn't spawn a window.
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        pygame.init()

        # Init Ursina
        self.app = Ursina(
            title='Kingdom Sim - Ursina 3D Viewer',
            borderless=False,
            fullscreen=False,
            development_mode=True,
        )
        window.exit_button.visible = False
        window.fps_counter.enabled = True

        # Set background color using Panda3D's native API (most reliable)
        from panda3d.core import LVecBase4f
        base = self.app  # Ursina app IS the Panda3D ShowBase
        base.setBackgroundColor(LVecBase4f(34/255, 139/255, 34/255, 1))

        # Setup Orthographic Camera centered on the map
        import config
        tiles_w = config.MAP_WIDTH   # 150
        tiles_h = config.MAP_HEIGHT  # 150
        camera.orthographic = True
        camera.fov = tiles_h  # Show the full map height in the view
        camera.position = (tiles_w / 2, tiles_h / 2, -10)
        camera.rotation = (0, 0, 0)
        # Make sure we can see everything
        camera.clip_plane_near = -100
        camera.clip_plane_far = 100

        # Create the underlying simulation engine with Ursina inputs
        self.input_manager = UrsinaInputManager()
        self.engine = GameEngine(input_manager=self.input_manager, headless=True)
        
        # Assign the AI
        if ai_controller_factory:
            self.engine.ai_controller = ai_controller_factory()
            
        # Create our visual translator
        self.renderer = UrsinaRenderer(self.engine)

    def run(self):
        # Define the global update hook that Ursina calls every frame
        def update():
            # dt is provided globally by ursina as time.dt
            dt = time.dt
            
            # Tick the simulation headless
            self.engine.tick_simulation(dt)
            
            # Sync the visual state
            self.renderer.update()
            
            # Basic camera panning for the MVP
            from ursina import held_keys
            speed = 50 * dt  # tiles per second
            if held_keys['a']: camera.x -= speed
            if held_keys['d']: camera.x += speed
            if held_keys['w']: camera.y += speed
            if held_keys['s']: camera.y -= speed
            
            # Zoom
            if held_keys['q']: camera.fov += speed * 2
            if held_keys['e']: camera.fov -= speed * 2
            camera.fov = max(20, min(300, camera.fov))

        # Hook it into Ursina's global namespace
        import __main__
        __main__.update = update
        
        # Start the Ursina loop
        self.app.run()
