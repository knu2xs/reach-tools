"""Normalized data models shared across all reach collectors."""

from dataclasses import dataclass, field
from typing import List, Optional

__all__ = ["PointData", "GaugeThreshold", "ReachData"]


@dataclass
class PointData:
    """Normalized representation of a single point of interest on a reach."""

    point_type: str  # "access", "rapid", "hazard", "generic"
    reach_id: Optional[str] = None
    name: Optional[str] = None
    subtype: Optional[str] = None  # "putin", "takeout", "intermediate", "playspot", "portage", "waterfall"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: Optional[str] = None
    difficulty: Optional[str] = None
    side_of_river: Optional[str] = None


@dataclass
class GaugeThreshold:
    """A single gauge threshold boundary."""

    value: float
    label: Optional[str] = None  # "low", "medium", "high", or None for the upper bound


@dataclass
class ReachData:
    """Normalized representation of a whitewater reach from any source."""

    source: str
    reach_id: Optional[str] = None
    river_name: Optional[str] = None
    reach_name: Optional[str] = None
    alternate_name: Optional[str] = None
    description: Optional[str] = None
    difficulty: Optional[str] = None
    length: Optional[float] = None
    url: Optional[str] = None
    geometry: Optional[dict] = None  # GeoJSON LineString dict, or None
    pois: List[PointData] = field(default_factory=list)
    has_gauge: bool = False
    gauge_id: Optional[str] = None
    gauge_source: Optional[str] = None
    gauge_units: Optional[str] = None
    gauge_min: Optional[float] = None
    gauge_max: Optional[float] = None
    gauge_observation: Optional[float] = None
    gauge_thresholds: List[GaugeThreshold] = field(default_factory=list)
    edited_at: Optional[str] = None   # ISO datetime string
    updated_at: Optional[int] = None  # Unix epoch integer
