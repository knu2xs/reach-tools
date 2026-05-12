import json
import time
from typing import Optional, Union

import requests

_TRPC_URL = "https://trpc-api.americanwhitewater.org/reach/reachDetailWithPhotos"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.1.0.dev0 Safari/537.36 "
        "Edg/135.0.1.0.dev0"
    )
}
_MAX_RETRIES = 3


def download_raw_json_from_aw(aw_reach_id: Union[int, str]) -> Optional[dict]:
    """Download reach data from the American Whitewater tRPC API.

    Returns the unwrapped reach object dict, or None if the reach does not exist
    (HTTP 404). Retries up to 3 times with exponential backoff on transient errors.
    Raises an exception if all retries are exhausted.
    """
    params = {
        "batch": "1",
        "input": json.dumps({"0": {"json": {"reachID": str(aw_reach_id)}}}),
    }

    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.get(_TRPC_URL, params=params, headers=_HEADERS, timeout=15)
        except requests.RequestException as exc:
            if attempt < _MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            raise Exception(
                f"Cannot download data for reach_id={aw_reach_id} from AW"
            ) from exc

        if resp.status_code == 404:
            return None

        if resp.status_code == 200:
            data = resp.json()
            return data[0]["result"]["data"]["json"]

        # transient error — retry with backoff
        if attempt < _MAX_RETRIES - 1:
            time.sleep(2 ** attempt)
        else:
            raise Exception(
                f"Cannot download data for reach_id={aw_reach_id} from AW "
                f"(HTTP {resp.status_code})"
            )

    return None