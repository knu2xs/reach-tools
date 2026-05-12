# Feature Specification: Bulk AW Reach JSON Downloader

**Feature Branch**: `001-bulk-aw-json-download`  
**Created**: 2026-05-11  
**Status**: Draft  
**Input**: User description: "Create a script in the scripts directory that downloads and saves the raw json to a folder ./references/aw_json with a naming convention of reach_<six digit reach id>.json retrieved from the rest endpoint https://trpc-api.americanwhitewater.org/reach/reachDetailWithPhotos for reach ids 1 to 2000, taking into account some reaches are not valid."

---

## Clarifications

### Session 2026-05-11

- Q: What should each `reach_XXXXXX.json` file contain — the inner reach object or the full tRPC response array? → A: Full tRPC response array exactly as returned by the API
- Q: What makes a reach valid — what JSON signal confirms a reach exists? → A: Any non-null `result.data.json` in the response is sufficient
- Q: Should the script use sequential or concurrent requests? → A: Concurrent with a limited thread pool
- Q: How many retries and what delay between retries? → A: 3 retries with exponential backoff starting at 2 seconds
- Q: Should HTTP 429 be handled differently from other transient errors? → A: Yes — respect the `Retry-After` header (or wait 30s if absent); does not count against the 3-retry limit

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Download all valid reaches (Priority: P1)

A researcher or developer runs the script from the project root and it fetches raw JSON for all valid American Whitewater reach IDs in the range 1–2000, saving each to `references/aw_json/reach_<reach_id padded to 6 digits>.json`.

**Why this priority**: This is the core purpose of the script — without it there is nothing else to test or extend.

**Independent Test**: Run the script and verify that one or more valid reach files appear in `references/aw_json/` with the correct naming convention and non-empty, parseable JSON content.

**Acceptance Scenarios**:

1. **Given** the script is run with no arguments, **When** it completes, **Then** all reachable valid reaches in the range 1–2000 are saved as individual JSON files in `references/aw_json/`.
2. **Given** a reach ID maps to a valid reach on AW, **When** the script downloads it, **Then** the saved file is named `reach_000042.json` (zero-padded to 6 digits) and contains the full tRPC response array as parseable JSON.
3. **Given** a reach ID is invalid (any of: HTTP 4xx/5xx, empty response body, or a null `result.data.json` in the response), **When** the script encounters it, **Then** no file is written for that reach ID and the script continues to the next ID.

---

### User Story 2 - Skip already-downloaded reaches (Priority: P2)

A developer re-runs the script after a partial run or after new reach IDs become available. Reaches already saved to disk are skipped without re-fetching.

**Why this priority**: The range 1–2000 involves many HTTP requests; resumability avoids redundant network traffic and allows safe re-runs.

**Independent Test**: Run the script once, interrupt it, then run it again and verify it skips files already present on disk without making duplicate requests.

**Acceptance Scenarios**:

1. **Given** a file for reach `000050` already exists in `references/aw_json/`, **When** the script runs, **Then** reach 50 is not re-fetched and the existing file is left unchanged.
2. **Given** no files exist in `references/aw_json/`, **When** the script runs, **Then** it attempts every reach ID in the range.

---

### User Story 3 - Progress visibility (Priority: P3)

A developer running the script can see which reach is currently being processed, how many have been completed, and how many were skipped (invalid or already downloaded).

**Why this priority**: A bulk download of 2000 requests is long-running; progress feedback is important for confidence and debugging.

**Independent Test**: Run the script and observe that output messages indicate the current reach ID, success/skip/invalid status, and a running count.

**Acceptance Scenarios**:

1. **Given** the script is running, **When** a reach is successfully downloaded, **Then** a message indicates the reach ID and success.
2. **Given** a reach is invalid, **When** it is skipped, **Then** a message indicates the reach ID and that it was skipped as invalid.
3. **Given** a file already exists, **When** it is skipped, **Then** a message indicates the reach ID and that it was skipped as already present.

---

### Edge Cases

- What happens if the network request times out? The script retries up to 3 times with exponential backoff starting at 2 seconds before marking the reach as unreachable and moving on.
- What happens if the server returns HTTP 429? The script waits for the duration specified in the `Retry-After` header (or 30 seconds if absent), then retries — this does not count against the 3-retry limit.
- What happens if the `references/aw_json/` output directory does not exist? The script must create it automatically.
- What happens if the JSON response has HTTP 200 but `result.data.json` is null? The reach is considered invalid and no file is written.
- What happens if the script is interrupted mid-run? Already-saved files must be intact (no partial writes); re-running picks up from where it left off.
- What happens if reach IDs above 2000 are passed? The script only processes IDs 1–2000 by default.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The script MUST be located in the `scripts/` directory and runnable directly from the project root.
- **FR-002**: The script MUST iterate over reach IDs 1 through 2000 inclusive.
- **FR-003**: For each reach ID, the script MUST request data from the tRPC endpoint `https://trpc-api.americanwhitewater.org/reach/reachDetailWithPhotos` using query parameters `batch=1` and `input={"0":{"json":{"reachID":"<id>"}}}`, saving the full response array as returned.
- **FR-004**: The script MUST save valid reach data as `references/aw_json/reach_<reach_id_zero_padded_6>.json` (e.g., `reach_000042.json`), containing the complete tRPC response array.
- **FR-005**: The script MUST consider a reach invalid if the HTTP status is 4xx/5xx, the response body is empty, or `data[0]["result"]["data"]["json"]` in the parsed response is null. In all such cases no file is written and the script continues.
- **FR-006**: The script MUST skip re-downloading a reach if the corresponding output file already exists on disk.
- **FR-007**: The script MUST create the `references/aw_json/` output directory if it does not already exist.
- **FR-008**: The script MUST write files atomically (write to a temp file, then rename) to prevent corrupt partial files on interruption.
- **FR-009**: The script MUST use a thread pool with a fixed concurrency limit to fetch multiple reach IDs simultaneously while still being respectful of the remote server.
- **FR-010**: The script MUST retry failed requests (network timeout or transient HTTP errors, excluding 429) up to 3 times with exponential backoff starting at 2 seconds. On HTTP 429, the script MUST pause for the duration in the `Retry-After` response header (or 30 seconds if the header is absent) before retrying, and this pause does NOT count against the 3-retry limit.
- **FR-011**: The script MUST log progress to the console, including current reach ID, outcome (saved / skipped-exists / skipped-invalid / error), and a running summary count.

### Key Entities

- **Reach**: An American Whitewater river reach identified by a numeric ID. Valid reaches contain reach metadata (name, difficulty, geometry, gauge data). Invalid reaches produce no usable data.
- **Output File**: A JSON file saved to `references/aw_json/reach_<6-digit-id>.json` containing the raw API response for a valid reach.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a full run, `references/aw_json/` contains one file per valid reach in the range 1–2000, with zero corrupted or empty files.
- **SC-002**: A re-run of the script after full completion produces no new file writes and completes significantly faster than the initial run.
- **SC-003**: All saved files are parseable as JSON.
- **SC-004**: The script completes the full 1–2000 range without crashing, even when individual reaches are invalid or the network is intermittently slow.
- **SC-005**: The output directory and file naming convention matches exactly: `references/aw_json/reach_XXXXXX.json` where `XXXXXX` is the reach ID zero-padded to 6 digits.

---

## Assumptions

- The tRPC endpoint accepts a `batch=1&input={"0":{"json":{"reachID":"<id>"}}}` query string and returns a JSON array; the full array is saved as-is for valid reaches.
- A reach is invalid if HTTP status is 4xx/5xx, the response body is empty, or `data[0]["result"]["data"]["json"]` is null — no file is written in these cases.
- The script uses concurrent requests via a thread pool; the concurrency limit should be conservative (e.g., 5 workers) to avoid rate-limiting.
- Transient errors are retried up to 3 times with exponential backoff starting at 2 seconds. HTTP 429 triggers a pause respecting `Retry-After` (default 30s) outside the retry budget.
- The script does not need a CLI argument interface for the ID range in v1; 1–2000 is hardcoded as the default range.
- The existing `references/` directory already exists at the project root; only the `aw_json/` subdirectory needs to be created if missing.
- Network connectivity is available when the script is run.
- Python is the implementation language, consistent with the rest of the project.
