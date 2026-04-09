"""
Generic Input Manager interface to decouple the engine simulation from Pygame.
"""
from dataclasses import dataclass
from typing import Optional, Tuple, List, Callable

@dataclass
class InputEvent:
    """A generic input event."""
    type: str # 'QUIT', 'KEYDOWN', 'KEYUP', 'MOUSEDOWN', 'MOUSEUP', 'MOUSEMOTION', 'WHEEL', etc.
    key: Optional[str] = None # 'esc', 'space', '1', 'w', 'a', 's', 'd', 'tab', 'f1', etc.
    button: Optional[int] = None # 1: left, 2: middle, 3: right, 4: scroll up, 5: scroll down
    pos: Optional[Tuple[int, int]] = None
    wheel_y: Optional[int] = None
    # MOUSEMOTION: pygame-style (left, middle, right) button hold masks, 0/1 each
    buttons: Optional[Tuple[int, int, int]] = None
    raw_event: any = None # The underlying framework event (e.g. pygame.event.Event) if needed


class InputManager:
    """Abstract interface for polling inputs."""
    
    def get_events(self) -> List[InputEvent]:
        """Poll and return a list of generic input events."""
        raise NotImplementedError
        
    def get_mouse_pos(self) -> Tuple[int, int]:
        """Get the current mouse position (x, y)."""
        raise NotImplementedError
        
    def is_key_pressed(self, key: str) -> bool:
        """Check if a specific key is currently held down."""
        raise NotImplementedError
        
    def is_mouse_focused(self) -> bool:
        """Check if the application window currently has mouse focus."""
        raise NotImplementedError
        
    def get_key_mods(self) -> dict:
        """Return a dictionary of active modifier keys (e.g., {'ctrl': True, 'shift': False})."""
        raise NotImplementedError

