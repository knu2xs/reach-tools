# Implementation Plan: Migrate to tRPC API

**Branch**: `main` | **Date**: 2026-05-11 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/002-migrate-to-trpc-api/spec.md`

## Summary

Migrate the `reach_tools` Python library from the defunct American Whitewater legacy JSON endpoint to the new tRPC API at `trpc-api.americanwhitewater.org`. The migration replaces all parsing, downloading, and data-access logic across three source files (`utils/procure.py`, `src/reach_tools/__init__.py`, `utils/aw.py`), replaces ~5136 old-format test fixtures with new-format equivalents from `references/aw_json/`, and removes all dead-code branches that detected the old JSON structure. The public `Reach` and `ReachPoint` API is preserved — property names remain unchanged; only the underlying data source changes.

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: `arcgis` (geometry types: `Polyline`, `Point`, `Geometry`, `Feature`), `requests` (HTTP), `pandas`, `numpy` (centroid), `pytest` (testing)  
**Storage**: JSON files — test fixtures in `data/raw/american_whitewater/`, reference cache in `references/aw_json/`  
**Testing**: pytest 8.3.5; parameterized over fixture directory; run with `env/bin/python -m pytest testing/`  
**Target Platform**: Developer workstation (library, not a service)  
**Project Type**: Python library  
**Performance Goals**: N/A — library is used interactively, not latency-sensitive  
**Constraints**: No new package dependencies; all public `Reach` and `ReachPoint` property names must remain unchanged; `from_aw_json()` accepts new-format tRPC JSON only (single code path, no dual-format branching)  
**Scale/Scope**: ~1700 valid test fixtures (IDs 1–2000 with valid AW data); library used locally

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The constitution file (`.specify/memory/constitution.md`) contains only unfilled template placeholders — no project principles or gates are defined. **No violations possible. ✓ Pass.**

Post-design re-check: Still no violations. ✓ Pass.

## Project Structure

### Documentation (this feature)

```text
specs/002-migrate-to-trpc-api/
├── plan.md              # This file
├── research.md          # Phase 0: decisions and API analysis
├── data-model.md        # Phase 1: old → new field mapping
├── quickstart.md        # Phase 1: usage after migration
├── contracts/
│   └── public-api.md    # Phase 1: public Reach / ReachPoint API contract
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code

```text
src/reach_tools/
├── __init__.py          # Reach + ReachPoint classes — update parser, properties, from_aw*
└── utils/
    ├── __init__.py      # Shared utilities — no changes
    ├── aw.py            # AW gauge functions — replace get_gauge_ranges / get_gauge_value_list / get_runnable / get_stage
    ├── procure.py       # HTTP download — replace URL, params, retry logic, return value
    └── reference.py     # Lookup tables — no changes

testing/
└── test_reach_tools.py  # Update fixture paths, tilton fixture file, gauge function call sites

data/raw/american_whitewater/
└── aw_*.json            # Replace all ~5136 old-format files with new-format from references/aw_json/

references/aw_json/
└── reach_*.json         # Source of truth for test fixtures — existing, ~1700 valid files
```

**Structure Decision**: Single-project library layout. No new files created in `src/`; all changes are in-place edits to the three existing source modules plus the test file and fixture directory.

## Complexity Tracking

> No constitution violations. Table not required.
