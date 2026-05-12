# Data Model: Bulk AW Reach JSON Downloader

**Feature**: 001-bulk-aw-json-download  
**Date**: 2026-05-11

---

## Entities

This feature is a standalone script — there is no persistent data model or database schema. The relevant entities are the data structures the script operates on.

---

### ReachID

An integer in the range `[1, 2000]` identifying an American Whitewater reach.

| Field | Type | Notes |
|---|---|---|
| `reach_id` | `int` | 1–2000 inclusive |

**Validation**: Integer, 1 ≤ reach_id ≤ 2000.  
**Derivation**: Generated as `range(1, 2001)` at script startup.

---

### DownloadJob

Represents a single unit of work dispatched to the thread pool.

| Field | Type | Notes |
|---|---|---|
| `reach_id` | `int` | The reach ID to attempt |
| `output_path` | `Path` | `references/aw_json/reach_{reach_id:06d}.json` |
| `skip` | `bool` | True if output file already exists on disk |

**State Transitions**:
```
[pending] → skip=True → [skipped-exists]
[pending] → fetch → HTTP 404 → [skipped-invalid]
[pending] → fetch → HTTP 200, null json → [skipped-invalid]
[pending] → fetch → HTTP 200, valid json → write → [saved]
[pending] → fetch → error (retries exhausted) → [error]
[pending] → fetch → HTTP 429 → wait → retry → [any of above]
```

---

### DownloadResult

The outcome of processing a single `DownloadJob`.

| Field | Type | Possible Values |
|---|---|---|
| `reach_id` | `int` | The reach ID processed |
| `outcome` | `str` | `"saved"`, `"skipped-exists"`, `"skipped-invalid"`, `"error"` |
| `message` | `str` \| `None` | Optional detail (e.g., error message) |

---

### OutputFile

A JSON file on disk representing a successfully downloaded valid reach.

| Attribute | Value |
|---|---|
| Location | `references/aw_json/` |
| Filename | `reach_{reach_id:06d}.json` (e.g., `reach_000042.json`) |
| Content | Complete tRPC response array as returned by the API |
| Encoding | UTF-8 |
| Write mode | Atomic (temp file + rename) |

---

## tRPC Response Shape (Reference)

The raw JSON saved per valid reach has this top-level structure:

```json
[
  {
    "result": {
      "data": {
        "json": {
          "id": "3411",
          "stub": { "river": "Tilton", "section": "...", ... },
          "primaryGaugeStatus": { ... },
          "pointOfInterests": [ ... ],
          "alerts": [ ... ],
          "photos": [ ... ],
          "detail": { ... },
          "updatedAt": 1778549978
        }
      }
    }
  }
]
```

Invalid reach response shape (HTTP 404, not saved):

```json
[
  {
    "error": {
      "json": {
        "message": "Invalid reach.",
        "code": -32004,
        "data": { "code": "NOT_FOUND", "httpStatus": 404 }
      }
    }
  }
]
```
