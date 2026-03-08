"""
Run the Kingdom simulation headlessly without a Pygame display.
Used to verify that the core engine logic is fully decoupled from rendering.
"""
import sys
import os
import time

# Ensure we can import from the game package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from game.engine import GameEngine
from game.input_manager import InputManager

class DummyInputManager(InputManager):
    """Provides no inputs to the engine."""
    def get_events(self):
        return []
    def get_mouse_pos(self):
        return (0, 0)
    def is_key_pressed(self, key):
        return False
    def is_mouse_focused(self):
        return False
    def get_key_mods(self):
        return {'ctrl': False, 'shift': False, 'alt': False}


def run_headless():
    print("Initializing headless simulation...")
    
    # IMPORTANT: We purposefully DO NOT init pygame.display here!
    # Engine requires `pygame.init` which we'll call safely, but we do not want a window.
    import pygame
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    pygame.init()
    
    # Initialize engine with dummy inputs
    engine = GameEngine(input_manager=DummyInputManager(), headless=True)
    
    # We want to run fast
    from config import SIM_TICK_HZ
    dt = 1.0 / SIM_TICK_HZ
    
    ticks_to_run = 1000
    print(f"Running {ticks_to_run} ticks of simulation...")
    
    start_time = time.time()
    for i in range(ticks_to_run):
        engine.tick_simulation(dt)
        if i % 100 == 0:
            print(f"  Tick {i}/{ticks_to_run} - Entities: " 
                  f"Heroes={len(engine.heroes)}, "
                  f"Enemies={len(engine.enemies)}, "
                  f"Gold={engine.economy.player_gold}")
            
    end_time = time.time()
    
    print("-" * 40)
    print("Headless simulation complete!")
    print(f"Real time elapsed: {end_time - start_time:.2f} seconds")
    print(f"Final state: Heroes={len(engine.heroes)}, Enemies={len(engine.enemies)}, Gold={engine.economy.player_gold}")

if __name__ == "__main__":
    run_headless()
