"""
Ursina-specific implementation of the InputManager interface.
Translates Ursina's input state (held_keys, mouse) into our generic InputEvent paradigm.
"""
from ursina import held_keys, mouse, window
from game.input_manager import InputManager, InputEvent

# Headless Ursina + Pygame HUD uses a fixed virtual framebuffer (see GameEngine headless_ui).
_DEFAULT_VIRTUAL_SCREEN = (1920, 1080)

# General map of Ursina key strings to our generic representations
_URSINA_KEY_MAP = {
    'escape': 'esc',
    'space': 'space',
    'tab': 'tab',
    # Note: Ursina provides '1', '2', 'a', 'b' natively as strings, which matches our generic format
}

class UrsinaInputManager(InputManager):
    def __init__(self, virtual_screen_size: tuple[int, int] = _DEFAULT_VIRTUAL_SCREEN):
        # We need to queue events since Ursina handles events via callbacks 
        # (input(key) function) rather than a pollable event queue.
        # However, for our engine, we will try to mimic standard key states.
        self._event_queue = []
        # PM WK20: fixed virtual resolution; map window pixels → engine.screen (stretch).
        self._virtual_w = max(1, int(virtual_screen_size[0]))
        self._virtual_h = max(1, int(virtual_screen_size[1]))
        
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
        """Map Ursina window pointer → pygame-style pixels on the virtual engine.screen.

        Ursina (see ursina.mouse.Mouse): x = ((px/W) - 0.5) * aspect_ratio,
        y = -((py/H) - 0.5). Invert to window pixels, then scale to virtual 1920×1080 HUD.
        """
        if not window:
            return (0, 0)
        W = int(window.size[0])
        H = int(window.size[1])
        if W <= 0 or H <= 0:
            return (0, 0)
        ar = float(window.aspect_ratio)
        if ar <= 1e-9:
            ar = 1.0
        mx = float(mouse.x)
        my = float(mouse.y)
        # Inverse of Ursina's mapping from pixel → normalized
        px_x = (mx / ar + 0.5) * W
        px_y = (0.5 - my) * H
        px_x = max(0.0, min(float(W - 1), px_x))
        px_y = max(0.0, min(float(H - 1), px_y))
        ew, eh = self._virtual_w, self._virtual_h
        sx = int(round(px_x * ew / W))
        sy = int(round(px_y * eh / H))
        sx = max(0, min(ew - 1, sx))
        sy = max(0, min(eh - 1, sy))
        return (sx, sy)

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

