__title__ = "reach-tools"
__version__ = "0.1.0.dev0"
__author__ = "Joel McCune (https://github.com/knu2xs)"
__license__ = "Apache 2.0"
__copyright__ = "Copyright 2023 by Joel McCune (https://github.com/knu2xs)"

__all__ = ["Reach", "ReachPoint", "utils"]

from datetime import datetime, timezone
from functools import cached_property
from typing import Any, Optional, Union

import numpy as np
from arcgis.features import Feature  # type: ignore[import-untyped]
from arcgis.geometry import Geometry, Polygon, Polyline, Point  # type: ignore[import-untyped]
import pandas as pd

from . import utils
from .utils.reference import difficulty_dict
from .models import PointData, ReachData

# Sentinel used to detect when gauge_observation has been explicitly overridden.
_UNSET = object()


class ReachPoint(object):
    """Discrete object facilitating working with reach points."""

    def __init__(
        self,
        reach_id: Optional[Union[str, int]],
        geometry: Optional[Point],
        point_type: str,
        subtype: Optional[str] = None,
        name: Optional[str] = None,
        side_of_river: Optional[str] = None,
        update_date: Optional[datetime] = None,
        description: Optional[str] = None,
        difficulty: Optional[str] = None,
    ):
        self.reach_id = str(reach_id) if reach_id is not None else None
        self.point_type = point_type
        self.subtype = subtype
        self.name = name
        self.update_date = update_date
        self.description: Optional[str] = description
        self.difficulty: Optional[str] = difficulty
        self._side_of_river: Optional[str] = side_of_river
        self._geometry: Optional[Point] = geometry

    def __repr__(self):
        if self.subtype is None:
            repr_str = f"{self.__class__.__name__} ({self.name} - {self.point_type})"
        else:
            repr_str = f"{self.__class__.__name__} ({self.name} - {self.point_type} - {self.subtype})"
        return repr_str

    @classmethod
    def from_data(cls, data: PointData) -> "ReachPoint":
        """Create a ReachPoint from a normalized PointData object."""
        lat = data.latitude
        lon = data.longitude
        if lat is not None and lon is not None:
            geom = Point({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}})
        else:
            geom = None
        return cls(
            reach_id=data.reach_id,
            geometry=geom,
            point_type=data.point_type,
            subtype=data.subtype,
            name=data.name,
            side_of_river=data.side_of_river,
            update_date=None,
            description=data.description,
            difficulty=data.difficulty,
        )

    @cached_property
    def wkt(self) -> Optional[str]:
        """Access point geometry in WKT format."""
        return self.geometry.WKT if self.geometry is not None else None  # type: ignore[return-value]

    @cached_property
    def ewkt(self) -> Optional[str]:
        """Access point geometry in EWKT format."""
        return self.geometry.EWKT if self.geometry is not None else None  # type: ignore[return-value]

    @cached_property
    def wkb(self) -> Optional[bytes]:
        """Access point geometry in WKB format."""
        return self.geometry.WKB if self.geometry is not None else None  # type: ignore[return-value]

    @cached_property
    def geojson(self) -> Optional[dict[str, Any]]:
        """Access point geometry in GeoJSON format."""
        return self.geometry.__geo_interface__ if self.geometry is not None else None  # type: ignore[return-value]

    @property
    def geometry(self) -> Optional[Point]:
        return self._geometry

    @geometry.setter
    def geometry(self, geometry: Any) -> None:
        if not isinstance(geometry, Point):
            raise Exception(
                "access geometry must be a valid ArcGIS Point Geometry object"
            )
        self._geometry = geometry

    @property
    def side_of_river(self) -> Optional[str]:
        """Which side of the river the access is on."""
        return self._side_of_river

    @side_of_river.setter
    def side_of_river(self, side_of_river: Optional[str]) -> None:
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

    def __init__(self, data: ReachData):
        self._data: ReachData = data
        self._reach_points: Optional[list["ReachPoint"]] = None  # lazy-loaded from _data.pois
        self._gauge_observation_override: Any = _UNSET
        self._difficulty_minimum: Optional[str] = None
        self._difficulty_maximum: Optional[str] = None
        self._difficulty_outlier: Optional[str] = None
        self.error: Optional[bool] = None
        self.notes: Optional[str] = None
        self.validated: Optional[bool] = None
        self.validated_by: Optional[str] = None
        self.agency: Optional[str] = None

    def __str__(self):
        return f"{self.river_name} - {self.reach_name} - {self.difficulty}"

    def __repr__(self):
        return f"{self.__class__.__name__} ({self.river_name} - {self.reach_name} - {self.difficulty})"

    @classmethod
    def from_data(cls, data: ReachData) -> "Reach":
        """Create a Reach from a normalized ReachData dict."""
        return cls(data)

    @property
    def reach_id(self) -> Optional[str]:
        return self._data.reach_id

    @property
    def source(self) -> str:
        return self._data.source

    @cached_property
    def difficulty_filter(self) -> Optional[float]:
        if self.difficulty_maximum is None:
            return None
        val = difficulty_dict.get(self.difficulty_maximum)
        return val

    @property
    def reach_points(self) -> list["ReachPoint"]:
        """List of reach point objects."""
        if self._reach_points is None:
            self._reach_points = [
                ReachPoint.from_data(p) for p in self._data.pois
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
    def centroid(self) -> Optional[Any]:
        """Get a point geometry centroid for the hydroline."""
        if self.geometry is not None:
            extent = self.geometry.extent  # type: ignore[union-attr]
            if extent is not None:
                xmin, ymin, xmax, ymax = extent  # type: ignore[misc]
                cntr = Geometry(
                    {
                        "x": (xmax - xmin) / 2 + xmin,
                        "y": (ymax - ymin) / 2 + ymin,
                        "spatialReference": self.geometry.spatial_reference,  # type: ignore[union-attr]
                    }
                )
            else:
                cntr = None
        elif self.putin is not None and self.takeout is not None:
            putin_geom = self.putin.geometry
            takeout_geom = self.takeout.geometry
            if putin_geom is not None and takeout_geom is not None:
                cntr = Geometry(
                    {
                        "x": np.mean([putin_geom.x, takeout_geom.x]),
                        "y": np.mean([putin_geom.y, takeout_geom.y]),
                        "spatialReference": putin_geom.spatial_reference,
                    }
                )
            else:
                cntr = putin_geom or takeout_geom
        elif self.putin is not None:
            cntr = self.putin.geometry
        elif self.takeout is not None:
            cntr = self.takeout.geometry
        else:
            cntr = None
        return cntr

    @cached_property
    def extent(self) -> Optional[tuple[float, float, float, float]]:
        """Provide the extent of the reach as (xmin, ymin, xmax, ymax)."""
        geom = self._data.geometry
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
        if self.reach_name is None and self.river_name is not None:
            return self.river_name
        elif self.river_name is None and self.reach_name is not None:
            return self.reach_name
        elif self.river_name is not None and self.reach_name is not None:
            return f"{self.river_name} - {self.reach_name}"
        return ""

    @cached_property
    def gauge_min(self) -> Optional[float]:
        """Minimum runnable gauge value (beginLowRunnable)."""
        return self._data.gauge_min

    @cached_property
    def gauge_max(self) -> Optional[float]:
        """Maximum runnable gauge value (endHighRunnable)."""
        return self._data.gauge_max

    @property
    def runnable(self) -> bool:
        """Whether the reach is runnable."""
        from .collectors.aw import get_runnable
        return get_runnable(self._data, self.gauge_observation)

    @property
    def gauge_stage(self) -> Optional[str]:
        """Human-readable interpretation of current gauge stage runnability."""
        from .collectors.aw import get_stage
        return get_stage(self._data, self.gauge_observation)

    @cached_property
    def river_name(self) -> Optional[str]:
        """Name of the River."""
        return self._data.river_name

    @cached_property
    def reach_name(self) -> Optional[str]:
        """Name of the reach (section)."""
        return self._data.reach_name

    @cached_property
    def section_name(self) -> Optional[str]:
        """Name of section (reach)."""
        return self.reach_name

    @cached_property
    def alternate_name(self) -> Optional[str]:
        """Alternate name for the reach."""
        return self._data.alternate_name

    @cached_property
    def description(self) -> Optional[str]:
        """Description of the reach."""
        return self._data.description

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
        return self._data.length

    @cached_property
    def has_gauge(self) -> bool:
        """Boolean indicating if gauge information is available."""
        return self._data.has_gauge

    @property
    def gauge_observation(self) -> Optional[float]:
        """Gauge observation — flow reading in the primary gauge metric."""
        if self._gauge_observation_override is not _UNSET:
            return self._gauge_observation_override
        return self._data.gauge_observation

    @gauge_observation.setter
    def gauge_observation(self, val: Optional[Union[str, int, float]]) -> None:
        if val is not None:
            if isinstance(val, str) and (len(val) == 0 or not val.replace(".", "", 1).isnumeric()):
                val = None
            else:
                val = float(val)
        self._gauge_observation_override = val

    @cached_property
    def gauge_id(self) -> Optional[str]:
        return self._data.gauge_id

    @cached_property
    def gauge_source(self) -> Optional[str]:
        """Source for the gauge."""
        return self._data.gauge_source

    @cached_property
    def gauge_units(self) -> Optional[str]:
        """Gauge units (e.g. cfs)."""
        return self._data.gauge_units

    @cached_property
    def gauge_metric(self) -> Optional[str]:
        """Gauge metric, typically cfs or cms."""
        return self.gauge_units

    @cached_property
    def edited_timestamp(self) -> Optional[datetime]:
        """Date last modified."""
        val = self._data.edited_at
        if val:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        return None

    @cached_property
    def update_timestamp(self) -> Optional[datetime]:
        """Date last updated (from updatedAt Unix epoch integer)."""
        val = self._data.updated_at
        if val is not None:
            return datetime.fromtimestamp(val, tz=timezone.utc)
        return None

    @cached_property
    def difficulty(self) -> Optional[str]:
        """Reach difficulty."""
        return self._data.difficulty

    def _lookup_difficulty(self) -> None:
        """Helper to assign difficulty parts from single difficulty string."""
        if self.difficulty is None:
            return
        (
            self._difficulty_minimum,
            self._difficulty_maximum,
            self._difficulty_outlier,
        ) = utils.get_difficulty_parts(self.difficulty)

    @property
    def difficulty_minimum(self) -> Optional[str]:
        if self._difficulty_minimum is None:
            self._lookup_difficulty()
        return self._difficulty_minimum

    @property
    def difficulty_maximum(self) -> Optional[str]:
        if self._difficulty_maximum is None:
            self._lookup_difficulty()
        return self._difficulty_maximum

    @property
    def difficulty_outlier(self) -> Optional[str]:
        if self._difficulty_outlier is None:
            self._lookup_difficulty()
        return self._difficulty_outlier

    @difficulty_minimum.setter
    def difficulty_minimum(self, val: Optional[str]) -> None:
        self._difficulty_minimum = val

    @difficulty_maximum.setter
    def difficulty_maximum(self, val: Optional[str]) -> None:
        self._difficulty_maximum = val

    @difficulty_outlier.setter
    def difficulty_outlier(self, val: Optional[str]) -> None:
        self._difficulty_outlier = val

    @cached_property
    def url(self) -> Optional[str]:
        """Web URL of the reach."""
        return self._data.url

    def _get_accesses_by_type(self, access_type: str) -> list["ReachPoint"]:
        if access_type not in ("putin", "takeout", "intermediate"):
            raise Exception(
                'access type must be either "putin", "takeout" or "intermediate"'
            )
        return [
            pt
            for pt in self.reach_points
            if pt.subtype == access_type and pt.point_type == "access"
        ]

    def _set_putin_takeout(self, access: "ReachPoint", access_type: str) -> None:
        """Set the putin or takeout using a ReachPoint object."""
        if not type(access) is ReachPoint:  # runtime type guard
            raise Exception(
                "{} access must be an instance of ReachPoint object type".format(access_type)
            )
        if access_type not in ("putin", "takeout"):
            raise Exception('access type must be either "putin" or "takeout"')
        # Ensure _reach_points is populated before mutating.
        pts = self.reach_points
        self._reach_points = [
            pt
            for pt in pts
            if not (pt.point_type == "access" and pt.subtype == access_type)
        ]
        access.point_type = "access"
        access.subtype = access_type
        self._reach_points.append(access)

    @property
    def putin(self) -> Optional["ReachPoint"]:
        access_lst = self._get_accesses_by_type("putin")
        return access_lst[0] if access_lst else None

    @putin.setter
    def putin(self, access: "ReachPoint") -> None:
        self._set_putin_takeout(access, "putin")

    @property
    def takeout(self) -> Optional["ReachPoint"]:
        access_lst = self._get_accesses_by_type("takeout")
        return access_lst[0] if access_lst else None

    @takeout.setter
    def takeout(self, access: "ReachPoint") -> None:
        self._set_putin_takeout(access, "takeout")

    @cached_property
    def intermediate_accesses(self):
        access_lst = self._get_accesses_by_type("intermediate")
        return access_lst if access_lst else None

    def add_intermediate_access(self, access: "ReachPoint") -> None:
        if not type(access) is ReachPoint:  # runtime type guard
            raise Exception(
                "intermediate access must be an instance of ReachPoint object type"
            )
        access.point_type = "access"
        access.subtype = "intermediate"
        pts = self.reach_points
        self._reach_points = pts
        self._reach_points.append(access)

    @cached_property
    def geometry(self) -> Optional[Polyline]:
        """Reach polyline geometry."""
        geom_json = self._data.geometry
        if geom_json is None:
            return None
        return Polyline(geom_json, sr=4326)

    @cached_property
    def wkt(self) -> Optional[str]:
        """Reach polyline geometry in WKT format."""
        return self.geometry.WKT if self.geometry is not None else None  # type: ignore[return-value]

    @cached_property
    def ewkt(self) -> Optional[str]:
        """Reach polyline geometry in EWKT format."""
        return self.geometry.EWKT if self.geometry is not None else None  # type: ignore[return-value]

    @cached_property
    def wkb(self) -> Optional[bytes]:
        """Reach polyline geometry in WKB format."""
        return self.geometry.WKB if self.geometry is not None else None  # type: ignore[return-value]

    @cached_property
    def geojson(self) -> Optional[dict[str, Any]]:
        """Reach polyline geometry in GeoJSON format."""
        return self.geometry.__geo_interface__ if self.geometry is not None else None  # type: ignore[return-value]

    @cached_property
    def attributes(self) -> dict[str, Any]:
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
