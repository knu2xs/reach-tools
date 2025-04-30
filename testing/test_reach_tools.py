"""
Quick PyTest script to test the Reach class.
"""
import json
from pathlib import Path
import sys

from arcgis.geometry import Polyline, Point

from reach_tools.utils.aw import get_gauge_stage


def test_get_gauge_stage():
    json_pth = Path(__file__).parent.parent / "data/raw/american_whitewater/aw_00003411.json"

    with open(json_pth, "r") as f:
        reach_dict = json.load(f)

    stage = get_gauge_stage(reach_dict, 1680)

    assert isinstance(stage, str)