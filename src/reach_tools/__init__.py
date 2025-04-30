__title__ = "reach-tools"
__version__ = "0.1.0.dev0"
__author__ = "Joel McCune (https://github.com/knu2xs)"
__license__ = "Apache 2.0"
__copyright__ = "Copyright 2023 by Joel McCune (https://github.com/knu2xs)"

__all__ = ["Reach", "ReachPoint", "utils"]

from datetime import datetime
from functools import cached_property
import re
from typing import Union
from uuid import uuid4

import numpy as np
from arcgis.features import Feature
from arcgis.geometry import Geometry, Polyline, Point
import pandas as pd
import requests

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
        self.reach_name = ""
        self.reach_name_alternate = ""
        self.river_name = ""
        self.river_name_alternate = ""
        self.error = None  # boolean
        self.notes = ""
        self.difficulty = ""
        self.difficulty_minimum = ""
        self.difficulty_maximum = ""
        self.difficulty_outlier = ""
        self.abstract = ""
        self.description = ""
        self.update_aw = None  # datetime
        self.validated = None  # boolean
        self.validated_by = ""
        self._geometry = None
        self._reach_points = []
        self.agency = None
        self.gauge_observation = None
        self.gauge_id = None
        self.gauge_units = None
        self.gauge_metric = None
        self.gauge_r0 = None
        self.gauge_r1 = None
        self.gauge_r2 = None
        self.gauge_r3 = None
        self.gauge_r4 = None
        self.gauge_r5 = None
        self.gauge_r6 = None
        self.gauge_r7 = None
        self.gauge_r8 = None
        self.gauge_r9 = None

    def __str__(self):
        return f"{self.river_name} - {self.reach_name} - {self.difficulty}"

    def __repr__(self):
        return f"{self.__class__.__name__ } ({self.river_name} - {self.reach_name} - {self.difficulty})"

    @cached_property
    def putin_x(self):
        return self.putin.geometry.x

    @cached_property
    def putin_y(self):
        return self.putin.geometry.y

    @cached_property
    def takeout_x(self):
        return self.takeout.geometry.x

    @cached_property
    def takeout_y(self):
        return self.takeout.geometry.y

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
    def extent(self):
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
    def reach_search(self):
        if len(self.river_name) and len(self.reach_name):
            return f"{self.river_name} {self.reach_name}"
        elif len(self.river_name) and not len(self.reach_name):
            return self.river_name
        elif len(self.reach_name) and not len(self.river_name):
            return self.reach_name
        else:
            return ""

    @cached_property
    def has_a_point(self):
        if self.putin is None and self.takeout is None:
            return False

        elif self.putin.geometry.type == "Point" or self.putin.geometry == "Point":
            return True

        else:
            return False

    @cached_property
    def gauge_min(self):
        gauge_min_lst = [
            self.gauge_r0,
            self.gauge_r1,
            self.gauge_r2,
            self.gauge_r3,
            self.gauge_r4,
            self.gauge_r5,
        ]
        gauge_min_lst = [val for val in gauge_min_lst if val is not None]
        if len(gauge_min_lst):
            return min(gauge_min_lst)
        else:
            return None

    @cached_property
    def gauge_max(self):
        gauge_max_lst = [
            self.gauge_r4,
            self.gauge_r5,
            self.gauge_r6,
            self.gauge_r7,
            self.gauge_r8,
            self.gauge_r9,
        ]
        gauge_max_lst = [val for val in gauge_max_lst if val is not None]
        if len(gauge_max_lst):
            return max(gauge_max_lst)
        else:
            return None

    @property
    def gauge_runnable(self):
        if (self.gauge_min and self.gauge_max and self.gauge_observation) and (
            self.gauge_min < self.gauge_observation < self.gauge_max
        ):
            return True
        else:
            return False

    @cached_property
    def gauge_stage(self):
        metric_keys = [
            "gauge_r0",
            "gauge_r1",
            "gauge_r2",
            "gauge_r3",
            "gauge_r4",
            "gauge_r5",
            "gauge_r6",
            "gauge_r7",
            "gauge_r8",
            "gauge_r9",
        ]

        def get_metrics(metric_keys):
            metrics = [getattr(self, key) for key in metric_keys]
            metrics = list(set(val for val in metrics if val is not None))
            metrics.sort()
            return metrics

        metrics = get_metrics(metric_keys)
        if not len(metrics):
            return None

        low_metrics = get_metrics(metric_keys[:6])
        high_metrics = get_metrics(metric_keys[5:])

        if not self.gauge_observation:
            return "no gauge reading"

        if self.gauge_observation < metrics[0]:
            return "too low"
        if self.gauge_observation > metrics[-1]:
            return "too high"

        if len(metrics) == 2 or (len(metrics) == 1 and len(high_metrics) > 0):
            return "runnable"

        if len(metrics) == 3:
            if metrics[0] < self.gauge_observation < metrics[1]:
                return "lower runnable"
            if metrics[1] < self.gauge_observation < metrics[2]:
                return "higher runnable"

        if len(metrics) == 4:
            if metrics[0] < self.gauge_observation < metrics[1]:
                return "low"
            if metrics[1] < self.gauge_observation < metrics[2]:
                return "medium"
            if metrics[2] < self.gauge_observation < metrics[3]:
                return "high"

        if len(metrics) == 5 and len(low_metrics) > len(high_metrics):
            if metrics[0] < self.gauge_observation < metrics[1]:
                return "very low"
            if metrics[1] < self.gauge_observation < metrics[2]:
                return "medium low"
            if metrics[2] < self.gauge_observation < metrics[3]:
                return "medium"
            if metrics[3] < self.gauge_observation < metrics[4]:
                return "high"

        if len(metrics) == 5 and len(low_metrics) < len(high_metrics):
            if metrics[0] < self.gauge_observation < metrics[1]:
                return "low"
            if metrics[1] < self.gauge_observation < metrics[2]:
                return "medium"
            if metrics[2] < self.gauge_observation < metrics[3]:
                return "medium high"
            if metrics[3] < self.gauge_observation < metrics[4]:
                return "very high"

        if len(metrics) == 6:
            if metrics[0] < self.gauge_observation < metrics[1]:
                return "low"
            if metrics[1] < self.gauge_observation < metrics[2]:
                return "medium low"
            if metrics[2] < self.gauge_observation < metrics[3]:
                return "medium"
            if metrics[3] < self.gauge_observation < metrics[4]:
                return "medium high"
            if metrics[4] < self.gauge_observation < metrics[5]:
                return "high"

        if len(metrics) == 7 and len(low_metrics) > len(high_metrics):
            if metrics[0] < self.gauge_observation < metrics[1]:
                return "very low"
            if metrics[1] < self.gauge_observation < metrics[2]:
                return "low"
            if metrics[2] < self.gauge_observation < metrics[3]:
                return "medium low"
            if metrics[3] < self.gauge_observation < metrics[4]:
                return "medium"
            if metrics[4] < self.gauge_observation < metrics[5]:
                return "medium high"
            if metrics[5] < self.gauge_observation < metrics[6]:
                return "high"

        if len(metrics) == 7 and len(low_metrics) < len(high_metrics):
            if metrics[0] < self.gauge_observation < metrics[1]:
                return "low"
            if metrics[1] < self.gauge_observation < metrics[2]:
                return "medium low"
            if metrics[2] < self.gauge_observation < metrics[3]:
                return "medium"
            if metrics[3] < self.gauge_observation < metrics[4]:
                return "medium high"
            if metrics[4] < self.gauge_observation < metrics[5]:
                return "high"
            if metrics[5] < self.gauge_observation < metrics[6]:
                return "very high"

        if len(metrics) == 8:
            if metrics[0] < self.gauge_observation < metrics[1]:
                return "very low"
            if metrics[1] < self.gauge_observation < metrics[2]:
                return "low"
            if metrics[2] < self.gauge_observation < metrics[3]:
                return "medium low"
            if metrics[3] < self.gauge_observation < metrics[4]:
                return "medium"
            if metrics[4] < self.gauge_observation < metrics[5]:
                return "medium high"
            if metrics[5] < self.gauge_observation < metrics[6]:
                return "high"
            if metrics[6] < self.gauge_observation < metrics[7]:
                return "very high"

        if len(metrics) == 9 and len(low_metrics) > len(high_metrics):
            if metrics[0] < self.gauge_observation < metrics[1]:
                return "extremely low"
            if metrics[1] < self.gauge_observation < metrics[2]:
                return "very low"
            if metrics[2] < self.gauge_observation < metrics[3]:
                return "low"
            if metrics[3] < self.gauge_observation < metrics[4]:
                return "medium low"
            if metrics[4] < self.gauge_observation < metrics[5]:
                return "medium"
            if metrics[5] < self.gauge_observation < metrics[6]:
                return "medium high"
            if metrics[6] < self.gauge_observation < metrics[7]:
                return "high"
            if metrics[7] < self.gauge_observation < metrics[8]:
                return "very high"

        if len(metrics) == 9 and len(low_metrics) > len(high_metrics):
            if metrics[0] < self.gauge_observation < metrics[1]:
                return "very low"
            if metrics[1] < self.gauge_observation < metrics[2]:
                return "low"
            if metrics[2] < self.gauge_observation < metrics[3]:
                return "medium low"
            if metrics[3] < self.gauge_observation < metrics[4]:
                return "medium"
            if metrics[4] < self.gauge_observation < metrics[5]:
                return "medium high"
            if metrics[5] < self.gauge_observation < metrics[6]:
                return "high"
            if metrics[6] < self.gauge_observation < metrics[7]:
                return "very high"
            if metrics[7] < self.gauge_observation < metrics[8]:
                return "extremely high"

        if len(metrics) == 10:
            if metrics[0] < self.gauge_observation < metrics[1]:
                return "extremely low"
            if metrics[1] < self.gauge_observation < metrics[2]:
                return "very low"
            if metrics[2] < self.gauge_observation < metrics[3]:
                return "low"
            if metrics[3] < self.gauge_observation < metrics[4]:
                return "medium low"
            if metrics[4] < self.gauge_observation < metrics[5]:
                return "medium"
            if metrics[5] < self.gauge_observation < metrics[6]:
                return "medium high"
            if metrics[6] < self.gauge_observation < metrics[7]:
                return "high"
            if metrics[7] < self.gauge_observation < metrics[8]:
                return "very high"
            if metrics[8] < self.gauge_observation < metrics[9]:
                return "extremely high"

    def _parse_difficulty_string(self, difficulty_combined):
        match = re.match(
            r"^([I|IV|V|VI|5\.\d]{1,3}(?=-))?-?([I|IV|V|VI|5\.\d]{1,3}[+|-]?)\(?([I|IV|V|VI|5\.\d]{0,3}[+|-]?)",
            difficulty_combined,
        )

        # helper function to get difficulty parts
        get_if_match = lambda match_string: (
            match_string if match_string and len(match_string) else None
        )

        self.difficulty_minimum = get_if_match(match.group(1))
        self.difficulty_maximum = get_if_match(match.group(2))
        self.difficulty_outlier = get_if_match(match.group(3))

    @staticmethod
    def _validate_aw_json(json_block, key):

        # check to ensure a value exists
        if key not in json_block.keys():
            return None

        # ensure there is a value for the key
        elif json_block[key] is None:
            return None

        else:

            # clean up the text garbage...because there is a lot of it
            value = cleanup_string(json_block[key])

            # now, ensure something is still there...not kidding, this frequently is the case...it is all gone
            if not value:
                return None
            elif not len(value):
                return None

            else:
                # now check to ensure there is actually some text in the block, not just blank characters
                if not (re.match(r"^([ \r\n\t])+$", value) or not (value != "N/A")):

                    # if everything is good, return a value
                    return value

                else:
                    return None

    def _load_properties_from_aw_json(self, raw_json: dict):

        def remove_backslashes(input_str: str) -> str:
            if isinstance(input_str, str) and len(input_str):
                return input_str.replace("\\", "")
            else:
                return input_str

        # pluck out the stuff we are interested in
        self._reach_json = raw_json["CContainerViewJSON_view"][
            "CRiverMainGadgetJSON_main"
        ]

        # pull a bunch of attributes through validation and save as properties
        reach_info = self._reach_json["info"]
        self.river_name = self._validate_aw_json(reach_info, "river")

        self.reach_name = remove_backslashes(
            self._validate_aw_json(reach_info, "section")
        )
        self.reach_alternate_name = remove_backslashes(
            self._validate_aw_json(reach_info, "altname")
        )

        self.huc = self._validate_aw_json(reach_info, "huc")
        self.description = self._validate_aw_json(reach_info, "description")
        self.abstract = self._validate_aw_json(reach_info, "abstract")
        self.agency = self._validate_aw_json(reach_info, "agency")
        length = self._validate_aw_json(reach_info, "length")
        if length:
            self.length = float(length)

        # helper to extract gauge information
        def get_gauge_metric(gauge_info, metric):
            if metric in gauge_info.keys() and gauge_info[metric] is not None:
                return float(gauge_info[metric])

        # get the gauge information
        if len(self._reach_json["gauges"]):
            gauge_info = self._reach_json["gauges"][0]

            self.gauge_observation = get_gauge_metric(gauge_info, "gauge_reading")
            self.gauge_id = gauge_info["gauge_id"]
            self.gauge_units = gauge_info["metric_unit"]
            self.gauge_metric = gauge_info["gauge_metric"]

            for rng in self._reach_json["guagesummary"]["ranges"]:
                if rng["range_min"] and rng["gauge_min"]:
                    setattr(
                        self,
                        f"gauge_{rng['range_min'].lower()}",
                        float(rng["gauge_min"]),
                    )
                if rng["range_max"] and rng["gauge_max"]:
                    setattr(
                        self,
                        f"gauge_{rng['range_max'].lower()}",
                        float(rng["gauge_max"]),
                    )

        # save the update datetime as a true datetime object
        if reach_info["edited"]:
            self.update_aw = datetime.strptime(
                reach_info["edited"], "%Y-%m-%d %H:%M:%S"
            )

        # process difficulty
        if len(reach_info["class"]) and reach_info["class"].lower() != "none":
            self.difficulty = self._validate_aw_json(reach_info, "class")
            self._parse_difficulty_string(str(self.difficulty))

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

        # if there is not an abstract, create one from the description
        if (not self.abstract or len(self.abstract) == 0) and (
            self.description and len(self.description) > 0
        ):

            # remove all line returns, html tags, trim to 500 characters, and trim to last space to ensure full word
            self.abstract = cleanup_string(reach_info["description_md"])
            self.abstract = self.abstract.replace("\\", "").replace("/n", "")[:500]
            self.abstract = self.abstract[: self.abstract.rfind(" ")]
            self.abstract = self.abstract + "..."

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

        # if a reach does not exist at url, simply a blank response, return false
        if not raw_json:
            return False

        # parse data out of the AW JSON
        reach = cls.from_aw_json(raw_json)

        # return the result
        return reach

    @classmethod
    def from_aw_json(cls, raw_aw_json: Union[str, dict]) -> "Reach":
        """
        Create a reach from a raw AW JSON string representation of reach data.

        Args:
            raw_aw_json: Raw AW JSON string representation of reach data.
        """
        # extract the reach_id from the JSON
        reach_id = raw_aw_json["CContainerViewJSON_view"]["CRiverMainGadgetJSON_main"][
            "info"
        ]["id"]

        # create instance of reach
        reach = cls(reach_id)

        # parse JSON into the object properties
        reach._load_properties_from_aw_json(raw_aw_json)

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

    @cached_property
    def putin(self):
        access_df = self._get_accesses_by_type("putin")
        if len(access_df) > 0:
            return access_df[0]
        else:
            return None

    def set_putin(self, access):
        self._set_putin_takeout(access, "putin")

    @cached_property
    def takeout(self):
        access_lst = self._get_accesses_by_type("takeout")
        if len(access_lst) > 0:
            return access_lst[0]
        else:
            return None

    def set_takeout(self, access):
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
        """ArcGIS Python API Feature object for the reach."""
        if self.geometry:
            feat = Feature(geometry=self.geometry, attributes=self.attributes)
        else:
            feat = Feature(attributes=self.attributes)
        return feat

    @property
    def centroid_feature(self) -> Feature:
        """
        Get a feature with the centroid geometry.
        :return: Feature with point geometry for the reach centroid.
        """
        feat = Feature(geometry=self.centroid, attributes=self.attributes)
        return feat

