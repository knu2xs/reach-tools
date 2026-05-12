__title__ = "reach-tools"
__version__ = "0.1.0.dev0"
__author__ = "Joel McCune (https://github.com/knu2xs)"
__license__ = "Apache 2.0"
__copyright__ = "Copyright 2023 by Joel McCune (https://github.com/knu2xs)"

__all__ = ["Reach", "ReachPoint", "utils"]

import json
from datetime import datetime, timezone
from functools import cached_property
from pathlib import Path
from typing import Optional, Union

import numpy as np
from arcgis.features import Feature
from arcgis.geometry import Geometry, Polygon, Polyline, Point
import pandas as pd

from . import utils
from .utils import strip_html_tags, cleanup_string
from .utils.reference import lookup_dict
from .utils.procure import download_raw_json_from_aw


# POI type string to (point_type, subtype) mapping
_POI_TYPE_MAP = {
    "put-in": ("access", "putin"),
    "takeout": ("access", "takeout"),
    "access": ("access", "intermediate"),
    "rapid": ("rapid", None),
    "hazard": ("hazard", None),
    "playspot": ("rapid", "playspot"),
    "portage": ("rapid", "portage"),
    "waterfall": ("hazard", "waterfall"),
    "other": ("generic", None),
}


class ReachPoint(object):
    """Discrete object facilitating working with reach points."""

    def __init__(
        self,
        reach_id,
        geometry,
        point_type,
        subtype=None,
        name=None,
        side_of_river=None,
        update_date=None,
        description=None,
        difficulty=None,
    ):
        self.reach_id = str(reach_id)
        self.point_type = point_type
        self.subtype = subtype
        self.name = name
        self.update_date = update_date
        self.description: str = description
        self.difficulty: str = difficulty
        self._side_of_river = side_of_river
        self._geometry = geometry

    def __repr__(self):
        if self.subtype is None:
            repr_str = f"{self.__class__.__name__} ({self.name} - {self.point_type})"
        else:
            repr_str = f"{self.__class__.__name__} ({self.name} - {self.point_type} - {self.subtype})"
        return repr_str

    @classmethod
    def from_aw_json(
        cls,
        aw_json: dict,
        reach_id: Optional[Union[str, int]] = None,
    ) -> "ReachPoint":
        """Create a ReachPoint from a new-format point-of-interest dict.

        Args:
            aw_json: A single POI dict from raw_reach["pointOfInterests"].
            reach_id: Optional reach ID to associate with this point.
        """
        if not isinstance(aw_json, dict) or "type" not in aw_json:
            raise ValueError(
                "Please provide a single new-format point-of-interest dict."
            )

        if reach_id is None:
            reach_id = aw_json.get("id")

        poi_type = aw_json.get("type", "other")
        typ, subtyp = _POI_TYPE_MAP.get(poi_type, ("generic", None))

        loc = aw_json.get("location") or {}
        lat_raw = loc.get("latitude")
        lon_raw = loc.get("longitude")
        if lat_raw is not None and lon_raw is not None:
            geom = Point(
                {
                    "x": float(lon_raw),
                    "y": float(lat_raw),
                    "spatialReference": {"wkid": 4326},
                }
            )
        else:
            geom = None

        diff = aw_json.get("difficulty")
        if diff == "N/A":
            diff = None

        pt = ReachPoint(
            reach_id=reach_id,
            geometry=geom,
            point_type=typ,
            subtype=subtyp,
            name=aw_json.get("name"),
            side_of_river=None,
            update_date=None,
            description=aw_json.get("description"),
            difficulty=diff,
        )
        return pt

    @cached_property
    def wkt(self) -> str:
        """Access point geometry in WKT format."""
        return self.geometry.WKT

    @cached_property
    def ewkt(self) -> str:
        """Access point geometry in EWKT format."""
        return self.geometry.EWKT

    @cached_property
    def wkb(self) -> bytes:
        """Access point geometry in WKB format."""
        return self.geometry.WKB

    @cached_property
    def geojson(self) -> dict:
        """Access point geometry in GeoJSON format."""
        return self.geometry.__geo_interface__

    @property
    def geometry(self):
        return self._geometry

    @geometry.setter
    def geometry(self, geometry):
        if not isinstance(geometry, Point):
            raise Exception(
                "access geometry must be a valid ArcGIS Point Geometry object"
            )
        self._geometry = geometry

    @property
    def side_of_river(self):
        """Which side of the river the access is on."""
        return self._side_of_river

    @side_of_river.setter
    def side_of_river(self, side_of_river):
        if isinstance(side_of_river, str):
            side_of_river = side_of_river.lower()
        if isinstance(side_of_river, str) and (
            side_of_river != "left" and side_of_river != "right"
        ):
            raise Exception('side of river must be either "left" or "right"')
        self._side_of_river = side_of_river

    @cached_property
    def feature(self):
        """Get the access as an ArcGIS Python API Feature object."""
        return Feature(
            geometry=self._geometry,
            attributes={
                key: vars(self)[key]
                for key in vars(self).keys()
                if key != "_geometry" and not key.startswith("_")
            },
        )

    @cached_property
    def dictionary(self):
        """Get the point as a dictionary of values."""
        dict_point = {
            key: vars(self)[key] for key in vars(self).keys() if not key.startswith("_")
        }
        dict_point["SHAPE"] = self.geometry
        return dict_point


class Reach(object):

    source = "american_whitewater"

    def __init__(self, reach_id):
        self.reach_id = str(reach_id)
        # Plain instance attributes — no @property getter for _raw_json.
        self._raw_json: dict = None
        self._poi_json: list = None
        self._correlation_details: dict = None
        self.error: bool = None
        self.notes: str = None
        self.validated: bool = None
        self.validated_by: str = None
        self._geometry: Polyline = None
        self._reach_points: list = []
        self.agency: str = None
        self._gauge_observation: Union[int, float] = None
        self._difficulty_minimum: str = None
        self._difficulty_maximum: str = None
        self._difficulty_outlier: str = None

    def __str__(self):
        return f"{self.river_name} - {self.reach_name} - {self.difficulty}"

    def __repr__(self):
        return f"{self.__class__.__name__} ({self.river_name} - {self.reach_name} - {self.difficulty})"

    def _hydrate(self, raw_json: dict) -> None:
        """Populate internal state from a new-format reach object dict."""
        self._raw_json = raw_json
        self._poi_json = raw_json.get("pointOfInterests") or []
        correlations = raw_json.get("detail", {}).get("correlations", [])
        if correlations:
            self._correlation_details = correlations[0].get("correlationDetails")
        else:
            self._correlation_details = None

    @cached_property
    def difficulty_filter(self) -> float:
        val = lookup_dict.get(self.difficulty_maximum)
        return val

    @property
    def reach_points(self) -> list:
        """List of reach point objects."""
        if len(self._reach_points) == 0 and self._poi_json:
            self._reach_points = [
                ReachPoint.from_aw_json(pt_json, reach_id=self.reach_id)
                for pt_json in self._poi_json
            ]
        return self._reach_points

    @cached_property
    def reach_points_features(self):
        """Get all the reach points as a list of features."""
        return [pt.feature for pt in self.reach_points]

    @cached_property
    def reach_points_dataframe(self):
        """Get the reach points as an Esri Spatially Enabled Pandas DataFrame."""
        df_pt = pd.DataFrame([pt.dictionary for pt in self.reach_points])
        df_pt.spatial.set_geometry("SHAPE")
        return df_pt

    @cached_property
    def centroid(self) -> Point:
        """Get a point geometry centroid for the hydroline."""
        if isinstance(self.geometry, Polyline):
            xmin, ymin, xmax, ymax = self.geometry.extent
            cntr = Geometry(
                {
                    "x": (xmax - xmin) / 2 + xmin,
                    "y": (ymax - ymin) / 2 + ymin,
                    "spatialReference": self.geometry.spatial_reference,
                }
            )
        elif isinstance(self.putin, ReachPoint) and isinstance(self.takeout, ReachPoint):
            cntr = Geometry(
                {
                    "x": np.mean([self.putin.geometry.x, self.takeout.geometry.x]),
                    "y": np.mean([self.putin.geometry.y, self.takeout.geometry.y]),
                    "spatialReference": self.putin.geometry.spatial_reference,
                }
            )
        elif isinstance(self.putin, ReachPoint):
            cntr = self.putin.geometry
        elif isinstance(self.takeout, ReachPoint):
            cntr = self.takeout.geometry
        else:
            cntr = None
        return cntr

    @cached_property
    def extent(self) -> Optional[tuple]:
        """Provide the extent of the reach as (xmin, ymin, xmax, ymax)."""
        geom = (self._raw_json or {}).get("detail", {}).get("geometry")
        if not geom:
            return None
        coords = geom.get("coordinates", [])
        if not coords:
            return None
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        return (min(xs), min(ys), max(xs), max(ys))

    @cached_property
    def extent_polygon(self) -> Optional[Polygon]:
        """Provide the extent of the reach as a Polygon."""
        if self.extent is None:
            return None
        xmin, ymin, xmax, ymax = self.extent
        poly = Polygon(
            {
                "rings": [
                    [
                        [xmin, ymin],
                        [xmin, ymax],
                        [xmax, ymax],
                        [xmax, ymin],
                        [xmin, ymin],
                    ]
                ],
                "spatialReference": 4326,
            }
        )
        return poly

    @cached_property
    def name(self) -> str:
        if self.reach_name is None and (
            self.river_name is not None and len(self.river_name)
        ):
            return self.river_name
        elif self.river_name is None and (
            self.reach_name is not None and len(self.reach_name)
        ):
            return self.reach_name
        elif self.river_name is None and self.reach_name is None:
            return ""
        elif len(self.river_name) and len(self.reach_name):
            return f"{self.river_name} - {self.reach_name}"

    @cached_property
    def gauge_min(self) -> Optional[float]:
        """Minimum runnable gauge value (beginLowRunnable)."""
        cd = self._correlation_details
        if cd is None:
            return None
        raw = cd.get("beginLowRunnable")
        return float(raw) if raw is not None else None

    @cached_property
    def gauge_max(self) -> Optional[float]:
        """Maximum runnable gauge value (endHighRunnable)."""
        cd = self._correlation_details
        if cd is None:
            return None
        raw = cd.get("endHighRunnable")
        return float(raw) if raw is not None else None

    @property
    def runnable(self) -> bool:
        """Whether the reach is runnable."""
        return utils.aw.get_runnable(self._raw_json, self.gauge_observation)

    @cached_property
    def gauge_stage(self) -> Optional[str]:
        """Human-readable interpretation of current gauge stage runnability."""
        return utils.aw.get_stage(self._raw_json, self.gauge_observation)

    @cached_property
    def river_name(self) -> Optional[str]:
        """Name of the River."""
        val = (self._raw_json or {}).get("stub", {}).get("river")
        if val:
            val = utils.remove_backslashes(cleanup_string(val))
        return val or None

    @cached_property
    def reach_name(self) -> Optional[str]:
        """Name of the reach (section)."""
        val = (self._raw_json or {}).get("stub", {}).get("section")
        if val:
            val = utils.remove_backslashes(cleanup_string(val))
        return val or None

    @cached_property
    def section_name(self) -> Optional[str]:
        """Name of section (reach)."""
        return self.reach_name

    @cached_property
    def alternate_name(self) -> Optional[str]:
        """Alternate name for the reach."""
        val = (self._raw_json or {}).get("stub", {}).get("altname")
        if val:
            val = utils.remove_backslashes(cleanup_string(val))
        return val or None

    @cached_property
    def description(self) -> Optional[str]:
        """Description of the reach."""
        val = (self._raw_json or {}).get("detail", {}).get("description")
        if val:
            val = cleanup_string(val)
        return val or None

    @cached_property
    def abstract(self) -> Optional[str]:
        """Abstract (short description) of the reach."""
        if self.description is not None and len(self.description) > 0:
            val = self.description.replace("\\", "").replace("/n", "")[:500]
            val = val[: val.rfind(" ")]
            val = val + "..."
            return val
        return None

    @cached_property
    def length(self) -> Optional[float]:
        val = (self._raw_json or {}).get("detail", {}).get("length")
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str) and val.replace(".", "", 1).isnumeric():
            return float(val)
        return val

    @cached_property
    def has_gauge(self) -> bool:
        """Boolean indicating if gauge information is available."""
        correlations = (self._raw_json or {}).get("detail", {}).get("correlations", [])
        if not correlations:
            return False
        gi = correlations[0].get("gaugeInfo")
        return gi is not None

    @property
    def gauge_observation(self) -> Optional[float]:
        """Gauge observation — flow reading in the primary gauge metric."""
        if self._gauge_observation is None and self.has_gauge:
            correlations = (self._raw_json or {}).get("detail", {}).get("correlations", [])
            if correlations:
                gi = correlations[0].get("gaugeInfo") or {}
                reading = gi.get("latestFlowReading") or {}
                raw = reading.get("value")
                if raw is not None:
                    try:
                        self._gauge_observation = float(raw)
                    except (ValueError, TypeError):
                        pass
        return self._gauge_observation

    @gauge_observation.setter
    def gauge_observation(self, val: Union[str, int, float]) -> None:
        if val is not None:
            if isinstance(val, str) and (len(val) == 0 or not val.replace(".", "", 1).isnumeric()):
                val = None
            else:
                val = float(val)
        self._gauge_observation = val

    @cached_property
    def gauge_id(self) -> Optional[str]:
        if self.has_gauge:
            correlations = (self._raw_json or {}).get("detail", {}).get("correlations", [])
            return correlations[0].get("gaugeInfo", {}).get("gaugeSourceIdentifier")
        return None

    @cached_property
    def gauge_source(self) -> Optional[str]:
        """Source for the gauge."""
        if self.has_gauge:
            correlations = (self._raw_json or {}).get("detail", {}).get("correlations", [])
            return correlations[0].get("gaugeInfo", {}).get("gaugeSource")
        return None

    @cached_property
    def gauge_units(self) -> Optional[str]:
        """Gauge units (e.g. cfs)."""
        cd = self._correlation_details
        if cd is not None:
            return cd.get("metric")
        return None

    @cached_property
    def gauge_metric(self) -> Optional[str]:
        """Gauge metric, typically cfs or cms."""
        return self.gauge_units

    @cached_property
    def edited_timestamp(self) -> Optional[datetime]:
        """Date last modified."""
        val = (self._raw_json or {}).get("detail", {}).get("editedAt")
        if val:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        return None

    @cached_property
    def update_timestamp(self) -> Optional[datetime]:
        """Date last updated (from updatedAt Unix epoch integer)."""
        val = (self._raw_json or {}).get("updatedAt")
        if val is not None:
            return datetime.fromtimestamp(val, tz=timezone.utc)
        return None

    @cached_property
    def difficulty(self) -> Optional[str]:
        """Reach difficulty."""
        val = (self._raw_json or {}).get("stub", {}).get("difficulty")
        return val or None

    def _lookup_difficulty(self):
        """Helper to assign difficulty parts from single difficulty string."""
        (
            self._difficulty_minimum,
            self._difficulty_maximum,
            self._difficulty_outlier,
        ) = utils.get_difficulty_parts(self.difficulty)

    @property
    def difficulty_minimum(self) -> str:
        if self._difficulty_minimum is None:
            self._lookup_difficulty()
        return self._difficulty_minimum

    @property
    def difficulty_maximum(self) -> str:
        if self._difficulty_maximum is None:
            self._lookup_difficulty()
        return self._difficulty_maximum

    @property
    def difficulty_outlier(self) -> str:
        if self._difficulty_outlier is None:
            self._lookup_difficulty()
        return self._difficulty_outlier

    @difficulty_minimum.setter
    def difficulty_minimum(self, val: str) -> None:
        if val is not None:
            self._difficulty_minimum = val

    @difficulty_maximum.setter
    def difficulty_maximum(self, val: str) -> None:
        if val is not None:
            self._difficulty_maximum = val

    @difficulty_outlier.setter
    def difficulty_outlier(self, val: str) -> None:
        if val is not None:
            self._difficulty_outlier = val

    @cached_property
    def url(self) -> str:
        """Web URL of the reach."""
        return f"https://www.americanwhitewater.org/content/River/view/river-detail/{self.reach_id}/main"

    @classmethod
    def from_aw(cls, reach_id: Union[str, int]) -> Optional["Reach"]:
        """Get a reach by retrieving JSON directly from American Whitewater.

        Args:
            reach_id: American Whitewater reach ID.

        Returns:
            A Reach instance, or None if the reach does not exist (HTTP 404).
        """
        raw_json = download_raw_json_from_aw(reach_id)
        if raw_json is None:
            return None
        return cls.from_aw_json(raw_json)

    @classmethod
    def from_aw_json(
        cls,
        aw_json: Union[dict, Path],
        reach_id: Optional[Union[str, int]] = None,
    ) -> "Reach":
        """Create a Reach from a new-format reach object dict or fixture file path.

        Args:
            aw_json: Either a dict (unwrapped reach object) or a Path to a
                fixture file containing the full tRPC response array.
            reach_id: Optional override for the reach ID.
        """
        if isinstance(aw_json, Path):
            with open(aw_json, "r") as f:
                data = json.load(f)
            aw_json = data[0]["result"]["data"]["json"]

        rid = reach_id if reach_id is not None else aw_json.get("id")
        reach = cls(rid)
        reach._hydrate(aw_json)
        return reach

    def _get_accesses_by_type(self, access_type):
        if access_type not in ("putin", "takeout", "intermediate"):
            raise Exception(
                'access type must be either "putin", "takeout" or "intermediate"'
            )
        return [
            pt
            for pt in self._reach_points
            if pt.subtype == access_type and pt.point_type == "access"
        ]

    def _set_putin_takeout(self, access, access_type):
        """Set the putin or takeout using a ReachPoint object."""
        if type(access) != ReachPoint:
            raise Exception(
                "{} access must be an instance of ReachPoint object type".format(access_type)
            )
        if access_type not in ("putin", "takeout"):
            raise Exception('access type must be either "putin" or "takeout"')
        self._reach_points = [
            pt
            for pt in self._reach_points
            if not (pt.point_type == "access" and pt.subtype == access_type)
        ]
        access.point_type = "access"
        access.subtype = access_type
        self._reach_points.append(access)

    @property
    def putin(self):
        access_lst = self._get_accesses_by_type("putin")
        return access_lst[0] if access_lst else None

    @putin.setter
    def putin(self, access):
        self._set_putin_takeout(access, "putin")

    @property
    def takeout(self):
        access_lst = self._get_accesses_by_type("takeout")
        return access_lst[0] if access_lst else None

    @takeout.setter
    def takeout(self, access):
        self._set_putin_takeout(access, "takeout")

    @cached_property
    def intermediate_accesses(self):
        access_lst = self._get_accesses_by_type("intermediate")
        return access_lst if access_lst else None

    def add_intermediate_access(self, access):
        if not isinstance(access, ReachPoint):
            raise Exception(
                "intermediate access must be an instance of ReachPoint object type"
            )
        access.point_type = "access"
        access.subtype = "intermediate"
        self._reach_points.append(access)

    @cached_property
    def geometry(self) -> Optional[Polyline]:
        """Reach polyline geometry."""
        geom_json = (self._raw_json or {}).get("detail", {}).get("geometry")
        if geom_json is None:
            return None
        return Polyline(geom_json, sr=4326)

    @cached_property
    def wkt(self) -> str:
        """Reach polyline geometry in WKT format."""
        return self.geometry.WKT

    @cached_property
    def ewkt(self) -> str:
        """Reach polyline geometry in EWKT format."""
        return self.geometry.EWKT

    @cached_property
    def wkb(self) -> bytes:
        """Reach polyline geometry in WKB format."""
        return self.geometry.WKB

    @cached_property
    def geojson(self) -> dict:
        """Reach polyline geometry in GeoJSON format."""
        return self.geometry.__geo_interface__

    @cached_property
    def attributes(self) -> dict:
        """Non-geometry properties for the reach."""
        prop_lst = [
            "abstract",
            "description",
            "difficulty",
            "difficulty_filter",
            "difficulty_maximum",
            "difficulty_minimum",
            "difficulty_outlier",
            "gauge_id",
            "gauge_max",
            "gauge_metric",
            "gauge_min",
            "gauge_observation",
            "gauge_source",
            "gauge_stage",
            "gauge_units",
            "length",
            "name",
            "notes",
            "reach_id",
            "river_name",
            "runnable",
            "section_name",
            "source",
            "url",
        ]
        return {k: getattr(self, k) for k in prop_lst}

    @property
    def line_feature(self) -> Feature:
        """ArcGIS Python API line Feature object for the reach."""
        if self.geometry:
            return Feature(geometry=self.geometry, attributes=self.attributes)
        return Feature(attributes=self.attributes)

    @property
    def centroid_feature(self) -> Feature:
        """ArcGIS Python API point Feature object for the reach."""
        return Feature(geometry=self.centroid, attributes=self.attributes)
