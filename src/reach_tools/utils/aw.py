"""Tools and utilities unique to working with American Whitewater data."""

import re
from typing import Any, Optional, Union

__all__ = ["get_stage", "get_runnable"]

# Ordered threshold names and their corresponding stage labels (below → above)
_THRESHOLD_KEYS = [
    "beginLowRunnable",
    "beginMediumRunnable",
    "beginHighRunnable",
    "endHighRunnable",
]
_STAGE_LABELS = ["low", "medium", "high"]


def _get_correlation_details(reach_json: dict) -> Optional[dict]:
    """Extract correlationDetails from a new-format reach object dict.

    Returns the correlationDetails dict from the first (primary) correlation,
    or None if correlations are absent, empty, or correlationDetails is null.
    """
    correlations = reach_json.get("detail", {}).get("correlations", [])
    if not correlations:
        return None
    cd = correlations[0].get("correlationDetails")
    return cd if cd else None


def get_runnable(
    reach_json: dict, gauge_observation: Optional[Union[float, int]]
) -> bool:
    """Return whether the reach is runnable at the given gauge observation.

    Args:
        reach_json: Full new-format reach object dict (as returned by
            ``download_raw_json_from_aw()`` or extracted from a fixture file).
        gauge_observation: Current gauge reading; None returns False.

    Returns:
        True if ``beginLowRunnable <= gauge_observation <= endHighRunnable``
        and both bounds are present; False otherwise.
    """
    if gauge_observation is None:
        return False

    cd = _get_correlation_details(reach_json)
    if cd is None:
        return False

    low_raw = cd.get("beginLowRunnable")
    high_raw = cd.get("endHighRunnable")

    if low_raw is None or high_raw is None:
        return False

    return float(low_raw) <= gauge_observation <= float(high_raw)


def get_stage(
    reach_json: dict, gauge_observation: Optional[Union[float, int]]
) -> Optional[str]:
    """Return a human-readable gauge stage label using null-collapse logic.

    Thresholds: beginLowRunnable, beginMediumRunnable, beginHighRunnable,
    endHighRunnable. Only non-null thresholds are used as boundaries; stages
    whose defining threshold is absent are skipped.

    Args:
        reach_json: Full new-format reach object dict.
        gauge_observation: Current gauge reading; None returns None.

    Returns:
        One of "too low", "low", "medium", "high", "too high", or None
        when no correlation data is available.
    """
    if gauge_observation is None:
        return None

    cd = _get_correlation_details(reach_json)
    if cd is None:
        return None

    # Collect only non-null thresholds as (value, label_after) pairs
    thresholds = []
    for key, label in zip(_THRESHOLD_KEYS, _STAGE_LABELS + [None]):
        raw = cd.get(key)
        if raw is not None:
            thresholds.append((float(raw), label))

    if not thresholds:
        return None

    # Below the lowest threshold
    if gauge_observation < thresholds[0][0]:
        return "too low"

    # Above the highest threshold
    if gauge_observation > thresholds[-1][0]:
        return "too high"

    # Walk through thresholds to find the matching stage.
    # Each threshold is the START of its stage, so use half-open intervals
    # [val, next_val) for all except the last pair which uses [val, next_val].
    last_pair_idx = len(thresholds) - 2
    for i, (val, label) in enumerate(thresholds[:-1]):
        next_val = thresholds[i + 1][0]
        if i < last_pair_idx:
            if val <= gauge_observation < next_val:
                return label
        else:
            # Final runnable interval includes endHighRunnable
            if val <= gauge_observation <= next_val:
                return label

    return "too high"


def get_key_from_block(json_block: dict, key: str) -> Any:
    """Helper with some validation and cleanup to retrieve values from a dictionary."""
    # late import to avoid circular imports
    from . import cleanup_string

    ret_val = json_block.get(key)

    if ret_val is not None:
        ret_val = cleanup_string(ret_val)
        if (
            (len(ret_val) == 0)
            or (re.match(r"^([\r\n\t])+$", ret_val))
            or (ret_val == "N/A")
        ):
            ret_val = None

    return ret_val
