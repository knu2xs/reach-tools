# Data Model: Migrate to tRPC API

**Feature**: 002-migrate-to-trpc-api  
**Date**: 2026-05-11

---

## Overview

This document maps the **old API JSON structure** (defunct `americanwhitewater.org/content/River/detail/id/{id}/.json`) to the **new tRPC API structure** (`trpc-api.americanwhitewater.org/reach/reachDetailWithPhotos`) for each public property of `Reach` and `ReachPoint`.

---

## Internal Storage Changes

### `Reach` — Internal Attributes

| Old Attribute | Old Source | New Attribute | New Source |
|---------------|-----------|---------------|-----------|
| `_main_json` | Normalized to `CRiverMainGadgetJSON_main` dict | `_raw_json` | The full inner reach object (unwrapped from tRPC array) |
| `_rapids_json` | `CRiverRapidsGadgetJSON_view-rapids.rapids` list | `_poi_json` | `raw_json["pointOfInterests"]` list |
| *(not present)* | — | `_correlation_details` | `raw_json["detail"]["correlations"][0]["correlationDetails"]` or `None` |
| *(not present)* | — | `_gauge_status` | `raw_json["primaryGaugeStatus"]` or `None` |

The `_raw_json` setter is simplified to a flat extraction — no old-key detection branching.

---

## `Reach` — Public Property Mapping

| Property | Old JSON path | New JSON path | Notes |
|----------|--------------|--------------|-------|
| `reach_id` | `CContainerViewJSON_view.CRiverMainGadgetJSON_main.info.id` | `raw_json["id"]` | Int → cast to str |
| `river_name` | `_main_json.info.river` | `raw_json["stub"]["river"]` | No `cleanup_string`/`remove_backslashes` needed |
| `reach_name` | `_main_json.info.section` | `raw_json["stub"]["section"]` | Same |
| `section_name` | Same as `reach_name` | Same as `reach_name` | Alias, unchanged |
| `alternate_name` | `_main_json.info.section` *(bug: same as reach_name)* | `raw_json["stub"]["altname"]` | Fixed to use correct field |
| `difficulty` | `_main_json.info.class` | `raw_json["stub"]["difficulty"]` | |
| `description` | `_main_json.info.description_md` | `raw_json["detail"]["description"]` | |
| `abstract` | `_main_json.info.abstract_md` → fallback to description | `raw_json["detail"]["description"]` truncated | No abstract field in new API; existing fallback path used directly |
| `length` | `_main_json.info.length` | `raw_json["detail"]["length"]` | May be `null` |
| `geometry` | `_main_json.info.geom` (GeoJSON LineString) → `Polyline` | `raw_json["detail"]["geometry"]` (GeoJSON LineString) → `Polyline` | Same type/constructor |
| `extent` | `_main_json.info.bbox` | Computed from `detail.geometry.coordinates` bounds | No `bbox` in new API; derive at call time |
| `url` | Constructed from `reach_id` | Constructed from `reach_id` | Unchanged |
| `gauge_min` | `_main_json.guagesummary.ranges` → `get_gauge_value_list()` | `_correlation_details["beginLowRunnable"]` cast to float | Direct access; None if no correlations |
| `gauge_max` | `_main_json.guagesummary.ranges` → `get_gauge_value_list()` | `_correlation_details["endHighRunnable"]` cast to float | Direct access; None if no correlations |
| `gauge_observation` | `_main_json.gauges[0].gauge_reading` cast to float | `_gauge_status["latestReading"]["value"]` cast to float | None if primaryGaugeStatus or latestReading is None |
| `has_gauge` | `_main_json.gauges` is not None and non-empty | `_gauge_status is not None` | |
| `gauge_metric` | `_main_json.gauges[0].metric_unit` | `_gauge_status["metric"]` | |
| `gauge_units` | `_main_json.gauges[0].gauge_units` | `_correlation_details["metric"]` | |
| `gauge_source` | `_main_json.gauges[0].source` | `raw_json["detail"]["correlations"][0]["gaugeInfo"]["gaugeSource"]` | |
| `gauge_id` | `_main_json.gauges[0].gauge_id` | `raw_json["detail"]["correlations"][0]["gaugeInfo"]["gaugeSourceIdentifier"]` | |
| `runnable` | `utils.aw.get_runnable(_main_json, gauge_observation)` | `utils.aw.get_runnable(raw_json, gauge_observation)` | Function updated |
| `gauge_stage` | `utils.aw.get_stage(_main_json, gauge_observation)` | `utils.aw.get_stage(raw_json, gauge_observation)` | Function updated |
| `edited_timestamp` | `_main_json.info.edited` (format: `"YYYY-MM-DD HH:MM:SS"`) | `raw_json["detail"]["editedAt"]` (ISO 8601 w/ timezone) | `datetime.fromisoformat()` works for both |
| `update_timestamp` | `_main_json.info.updated_at` (ISO string) | `raw_json["updatedAt"]` (Unix epoch int) | `datetime.fromtimestamp(val, tz=timezone.utc)` |
| `centroid` | Derived from `geometry` / reach points | Derived from `geometry` / reach points | Logic unchanged |
| `reach_points` | Built from `_rapids_json` via `ReachPoint.from_aw_json()` | Built from `_poi_json` via `ReachPoint.from_aw_json()` | `from_aw_json` updated |
| `name` | Combination of `river_name` + `reach_name` | Same logic | Unchanged |
| `difficulty_minimum` | Parsed from `difficulty` | Parsed from `difficulty` | Unchanged |
| `difficulty_maximum` | Parsed from `difficulty` | Parsed from `difficulty` | Unchanged |
| `difficulty_outlier` | Parsed from `difficulty` | Parsed from `difficulty` | Unchanged |
| `difficulty_filter` | `lookup_dict[difficulty_maximum]` | Same | Unchanged |

---

## `ReachPoint` — Field Mapping

### Old vs New Input Format

| Aspect | Old format | New format |
|--------|-----------|-----------|
| Input object source | `_rapids_json` item (from `CRiverRapidsGadgetJSON_view-rapids.rapids`) | `_poi_json` item (from `pointOfInterests`) |
| Type determination | Integer flags: `isputin`, `istakeout`, `israpid`, `ishazard`, `isplayspot`, `isportage`, `iswaterfall` | String field `type`: one of `put-in`, `takeout`, `access`, `rapid`, `hazard`, `playspot`, `portage`, `waterfall`, `other` |
| Geometry | `rloc` (GeoJSON Point dict) → `Geometry(rloc)` | `location.latitude` + `location.longitude` (strings) → `Point({"x": float(lon), "y": float(lat), "spatialReference": {"wkid": 4326}})` |
| Name | `name` field | `name` field |
| Description | `description_md` | `description` |
| Difficulty | `difficulty` | `difficulty` |
| Update date | `updatedate` (ISO date string) → `datetime.fromisoformat()` | *(not present in POI)* → `None` |
| Reach ID | `reach_id` field | *(not present in POI)* → inherited from parent `Reach.reach_id` (passed at construction) |
| Side of river | `side_of_river` | *(not present in POI)* → `None` |

### `ReachPoint` Type/Subtype Mapping

| New `type` string | `point_type` | `subtype` |
|-------------------|-------------|-----------|
| `"put-in"` | `"access"` | `"putin"` |
| `"takeout"` | `"access"` | `"takeout"` |
| `"access"` | `"access"` | `"intermediate"` |
| `"rapid"` | `"rapid"` | `None` |
| `"hazard"` | `"hazard"` | `None` |
| `"playspot"` | `"rapid"` | `"playspot"` |
| `"portage"` | `"rapid"` | `"portage"` |
| `"waterfall"` | `"hazard"` | `"waterfall"` |
| `"other"` | `"generic"` | `None` |
| *(any other)* | `"generic"` | `None` |

### Note on Reach ID for ReachPoints

The new `pointOfInterests` entries do not include a `reach_id` field. The `Reach` class must pass its own `reach_id` when constructing each `ReachPoint`:
```python
ReachPoint.from_aw_json(poi_json, reach_id=self.reach_id)
```
Or the `from_aw_json` class method signature can be updated to accept `reach_id` as a separate parameter.

---

## `utils/aw.py` — Function Interface Changes

### Functions to Remove
- `get_gauge_ranges()` — replaced by direct `correlationDetails` extraction in `Reach`
- `get_gauge_value_list()` — replaced by direct threshold reads
- `get_range_bias()` — no longer applicable (named thresholds, not indexed)

### Functions to Update

#### `get_runnable(reach_json, gauge_observation)`
- **Old signature**: accepted `Union[dict, list[dict]]` (old JSON or ranges list)
- **New signature**: accepts full reach object dict (new format)
- **Logic**: Extract `detail.correlations[0].correlationDetails`; if absent/null, return `False`. Cast `beginLowRunnable` and `endHighRunnable` to float. Return `float(low) <= gauge_observation <= float(high)`.

#### `get_stage(reach_json, gauge_observation)`
- **Old signature**: accepted `Union[dict, list[dict]]`
- **New signature**: accepts full reach object dict (new format)
- **Logic**: Null-collapse — use only non-null thresholds as stage boundaries. See Decision 3 in research.md for stage label table.

### New Helper

#### `_get_correlation_details(reach_json)` *(private)*
- Extracts and returns `detail.correlations[0].correlationDetails` or `None` if missing/empty
- Used internally by `get_runnable` and `get_stage`

---

## `utils/procure.py` — Changes

### `download_raw_json_from_aw(aw_reach_id)`

| Aspect | Old | New |
|--------|-----|-----|
| URL | `https://www.americanwhitewater.org/content/River/detail/id/{id}/.json` | `https://trpc-api.americanwhitewater.org/reach/reachDetailWithPhotos` |
| Method | GET (URL path) | GET (query params: `batch=1&input={"0":{"json":{"reachID":"<id>"}}}`) |
| Max retries | 10 (no sleep) | 3 (sleep `2 ** attempt` seconds) |
| 404 handling | Not distinguished from other errors | Return `None` |
| Return value | Raw response JSON (full nested old-format dict) | `resp[0]["result"]["data"]["json"]` (unwrapped reach object dict) |
| Invalid reach return | *(varied — might raise after 10 retries)* | `None` |

---

## Test Fixture Format

| Aspect | Old | New |
|--------|-----|-----|
| File naming | `data/raw/american_whitewater/aw_{id:08d}.json` | `data/raw/american_whitewater/aw_{id:08d}.json` *(same)* |
| File content | Old nested AW JSON (`CContainerViewJSON_view` root) | tRPC array: `[{"result":{"data":{"json":{...}}}}]` |
| Count | ~5136 files | ~1700 files (all valid reaches in 1–2000 range + reach 3411) |
| Source | Historic crawl of defunct endpoint | `references/aw_json/reach_{id:06d}.json` + fetch of reach 3411 |

### Fixture Replacement Script (inline — no new script file needed)
```python
import shutil
from pathlib import Path

src = Path("references/aw_json")
dst = Path("data/raw/american_whitewater")

for src_file in src.glob("reach_*.json"):
    reach_id = int(src_file.stem.split("_")[1])
    dst_file = dst / f"aw_{reach_id:08d}.json"
    shutil.copy2(src_file, dst_file)
```
Old files not overwritten by this (IDs > 2000 in old fixtures) must be deleted to avoid mixing formats.
