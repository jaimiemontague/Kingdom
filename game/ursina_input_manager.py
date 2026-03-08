"""
Ursina-specific implementation of the InputManager interface.
Translates Ursina's input state (held_keys, mouse) into our generic InputEvent paradigm.
"""
from ursina import held_keys, mouse, window
from game.input_manager import InputManager, InputEvent

# General map of Ursina key strings to our generic representations
_URSINA_KEY_MAP = {
    'escape': 'esc',
    'space': 'space',
    'tab': 'tab',
    # Note: Ursina provides '1', '2', 'a', 'b' natively as strings, which matches our generic format
}

class UrsinaInputManager(InputManager):
    def __init__(self):
        # We need to queue events since Ursina handles events via callbacks 
        # (input(key) function) rather than a pollable event queue.
        # However, for our engine, we will try to mimic standard key states.
        self._event_queue = []
        
        # We'll hook into Ursina's global input callback if needed later, 
        # but for an MVP headless viewer, we might not even need to generate dynamic 
        # mousedown/up events, just state-based polling.

    def queue_event(self, event: InputEvent):
        """Called by Ursina's input() hook to push events to the engine."""
        self._event_queue.append(event)

    def get_events(self) -> list[InputEvent]:
        # Return and clear the queue
        events = list(self._event_queue)
        self._event_queue.clear()
        return events

    def get_mouse_pos(self) -> tuple[int, int]:
        # Ursina mouse.position is a relative Vec2 from center (-0.5 to 0.5 roughly)
        # We must convert it to screen pixels for the engine if it relies on pixels.
        if not window:
            return (0, 0)
        
        # window.resolution is (width, height)
        # mouse.x goes from approx -0.5 (left) to 0.5 (right) depending on aspect ratio
        # Actually window.top_left, etc. are used, but typically:
        # pixel_x = (mouse.x + 0.5) * window.size[0] (roughly, if 0,0 is center)
        # Ursina UI space: (0,0) is center. x goes -0.5 to 0.5 (if aspect ratio 1:1, usually -0.5*aspect to 0.5*aspect)
        # To avoid complex math for the MVP (which doesn't use the mouse yet), we return 0,0
        return (0, 0)

    def is_key_pressed(self, key_str: str) -> bool:
        # Map our generic key back to Ursina's key names if necessary
        ursina_key = key_str
        for u_key, gen_key in _URSINA_KEY_MAP.items():
            if gen_key == key_str:
                ursina_key = u_key
                break
                
        return bool(held_keys.get(ursina_key, 0))

    def is_mouse_focused(self) -> bool:
        # Ursina doesn't have a direct "focused" bool that mirrors Pygame easily,
        # but if the window is active it works.
        return True

    def get_key_mods(self) -> dict:
        return {
            'ctrl': bool(held_keys.get('control', 0) or held_keys.get('left control', 0)),
            'shift': bool(held_keys.get('shift', 0) or held_keys.get('left shift', 0)),
            'alt': bool(held_keys.get('alt', 0) or held_keys.get('left alt', 0))
        }

