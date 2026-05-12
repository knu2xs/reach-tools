# Implementation Plan: Bulk AW Reach JSON Downloader

**Branch**: `main` | **Date**: 2026-05-11 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/001-bulk-aw-json-download/spec.md`

## Summary

A Python script (`scripts/download_aw_json.py`) that downloads raw JSON for all valid American Whitewater reaches with IDs 1–2000 from the tRPC endpoint `https://trpc-api.americanwhitewater.org/reach/reachDetailWithPhotos`, saving the full response array per file to `references/aw_json/reach_XXXXXX.json`. Uses a 5-worker `ThreadPoolExecutor` for concurrent I/O, skips already-downloaded files to support resume, handles HTTP 404 (invalid reach) and HTTP 429 (rate limit), and retries transient errors up to 3 times with exponential backoff.

## Technical Context

**Language/Version**: Python 3.12 (project env)  
**Primary Dependencies**: `requests` (HTTP), `tqdm` (progress), `concurrent.futures` (stdlib ThreadPoolExecutor)  
**Storage**: Local filesystem — `references/aw_json/` directory, one JSON file per valid reach  
**Testing**: pytest (existing project test runner)  
**Target Platform**: macOS/Linux (developer workstation)  
**Project Type**: CLI script (one-shot batch utility)  
**Performance Goals**: Complete 2000 requests in under 10 minutes with 5 concurrent workers  
**Constraints**: Polite to remote server — max 5 concurrent workers; respects HTTP 429 Retry-After  
**Scale/Scope**: 2000 reach IDs; expected ~1000–1500 valid reaches based on AW data density

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The project constitution file is a blank template with no principles populated. No constitutional gates apply. ✅ Pass.

## Project Structure

### Documentation (this feature)

```text
specs/001-bulk-aw-json-download/
├── plan.md          ← this file
├── research.md      ← Phase 0 complete
├── data-model.md    ← Phase 1 complete
├── quickstart.md    ← Phase 1 complete
└── tasks.md         ← Phase 2 output (from /speckit.tasks)
```

### Source Code (repository root)

```text
scripts/
└── download_aw_json.py    ← new script (sole deliverable)

references/
└── aw_json/               ← created by script at runtime
    ├── reach_000001.json
    ├── reach_000002.json
    └── ...
```

**Structure Decision**: Single-script utility. No new package, module, or library. Placed in `scripts/` consistent with existing scripts (`make_data.py`, `make_pyt_archive.py`). Output to `references/aw_json/` as specified.

---

## Implementation Design

### Script: `scripts/download_aw_json.py`

#### Top-level constants

```python
API_URL     = "https://trpc-api.americanwhitewater.org/reach/reachDetailWithPhotos"
OUT_DIR     = Path(__file__).parent.parent / "references" / "aw_json"
ID_RANGE    = range(1, 2001)
MAX_WORKERS = 5
MAX_RETRIES = 3
BACKOFF_BASE = 2        # seconds — attempt n waits BACKOFF_BASE^n seconds
RATE_LIMIT_DEFAULT_WAIT = 30   # seconds — used when Retry-After header absent
```

#### Function: `fetch_reach(reach_id: int) -> DownloadResult`

Fetches one reach ID and writes to disk. Called by each worker thread.

```
1. Compute output_path = OUT_DIR / f"reach_{reach_id:06d}.json"
2. If output_path.exists(): return DownloadResult(reach_id, "skipped-exists")
3. attempt = 0
4. LOOP:
   a. GET API_URL with params batch=1, input=json-encoded reach ID
      headers: User-Agent set to browser-like string
      timeout: 10 seconds
   b. If response.status_code == 429:
      - Read Retry-After header; default to RATE_LIMIT_DEFAULT_WAIT
      - Sleep(wait_seconds)
      - Continue loop (does NOT increment attempt)
   c. If response.status_code == 404:
      - return DownloadResult(reach_id, "skipped-invalid")
   d. If response.status_code != 200 OR response body empty:
      - attempt += 1
      - If attempt >= MAX_RETRIES: return DownloadResult(reach_id, "error", msg)
      - Sleep(BACKOFF_BASE ** attempt)
      - Continue loop
   e. Parse JSON; extract data[0]["result"]["data"]["json"]
   f. If inner is None: return DownloadResult(reach_id, "skipped-invalid")
   g. Write full response array atomically:
      - tmp_path = output_path.with_suffix(".tmp")
      - Write resp.text to tmp_path (UTF-8)
      - tmp_path.rename(output_path)
   h. return DownloadResult(reach_id, "saved")
```

#### Function: `main()`

```
1. OUT_DIR.mkdir(parents=True, exist_ok=True)
2. Build jobs = [id for id in ID_RANGE]
3. Initialise counters: saved=0, skipped_exists=0, skipped_invalid=0, errors=0
4. with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
     with tqdm(total=len(jobs), unit="reach") as pbar:
       for result in executor.map(fetch_reach, jobs):
         - Increment appropriate counter based on result.outcome
         - tqdm.write(f"{result.outcome:20s} reach_{result.reach_id:06d}")
         - pbar.update(1)
5. Print summary line: saved / skipped-invalid / skipped-exists / errors
```

#### Error handling summary

| Condition | Handling |
|---|---|
| HTTP 404 | `skipped-invalid` — no retry |
| HTTP 429 | Sleep `Retry-After` (or 30s), retry; does not consume retry budget |
| HTTP other non-200 | Retry up to 3×, exponential backoff; then `error` |
| Empty response body | Retry (treated as transient) |
| `result.data.json` is null | `skipped-invalid` — no retry |
| JSON parse failure | Retry (treated as transient) |
| Network timeout | Retry (10s request timeout; backoff between attempts) |
| Interrupt (Ctrl-C) | Already-written files intact; re-run resumes |

---

## Artifacts

| Artifact | Path | Status |
|---|---|---|
| Specification | `specs/001-bulk-aw-json-download/spec.md` | ✅ Complete |
| Research | `specs/001-bulk-aw-json-download/research.md` | ✅ Complete |
| Data Model | `specs/001-bulk-aw-json-download/data-model.md` | ✅ Complete |
| Quickstart | `specs/001-bulk-aw-json-download/quickstart.md` | ✅ Complete |
| Contracts | N/A — internal script, no external interface | — |
| Tasks | `specs/001-bulk-aw-json-download/tasks.md` | ⏳ `/speckit.tasks` |
| Script | `scripts/download_aw_json.py` | ⏳ `/speckit.implement` |
