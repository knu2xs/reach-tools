"""American Whitewater data collector."""

import json
import time
from pathlib import Path
from typing import List, Optional, Union

import requests

from ..models import GaugeThreshold, PointData, ReachData
from ..utils import cleanup_string, remove_backslashes
from . import BaseCollector

__all__ = ["AWCollector", "get_runnable", "get_stage"]

_TRPC_URL = "https://trpc-api.americanwhitewater.org/reach/reachDetailWithPhotos"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.1.0.dev0 Safari/537.36 "
        "Edg/135.0.1.0.dev0"
    )
}
_MAX_RETRIES = 3


def download_raw_json_from_aw(aw_reach_id: Union[int, str]) -> Optional[dict]:
    """Download reach data from the American Whitewater tRPC API.

    Returns the unwrapped reach object dict, or None if the reach does not exist
    (HTTP 404). Retries up to 3 times with exponential backoff on transient errors.
    Raises an exception if all retries are exhausted.
    """
    params = {
        "batch": "1",
        "input": json.dumps({"0": {"json": {"reachID": str(aw_reach_id)}}}),
    }

    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.get(_TRPC_URL, params=params, headers=_HEADERS, timeout=15)
        except requests.RequestException as exc:
            if attempt < _MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            raise Exception(
                f"Cannot download data for reach_id={aw_reach_id} from AW"
            ) from exc

        if resp.status_code == 404:
            return None

        if resp.status_code == 200:
            data = resp.json()
            return data[0]["result"]["data"]["json"]

        # transient error — retry with backoff
        if attempt < _MAX_RETRIES - 1:
            time.sleep(2 ** attempt)
        else:
            raise Exception(
                f"Cannot download data for reach_id={aw_reach_id} from AW "
                f"(HTTP {resp.status_code})"
            )

    return None

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

# Ordered threshold field names and their corresponding stage labels.
# endHighRunnable (the 4th key) is the upper bound and has no label of its own.
_THRESHOLD_KEYS = [
    "beginLowRunnable",
    "beginMediumRunnable",
    "beginHighRunnable",
    "endHighRunnable",
]
_STAGE_LABELS: List[Optional[str]] = ["low", "medium", "high", None]


def get_runnable(
    reach_data: ReachData, gauge_observation: Optional[Union[float, int]]
) -> bool:
    """Return whether the reach is runnable at the given gauge observation.

    Args:
        reach_data: Normalized ReachData dict.
        gauge_observation: Current gauge reading; None returns False.

    Returns:
        True if the observation falls within [beginLowRunnable, endHighRunnable].
    """
    if gauge_observation is None:
        return False
    thresholds = reach_data.gauge_thresholds
    if not thresholds:
        return False
    return thresholds[0].value <= gauge_observation <= thresholds[-1].value


def get_stage(
    reach_data: ReachData, gauge_observation: Optional[Union[float, int]]
) -> Optional[str]:
    """Return a human-readable gauge stage label using null-collapse logic.

    Only non-null thresholds are used as boundaries; stages whose defining
    threshold is absent are skipped.

    Args:
        reach_data: Normalized ReachData dict.
        gauge_observation: Current gauge reading; None returns None.

    Returns:
        One of "too low", "low", "medium", "high", "too high", or None
        when no threshold data is available.
    """
    if gauge_observation is None:
        return None
    thresholds = reach_data.gauge_thresholds
    if not thresholds:
        return None

    if gauge_observation < thresholds[0].value:
        return "too low"
    if gauge_observation > thresholds[-1].value:
        return "too high"

    # Walk pairs using half-open intervals [val, next_val) for all pairs
    # except the last, which is closed [val, next_val].
    last_pair_idx = len(thresholds) - 2
    for i, thresh in enumerate(thresholds[:-1]):
        val = thresh.value
        label = thresh.label
        next_val = thresholds[i + 1].value
        if i < last_pair_idx:
            if val <= gauge_observation < next_val:
                return label
        else:
            if val <= gauge_observation <= next_val:
                return label

    return "too high"


def _clean(val: Optional[str]) -> Optional[str]:
    """Strip HTML, collapse whitespace, and remove backslashes from a string."""
    if val:
        val = remove_backslashes(cleanup_string(val))
    return val or None


class AWCollector(BaseCollector):
    """Collector for American Whitewater reach data via the tRPC API."""

    source = "american_whitewater"

    def fetch(self, reach_id: Union[str, int]) -> Optional[ReachData]:
        """Fetch a reach by ID from the AW tRPC API."""
        raw = download_raw_json_from_aw(reach_id)
        if raw is None:
            return None
        return self._normalize(raw)

    def from_file(self, path: Path) -> Optional[ReachData]:
        """Load a reach from a local tRPC fixture file."""
        with open(path, "r") as f:
            data = json.load(f)
        raw = data[0]["result"]["data"]["json"]
        if raw is None:
            return None
        return self._normalize(raw)

    def _normalize(self, raw: dict) -> ReachData:
        """Normalize a raw AW reach object dict to ReachData."""
        stub = raw.get("stub") or {}
        detail = raw.get("detail") or {}
        correlations = detail.get("correlations") or []
        correlation = correlations[0] if correlations else {}
        cd = correlation.get("correlationDetails") or {}
        gi_raw = correlation.get("gaugeInfo")
        gi = gi_raw or {}

        # Pre-compute gauge thresholds (ascending, non-null only).
        gauge_thresholds: List[GaugeThreshold] = []
        for key, label in zip(_THRESHOLD_KEYS, _STAGE_LABELS):
            raw_val = cd.get(key)
            if raw_val is not None:
                gauge_thresholds.append(GaugeThreshold(value=float(raw_val), label=label))

        # Gauge observation from latest reading.
        reading = gi.get("latestFlowReading") or {}
        obs_raw = reading.get("value")
        gauge_observation: Optional[float] = None
        if obs_raw is not None:
            try:
                gauge_observation = float(obs_raw)
            except (ValueError, TypeError):
                pass

        # Gauge runnable bounds.
        gauge_min = float(cd["beginLowRunnable"]) if cd.get("beginLowRunnable") is not None else None
        gauge_max = float(cd["endHighRunnable"]) if cd.get("endHighRunnable") is not None else None

        # Length — accept numeric types or numeric strings.
        length_raw = detail.get("length")
        if isinstance(length_raw, (int, float)):
            length: Optional[float] = float(length_raw)
        elif isinstance(length_raw, str) and length_raw.replace(".", "", 1).isnumeric():
            length = float(length_raw)
        else:
            length = length_raw  # may be None or a non-numeric string

        # Points of interest.
        reach_id_str = str(raw["id"]) if raw.get("id") is not None else None
        pois: List[PointData] = []
        for poi in (raw.get("pointOfInterests") or []):
            typ, subtyp = _POI_TYPE_MAP.get(poi.get("type", "other"), ("generic", None))
            loc = poi.get("location") or {}
            lat_raw = loc.get("latitude")
            lon_raw = loc.get("longitude")
            diff = poi.get("difficulty")
            if diff == "N/A":
                diff = None
            pois.append(
                PointData(
                    reach_id=reach_id_str,
                    name=poi.get("name"),
                    point_type=typ,
                    subtype=subtyp,
                    latitude=float(lat_raw) if lat_raw is not None else None,
                    longitude=float(lon_raw) if lon_raw is not None else None,
                    description=poi.get("description"),
                    difficulty=diff,
                    side_of_river=None,
                )
            )

        return ReachData(
            reach_id=reach_id_str,
            source=self.source,
            river_name=_clean(stub.get("river")),
            reach_name=_clean(stub.get("section")),
            alternate_name=_clean(stub.get("altname")),
            description=cleanup_string(detail["description"]) if detail.get("description") else None,
            difficulty=stub.get("difficulty") or None,
            length=length,
            url=f"https://www.americanwhitewater.org/content/River/view/river-detail/{reach_id_str}/main",
            geometry=detail.get("geometry") or None,
            pois=pois,
            has_gauge=gi_raw is not None,
            gauge_id=gi.get("gaugeSourceIdentifier"),
            gauge_source=gi.get("gaugeSource"),
            gauge_units=cd.get("metric"),
            gauge_min=gauge_min,
            gauge_max=gauge_max,
            gauge_observation=gauge_observation,
            gauge_thresholds=gauge_thresholds,
            edited_at=detail.get("editedAt"),
            updated_at=raw.get("updatedAt"),
        )
