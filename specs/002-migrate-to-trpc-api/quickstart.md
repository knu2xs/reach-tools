# Quickstart: reach_tools after tRPC Migration

**Feature**: 002-migrate-to-trpc-api  
**Date**: 2026-05-11

This guide shows how to use `reach_tools` after the API migration. The public interface is unchanged — all existing code that uses `Reach` and `ReachPoint` properties continues to work without modification.

---

## Load a reach from a local file

```python
from pathlib import Path
from reach_tools import Reach

# Load from a file in references/aw_json/ (new tRPC format)
pth = Path("references/aw_json/reach_000004.json")
reach = Reach.from_aw_json(pth)

print(reach.river_name)   # "Sixmile Creek"
print(reach.difficulty)   # "IV+toV"
print(reach.length)       # 6.0 (miles)
print(reach.gauge_min)    # 900.0
print(reach.gauge_max)    # 3000.0
```

---

## Fetch a reach live from American Whitewater

```python
from reach_tools import Reach

reach = Reach.from_aw(3411)  # Tilton River, Lower
if reach is not None:
    print(reach.river_name)         # "Tilton"
    print(reach.difficulty)         # "IIItoIV"
    print(reach.runnable)           # True/False depending on current gauge
    print(reach.gauge_stage)        # e.g., "too low", "medium", "too high"
    print(reach.gauge_observation)  # e.g., 244.0 (cfs)
```

Returns `None` for invalid reach IDs. Retries up to 3 times with exponential backoff on transient errors.

---

## Access reach points (rapids, put-ins, takeouts)

```python
from reach_tools import Reach

reach = Reach.from_aw(4)

for pt in reach.reach_points:
    print(pt.point_type, pt.subtype, pt.name)
    # e.g.: "access" "putin" "Put In"
    #       "rapid"  None   "Upper Canyon"
    #       "access" "takeout" "Takeout"

# Filter to just the put-in
putin = next((pt for pt in reach.reach_points if pt.subtype == "putin"), None)
if putin:
    print(f"Put-in at ({putin.geometry.y:.4f}, {putin.geometry.x:.4f})")
```

---

## Check gauge stage with custom observation

```python
import reach_tools

# Load a reach object from a file
reach = reach_tools.Reach.from_aw_json("references/aw_json/reach_000004.json")

# Override with a custom observation
reach.gauge_observation = 1500.0
print(reach.runnable)     # True (between 900 and 3000)
print(reach.gauge_stage)  # "medium" or "runnable" depending on thresholds
```

---

## Use gauge functions directly

```python
import json
from pathlib import Path
import reach_tools

# Load the raw reach object dict
data = json.loads(Path("references/aw_json/reach_000004.json").read_text())
reach_json = data[0]["result"]["data"]["json"]

# Test runnability and stage at different observations
print(reach_tools.utils.aw.get_runnable(reach_json, 500))   # True
print(reach_tools.utils.aw.get_runnable(reach_json, 3500))  # False (above max)
print(reach_tools.utils.aw.get_stage(reach_json, 500))      # "low" or "runnable"
print(reach_tools.utils.aw.get_stage(reach_json, 100))      # "too low"
print(reach_tools.utils.aw.get_stage(reach_json, 5000))     # "too high"
```

---

## Run the test suite

```bash
cd /path/to/reach-tools
env/bin/python -m pytest testing/ -v
```

Expected: tests run against new-format fixture files in `data/raw/american_whitewater/`. The number of parametrized tests will decrease from ~5136 to ~1700 (valid reaches in the 1–2000 ID range + reach 3411).

---

## Fixture file format

New fixture files are the raw tRPC array response:
```json
[{"result": {"data": {"json": { ... reach object ... }}}}]
```

To extract the reach object directly:
```python
import json
data = json.loads(open("data/raw/american_whitewater/aw_00000004.json").read())
reach_obj = data[0]["result"]["data"]["json"]
```
