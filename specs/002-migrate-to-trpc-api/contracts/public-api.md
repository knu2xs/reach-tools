# Public API Contract: reach_tools

**Feature**: 002-migrate-to-trpc-api  
**Date**: 2026-05-11  
**Scope**: All public symbols exported from `reach_tools` — no breaking changes to names, types, or signatures.

---

## Module-Level Exports

```python
from reach_tools import Reach, ReachPoint, utils
```

---

## `Reach`

### Constructor

```python
Reach(reach_id: Union[str, int])
```

Not called directly. Use `Reach.from_aw()` or `Reach.from_aw_json()`.

### Class Methods

```python
@classmethod
def from_aw(cls, reach_id: Union[str, int]) -> Optional["Reach"]
```
Fetches reach from the tRPC API. Returns `None` if the reach ID does not exist. Raises on persistent network failure (3 retries exhausted).

```python
@classmethod
def from_aw_json(cls, raw_aw_json: Union[dict, Path]) -> "Reach"
```
Creates a reach from a tRPC-format JSON file path or an already-unwrapped reach object dict.  
- `Path` → reads file, extracts `[0]["result"]["data"]["json"]`  
- `dict` → used directly as the reach object

### Properties — Identity

| Property | Type | Description |
|----------|------|-------------|
| `reach_id` | `str` | AW reach ID |
| `name` | `str` | Combined river + reach name |
| `river_name` | `str` | River name |
| `reach_name` | `str` | Reach section name |
| `section_name` | `str` | Alias for `reach_name` |
| `alternate_name` | `str \| None` | Alternate section name |
| `difficulty` | `str` | Difficulty rating string (e.g., `"IV+toV"`) |
| `difficulty_minimum` | `str \| None` | Parsed minimum difficulty |
| `difficulty_maximum` | `str` | Parsed maximum difficulty |
| `difficulty_outlier` | `str \| None` | Parsed outlier difficulty |
| `difficulty_filter` | `float` | Numeric difficulty for filtering |
| `description` | `str \| None` | Full reach description |
| `abstract` | `str \| None` | Short description (truncated from description) |
| `length` | `float \| None` | Length in miles |
| `url` | `str` | AW web URL for the reach |

### Properties — Geometry

| Property | Type | Description |
|----------|------|-------------|
| `geometry` | `Polyline \| None` | GeoJSON LineString as ArcGIS Polyline |
| `extent` | `tuple[float,float,float,float] \| None` | `(xmin, ymin, xmax, ymax)` derived from geometry |
| `extent_polygon` | `Polygon \| None` | Extent as ArcGIS Polygon |
| `centroid` | `Point \| None` | Centroid of the reach |

### Properties — Gauge

| Property | Type | Description |
|----------|------|-------------|
| `has_gauge` | `bool` | Whether gauge data is available |
| `gauge_id` | `str \| None` | Gauge source identifier |
| `gauge_source` | `str \| None` | Gauge source name (e.g., `"USGS"`) |
| `gauge_units` | `str \| None` | Gauge units (e.g., `"cfs"`) |
| `gauge_metric` | `str \| None` | Gauge metric key (e.g., `"levelFT"`, `"cfs"`) |
| `gauge_min` | `float \| None` | Minimum runnable level (`beginLowRunnable`) |
| `gauge_max` | `float \| None` | Maximum runnable level (`endHighRunnable`) |
| `gauge_observation` | `float \| None` | Most recent gauge reading; settable |
| `runnable` | `bool` | Whether current observation is within runnable range |
| `gauge_stage` | `str \| None` | Human-readable stage: `"too low"`, `"low"`, `"medium"`, `"high"`, `"too high"`, or `None` |

### Properties — Timestamps

| Property | Type | Description |
|----------|------|-------------|
| `edited_timestamp` | `datetime` | Last-edited timestamp |
| `update_timestamp` | `datetime` | Last-updated timestamp (from Unix epoch int) |

### Properties — Reach Points

| Property | Type | Description |
|----------|------|-------------|
| `reach_points` | `list[ReachPoint]` | All points of interest |
| `reach_points_features` | `list[Feature]` | Reach points as ArcGIS Feature objects |
| `reach_points_dataframe` | `DataFrame` | Reach points as spatially-enabled pandas DataFrame |

### Features

| Property | Type | Description |
|----------|------|-------------|
| `line_feature` | `Feature` | Reach LineString as ArcGIS Feature |

---

## `ReachPoint`

### Constructor

```python
ReachPoint(
    reach_id: Union[str, int],
    geometry: Point,
    point_type: str,
    subtype: Optional[str] = None,
    name: Optional[str] = None,
    side_of_river: Optional[str] = None,
    update_date: Optional[datetime] = None,
    description: Optional[str] = None,
    difficulty: Optional[str] = None,
)
```

### Class Method

```python
@classmethod
def from_aw_json(cls, aw_json: dict, reach_id: Optional[Union[str, int]] = None) -> "ReachPoint"
```
Creates a `ReachPoint` from a `pointOfInterests` entry (new format). `reach_id` is passed explicitly since POI entries do not include it.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `reach_id` | `str` | Parent reach ID |
| `point_type` | `str` | One of: `"access"`, `"rapid"`, `"hazard"`, `"generic"` |
| `subtype` | `str \| None` | E.g., `"putin"`, `"takeout"`, `"playspot"`, `"portage"`, `"waterfall"` |
| `name` | `str \| None` | Point name |
| `description` | `str \| None` | Point description |
| `difficulty` | `str \| None` | Rapid difficulty rating |
| `side_of_river` | `str \| None` | `"left"` or `"right"` (not in new API; always `None`) |
| `update_date` | `datetime \| None` | Last updated (not in new API; always `None`) |
| `geometry` | `Point` | ArcGIS Point geometry (WGS84) |
| `wkt` | `str` | WKT geometry |
| `ewkt` | `str` | EWKT geometry |
| `wkb` | `bytes` | WKB geometry |
| `geojson` | `dict` | GeoJSON Point dict |
| `feature` | `Feature` | ArcGIS Python API Feature object |
| `dictionary` | `dict` | All properties as dict (with `SHAPE` key) |

---

## `reach_tools.utils.aw` — Gauge Functions

```python
def get_runnable(reach_json: dict, gauge_observation: Optional[Union[float, int]]) -> bool
```
Returns `True` if `gauge_observation` is within `[beginLowRunnable, endHighRunnable]`.  
Returns `False` if: correlations absent, observation is `None`, or either bound is `None`.

```python
def get_stage(reach_json: dict, gauge_observation: Optional[Union[float, int]]) -> Optional[str]
```
Returns a stage label string using null-collapse logic:  
`"too low"` | `"low"` | `"medium"` | `"high"` | `"too high"` | `None` (no correlations)

Both functions accept the **full reach object dict** (as returned by `download_raw_json_from_aw()` or extracted from a file via `from_aw_json()`).

---

## Backward Compatibility Notes

- All public property names unchanged.
- `get_stage()` and `get_runnable()` signatures unchanged (still accept `dict, observation`), but the dict must now be a new-format reach object, not an old-format nested dict.
- `side_of_river` and `update_date` on `ReachPoint` always return `None` after migration (not present in new API POI entries). This is a data regression — acceptable because the old API is defunct.
- `alternate_name` previously returned the same value as `reach_name` (bug). Post-migration it correctly returns `stub.altname`, which may be `None` for most reaches.
- `extent` is now derived from geometry bounds rather than a stored `bbox` field; the return type `(xmin, ymin, xmax, ymax)` is unchanged.
