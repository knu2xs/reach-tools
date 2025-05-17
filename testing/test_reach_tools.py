"""
Quick PyTest script to test the Reach class.
"""

import json
from pathlib import Path

import pytest
from arcgis.features import Feature
from arcgis.geometry import Polygon, Polyline

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


# get list of all available files
raw_dir_pth = Path(__file__).parent.parent / f"data/raw/american_whitewater/"
reach_id_lst = [int(val.stem.lstrip("aw_")) for val in raw_dir_pth.glob("aw_*.json")]
reach_id_lst.sort()


@pytest.mark.parametrize("reach_id", reach_id_lst)
def test_reach_from_aw_json(reach_id):
    json_pth = (
        Path(__file__).parent.parent
        / f"data/raw/american_whitewater/aw_{reach_id:08d}.json"
    )

    reach = reach_tools.Reach.from_aw_json(json_pth)

    assert isinstance(reach, reach_tools.Reach)
    assert isinstance(reach.name, str)
    assert isinstance(reach.difficulty, str)
    assert isinstance(reach.difficulty_maximum, str)
    assert isinstance(reach.difficulty_minimum, str) or reach.difficulty_minimum is None
    assert isinstance(reach.difficulty_filter, float)

    if reach._main_json.get("info").get("geom") is not None:
        assert isinstance(reach.geometry, Polyline)

    if len(reach._rapids_json) > 0:
        assert isinstance(reach.reach_points, list)
        assert isinstance(reach.reach_points[0], reach_tools.ReachPoint)

    if len(reach._main_json.get("guagesummary").get("ranges")) > 0 and (
        reach.gauge_min is not None or reach.gauge_max is not None
    ):
        assert isinstance(reach.gauge_max, float)
        assert isinstance(reach.gauge_min, float)

        if reach.gauge_observation is None:
            assert reach.runnable is False
        else:
            assert isinstance(reach.runnable, bool)
            assert isinstance(reach.gauge_stage, str)

    assert isinstance(reach.line_feature, Feature)
