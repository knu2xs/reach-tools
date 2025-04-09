"""
Quick PyTest script to test the Reach class.
"""

from pathlib import Path
import sys

from arcgis.geometry import Polyline, Point

from reach_tools import ReachPoint, Reach


def test_create_reach_from_aw():
    reach = Reach.from_aw(3411)
    assert isinstance(reach, Reach)                 # validates object can be created
    assert reach.difficulty_filter == 4.1           # validates properties read from JSON
    assert isinstance(reach.geometry, Polyline)     # validates geometry was correctly created
    assert isinstance(reach.putin, ReachPoint)      # validates point was correctly created
    assert isinstance(reach.putin.geometry, Point)  # validates point geometry was correctly created