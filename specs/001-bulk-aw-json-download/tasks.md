# Tasks: Bulk AW Reach JSON Downloader

**Input**: Design documents from `specs/001-bulk-aw-json-download/`
**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ quickstart.md ✅

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Exact file paths included in all descriptions

---

## Phase 1: Setup

**Purpose**: Create the script file and output directory scaffolding

- [x] T001 Create `scripts/download_aw_json.py` with module docstring, imports (`json`, `pathlib`, `time`, `concurrent.futures`, `requests`, `tqdm`), and top-level constants (`API_URL`, `OUT_DIR`, `ID_RANGE`, `MAX_WORKERS`, `MAX_RETRIES`, `BACKOFF_BASE`, `RATE_LIMIT_DEFAULT_WAIT`)
- [x] T002 [P] Verify `references/` directory exists at repo root; add `references/aw_json/.gitkeep` so the output directory is tracked in git

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core helpers all user stories depend on — validity check and atomic write — must be complete before story implementation begins

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 Implement `_is_valid_response(data: list) -> bool` helper in `scripts/download_aw_json.py` — returns `True` if `data[0]["result"]["data"]["json"]` is non-null, `False` otherwise; handles `KeyError`/`IndexError`/`TypeError` gracefully
- [x] T004 [P] Implement `_write_atomic(path: Path, text: str) -> None` helper in `scripts/download_aw_json.py` — writes `text` to `path.with_suffix(".tmp")` then renames to `path` (atomic on POSIX)

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 - Download All Valid Reaches (Priority: P1) 🎯 MVP

**Goal**: Fetch the tRPC API for each reach ID 1–2000, detect validity, and save valid reaches as `references/aw_json/reach_XXXXXX.json` containing the full response array

**Independent Test**: Run `python scripts/download_aw_json.py` and verify at least one file appears in `references/aw_json/` with the correct name format and parseable JSON content; also verify that for a known-invalid ID (e.g., 9999) no file is written

### Implementation for User Story 1

- [x] T005 [US1] Implement `_fetch_one(reach_id: int) -> dict` in `scripts/download_aw_json.py` — performs the GET request to `API_URL` with `batch=1` and URL-encoded `input` param, returns `{"reach_id": reach_id, "outcome": ..., "message": ...}`; implements retry loop (up to `MAX_RETRIES`) with `BACKOFF_BASE ** attempt` exponential backoff for transient errors (non-200 except 404/429, empty body, JSON parse failure)
- [x] T006 [US1] Add HTTP 404 handling inside `_fetch_one` — return `{"outcome": "skipped-invalid"}` immediately without retry
- [x] T007 [US1] Add HTTP 429 handling inside `_fetch_one` — read `Retry-After` header (default `RATE_LIMIT_DEFAULT_WAIT`), sleep that many seconds, then retry without consuming the retry budget
- [x] T008 [US1] Add validity check inside `_fetch_one` after a successful HTTP 200 response — call `_is_valid_response(data)`; if `False` return `{"outcome": "skipped-invalid"}`; if `True` call `_write_atomic(output_path, resp.text)` and return `{"outcome": "saved"}`

**Checkpoint**: At this point User Story 1 is fully functional — script can download and save valid reaches, skip invalid reaches, and handles all error cases

---

## Phase 4: User Story 2 - Skip Already-Downloaded Reaches (Priority: P2)

**Goal**: Before fetching, check if the output file already exists on disk; if so skip the reach without making any HTTP request, enabling safe re-runs and resume after interruption

**Independent Test**: Run the script once, note files saved, run again and verify no new requests are made (all outcomes are `skipped-exists`) and files are unchanged

### Implementation for User Story 2

- [x] T009 [US2] Add early-exit check at the top of `_fetch_one` in `scripts/download_aw_json.py` — if `output_path.exists()` return `{"outcome": "skipped-exists"}` before any network call

**Checkpoint**: At this point User Stories 1 and 2 both work — the script is fully resumable

---

## Phase 5: User Story 3 - Progress Visibility (Priority: P3)

**Goal**: Show a live progress bar and per-reach outcome lines while the script runs; print a summary on completion

**Independent Test**: Run the script and observe a `tqdm` progress bar advancing, per-reach lines printing (`saved`, `skipped-exists`, `skipped-invalid`, `error`), and a final summary count

### Implementation for User Story 3

- [x] T010 [P] [US3] Implement `main()` in `scripts/download_aw_json.py` — creates `OUT_DIR` with `mkdir(parents=True, exist_ok=True)`, builds job list from `ID_RANGE`, initialises counters (`saved`, `skipped_exists`, `skipped_invalid`, `errors`), dispatches `_fetch_one` across a `ThreadPoolExecutor(max_workers=MAX_WORKERS)`, collects results via `executor.map`, updates counters, calls `tqdm.write()` for each per-reach outcome line, advances a `tqdm` progress bar
- [x] T011 [US3] Add `if __name__ == "__main__": main()` entry point at the bottom of `scripts/download_aw_json.py`
- [x] T012 [US3] Add final summary `print()` in `main()` after all results are processed — format: `Summary: {saved} saved, {skipped_invalid} skipped (invalid), {skipped_exists} skipped (exists), {errors} errors`

**Checkpoint**: All three user stories are complete — script is fully functional with live progress and summary

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T013 [P] Add `User-Agent` header to all requests in `_fetch_one` in `scripts/download_aw_json.py` to match browser-like string (reduces likelihood of server-side blocking)
- [x] T014 [P] Add 10-second `timeout` to all `requests.get()` calls in `_fetch_one` in `scripts/download_aw_json.py` to prevent hung workers
- [x] T015 Smoke-test the complete script end-to-end: run `python scripts/download_aw_json.py` and verify output files exist in `references/aw_json/`, filenames match `reach_XXXXXX.json`, each file parses as valid JSON, a re-run skips all existing files

---

## Dependencies

```
T001 → T003, T004 (setup must exist before helpers)
T003, T004 → T005 (helpers needed before fetch logic)
T005 → T006, T007, T008 (retry loop must exist before specialised handlers)
T008 → T009 (US1 complete before adding US2 skip logic)
T009 → T010 (US2 complete before wiring into main)
T010 → T011 → T012 (main scaffolding before entry point and summary)
T012 → T013, T014, T015 (polish after full pipeline works)
```

## Parallel Opportunities

- T002 can be done in parallel with T003/T004
- T003 and T004 can be done in parallel with each other
- T006 and T007 can be done in parallel once T005 exists
- T013 and T014 can be done in parallel

## Implementation Strategy

**MVP = Phase 3 complete (T001–T008)**: a working single-threaded script that downloads and saves reaches, skips invalids, and retries errors — delivers core value immediately.

**Full delivery**: Add Phase 4 (resume, T009) → Phase 5 (progress/main, T010–T012) → Phase 6 (polish, T013–T015).

## Summary

| Phase | Tasks | User Story |
|---|---|---|
| Setup | T001–T002 | — |
| Foundation | T003–T004 | — |
| Phase 3 | T005–T008 | US1 (P1) 🎯 MVP |
| Phase 4 | T009 | US2 (P2) |
| Phase 5 | T010–T012 | US3 (P3) |
| Polish | T013–T015 | — |
| **Total** | **15 tasks** | |

**Parallel opportunities**: 6 identified  
**Independent test criteria**: Each phase has a standalone verification step  
**Suggested MVP scope**: T001–T008 (Phases 1–3)
