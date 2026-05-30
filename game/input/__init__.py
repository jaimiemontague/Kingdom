"""Input-routing package — mechanical extraction of InputHandler's heavy methods.

WK77 Round B-2e: ``InputHandler.handle_mousedown`` / ``handle_mousemove`` /
``handle_keydown`` / ``select_building_for_placement`` were moved here verbatim as
module functions taking the live ``InputHandler`` as ``ih`` (WK69/WK75/WK76 pure-move
pattern). ``game/input_handler.py`` keeps 1-line delegating wrappers of the same names,
so the event-poll loop and every caller (GameCommands / hud / tests) are unchanged.
Behavior is byte-identical.
"""
