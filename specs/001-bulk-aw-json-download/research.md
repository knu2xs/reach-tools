# Research: Bulk AW Reach JSON Downloader

**Feature**: 001-bulk-aw-json-download  
**Date**: 2026-05-11  
**Status**: Complete — all NEEDS CLARIFICATION resolved

---

## API Behaviour (Verified by Live Testing)

### Decision
Use the tRPC endpoint `https://trpc-api.americanwhitewater.org/reach/reachDetailWithPhotos` with `batch=1` and URL-encoded `input` query parameter.

### Findings

| Scenario | HTTP Status | Response body |
|---|---|---|
| Valid reach (e.g., 1, 2, 3411) | 200 | JSON array: `[{"result": {"data": {"json": { ...reach payload... }}}}]` |
| Invalid/missing reach (e.g., 9999) | 404 | JSON array: `[{"error": {"json": {"message": "Invalid reach.", "code": -32004, "data": {"code": "NOT_FOUND", ...}}}}]` |
| Old endpoint (`/content/River/detail/id/{id}/.json`) | 502 | Bad Gateway HTML — server is down |

### Validity Detection (Confirmed)
- HTTP 404 → invalid reach (AW returns a tRPC error payload, not a blank body)
- HTTP 200 + `data[0]["result"]["data"]["json"]` is non-null → valid reach
- The spec uses "non-null `result.data.json`" as the validity gate; confirmed this is the correct field path

### Full Response Saved
Per clarification, the **complete tRPC response array** as returned (HTTP 200 body) is saved per file — not just the inner reach object.

---

## Python Standard Library: `concurrent.futures.ThreadPoolExecutor`

### Decision
Use `concurrent.futures.ThreadPoolExecutor` with `max_workers=5` for concurrent requests. No third-party concurrency library needed.

### Rationale
- Ships with Python 3.10+ standard library; zero additional dependency
- `ThreadPoolExecutor` is appropriate for I/O-bound work (HTTP requests)
- 5 workers is conservative enough to avoid triggering rate-limiting on the AW server
- Work queue is the list of reach IDs not yet on disk; each worker pulls from the queue atomically via `executor.map`

### Alternatives Considered
- `asyncio` + `aiohttp`: More complex, requires third-party dependency (`aiohttp`), overkill for a one-shot batch script
- `multiprocessing`: CPU-bound concurrency model, inappropriate for I/O-bound HTTP work
- Single-threaded sequential: Too slow (~17–33 minutes for 2000 IDs at 0.5–1s each)

---

## Retry Strategy: `tenacity` vs Manual

### Decision
Implement retry logic manually using a simple loop with `time.sleep` for exponential backoff. No additional library.

### Rationale
- `tenacity` is not installed in the project environment; adding a dependency for 20 lines of retry logic is unnecessary
- Manual implementation is transparent and easy to read
- Backoff: attempt 1 waits 2s, attempt 2 waits 4s, attempt 3 waits 8s (2^attempt seconds)
- HTTP 429 handling is outside the retry budget: pause for `Retry-After` header value (or 30s) then retry — all workers pause proportionally

### Alternatives Considered
- `tenacity`: Cleaner decorator-based API but adds a dependency not present in the project
- `urllib3` retry adapter: Works but couples retry logic to the HTTP layer rather than the application layer

---

## Atomic File Writes

### Decision
Write to a `.tmp` file in the same directory, then `Path.rename()` to the final path. On POSIX (macOS/Linux), rename is atomic at the OS level.

### Rationale
- Prevents partially-written JSON from being seen as a valid completed file on resume
- `Path.rename()` is atomic on same-filesystem moves (POSIX guarantee)
- Simple, no third-party dependency

---

## Progress Reporting: `tqdm`

### Decision
Use `tqdm` for a live progress bar plus per-reach status messages to stdout. `tqdm` is already installed in the project environment.

### Rationale
- `tqdm` integrates cleanly with `ThreadPoolExecutor` via `tqdm(executor.map(...), total=n)`
- Provides running count of processed IDs without manual counter management
- Per-reach outcome (saved / skipped-exists / skipped-invalid / error) logged via `tqdm.write()` which does not corrupt the progress bar

---

## Output Directory & File Naming

### Decision
- Output dir: `references/aw_json/` (created with `Path.mkdir(parents=True, exist_ok=True)`)
- Filename: `reach_{reach_id:06d}.json` (e.g., `reach_000042.json`)

### Confirmed
Matches FR-004 and SC-005 exactly.

---

## Packages Available in Project Environment

Verified present (no new installs needed):
- `requests` — HTTP client
- `tqdm` — progress bars
- `concurrent.futures` — stdlib ThreadPoolExecutor
- `json`, `pathlib`, `time`, `os` — stdlib

---

## All NEEDS CLARIFICATION Items Resolved

| Item | Resolution |
|---|---|
| File content (full response vs inner object) | Full tRPC response array |
| Validity detection signal | Non-null `result.data.json` (HTTP 200) vs HTTP 404 |
| Sequential vs concurrent | Concurrent, `ThreadPoolExecutor`, 5 workers |
| Retry count and backoff | 3 retries, exponential backoff at 2s |
| HTTP 429 handling | Respect `Retry-After` header (30s default), outside retry budget |
