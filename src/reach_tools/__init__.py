__title__ = "reach-tools"
__version__ = "0.1.0.dev0"
__author__ = "Joel McCune (https://github.com/knu2xs)"
__license__ = "Apache 2.0"
__copyright__ = "Copyright 2023 by Joel McCune (https://github.com/knu2xs)"

__all__ = ["Reach", "ReachPoint", "utils"]

import json
from datetime import datetime
from functools import cached_property
from hashlib import md5
from pathlib import Path
from typing import Union

import numpy as np
from arcgis.features import Feature
from arcgis.geometry import Geometry, Polygon, Polyline, Point
import pandas as pd

from . import utils
from .utils import strip_html_tags, cleanup_string
from .utils.reference import lookup_dict
from .utils.procure import download_raw_json_from_aw


class ReachPoint(object):
    """
    Discrete object facilitating working with reach points.
    """

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
        self.description: str = None if description is None else cleanup_string(description)
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
    def from_aw_json(cls, aw_json: dict) -> "ReachPoint":
        """Create a Reach Point from point (rapids) JSON."""
        # check for a couple of keys to ensure have the right object
        if not isinstance(aw_json, dict) or (
            "name" not in aw_json.keys() and "reach_id" not in aw_json.keys()
        ):
            raise ValueError(
                "Please provide a single JSON point JSON (rapids list item)."
            )

        # initialize subtype
        subtyp = None

        # determine the type and subtype based on the "is" properties
        if aw_json.get("isputin") == 1:
            typ, subtyp = "access", "putin"
        elif aw_json.get("istakeout") == 1:
            typ, subtyp = "access", "takeout"
        elif aw_json.get("access") == 1:
            typ, subtyp = "access", "intermediate"
        elif aw_json.get("israpid") == 1:
            typ = "rapid"
        elif aw_json.get("ishazard") == 1:
            typ = "hazard"
        else:
            typ = "generic"

        if aw_json.get("isportage") == 1:
            subtyp = "portage"
        elif aw_json.get("iswaterfall") == 1:
            subtyp = "waterfall"
        elif aw_json.get("isplayspot") == 1:
            subtyp = "playspot"

        # build the geometry
        geom = (
            Geometry(aw_json.get("rloc")) if aw_json.get("rloc") is not None else None
        )

        # get the update date, as a datetime
        update_dt = (
            datetime.fromisoformat(aw_json.get("updatedate"))
            if aw_json.get("updatedate") is not None
            else None
        )

        # create a point with the correct properties
        pt = ReachPoint(
            reach_id=aw_json.get("reach_id"),
            geometry=geom,
            point_type=typ,
            subtype=subtyp,
            name=aw_json.get("name"),
            side_of_river=aw_json.get("side_of_river"),
            update_date=update_dt,
            description=aw_json.get("description_md"),
            difficulty=aw_json.get("difficulty"),
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
        geom = self._geometry
        return geom

    @geometry.setter
    def geometry(self, geometry):
        if not isinstance(geometry, Point):
            raise Exception(
                "access geometry must be a valid ArcGIS Point Geometry object"
            )
        else:
            self._geometry = geometry

    @property
    def side_of_river(self):
        """Which side of the river, when facing downstream (left or right), the access is on."""
        return self._side_of_river

    @side_of_river.setter
    def side_of_river(self, side_of_river):
        # ensure lowercase
        if isinstance(side_of_river, str):
            side_of_river = side_of_river.lower()

        # if a string, ensure is left or right
        if isinstance(side_of_river, str) and (
            side_of_river != "left" and side_of_river != "right"
        ):
            raise Exception('side of river must be either "left" or "right"')
        else:
            self._side_of_river = side_of_river

    @cached_property
    def feature(self):
        """
        Get the access as an ArcGIS Python API Feature object.
        :return: ArcGIS Python API Feature object representing the access.
        """
        return Feature(
            geometry=self.geometry,
            attributes={
                key: vars(self)[key]
                for key in vars(self).keys()
                if key != "_geometry" and not key.startswith("_")
            },
        )

    @cached_property
    def dictionary(self):
        """
        Get the point as a dictionary of values making it easier to build DataFrames.
        :return: Dictionary of all properties, with a little modification for geometries.
        """
        dict_point = {
            key: vars(self)[key] for key in vars(self).keys() if not key.startswith("_")
        }
        dict_point["SHAPE"] = self.geometry
        return dict_point


class Reach(object):

    def __init__(self, reach_id):

        self.reach_id = str(reach_id)
        self._raw_json: dict = None
        self._main_json: dict = None
        self._rapids_json: list[dict] = None
        self.error: bool = None
        self.notes: str = None
        self.validated: bool = None
        self.validated_by: str = None
        self._geometry: Polyline = None
        self._reach_points: list[ReachPoint] = []
        self.agency: str = None
        self._gauge_observation: Union[int, float] = None
        self._difficulty_minimum: str = None
        self._difficulty_maximum: str = None
        self._difficulty_outlier: str = None
        self._gauge_id: str = None
        self._gauge_metric: str = None
        self.source = None

    def __str__(self):
        return f"{self.river_name} - {self.reach_name} - {self.difficulty}"

    def __repr__(self):
        return f"{self.__class__.__name__} ({self.river_name} - {self.reach_name} - {self.difficulty})"

    @property
    def _raw_json(self) -> dict:
        """Access saved raw JSON"""
        return self._raw_json

    @_raw_json.setter
    def _raw_json(self, raw_json: dict) -> None:
        """When setting raw JSON, make different blocks easily accessible."""
        if raw_json is not None:
            # hydrate main json
            if "CContainerViewJSON_view" in raw_json.keys():
                self._main_json = raw_json["CContainerViewJSON_view"].get(
                    "CRiverMainGadgetJSON_main"
                )
            elif "CRiverMainGadgetJSON_main" in raw_json.keys():
                self._main_json = raw_json.get("CRiverMainGadgetJSON_main")
            else:
                self._main_json = raw_json

            # hydrate rapids list
            if "CContainerViewJSON_view" in raw_json.keys():
                rapids_dict = raw_json["CContainerViewJSON_view"].get(
                    "CRiverRapidsGadgetJSON_view-rapids"
                )
            elif "CRiverMainGadgetJSON_rapids" in raw_json.keys():
                rapids_dict = raw_json.get("CRiverRapidsGadgetJSON_view-rapids")
            else:
                rapids_dict = raw_json

            if "rapids" in rapids_dict.keys():
                self._rapids_json = rapids_dict.get("rapids")

    @cached_property
    def difficulty_filter(self) -> float:
        val = lookup_dict.get(self.difficulty_maximum)
        return val

    @property
    def reach_points(self) -> list[ReachPoint]:
        """List of reach point objects."""
        # if there are not any points hydrated yet
        if len(self._reach_points) == 0 and self._rapids_json is not None:

            # hydrate reach points from the json
            self._reach_points = [
                ReachPoint.from_aw_json(pt_json) for pt_json in self._rapids_json
            ]

        return self._reach_points

    @cached_property
    def reach_points_features(self):
        """
        Get all the reach points as a list of features.
        :return: List of ArcGIS Python API Feature objects.
        """
        return [pt.to_feature for pt in self._reach_points]

    @cached_property
    def reach_points_dataframe(self):
        """
        Get the reach points as an Esri Spatially Enabled Pandas DataFrame.
        :return:
        """
        df_pt = pd.DataFrame([pt.to_dictionary for pt in self._reach_points])
        df_pt.spatial.set_geometry("SHAPE")
        return df_pt

    @cached_property
    def centroid(self) -> Point:
        """
        Get a point geometry centroid for the hydroline.

        :return: Point Geometry
            Centroid representing the reach location as a point.
        """
        # if the hydroline is defined, use the centroid of the hydroline extent
        if isinstance(self.geometry, Polyline):

            xmin, ymin, xmax, ymax = self.geometry.extent

            cntr = Geometry(
                {
                    "x": (xmax - xmin) / 2 + xmin,
                    "y": (ymax - ymin) / 2 + ymin,
                    "spatialReference": self.geometry.spatial_reference,
                }
            )

        # if both accesses are defined, use the mean of the accesses
        elif isinstance(self.putin, ReachPoint) and isinstance(
            self.takeout, ReachPoint
        ):

            # create a point geometry using the average coordinates
            cntr = Geometry(
                {
                    "x": np.mean([self.putin.geometry.x, self.takeout.geometry.x]),
                    "y": np.mean([self.putin.geometry.y, self.takeout.geometry.y]),
                    "spatialReference": self.putin.geometry.spatial_reference,
                }
            )

        # if only the putin is defined, use that
        elif isinstance(self.putin, ReachPoint):
            cntr = self.putin.geometry

        # and if on the takeout is defined, likely the person digitizing was taking too many hits from the bong
        elif isinstance(self.takeout, ReachPoint):
            cntr = self.takeout.geometry

        else:
            cntr = None

        return cntr

    @cached_property
    def extent(self) -> tuple[float, float, float, float]:
        """Provide the extent of the reach as (xmin, ymin, xmax, ymax)"""
        val = self._main_json.get("info").get("bbox")
        return val

    @cached_property
    def extent_polygon(self) -> Polygon:
        """Provide the extent of the reach as a Polygon."""
        # get the extent parts
        xmin, ymin, xmax, ymax = self.extent

        # create the polygon extent
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
    def gauge_min(self) -> float:
        """Minimum runnable gauge value."""
        # get the values from the AW JSON dict
        res = list(
            zip(
                *(
                    utils.aw.get_gauge_value_list(
                        self._main_json.get("guagesummary").get("ranges")
                    )
                )
            )
        )

        # ensure there are values to with
        if len(res) != 2:
            min_val = None

        # get the minimum value, if values exist
        else:
            val_lst = res[1]
            min_val = min(val_lst) if len(val_lst) > 0 else None

        return min_val

    @cached_property
    def gauge_max(self) -> float:
        """Maximum runnable gauge value."""
        # get the values from the AW JSON dict
        res = list(
            zip(
                *(
                    utils.aw.get_gauge_value_list(
                        self._main_json.get("guagesummary").get("ranges")
                    )
                )
            )
        )

        # ensure there are values to with
        if len(res) != 2:
            max_val = None

        # get the minimum value, if values exist
        else:
            val_lst = res[1]
            max_val = max(val_lst) if len(val_lst) > 0 else None

        return max_val

    @property
    def runnable(self) -> bool:
        """Whether the reach is runnable."""
        return utils.aw.get_runnable(self._main_json, self.gauge_observation)

    @cached_property
    def gauge_stage(self) -> str:
        """Human-readable interpretation of current gauge stage runnability."""
        if isinstance(self.gauge_observation, (int, float)) and (
            isinstance(self.gauge_max, (int, float))
            or isinstance(self.gauge_min, (int, float))
        ):
            stage = utils.aw.get_stage(self._main_json, self.gauge_observation)
        else:
            stage = None
        return stage

    @cached_property
    def river_name(self):
        """Name of the River."""
        val = utils.aw.get_key_from_block(self._main_json.get("info"), "river")
        val = utils.remove_backslashes(val)
        return val

    @cached_property
    def reach_name(self):
        """Name of the reach (section)."""
        val = utils.aw.get_key_from_block(self._main_json.get("info"), "section")
        val = utils.remove_backslashes(val)
        return val

    @cached_property
    def section_name(self):
        """Name of section (reach)."""
        return self.reach_name

    @cached_property
    def alternate_name(self):
        """Alternate name for the reach (section)."""
        val = utils.aw.get_key_from_block(self._main_json.get("info"), "section")
        val = utils.remove_backslashes(val)
        return val

    @cached_property
    def description(self):
        """Description of the reach."""
        val = utils.aw.get_key_from_block(self._main_json.get("info"), "description_md")
        return val

    @cached_property
    def abstract(self):
        """Abstract (short description) of the reach."""
        val = utils.aw.get_key_from_block(self._main_json.get("info"), "abstract_md")

        # if there is not an abstract, create one from the description
        if (val is None or len(val) == 0) and (
            self.description is not None and len(self.description) > 0
        ):

            # remove all line returns, html tags, trim to 500 characters, and trim to last space to ensure full word
            val = self.description.replace("\\", "").replace("/n", "")[:500]
            val = val[: val.rfind(" ")]
            val = val + "..."

        return val

    @cached_property
    def length(self) -> float:
        val = utils.aw.get_key_from_block(self._main_json.get("info"), "length")

        # make sure returning a float
        if isinstance(val, int) or (isinstance(val, str) and val.isnumeric()):
            val = float(val)

        return val

    @cached_property
    def has_gauge(self) -> bool:
        """Boolean indicating if gauge information is available."""
        if (
            self._main_json.get("gauges") is not None
            and len(self._main_json.get("gauges")) > 0
        ):
            val = True
        else:
            val = False

        return val

    @property
    def gauge_observation(self) -> float:
        """Gage observation (stage)."""
        # if nothing already saved and data is available, set it
        if self._gauge_observation is None and self.has_gauge:
            obs = self._main_json.get("gauges")[0].get("gauge_reading")
            if (isinstance(obs, str) and obs.isnumeric()) or isinstance(obs, int):
                self._gauge_observation = float(obs)

        return self._gauge_observation

    @gauge_observation.setter
    def gauge_observation(self, val: Union[str, int, float]) -> None:
        if val is not None:
            if isinstance(val, str) and (len(val) == 0 or not val.isnumeric()):
                val = None
            else:
                val = float(val)

            self.gauge_observation = val

    @cached_property
    def gauge_id(self) -> str:
        if self.has_gauge and self._gauge_id is None:
            self._gauge_id = str(self._main_json.get("gauges")[0].get("gauge_id"))
        return self._gauge_id

    @cached_property
    def gauge_source(self) -> str:
        """Source for the gauge."""
        if self.has_gauge:
            val = self._main_json.get("gauges")[0].get("source")
        else:
            val = None
        return val

    @cached_property
    def gauge_metric(self) -> str:
        """Gauge metric, typically feet, inches, meters, cfs (cubic feet per second) or cms (cubic meters per second)."""
        if self.has_gauge and self._gauge_metric is None:
            self._gauge_metric = self._main_json.get("gauges")[0].get("metric_unit")

        return self._gauge_metric

    @cached_property
    def edited_timestamp(self) -> datetime:
        """Date last modified."""
        val = self._main_json.get("info").get("edited")
        val = datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
        return val

    @cached_property
    def difficulty(self) -> str:
        """Reach difficulty."""
        val = self._main_json.get("info").get("class")
        return val

    def _lookup_difficulty(self):
        """Helper to assign difficulty parts from single difficultly string."""

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
    def update_timestamp(self):
        val = self._main_json.get("info").get("updated_at")
        val_dt = datetime.fromisoformat(val)
        return val_dt

    @cached_property
    def url(self) -> str:
        """Web URL of the reach."""
        val = f"https://www.americanwhitewater.org/content/River/view/river-detail/{self.reach_id}/main"
        return val

    @classmethod
    def from_aw(cls, reach_id: Union[str, int]) -> "Reach":
        """
        Get a reach by retrieving JSON directly from American Whitewater.

        Args:
            reach_id: American Whitewater reach ID.
        """
        # download raw JSON from American Whitewater
        raw_json = download_raw_json_from_aw(reach_id)

        # if a reach exists, make something to work with
        if not raw_json:
            reach = cls.from_aw_json(raw_json)

        # if a reach does not exist at url, simply a blank response, nothing to return
        else:
            reach = None

        return reach

    @classmethod
    def from_aw_json(cls, raw_aw_json: Union[dict, Path]) -> "Reach":
        """
        Create a reach from a raw AW JSON string representation of reach data.

        Args:
            raw_aw_json: Raw AW JSON string representation of reach data.
        """
        # if provided a path to JSON
        if isinstance(raw_aw_json, Path):
            with open(raw_aw_json, "r") as f:
                raw_aw_json = json.load(f)

        # extract the reach_id from the JSON
        reach_id = (
            raw_aw_json.get("CContainerViewJSON_view")
            .get("CRiverMainGadgetJSON_main")
            .get("info")
            .get("id")
        )

        # create instance of reach
        reach = cls(reach_id)

        # load the JSON into the reach
        reach._raw_json = raw_aw_json

        # set the source
        reach.source = "american_whitewater"

        return reach

    def _get_accesses_by_type(self, access_type):

        # check to ensure the correct access type is being specified
        if (
            access_type != "putin"
            and access_type != "takeout"
            and access_type != "intermediate"
        ):
            raise Exception(
                'access type must be either "putin", "takeout" or "intermediate"'
            )

        # return list of all accesses of specified type
        pt_lst = [
            pt
            for pt in self._reach_points
            if pt.subtype == access_type and pt.point_type == "access"
        ]

        return pt_lst

    def _set_putin_takeout(self, access, access_type):
        """
        Set the putin or takeout using a ReachPoint object.
        :param access: ReachPoint - Required
            ReachPoint geometry delineating the location of the geometry to be modified.
        :param access_type: String - Required
            Either "putin" or "takeout".
        :return:
        """
        # enforce correct object type
        if type(access) != ReachPoint:
            raise Exception(
                "{} access must be an instance of ReachPoint object type".format(
                    access_type
                )
            )

        # check to ensure the correct access type is being specified
        if access_type != "putin" and access_type != "takeout":
            raise Exception('access type must be either "putin" or "takeout"')

        # update the list to NOT include the point we are adding
        self._reach_points = [
            pt
            for pt in self._reach_points
            if not (pt.point_type == "access" and pt.subtype == access_type)
        ]

        # ensure the new point being added is the correct type
        access.point_type = "access"
        access.subtype = access_type

        # add it to the reach point list
        self._reach_points.append(access)

    @property
    def putin(self):
        access_df = self._get_accesses_by_type("putin")
        if len(access_df) > 0:
            return access_df[0]
        else:
            return None

    @putin.setter
    def putin(self, access):
        self._set_putin_takeout(access, "putin")

    @property
    def takeout(self):
        access_lst = self._get_accesses_by_type("takeout")
        if len(access_lst) > 0:
            return access_lst[0]
        else:
            return None

    @takeout.setter
    def takeout(self, access):
        self._set_putin_takeout(access, "takeout")

    @cached_property
    def intermediate_accesses(self):
        access_lst = self._get_accesses_by_type("intermediate")
        if len(access_lst) > 0:
            return access_lst
        else:
            return None

    def add_intermediate_access(self, access):
        if not isinstance(access, ReachPoint):
            raise Exception(
                "intermediate access must be an instance of ReachPoint object type"
            )
        access.point_type = "access"
        access.subtype = "intermediate"
        self._reach_points.append(access)

    @cached_property
    def geometry(self) -> Polygon:
        """Reach polyline geometry."""
        geojson = self._main_json.get("info").get("geom")
        if geojson is None:
            geom = None
        else:
            geom = Polygon(geojson, sr=4326)
        return geom

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
        # list of properties to retrieve
        prop_lst = [
            "abstract",
            "description",
            "difficulty",
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
            "length",
            "name",
            "notes",
            "reach_id",
            "river_name",
            "runnable",
            "section_name",
            "source",
            "uid",
            "url",
        ]

        # create a dictionary of properties
        properties = {k: getattr(self, k) for k in prop_lst}

        return properties

    @property
    def uid(self) -> str:
        """Universal unique identifier created by hashing the source and reach_id."""
        comb_str = self.source + self.reach_id
        hsh = md5(comb_str.encode()).hexdigest()
        return hsh

    @property
    def line_feature(self) -> Feature:
        """ArcGIS Python API line Feature object for the reach."""
        if self.geometry:
            feat = Feature(geometry=self.geometry, attributes=self.attributes)
        else:
            feat = Feature(attributes=self.attributes)
        return feat

    @property
    def centroid_feature(self) -> Feature:
        """ArcGIS Python API point Feature object for the reach."""
        feat = Feature(geometry=self.centroid, attributes=self.attributes)
        return feat
