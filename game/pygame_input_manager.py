"""
Pygame-specific implementation of the InputManager interface.
"""
import pygame
from game.input_manager import InputManager, InputEvent

# Generic key mapping
_PYGAME_KEY_MAP = {
    pygame.K_ESCAPE: 'esc',
    pygame.K_SPACE: 'space',
    pygame.K_TAB: 'tab',
    pygame.K_1: '1', pygame.K_2: '2', pygame.K_3: '3', pygame.K_4: '4', pygame.K_5: '5',
    pygame.K_6: '6', pygame.K_7: '7', pygame.K_8: '8', pygame.K_9: '9', pygame.K_0: '0',
    pygame.K_a: 'a', pygame.K_b: 'b', pygame.K_c: 'c', pygame.K_d: 'd', pygame.K_e: 'e',
    pygame.K_f: 'f', pygame.K_g: 'g', pygame.K_h: 'h', pygame.K_i: 'i', pygame.K_j: 'j',
    pygame.K_k: 'k', pygame.K_l: 'l', pygame.K_m: 'm', pygame.K_n: 'n', pygame.K_o: 'o',
    pygame.K_p: 'p', pygame.K_q: 'q', pygame.K_r: 'r', pygame.K_s: 's', pygame.K_t: 't',
    pygame.K_u: 'u', pygame.K_v: 'v', pygame.K_w: 'w', pygame.K_x: 'x', pygame.K_y: 'y',
    pygame.K_z: 'z',
    pygame.K_F1: 'f1', pygame.K_F2: 'f2', pygame.K_F3: 'f3', pygame.K_F4: 'f4',
    pygame.K_F12: 'f12',
    pygame.K_EQUALS: '=', pygame.K_KP_PLUS: '+',
    pygame.K_MINUS: '-', pygame.K_KP_MINUS: '-',
    pygame.K_BACKQUOTE: '`',
    pygame.K_LEFTBRACKET: '[',
    pygame.K_RIGHTBRACKET: ']',
}

class PygameInputManager(InputManager):
    def get_events(self) -> list[InputEvent]:
        events = []
        for pg_event in pygame.event.get():
            evt = InputEvent(type='UNKNOWN', raw_event=pg_event)
            
            if pg_event.type == pygame.QUIT:
                evt.type = 'QUIT'
            elif pg_event.type == pygame.KEYDOWN:
                evt.type = 'KEYDOWN'
                evt.key = _PYGAME_KEY_MAP.get(pg_event.key, str(pg_event.key))
            elif pg_event.type == pygame.KEYUP:
                evt.type = 'KEYUP'
                evt.key = _PYGAME_KEY_MAP.get(pg_event.key, str(pg_event.key))
            elif pg_event.type == pygame.MOUSEBUTTONDOWN:
                evt.type = 'MOUSEDOWN'
                evt.button = pg_event.button
                evt.pos = pg_event.pos
            elif pg_event.type == pygame.MOUSEBUTTONUP:
                evt.type = 'MOUSEUP'
                evt.button = pg_event.button
                evt.pos = pg_event.pos
            elif pg_event.type == pygame.MOUSEMOTION:
                evt.type = 'MOUSEMOTION'
                evt.button = pg_event.buttons[0] if pg_event.buttons else None # Just grab first if exists
                evt.pos = pg_event.pos
            elif hasattr(pygame, "MOUSEWHEEL") and pg_event.type == pygame.MOUSEWHEEL:
                evt.type = 'WHEEL'
                evt.wheel_y = pg_event.y
            elif pg_event.type == pygame.VIDEORESIZE:
                evt.type = 'VIDEORESIZE'
                evt.pos = (pg_event.w, pg_event.h)

            events.append(evt)
        return events

    def get_mouse_pos(self) -> tuple[int, int]:
        return pygame.mouse.get_pos()

    def is_key_pressed(self, key_str: str) -> bool:
        keys = pygame.key.get_pressed()
        # Reverse map string to pygame constant
        for pg_key, mapped_str in _PYGAME_KEY_MAP.items():
            if mapped_str == key_str:
                return keys[pg_key]
        return False

    def is_mouse_focused(self) -> bool:
        return pygame.mouse.get_focused()

    def get_key_mods(self) -> dict:
        mods = pygame.key.get_mods()
        return {
            'ctrl': bool(mods & pygame.KMOD_CTRL),
            'shift': bool(mods & pygame.KMOD_SHIFT),
            'alt': bool(mods & pygame.KMOD_ALT)
        }
