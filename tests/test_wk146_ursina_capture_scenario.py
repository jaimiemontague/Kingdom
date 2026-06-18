from __future__ import annotations

from tools.screenshot_scenarios import (
    URSINA_CAPTURE_SCENARIOS,
    get_ursina_capture_scenario,
)


def test_wk146_ursina_quest_chain_launcher_registered() -> None:
    assert "ursina_wk146_quest_chain_launcher" in URSINA_CAPTURE_SCENARIOS

    cfg = get_ursina_capture_scenario("ursina_wk146_quest_chain_launcher")

    assert cfg["patch_path"] == "tools/wk146_quest_chain_launcher_capture_patch.py"
    assert cfg["default_ticks"] == 480
    assert cfg["default_out_subdir"] == "wk146_ursina_quest_chain_launcher"
    assert cfg["stem"] == "wk146_ursina_quest_chain_launcher"
    env = cfg["env"]
    assert env["KINGDOM_URSINA_REVEAL_ON_START"] == "1"
    assert env["KINGDOM_URSINA_EDITORCAMERA"] == "0"
    assert env["KINGDOM_URSINA_DISABLE_NEUTRAL_SPAWN"] == "1"
    assert env["KINGDOM_WK146_URSINA_CAM_SPAN"] == "14"
