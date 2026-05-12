# Feature Specification: Migrate to tRPC API

**Feature Branch**: `002-migrate-to-trpc-api`  
**Created**: 2026-05-11  
**Status**: Draft  
**Input**: User description: "Rebuild the download and processing to use the new api endpoint and remove the overhead for using the old one. Use the downloaded example data in references/aw_json as a model for how the responses can be structured."

---

## Clarifications

### Session 2026-05-11

- Q: Should the existing tests be updated via (A) replacing old fixtures with new-format files and making `from_aw_json()` new-format only, (B) dual-format detection, or (C) keeping old tests and adding new ones separately? → A: Option A — replace old fixtures with new-format files from `references/aw_json/`; `from_aw_json()` handles new format only.
- Q: What retry behavior should the new `download_raw_json_from_aw()` have on transient errors? → A: Option A — retry up to 3 times with exponential backoff (2^attempt seconds), consistent with `scripts/download_aw_json.py`.
- Q: How should `get_stage()` behave when intermediate runnable thresholds (`beginMediumRunnable`, `beginHighRunnable`) are null? → A: Collapse nulls — treat only non-null thresholds as boundaries and skip the corresponding stage label. E.g., with only `beginLowRunnable` and `endHighRunnable` present: below low → "Too Low", between → "Runnable", above end → "Too High".

---

## Background

The American Whitewater website previously exposed reach data through a legacy endpoint (`/content/River/detail/id/{id}/.json`) that returned a deeply nested JSON object keyed on `CContainerViewJSON_view` / `CRiverMainGadgetJSON_main`. That endpoint now returns HTTP 502 — it is defunct.

A new tRPC endpoint (`https://trpc-api.americanwhitewater.org/reach/reachDetailWithPhotos`) is now the live source of reach data. The response structure is substantially different: flatter, with reach metadata in `stub`, geometry in `detail.geometry`, points of interest (rapids, accesses, hazards, playspots) in `pointOfInterests`, gauge status in `primaryGaugeStatus`, and runnable ranges in `detail.correlations[].correlationDetails`.

The `reach_tools` library currently parses the old format throughout. This feature migrates all parsing, downloading, and data-access logic to the new format and removes all dead code that only handled the old format.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Load a reach from a locally saved new-format file (Priority: P1)

A developer creates a `Reach` object by loading one of the JSON files saved in `references/aw_json/` (new tRPC format) and accesses all the same properties that were available before: name, river name, difficulty, geometry, reach points, gauge ranges, and runnability.

**Why this priority**: This is the core smoke test — if the library can parse the new format from a saved file, the data model migration is correct. Everything else builds on this.

**Independent Test**: Call `Reach.from_aw_json(path_to_new_format_file)` and assert all previously working properties (`name`, `river_name`, `difficulty`, `geometry`, `reach_points`, `gauge_min`, `gauge_max`, `runnable`) return correct values or `None` where data is absent — without raising an exception.

**Acceptance Scenarios**:

1. **Given** a saved new-format reach file with a river name, section, and difficulty, **When** `Reach.from_aw_json()` is called, **Then** `reach.river_name`, `reach.reach_name`, and `reach.difficulty` return the correct string values.
2. **Given** a reach file that contains a `detail.geometry` LineString, **When** `reach.geometry` is accessed, **Then** it returns a `Polyline` object (not `None`).
3. **Given** a reach file that contains `pointOfInterests` entries of type `put-in`, `takeout`, `rapid`, `hazard`, and `playspot`, **When** `reach.reach_points` is accessed, **Then** it returns a list of `ReachPoint` objects with correct `point_type` and `subtype` values.
4. **Given** a reach file with no `detail.correlations` entries, **When** `reach.gauge_min` and `reach.gauge_max` are accessed, **Then** they return `None` without raising an exception.
5. **Given** a reach file with `detail.correlations[0].correlationDetails` containing `beginLowRunnable` and `endHighRunnable` values, **When** `reach.gauge_min` and `reach.gauge_max` are accessed, **Then** they return the correct float values.

---

### User Story 2 - Fetch a reach live from the new API (Priority: P2)

A developer calls `Reach.from_aw(reach_id)` and receives a populated `Reach` object fetched in real time from the new tRPC endpoint.

**Why this priority**: Confirms the download path uses the new endpoint end-to-end, not just local file parsing.

**Independent Test**: Call `Reach.from_aw(3411)` and verify `reach.river_name == "Tilton"` and `reach.difficulty` is non-empty.

**Acceptance Scenarios**:

1. **Given** a valid reach ID, **When** `Reach.from_aw(reach_id)` is called, **Then** a populated `Reach` object is returned with correct `river_name` and `difficulty`.
2. **Given** an invalid reach ID (one with no AW data), **When** `Reach.from_aw(reach_id)` is called, **Then** `None` is returned (not an exception).

---

### User Story 3 - Old format code is fully removed (Priority: P3)

The codebase no longer contains any references to the old endpoint URL, old JSON key names (`CContainerViewJSON_view`, `CRiverMainGadgetJSON_main`, `guagesummary`, `range_min`, `range_max`, `isputin`, `istakeout`, `israpid`, `rloc`), or any branching logic that attempted to detect and handle both formats simultaneously.

**Why this priority**: Cleanup reduces confusion and eliminates dead code paths that could mislead future contributors.

**Independent Test**: Search the codebase for the old key names and old endpoint URL — none should appear in any non-test, non-spec file.

**Acceptance Scenarios**:

1. **Given** the updated codebase, **When** a search is performed for `CContainerViewJSON_view`, `CRiverMainGadgetJSON_main`, `guagesummary`, `range_min`, `range_max`, `isputin`, `istakeout`, `israpid`, and the old endpoint URL, **Then** zero matches are found in `src/` and `scripts/`.
2. **Given** the updated codebase, **When** `get_gauge_ranges()` and `get_gauge_value_list()` in `utils/aw.py` are examined, **Then** they operate only on the new `correlationDetails` structure, not the old `ranges` list.

---

### Edge Cases

- What if `detail.correlations` is an empty list? `gauge_min`, `gauge_max`, and `runnable` must return `None`/`False` gracefully.
- What if `detail.geometry` is `null`? `reach.geometry` must return `None` without raising an exception.
- What if `primaryGaugeStatus.latestReading.value` is `null` or absent? `gauge_observation` must return `None`.
- What if a `pointOfInterests` entry has a `type` not previously seen (e.g., `"portage"`, `"campsite"`)? The `ReachPoint` must still be created with a sensible fallback type rather than raising an exception.
- What if the old-format cached files in `data/raw/american_whitewater/` are still present? Those files will be replaced with new-format equivalents sourced from `references/aw_json/`; `from_aw_json()` will be a single-format parser for the new API structure only.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `Reach.from_aw_json()` MUST accept a path to a new-format tRPC response file (the array saved by `scripts/download_aw_json.py`) and correctly populate all `Reach` properties.
- **FR-002**: `Reach.from_aw()` MUST fetch from the new tRPC endpoint (`https://trpc-api.americanwhitewater.org/reach/reachDetailWithPhotos`) and return a populated `Reach` for valid reach IDs, or `None` for invalid ones.
- **FR-003**: `download_raw_json_from_aw()` in `utils/procure.py` MUST be updated to use the new tRPC endpoint and return the inner reach payload (`result[0]["result"]["data"]["json"]`) to maintain the same return contract expected by callers. On transient network errors it MUST retry up to 3 times with exponential backoff (sleep `2^attempt` seconds between retries); raise an exception only if all retries are exhausted. Returns `None` on HTTP 404 (invalid reach ID).
- **FR-004**: The `Reach._raw_json` setter MUST parse the new response structure: extract reach identity and metadata from `stub`, geometry from `detail.geometry`, description from `detail.description`, and points of interest from `pointOfInterests`.
- **FR-005**: `ReachPoint.from_aw_json()` MUST be updated to parse the new `pointOfInterests` entry structure (fields: `type`, `name`, `description`, `difficulty`, `location.latitude`, `location.longitude`, `distance`, `approximate`) instead of the old rapids structure (fields: `isputin`, `istakeout`, `israpid`, `ishazard`, `isplayspot`, `isportage`, `iswaterfall`, `rloc`).
- **FR-006**: The gauge properties (`gauge_min`, `gauge_max`, `gauge_observation`, `runnable`, `gauge_stage`) MUST be derived from the new `detail.correlations[0].correlationDetails` and `primaryGaugeStatus.latestReading.value` fields.
- **FR-007**: `utils/aw.py` gauge functions MUST be updated or replaced to work with the new `correlationDetails` structure (`beginLowRunnable`, `beginMediumRunnable`, `beginHighRunnable`, `endHighRunnable`) rather than the old `ranges` list with `range_min`/`range_max`/`min`/`max` fields. `get_stage()` MUST use null-collapse logic: only non-null thresholds are treated as boundaries; stages whose defining threshold is `null` are skipped. With only `beginLowRunnable` and `endHighRunnable` present the stages collapse to "Too Low" / "Runnable" / "Too High". With all four thresholds present the full "Too Low" / "Low" / "Medium" / "High" / "Too High" label set is used.
- **FR-008**: All dead code referencing the old endpoint URL, old JSON key names, and old format detection branching MUST be removed from `src/` and `scripts/`.
- **FR-009**: The existing test suite (`testing/test_reach_tools.py`) MUST be updated to load new-format fixture files (copied from `references/aw_json/` into `data/raw/american_whitewater/` or referenced directly from `references/aw_json/`). Old-format cached files in `data/raw/american_whitewater/` will be replaced. `from_aw_json()` will parse the new format only — no dual-format detection logic.
- **FR-010**: No new required dependencies may be introduced — only packages already present in the project environment may be used.

### Key Entities

- **Reach**: A river reach. In the new format: identity from `stub` (`id`, `river`, `section`, `altname`, `difficulty`), geometry from `detail.geometry` (GeoJSON LineString), points of interest from `pointOfInterests`, gauge ranges from `detail.correlations[0].correlationDetails`, live gauge reading from `primaryGaugeStatus.latestReading.value`.
- **ReachPoint**: A discrete point on a reach (put-in, takeout, rapid, hazard, playspot, portage). In the new format: identified by `type` field (replaces old `isputin`/`istakeout`/`israpid`/`ishazard`/`isplayspot` boolean flags); geometry from `location.latitude`/`location.longitude` (replaces old `rloc` GeoJSON).
- **GaugeRanges**: In the new format: a single `correlationDetails` object with named thresholds (`beginLowRunnable`, `beginMediumRunnable`, `beginHighRunnable`, `endHighRunnable`) replacing the old variable-length `ranges` list keyed with `R0`–`R9` index codes.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All existing tests in `testing/test_reach_tools.py` that currently pass continue to pass after the migration.
- **SC-002**: A `Reach` object loaded from any file in `references/aw_json/` returns correct non-null values for `river_name`, `reach_name`, and `difficulty` without raising an exception.
- **SC-003**: `Reach.from_aw(3411)` returns a `Reach` with `river_name == "Tilton"`.
- **SC-004**: Zero occurrences of old JSON key names (`CContainerViewJSON_view`, `CRiverMainGadgetJSON_main`, `guagesummary`, `range_min`, `range_max`, `isputin`, `istakeout`, `israpid`, `rloc`) remain in `src/` or `scripts/`.
- **SC-005**: Reaches with no gauge data (`detail.correlations` is empty) do not raise exceptions when `gauge_min`, `gauge_max`, or `runnable` are accessed.

---

## Assumptions

- The downloaded files in `references/aw_json/` represent the full range of structural variation in the new API — reaches with and without gauge data, with and without geometry, with various point-of-interest type combinations.
- The new `primaryGaugeStatus.latestReading.value` is a string that can be cast to `float` for numeric comparison; it may be `null`.
- The new gauge ranges are simpler than the old format: at most 4 named thresholds (`beginLow`, `beginMedium`, `beginHigh`, `endHigh`), not the variable-length `R0`–`R9` index system. The `get_stage()` and `get_runnable()` logic can be significantly simplified.
- The old `data/raw/american_whitewater/` cached files (old format) will be **replaced** with new-format equivalents from `references/aw_json/` for the reach IDs used in tests. `from_aw_json()` will be a single-format parser — no dual-format detection branching.
- `ReachPoint` type mapping from new `type` string to old `point_type`/`subtype`: `"put-in"` → access/putin, `"takeout"` → access/takeout, `"rapid"` → rapid, `"hazard"` → hazard, `"playspot"` → rapid/playspot, `"portage"` → (any type)/portage, `"access"` → access/intermediate.
- The `detail.geometry` field is a GeoJSON LineString; the existing `Polyline` geometry handling is compatible with GeoJSON and does not need to change — only the field path changes.
- Python is the implementation language, consistent with the rest of the project.
