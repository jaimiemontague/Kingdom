"""WK38/WK63: InputHandler routes through narrow command protocols — mock-based regression tests.

WK63 Wave 2: InputHandler now checks c._command_mode directly (not c._engine),
so mock command surfaces must include _command_mode=False.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from game.input_handler import InputHandler
from game.input_manager import InputEvent


def _minimal_hud_no_chat():
    return SimpleNamespace(_chat_panel=None)


def _minimal_pause_closed():
    return SimpleNamespace(visible=False)


def test_process_events_quit_sets_running_false():
    """QUIT event must only touch command surface (no GameEngine import in handler)."""
    input_manager = MagicMock()
    input_manager.get_events.return_value = [InputEvent(type="QUIT")]

    cmd = SimpleNamespace(
        running=True,
        _skip_event_processing_frames=0,
        dev_tools_panel=None,
        input_manager=input_manager,
    )

    InputHandler(cmd).process_events()

    assert cmd.running is False


def test_select_building_when_unaffordable_returns_false_and_toasts():
    economy = MagicMock()
    economy.can_afford_building.return_value = False
    hud = MagicMock()

    cmd = SimpleNamespace(economy=economy, hud=hud)

    ih = InputHandler(cmd)
    assert ih.select_building_for_placement("warrior_guild") is False

    economy.can_afford_building.assert_called_once_with("warrior_guild")
    hud.add_message.assert_called_once()
    args, _kw = hud.add_message.call_args
    assert "Not enough gold!" in args[0]


def test_handle_keydown_h_invokes_try_hire_hero_on_command_surface():
    """Hotkey path must call try_hire_hero on self.commands (no raw engine)."""
    try_hire = MagicMock()
    cmd = SimpleNamespace(
        hud=_minimal_hud_no_chat(),
        pause_menu=_minimal_pause_closed(),
        paused=False,
        try_hire_hero=try_hire,
        _command_mode=False,
        _command_buffer="",
    )

    InputHandler(cmd).handle_keydown(InputEvent(type="KEYDOWN", key="h"))

    try_hire.assert_called_once_with()


def test_handle_keydown_enter_opens_command_mode():
    """Enter key should set _command_mode=True on the command surface directly."""
    cmd = SimpleNamespace(
        hud=_minimal_hud_no_chat(),
        pause_menu=_minimal_pause_closed(),
        paused=False,
        _command_mode=False,
        _command_buffer="",
    )

    InputHandler(cmd).handle_keydown(InputEvent(type="KEYDOWN", key="enter"))

    assert cmd._command_mode is True
    assert cmd._command_buffer == ""


def test_command_mode_typing_and_submit():
    """While _command_mode is True, keystrokes fill _command_buffer and Enter submits."""
    process_command = MagicMock()
    cmd = SimpleNamespace(
        hud=_minimal_hud_no_chat(),
        pause_menu=_minimal_pause_closed(),
        paused=False,
        _command_mode=True,
        _command_buffer="",
        process_command=process_command,
    )

    ih = InputHandler(cmd)

    # Type a character (single printable key)
    ih.handle_keydown(InputEvent(type="KEYDOWN", key="a", raw_event=None))
    assert cmd._command_buffer == "a"

    # Submit with enter
    ih.handle_keydown(InputEvent(type="KEYDOWN", key="enter", raw_event=None))
    process_command.assert_called_once_with("a")
    assert cmd._command_mode is False
    assert cmd._command_buffer == ""


def test_protocol_aliases_set_on_init():
    """InputHandler stores typed aliases: camera, selection, placement, menu, state."""
    cmd = SimpleNamespace()
    ih = InputHandler(cmd)
    assert ih.camera is cmd
    assert ih.selection is cmd
    assert ih.placement is cmd
    assert ih.menu is cmd
    assert ih.state is cmd
    assert ih.commands is cmd
