"""
Quick PyTest script to test the Reach class.
"""

from pathlib import Path

import pytest
from arcgis.features import Feature
from arcgis.geometry import Polyline

import reach_tools
from reach_tools.collectors.aw import AWCollector, get_runnable, get_stage

_collector = AWCollector()


@pytest.fixture(scope="module")
def tilton_data():
    json_pth = (
        Path(__file__).parent.parent / "data/raw/american_whitewater/aw_00003411.json"
    )
    return _collector.from_file(json_pth)


def test_get_gauge_stage_tilton_too_low(tilton_data):
    assert get_stage(tilton_data, 360) == "too low"


def test_get_gauge_stage_tilton_medium(tilton_data):
    assert get_stage(tilton_data, 1680) == "medium"


def test_get_gauge_stage_tilton_too_high(tilton_data):
    assert get_stage(tilton_data, 8000) == "too high"


def test_get_runnable_tilton_true(tilton_data):
    assert get_runnable(tilton_data, 1000) is True


def test_get_runnable_tilton_false(tilton_data):
    assert get_runnable(tilton_data, 360) is False
    assert get_runnable(tilton_data, 10000) is False


# get list of all available files
raw_dir_pth = Path(__file__).parent.parent / "data/raw/american_whitewater/"
reach_id_lst = [int(val.stem.lstrip("aw_")) for val in raw_dir_pth.glob("aw_*.json")]
reach_id_lst.sort()


@pytest.mark.parametrize("reach_id", reach_id_lst)
def test_reach_from_collector(reach_id):
    json_pth = (
        Path(__file__).parent.parent
        / f"data/raw/american_whitewater/aw_{reach_id:08d}.json"
    )

    data = _collector.from_file(json_pth)
    reach = reach_tools.Reach.from_data(data)

    assert isinstance(reach, reach_tools.Reach)
    assert isinstance(reach.name, str)
    assert isinstance(reach.difficulty, str)
    assert isinstance(reach.difficulty_maximum, str)
    assert isinstance(reach.difficulty_minimum, str) or reach.difficulty_minimum is None
    assert isinstance(reach.difficulty_filter, float)

    if reach.geometry is not None:
        assert isinstance(reach.geometry, Polyline)

    if reach.reach_points:
        assert isinstance(reach.reach_points, list)
        assert isinstance(reach.reach_points[0], reach_tools.ReachPoint)

    if reach.gauge_min is not None or reach.gauge_max is not None:
        assert isinstance(reach.gauge_max, float)
        assert isinstance(reach.gauge_min, float)

    if reach.gauge_observation is None:
        assert reach.runnable is False
        assert reach.gauge_stage is None
    else:
        assert isinstance(reach.runnable, bool)
        assert reach.gauge_stage in ("too low", "low", "medium", "high", "too high", None)

    assert isinstance(reach.line_feature, Feature)
