# Research: Migrate to tRPC API

**Feature**: 002-migrate-to-trpc-api  
**Date**: 2026-05-11  
**Purpose**: Resolve all unknowns from the spec and establish decisions used in Phase 1 design.

---

## Decision 1: Test Fixture Strategy

**Decision**: Replace all old-format files in `data/raw/american_whitewater/` with new-format tRPC JSON files sourced from `references/aw_json/`. `from_aw_json()` will be a single-format parser — no dual-format detection.

**Rationale**: Dual-format detection adds dead-code complexity that the feature is specifically designed to remove. The `references/aw_json/` directory already contains valid new-format files for all reaches 1–2000 with AW data. The test suite auto-discovers fixtures by glob, so reducing the fixture count (from ~5136 to ~1700) is automatically handled.

**Alternatives Considered**:
- Keep old fixtures, add dual-format detection → rejected: perpetuates the old format complexity that motivated this feature
- Keep old fixtures, add new tests in parallel → rejected: two incompatible parsers creates maintenance burden

**Implementation Notes**:
- Script fixture replacement: copy `references/aw_json/reach_{id:06d}.json` to `data/raw/american_whitewater/aw_{id:08d}.json` for all valid files
- The `tilton_dict` fixture (reach 3411, outside 1–2000) must be fetched separately and saved to `references/aw_json/reach_003411.json` and mirrored to `data/raw/american_whitewater/aw_00003411.json`
- The fixture JSON file format is the full tRPC array: `[{"result":{"data":{"json":{...}}}}]`
- `from_aw_json(path)` extracts inner payload: `json.load(f)[0]["result"]["data"]["json"]`

---

## Decision 2: HTTP Retry Strategy

**Decision**: Retry up to 3 times with exponential backoff — sleep `2 ** attempt` seconds between retries (2s, 4s, 8s). Return `None` on HTTP 404. Raise exception only if all 3 retries are exhausted on non-404 errors.

**Rationale**: Consistent with the proven pattern in `scripts/download_aw_json.py`. The old `procure.py` retried 10 times with no backoff — too aggressive. 3 retries with backoff is sufficient for transient network issues. HTTP 404 is a definitive "reach does not exist" response and should never be retried.

**Alternatives Considered**:
- No retries → rejected: live API calls can fail transiently (network blip, rate limit)
- 10 retries (old behavior) → rejected: too many attempts; no backoff causes request floods

**New tRPC endpoint**:
```
GET https://trpc-api.americanwhitewater.org/reach/reachDetailWithPhotos
?batch=1&input={"0":{"json":{"reachID":"<id>"}}}
```
Response: `[{"result":{"data":{"json": <reach_object> | null}}}]`  
Inner payload: `resp[0]["result"]["data"]["json"]`  
Valid reach: inner payload is not `null`, HTTP 200  
Invalid reach: HTTP 404 response  

**User-Agent header**: Retain the existing browser-spoofing User-Agent string (Cloudflare mitigation — required by the old server; new tRPC API may also be behind CDN).

---

## Decision 3: Gauge Stage Null-Collapse Logic

**Decision**: Use only non-null thresholds as stage boundaries. Skip stages whose defining threshold is absent. Stage labels depend on which thresholds are present:

| Present thresholds | Stage output (ascending observation) |
|--------------------|--------------------------------------|
| `beginLow` + `endHigh` only | "too low" → "runnable" → "too high" |
| `beginLow` + `beginMedium` + `endHigh` | "too low" → "low" → "medium runnable" → "too high" |
| All four: `beginLow`, `beginMedium`, `beginHigh`, `endHigh` | "too low" → "low" → "medium" → "high" → "too high" |
| None / correlations empty | return `None` |

**Rationale**: Matches the structure of the new API — only 2 of 4 thresholds are populated for many reaches (e.g., reach 4 has only `beginLow=900`, `endHigh=3000`; medium and high are `null`). The old `R0–R9` index system allowed arbitrary granularity; the new system uses named semantic levels.

**Runnable determination**: A reach is runnable if `beginLowRunnable ≤ gauge_observation ≤ endHighRunnable` (when both are present). If either bound is `null`, `runnable` returns `False`.

**Tilton (reach 3411) verified thresholds** (cfs, from live API 2026-05-11):
- `beginLowRunnable`: 400  
- `beginMediumRunnable`: 1000  
- `beginHighRunnable`: 3000  
- `endHighRunnable`: 5000  

Verified test assertions still hold with new data:
- `get_stage(tilton, 360)` → "too low" (360 < 400) ✓  
- `get_stage(tilton, 1680)` → "medium" (1000 ≤ 1680 < 3000) ✓  
- `get_stage(tilton, 8000)` → "too high" (8000 > 5000) ✓  
- `get_runnable(tilton, 1000)` → `True` (400 ≤ 1000 ≤ 5000) ✓  
- `get_runnable(tilton, 360)` → `False` (360 < 400) ✓  
- `get_runnable(tilton, 10000)` → `False` (10000 > 5000) ✓  

---

## Decision 4: New API Response Structure

**Decision**: Use the tRPC response structure as the canonical data source. The inner JSON object (hereafter "reach object") is the value at `resp[0]["result"]["data"]["json"]`.

**Reach object top-level structure**:
```json
{
  "id": 4,
  "stub": {
    "id": 4, "river": "Sixmile Creek", "section": "Lower Canyon",
    "altname": null, "difficulty": "IV+toV", "states": [...]
  },
  "detail": {
    "id": 4, "permitUrl": null, "permitInfo": null,
    "description": "...", "averageGradient": 100, "maxGradient": 200,
    "length": 6.0, "correlations": [...], "pointOfInterestIDs": [...],
    "geometry": {"type": "LineString", "coordinates": [...]},
    "bannerPhotoID": null, "editedAt": "2024-03-15T12:00:00.000Z"
  },
  "primaryGaugeStatus": {
    "status": "below-recommended",
    "latestReading": {"value": "754", "dateTime": "...", "qualifier": "NORMAL"},
    "metric": "cfs",
    "adjustedDifficulty": null
  },
  "pointOfInterests": [...],
  "updatedAt": 1778556411
}
```

**Correlation structure** (when present):
```json
{
  "reachID": "4", "isPrimary": true,
  "correlationDetails": {
    "metric": "cfs",
    "beginLowRunnable": "900",
    "beginMediumRunnable": null,
    "beginHighRunnable": null,
    "endHighRunnable": "3000",
    ...comments...
  },
  "gaugeInfo": {
    "name": "...", "gaugeSource": "USGS", "gaugeSourceIdentifier": "15271000",
    "latestFlowReading": {"value": "754", "dateTime": "...", "qualifier": "NORMAL"},
    "latestStageReading": {"value": "9.16", ...},
    "location": {"latitude": "...", "longitude": "..."}
  }
}
```

**`correlationDetails` threshold values are strings** (e.g., `"900"`, `"3000"`) — must be cast to `float`.

---

## Decision 5: Point of Interest Type Mapping

**Decision**: Map new `type` strings to `(point_type, subtype)` tuples for `ReachPoint`:

| New `type` | `point_type` | `subtype` |
|------------|-------------|-----------|
| `"put-in"` | `"access"` | `"putin"` |
| `"takeout"` | `"access"` | `"takeout"` |
| `"access"` | `"access"` | `"intermediate"` |
| `"rapid"` | `"rapid"` | `None` |
| `"hazard"` | `"hazard"` | `None` |
| `"playspot"` | `"rapid"` | `"playspot"` |
| `"portage"` | `"rapid"` | `"portage"` |
| `"waterfall"` | `"hazard"` | `"waterfall"` |
| `"other"` | `"generic"` | `None` |
| (unknown) | `"generic"` | `None` |

All 9 types observed across the first 200 downloaded files (1–2000 range):  
`access`, `hazard`, `other`, `playspot`, `portage`, `put-in`, `rapid`, `takeout`, `waterfall`

**POI geometry** (new): `location.latitude`, `location.longitude` as strings → cast to `float`:
```python
Point({"x": float(poi["location"]["longitude"]),
       "y": float(poi["location"]["latitude"]),
       "spatialReference": {"wkid": 4326}})
```

**POI fields available**: `type`, `name`, `description`, `difficulty`, `distance`, `approximate`, `photoID`, `id`, `location`

---

## Decision 6: Reach Properties Without New Equivalents

**Decision**: Two properties lose their data source in the new API:

- **`extent`** (`info.bbox` in old → **absent** in new): Derive from `detail.geometry.coordinates` bounding box at call time. If geometry is `null`, return `None`.
- **`alternate_name`** (old: `info.altname`, but it actually reads `info.section` — a bug): New API has `stub.altname` which is the correct field. Map to `stub.altname`.
- **`gauge_id`**: Old: `gauges[0].gauge_id`. New: `detail.correlations[0].gaugeInfo.gaugeSourceIdentifier`. Available but requires navigating the correlations array.
- **`gauge_source`**: Old: `gauges[0].source`. New: `detail.correlations[0].gaugeInfo.gaugeSource`. Same path.
- **`gauge_units`**: Old: `gauges[0].gauge_units`. New: `detail.correlations[0].correlationDetails.metric`. Available.
- **`gauge_metric`**: Old: `gauges[0].metric_unit`. New: `primaryGaugeStatus.metric`. Available.
- **`edited_timestamp`**: Old: `info.edited` (ISO "YYYY-MM-DD HH:MM:SS"). New: `detail.editedAt` (ISO 8601 with timezone). Parse with `datetime.fromisoformat()`.
- **`update_timestamp`**: Old: `info.updated_at` (ISO string). New: `updatedAt` (Unix epoch int). Convert: `datetime.fromtimestamp(updatedAt, tz=timezone.utc)`.
- **`abstract`**: Old: `info.abstract_md`. New: **absent** — generate from `detail.description` (existing fallback logic already handles this case). No change needed.

---

## Decision 7: `get_key_from_block` Disposition

**Decision**: Remove usage from `Reach` properties (all fields are now clean strings, no HTML garbage or backslash escaping in the new API). Keep the function definition in `utils/aw.py` (it's not in `__all__` so removal is low-risk, but retention is safer). The `remove_backslashes()` call on `river_name` and `reach_name` can also be removed — new API returns clean strings.

**Rationale**: The old API embedded HTML entities and backslash-escaped strings in many fields; the new API returns clean UTF-8 JSON strings. The `cleanup_string` calls were defensive — they are no longer necessary for the new data. Removing them reduces noise.

---

## Decision 8: `from_aw_json()` Signature Clarification

**Decision**: `Reach.from_aw_json()` accepts either:
1. A `Path` object → reads the tRPC array file and extracts the inner payload
2. A `dict` → treated directly as the inner reach object (already unwrapped)

This mirrors the existing signature and allows `Reach.from_aw()` to pass the already-fetched dict directly without writing to disk.
