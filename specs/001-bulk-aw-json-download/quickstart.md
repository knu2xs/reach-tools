# Quickstart: Bulk AW Reach JSON Downloader

**Feature**: 001-bulk-aw-json-download  
**Date**: 2026-05-11

---

## Prerequisites

- Python environment activated (`conda activate ./env` or equivalent)
- `requests` and `tqdm` installed (both already present in the project env)
- Network access to `trpc-api.americanwhitewater.org`

---

## Run the Script

From the project root:

```bash
python scripts/download_aw_json.py
```

The script will:
1. Create `references/aw_json/` if it does not already exist
2. Iterate over reach IDs 1–2000 using a 5-worker thread pool
3. Skip any reach whose file is already present on disk
4. Save each valid reach as `references/aw_json/reach_XXXXXX.json` (6-digit zero-padded ID)
5. Print a live progress bar and per-reach outcome to the console

---

## Resume a Partial Run

Just re-run the same command — already-downloaded files are detected by presence on disk and skipped without re-fetching:

```bash
python scripts/download_aw_json.py
```

---

## Expected Output

```
Downloading AW reaches 1–2000 → references/aw_json/
Skipped (exists):  reach_000001.json
Saved:             reach_000002.json
Skipped (invalid): reach_000005.json
...
100%|████████████████| 2000/2000 [04:12<00:00,  7.92it/s]

Summary: 1423 saved, 411 skipped (invalid), 166 skipped (exists), 0 errors
```

---

## Output Files

| Location | `references/aw_json/` |
|---|---|
| Filename pattern | `reach_000001.json` … `reach_002000.json` |
| Content | Full tRPC response array as returned by the API |
| Encoding | UTF-8 |

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| `requests.exceptions.ConnectionError` | No network | Check connectivity |
| Script pauses for 30+ seconds | Hit HTTP 429 rate limit | Normal — script will resume automatically |
| File count lower than expected | Some IDs truly don't exist on AW | Expected; not all IDs 1–2000 are valid reaches |
| `ModuleNotFoundError: tqdm` | Wrong environment active | Run `conda activate ./env` first |
