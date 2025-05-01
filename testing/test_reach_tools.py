"""
Quick PyTest script to test the Reach class.
"""

import json
from pathlib import Path

import pytest

import reach_tools


@pytest.fixture(scope="module")
def tilton_dict():
    json_pth = (
        Path(__file__).parent.parent / "data/raw/american_whitewater/aw_00003411.json"
    )

    with open(json_pth, "r") as f:
        reach_dict = json.load(f)

    return reach_dict


def test_get_gauge_stage_tilton_too_low(tilton_dict):
    stage = reach_tools.utils.aw.get_stage(tilton_dict, 360)
    assert stage == "too low"


def test_get_gauge_stage_tilton_medium(tilton_dict):
    stage = reach_tools.utils.aw.get_stage(tilton_dict, 1680)
    assert stage == "medium"


def test_get_gauge_stage_tilton_too_high(tilton_dict):
    stage = reach_tools.utils.aw.get_stage(tilton_dict, 8000)
    assert stage == "too high"


def test_get_runnable_tilton_true(tilton_dict):
    runnable = reach_tools.utils.aw.get_runnable(tilton_dict, 1000)
    assert runnable is True


def test_get_runnable_tilton_false(tilton_dict):
    runnable = reach_tools.utils.aw.get_runnable(tilton_dict, 360)
    assert runnable is False
    runnable = reach_tools.utils.aw.get_runnable(tilton_dict, 10000)
    assert runnable is False
