# Tasks: Migrate to tRPC API

**Input**: Design documents from `specs/002-migrate-to-trpc-api/`  
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/public-api.md ✓, quickstart.md ✓

**Tests**: Not TDD — tests updated to match new fixture format, not written first. Existing test assertions reused where valid.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

---

## Phase 1: Setup (Replace Test Fixtures)

**Purpose**: Replace all old-format fixture files with new-format tRPC JSON so the test suite can run against real data throughout implementation. No source code changes yet.

- [X] T001 Fetch reach 3411 (Tilton) from new tRPC API and save to `references/aw_json/reach_003411.json`
- [X] T002 Delete all existing old-format files in `data/raw/american_whitewater/` (they are incompatible with the new parser)
- [X] T003 Copy all files from `references/aw_json/reach_*.json` to `data/raw/american_whitewater/aw_{id:08d}.json` for all valid reach IDs (including reach 3411)

**Checkpoint**: `data/raw/american_whitewater/` contains ~1700 new-format tRPC JSON files. No source code has changed yet — tests will fail until Phase 3 is complete.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Update `utils/procure.py` and `utils/aw.py` first — both are imported by `__init__.py`. These must be complete before the `Reach` class can be updated.

**⚠️ CRITICAL**: `__init__.py` changes (Phase 3) depend on both of these being done.

- [X] T004 Rewrite `download_raw_json_from_aw()` in `src/reach_tools/utils/procure.py` to use the new tRPC endpoint URL and query params, retry up to 3 times with exponential backoff (`time.sleep(2 ** attempt)`), return `None` on HTTP 404, and return the unwrapped inner reach object dict (`resp[0]["result"]["data"]["json"]`)
- [X] T005 [P] Replace `get_gauge_ranges()` in `src/reach_tools/utils/aw.py` with a private `_get_correlation_details(reach_json)` helper that extracts `reach_json["detail"]["correlations"][0]["correlationDetails"]` or returns `None` if correlations list is empty or `correlationDetails` is null
- [X] T006 [P] Rewrite `get_runnable(reach_json, gauge_observation)` in `src/reach_tools/utils/aw.py` to use `_get_correlation_details()`, cast `beginLowRunnable` and `endHighRunnable` to float, return `True` only when both bounds are present and `float(low) <= gauge_observation <= float(high)`, return `False` otherwise
- [X] T007 Rewrite `get_stage(reach_json, gauge_observation)` in `src/reach_tools/utils/aw.py` using null-collapse logic: collect only non-null thresholds from `[beginLowRunnable, beginMediumRunnable, beginHighRunnable, endHighRunnable]`, map to stage labels `["low", "medium", "high"]`, return `"too low"` / `"too high"` for out-of-range, return `None` when no correlations (depends on T005)
- [X] T008 Remove `get_gauge_value_list()`, `get_range_bias()`, and all old nested-key detection branching from `src/reach_tools/utils/aw.py`; remove `get_gauge_ranges` from `__all__` if present; keep `get_key_from_block()` definition (not in `__all__`, low removal risk)

**Checkpoint**: `utils/procure.py` and `utils/aw.py` are fully migrated. Verify with a quick Python import: `from reach_tools.utils.procure import download_raw_json_from_aw` and `from reach_tools.utils.aw import get_runnable, get_stage`.

---

## Phase 3: User Story 1 — Load a reach from a locally saved new-format file (Priority: P1) 🎯 MVP

**Goal**: `Reach.from_aw_json(path)` correctly parses a tRPC-format JSON file and all public properties return correct values.

**Independent Test**: 
```python
from pathlib import Path
from reach_tools import Reach
reach = Reach.from_aw_json(Path("references/aw_json/reach_000004.json"))
assert reach.river_name == "Sixmile Creek"
assert reach.difficulty == "IV+toV"
assert reach.gauge_min == 900.0
assert reach.gauge_max == 3000.0
assert reach.geometry is not None
```

### Implementation for User Story 1

- [X] T009 [US1] Refactor `Reach._raw_json` property in `src/reach_tools/__init__.py`: **⚠️ NAMING TRAP** — the existing `@property` getter does `return self._raw_json` which causes infinite recursion; the getter is unused and the backing store is never set. Fix: remove the `@property` / `@_raw_json.setter` descriptors entirely and make `_raw_json` a plain instance attribute (set via `self._raw_json = raw_json` in `from_aw_json()`). Then implement a `_hydrate(raw_json: dict)` instance method containing all extraction logic: store `raw_json` into `self._raw_json`; extract `raw_json["pointOfInterests"]` into `self._poi_json` (rename `_rapids_json` → `_poi_json` throughout the class); extract `raw_json["detail"]["correlations"][0]["correlationDetails"]` into `self._correlation_details` if correlations list is non-empty and `correlationDetails` is not null, else `None`. Add `self._correlation_details: dict = None` and `self._poi_json: list = []` to `__init__`.
- [X] T010 [US1] Update `Reach.from_aw_json()` in `src/reach_tools/__init__.py`: extract `reach_id` from `raw_json["id"]` (not the old deep nested path); if input is a `Path`, load file and extract inner object via `json.load(f)[0]["result"]["data"]["json"]`; pass dict directly as `_raw_json`
- [X] T011 [P] [US1] Update identity properties in `src/reach_tools/__init__.py` to read from new paths: `river_name` → `_raw_json["stub"]["river"]`, `reach_name` → `_raw_json["stub"]["section"]`, `alternate_name` → `_raw_json["stub"]["altname"]`, `difficulty` → `_raw_json["stub"]["difficulty"]`; remove `get_key_from_block()` and `remove_backslashes()` calls from these properties
- [X] T012 [P] [US1] Update content/metadata properties in `src/reach_tools/__init__.py`: `description` → `_raw_json["detail"]["description"]`, `length` → `_raw_json["detail"]["length"]`, `abstract` → use description fallback directly (no `abstract_md` field in new API)
- [X] T013 [P] [US1] Update geometry property in `src/reach_tools/__init__.py`: `geometry` → construct `Polyline` from `_raw_json["detail"]["geometry"]` (GeoJSON LineString dict) if not null, else `None`; update `extent` → compute `(xmin, ymin, xmax, ymax)` from `detail.geometry.coordinates` bounds if geometry present, else `None`
- [X] T014 [US1] Update gauge properties in `src/reach_tools/__init__.py`: `has_gauge` → `_raw_json["primaryGaugeStatus"] is not None`; `gauge_observation` → `float(_raw_json["primaryGaugeStatus"]["latestReading"]["value"])` (guard for None at each level); `gauge_metric` → `_raw_json["primaryGaugeStatus"]["metric"]`; `gauge_min` → `float(_correlation_details["beginLowRunnable"])` if `_correlation_details` and value not None; `gauge_max` → `float(_correlation_details["endHighRunnable"])` if same condition (depends on T009)
- [X] T015 [P] [US1] Update secondary gauge properties in `src/reach_tools/__init__.py`: `gauge_units` → `_correlation_details["metric"]` if correlations present; `gauge_source` → `_raw_json["detail"]["correlations"][0]["gaugeInfo"]["gaugeSource"]`; `gauge_id` → `_raw_json["detail"]["correlations"][0]["gaugeInfo"]["gaugeSourceIdentifier"]` — all guarded for empty correlations
- [X] T016 [US1] Update timestamp properties in `src/reach_tools/__init__.py`: `edited_timestamp` → `datetime.fromisoformat(_raw_json["detail"]["editedAt"])`; `update_timestamp` → `datetime.fromtimestamp(_raw_json["updatedAt"], tz=timezone.utc)` (add `timezone` import from `datetime`)
- [X] T017 [US1] Update `ReachPoint.from_aw_json()` signature in `src/reach_tools/__init__.py` to `from_aw_json(cls, aw_json: dict, reach_id: Optional[Union[str, int]] = None) -> "ReachPoint"`. Map `poi["type"]` string to `(point_type, subtype)` using the 9-type lookup table from data-model.md; build geometry from `Point({"x": float(poi["location"]["longitude"]), "y": float(poi["location"]["latitude"]), "spatialReference": {"wkid": 4326}})`; use `reach_id` parameter (default `None`) for `ReachPoint.reach_id`; `update_date=None`; `side_of_river=None`; `description=poi["description"]`; `difficulty=poi["difficulty"]`; `name=poi["name"]`. **Note**: the existing `test_reach_tools.py` does NOT call `ReachPoint.from_aw_json()` directly (only via `reach.reach_points`) — the `reach_id=None` default keeps backward compatibility. No test call-site changes required.
- [X] T018 [US1] Update `Reach.reach_points` property in `src/reach_tools/__init__.py` to build from `self._poi_json` instead of `self._rapids_json`, passing `reach_id=self.reach_id` to `ReachPoint.from_aw_json()`; rename internal `_rapids_json` attribute to `_poi_json` everywhere in the class

**Checkpoint**: Run `env/bin/python -m pytest testing/ -v -k "test_reach_from_aw_json"` — all parametrized fixture tests should pass. Additionally verify in a REPL:
```python
from pathlib import Path
from reach_tools import Reach
reach = Reach.from_aw_json(Path("references/aw_json/reach_000004.json"))
assert reach.gauge_min == 900.0 and reach.gauge_max == 3000.0
reach.gauge_observation = 1500.0
assert reach.runnable is True
assert reach.gauge_stage in ("low", "medium", "runnable")
reach.gauge_observation = 100.0
assert reach.runnable is False
assert reach.gauge_stage == "too low"
```

---

## Phase 4: User Story 2 — Fetch a reach live from the new API (Priority: P2)

**Goal**: `Reach.from_aw(reach_id)` fetches from the new tRPC endpoint and returns a populated `Reach` or `None`.

**Independent Test**:
```python
from reach_tools import Reach
reach = Reach.from_aw(3411)
assert reach is not None
assert reach.river_name == "Tilton"
assert reach.difficulty == "IIItoIV"
assert Reach.from_aw(99999999) is None
```

### Implementation for User Story 2

- [X] T019 [US2] Update `Reach.from_aw()` in `src/reach_tools/__init__.py` to call the updated `download_raw_json_from_aw()` and handle its return contract: if result is `None` (404), return `None`; otherwise pass the dict directly to `cls.from_aw_json()` (fix the existing logic inversion bug — old code returned `None` when JSON was truthy)

**Checkpoint**: Manually call `Reach.from_aw(4)` and `Reach.from_aw(3411)` in a Python REPL and verify properties. Call `Reach.from_aw(99999999)` and verify `None` is returned.

---

## Phase 5: User Story 3 — Remove all old-format dead code (Priority: P3)

**Goal**: Zero occurrences of old API key names or the old endpoint URL remain in `src/` or `scripts/`.

**Independent Test**:
```bash
grep -r "CContainerViewJSON_view\|CRiverMainGadgetJSON_main\|guagesummary\|range_min\|range_max\|isputin\|istakeout\|israpid\|rloc\|americanwhitewater.org/content/River" src/ scripts/
# Expected: no output (zero matches)
```

### Implementation for User Story 3

- [X] T020 [P] [US3] Audit `src/reach_tools/__init__.py` for any remaining references to old keys (`CContainerViewJSON_view`, `CRiverMainGadgetJSON_main`, `CRiverRapidsGadgetJSON_view-rapids`, `guagesummary`, `isputin`, `istakeout`, `israpid`, `ishazard`, `isportage`, `iswaterfall`, `isplayspot`, `rloc`, `updatedate`, `side_of_river` input, `reach_id` from JSON) and remove them
- [X] T021 [P] [US3] Audit `src/reach_tools/utils/aw.py` for remaining old keys (`range_min`, `range_max`, `CContainerViewJSON_view`, `CRiverMainGadgetJSON_main`, `guagesummary`) and remove — confirm `get_gauge_value_list`, `get_gauge_ranges`, `get_range_bias` are gone
- [X] T022 [P] [US3] Confirm `src/reach_tools/utils/procure.py` contains no reference to the old endpoint URL (`americanwhitewater.org/content/River`) — should already be clean from T004
- [X] T023 [US3] Run the grep audit command above and confirm zero matches across `src/` and `scripts/`

**Checkpoint**: `grep` returns no output. All tests still pass.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Fix test file to use new fixture paths/API and clean up test assertions that referenced internal old-format fields.

- [X] T024 [P] Update `testing/test_reach_tools.py` `tilton_dict` fixture: load `data/raw/american_whitewater/aw_00003411.json`, then extract the inner reach object with `data[0]["result"]["data"]["json"]` and return that dict. This is what `get_stage(reach_json, obs)` and `get_runnable(reach_json, obs)` now expect — the full new-format reach object, not the old nested `CContainerViewJSON_view` dict.
- [X] T025 [P] Update `test_reach_from_aw_json` in `testing/test_reach_tools.py`: (1) replace `reach._main_json.get("info").get("geom")` guard with `reach._raw_json.get("detail", {}).get("geometry") is not None`; (2) replace `reach._rapids_json` reference with `reach._poi_json`; (3) replace `reach._main_json.get("guagesummary").get("ranges")` guard with `reach._correlation_details is not None`; (4) add assertions for `reach.runnable` (is bool) and `reach.gauge_stage` (is str or None) when `reach._correlation_details is not None` to close the A1 coverage gap. No `ReachPoint.from_aw_json()` direct call sites exist in `test_reach_tools.py` — no changes needed there.
- [X] T026 Run full test suite: `env/bin/python -m pytest testing/ -v` — confirm all tests pass (expect ~1700+ parametrized runs); document any remaining failures
- [X] T027 Verify `quickstart.md` examples work by running them in a Python REPL: load reach 4 from file, call `from_aw(3411)`, check `get_stage` and `get_runnable` directly

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Fixtures)**: No code dependencies — can start immediately
- **Phase 2 (Foundational)**: Independent of Phase 1; can run in parallel with fixture replacement
- **Phase 3 (US1)**: Depends on Phase 2 complete (imports `procure.py` and `aw.py`)
- **Phase 4 (US2)**: Depends on Phase 3 (uses updated `from_aw_json()` and `_raw_json` setter)
- **Phase 5 (US3)**: Depends on Phase 3 + Phase 4 (audit after all replacements done)
- **Phase 6 (Polish)**: Depends on Phase 3 (test file references internal attribute names)

### User Story Dependencies

- **US1 (P1)**: Depends on Foundational (Phase 2) — blocks US2 and US3
- **US2 (P2)**: Depends on US1 (`from_aw_json` must work before `from_aw` can use it)
- **US3 (P3)**: Depends on US1 + US2 (dead code audit after all replacements)

### Within Each Phase — Parallel Opportunities

- **Phase 2**: T005 (`_get_correlation_details`) and T006 (`get_runnable`) can run in parallel; T007 depends on T005
- **Phase 3**: T011, T012, T013, T015, T016, T017 are all parallel (different properties/methods); T009 and T010 must come first (they establish `_raw_json` and `_poi_json`); T014 and T018 depend on T009
- **Phase 5**: T020, T021, T022 all parallel (different files)
- **Phase 6**: T024 and T025 parallel (different test functions)

---

## Parallel Execution Example: Phase 3 (US1)

```
Start:    T009 (setter) → T010 (from_aw_json)
Parallel: T011, T012, T013, T015, T016, T017  [once T009 done]
Serial:   T014 (gauge props, needs T009) → T018 (reach_points, needs T009+T017)
End:      Run pytest -k test_reach_from_aw_json
```

---

## Implementation Strategy

**MVP Scope**: Complete Phase 1 + Phase 2 + Phase 3 (US1). This delivers a working local-file parser with correct output for all downloaded fixtures.

**Increment 2**: Phase 4 (US2) — live fetch from new API.

**Increment 3**: Phase 5 + 6 (US3 + Polish) — dead code removal + test cleanup.

Each increment is independently runnable and testable. The test suite can be run after each phase to track progress.
