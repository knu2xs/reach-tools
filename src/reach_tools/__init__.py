__title__ = "reach-tools"
__version__ = "0.1.0.dev0"
__author__ = "Joel McCune (https://github.com/knu2xs)"
__license__ = "Apache 2.0"
__copyright__ = "Copyright 2023 by Joel McCune (https://github.com/knu2xs)"

__all__ = ["Reach", "ReachPoint", "utils"]

from datetime import datetime
from functools import cached_property
from typing import Union
from uuid import uuid4

import numpy as np
from arcgis.features import Feature
from arcgis.geometry import Geometry, Polyline, Point
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
        uid=None,
        subtype=None,
        name=None,
        side_of_river=None,
        update_date=None,
        notes=None,
        description=None,
        difficulty=None,
        **kwargs,
    ):

        self.reach_id = str(reach_id)
        self.point_type = point_type
        self.subtype = subtype
        self.name = name
        self.update_date = update_date
        self.notes = notes
        self.description = description
        self.difficulty = difficulty
        self._geometry = None

        self.set_geometry(geometry)
        self.set_side_of_river(side_of_river)  # left or right

        if uid is None:
            self.uid = uuid4().hex
        else:
            self.uid = uid

    def __repr__(self):
        return f"{self.__class__.__name__ } ({self.reach_id} - {self.point_type} - {self.subtype})"

    @cached_property
    def type_id(self):
        id_list = [
            "null" if val is None else val
            for val in [self.reach_id, self.point_type, self.subtype]
        ]
        return "_".join(id_list)

    @cached_property
    def geometry(self):
        """Point geometry for the access."""
        return self._geometry

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

    def set_geometry(self, geometry):
        """
        Set the geometry for the point.

        Args:
            geometry: ArcGIS Python API Point Geometry object.
        """
        if not isinstance(geometry, Point):
            raise Exception(
                "access geometry must be a valid ArcGIS Point Geometry object"
            )
        else:
            self._geometry = geometry
            return True

    def set_side_of_river(self, side_of_river):
        """
        Set the side of the river the access is located on.

        Args:
            side_of_river: `left` or `right` when facing downstream.
        """
        # ensure lowercase
        if isinstance(side_of_river, str):
            side_of_river = side_of_river.lower()

        if (
            side_of_river is not None
            and side_of_river != "left"
            and side_of_river != "right"
        ):
            raise Exception('side of river must be either "left" or "right"')
        else:
            self.side_of_river = side_of_river

    @cached_property
    def feature(self):
        """
        Get the access as an ArcGIS Python API Feature object.
        :return: ArcGIS Python API Feature object representing the access.
        """
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
        self.error: bool = None  # boolean
        self.notes: str = None
        self.update_aw: datetime = None
        self.validated: bool = None
        self.validated_by: str = None
        self._geometry = None
        self._reach_points = []
        self.agency = None
        self.gauge_observation = None
        self.gauge_id = None
        self.gauge_units = None
        self.aw_json: dict = None

    def __str__(self):
        return f"{self.river_name} - {self.reach_name} - {self.difficulty}"

    def __repr__(self):
        return f"{self.__class__.__name__} ({self.river_name} - {self.reach_name} - {self.difficulty})"

    @property
    def aw_json(self) -> dict:
        return self.aw_json

    @aw_json.setter
    def aw_json(self, raw_json: dict) -> None:
        if "CContainerViewJSON_view" in raw_json.keys():
            self.aw_json = raw_json["CContainerViewJSON_view"].get(
                "CRiverMainGadgetJSON_main"
            )
        elif "CRiverMainGadgetJSON_main" in raw_json.keys():
            self.aw_json = raw_json.get("CRiverMainGadgetJSON_main")
        else:
            self.aw_json = raw_json

    @cached_property
    def difficulty_filter(self):
        return lookup_dict[self.difficulty_maximum]

    @cached_property
    def reach_points_features(self):
        """
        Get all the reach points as a list of features.
        :return: List of ArcGIS Python API Feature objects.
        """
        return [pt.as_feature for pt in self._reach_points]

    @cached_property
    def reach_points_dataframe(self):
        """
        Get the reach points as an Esri Spatially Enabled Pandas DataFrame.
        :return:
        """
        df_pt = pd.DataFrame([pt.as_dictionary for pt in self._reach_points])
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
        """
        Provide the extent of the reach as (xmin, ymin, xmax, ymax)
        :return: Set (xmin, ymin, xmax, ymax)
        """
        return (
            min(self.putin.geometry.x, self.takeout.geometry.x),
            min(self.putin.geometry.y, self.takeout.geometry.y),
            max(self.putin.geometry.x, self.takeout.geometry.x),
            max(self.putin.geometry.y, self.takeout.geometry.y),
        )

    @cached_property
    def name(self) -> str:
        if len(self.river_name) and len(self.reach_name):
            return f"{self.river_name} {self.reach_name}"
        elif len(self.river_name) and not len(self.reach_name):
            return self.river_name
        elif len(self.reach_name) and not len(self.river_name):
            return self.reach_name
        else:
            return ""

    @cached_property
    def gauge_min(self):
        # get the values from the AW JSON dict
        _, val_lst = zip(*(utils.aw.get_gauge_value_list(self.aw_json)))

        # get the minimum value, if values exist
        min_val = min(val_lst) if len(val_lst) > 0 else None

        return min_val

    @cached_property
    def gauge_max(self):
        # get the values from the AW JSON dict
        _, val_lst = zip(*(utils.aw.get_gauge_value_list(self.aw_json)))

        # get the minimum value, if values exist
        max_val = max(val_lst) if len(val_lst) > 0 else None

        return max_val

    @property
    def gauge_runnable(self):
        return utils.aw.get_runnable(self.aw_json, self.gauge_observation)

    @cached_property
    def gauge_stage(self):
        return utils.aw.get_stage(self.aw_json, self.gauge_observation)

    @cached_property
    def river_name(self):
        """Name of the River."""
        val = utils.aw.get_key_from_block(self.aw_json.get("info"), "river")
        val = utils.remove_backslashes(val)
        return val

    @cached_property
    def reach_name(self):
        """Name of the reach (section)."""
        val = utils.aw.get_key_from_block(self.aw_json.get("info"), "section")
        val = utils.remove_backslashes(val)
        return val

    @cached_property
    def section_name(self):
        """Name of section (reach)."""
        return self.reach_name

    @cached_property
    def alternate_name(self):
        """Alternate name for the reach (section)."""
        val = utils.aw.get_key_from_block(self.aw_json.get("info"), "section")
        val = utils.remove_backslashes(val)
        return val

    @cached_property
    def description(self):
        """Description of the reach."""
        val = utils.aw.get_key_from_block(self.aw_json.get("info"), "description_md")
        return val

    @cached_property
    def abstract(self):
        """Abstract (short description) of the reach."""
        val = utils.aw.get_key_from_block(self.aw_json.get("info"), "abstract_md")

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
        val = utils.aw.get_key_from_block(self.aw_json.get("info"), "length")

        # make sure returning a float
        if isinstance(val, int) or (isinstance(val, str) and val.isnumeric()):
            val = float(val)

        return val

    @property
    def gauge_observation(self) -> float:
        """Gage observation (stage)."""
        # if nothing already saved and data is available, set it
        if self.gauge_observation is None and self.aw_json.get("gauges") is not None:
            self.gauge_observation = self.aw_json.get("gauges").get("gauge_reading")

        return self.gauge_observation

    @gauge_observation.setter
    def gauge_observation(self, val: Union[str, int, float]) -> None:
        if isinstance(val, str) and (len(val) == 0 or not val.isnumeric()):
            val = None
        else:
            val = float(val)

        self.gauge_observation = val

    def gauge_id(self) -> str:
        if self.aw_json.get("gauges") is None:
            val = None
        else:
            val = self.aw_json.get("gauges").get("gauge_id")

        return val

    def gauge_units(self) -> str:
        if self.aw_json.get("gauges") is None:
            val = None
        else:
            val = self.aw_json.get("gauges").get("gauge_units")
        return val

    def gauge_metric(self) -> str:
        if self.aw_json.get("gauges") is None:
            val = None
        else:
            val = self.aw_json.get("gauges").get("gauge_metric")
        return val

    def edited(self) -> datetime:
        """Date last modified."""
        val = self.aw_json.get("info").get("edited")
        val = datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
        return val

    @property
    def difficulty_minimum(self) -> str:
        if self.difficulty_minimum is None:
            (
                self.difficulty_minimum,
                self.difficulty_maximum,
                self.difficulty_outlier,
            ) = utils.get_difficulty_parts(self.aw_json.get('gauges'))
        return self.difficulty_minimum

    @difficulty_minimum.setter
    def difficulty_minimum(self, val: str) -> None:
        self.difficulty_minimum = val

    def _load_properties_from_aw_json(self, raw_json: dict):

        # process difficulty
        if len(reach_info["class"]) and reach_info["class"].lower() != "none":
            self.difficulty = self._validate_aw_json(reach_info, "class")
            (
                self.difficulty_minimum,
                self.difficulty_maximum,
                self.difficulty_outlier,
            ) = utils.get_difficulty_parts(self.difficulty)

        # ensure putin coordinates are present, and if so, add the put-in point to the points list
        if reach_info["plon"] is not None and reach_info["plat"] is not None:
            pi_pt = ReachPoint(
                reach_id=self.reach_id,
                point_type="access",
                subtype="putin",
                geometry=Point(
                    {
                        "x": float(reach_info["plon"]),
                        "y": float(reach_info["plat"]),
                        "spatialReference": {"wkid": 4326},
                    }
                ),
            )
            self._reach_points.append(pi_pt)

        # ensure take-out coordinates are present, and if so, add take-out point to points list
        if reach_info["tlon"] is not None and reach_info["tlat"] is not None:
            to_pt = ReachPoint(
                reach_id=self.reach_id,
                point_type="access",
                subtype="takeout",
                geometry=Point(
                    {
                        "x": float(reach_info["tlon"]),
                        "y": float(reach_info["tlat"]),
                        "spatialReference": {"wkid": 4326},
                    }
                ),
            )
            self._reach_points.append(to_pt)

        # pull out the polyline geometry
        geojson = reach_info.get("geom")
        if geojson is not None:
            self._geometry = Polyline._from_geojson(geojson, sr=4326)

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
    def from_aw_json(cls, raw_aw_json: Union[str, dict]) -> "Reach":
        """
        Create a reach from a raw AW JSON string representation of reach data.

        Args:
            raw_aw_json: Raw AW JSON string representation of reach data.
        """
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
        reach.aw_json = raw_aw_json

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
            pt for pt in self._reach_points if pt.subtype != access_type
        ]

        # ensure the new point being added is the right type
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
        access_df = self._get_accesses_by_type("intermediate")
        if len(access_df) > 0:
            return access_df
        else:
            return None

    def add_intermediate_access(self, access):
        if not isinstance(access, ReachPoint):
            raise Exception(
                "intermediate access must be an instance of ReachPoint object type"
            )
        access.set_type("intermediate")
        self.access_list.append(access)

    @cached_property
    def geometry(self) -> Polyline:
        """Reach polyline geometry."""
        return self._geometry

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
        # list of those to exclude
        exclude_lst = [
            "putin",
            "takeout",
            "intermediate_accesses",
            "geometry",
            "has_a_point",
        ]

        # get properties to include in the reach
        property_keys = [
            k
            for k in self.__dict__.keys()
            if k not in exclude_lst and not k.startswith("_")
        ]

        # create a dictionary of properties
        properties = {k: getattr(self, k) for k in property_keys}

        return properties

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
