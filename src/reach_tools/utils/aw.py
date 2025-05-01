"""Tools and utilities unique to working with American Whitewater data."""

from typing import Union

__all__ = ["get_gauge_stage", "get_runnable"]


def get_gauge_ranges(gauge_ranges: Union[dict, list[dict]]) -> list[dict]:
    """Based on the input JSON, make sure have the correct information from the AW JSON dictionary."""
    # bore down into AW JSON if necessary
    if "CContainerViewJSON_view" in gauge_ranges.keys():
        gauge_ranges = gauge_ranges["CContainerViewJSON_view"][
            "CRiverMainGadgetJSON_main"
        ]["guagesummary"].get("ranges")
    elif "CRiverMainGadgetJSON_main" in gauge_ranges.keys():
        gauge_ranges = gauge_ranges["CRiverMainGadgetJSON_main"]["guagesummary"].get(
            "ranges"
        )
    elif "guagesummary" in gauge_ranges.keys():
        gauge_ranges = gauge_ranges["guagesummary"].get("ranges")
    elif "ranges" in gauge_ranges.keys():
        gauge_ranges = gauge_ranges["ranges"]

    # check if some of the necessary keys are in the first object
    if gauge_ranges[0].get("range_min") is None:
        raise ValueError(
            'Please ensure the input gauge ranges are valid. Cannot retrieve "min" from first item in gauge summary.'
        )

    return gauge_ranges


def get_gauge_value_list(gauge_ranges: Union[dict, list[dict]]) -> list[list]:
    """Helper to get non-repeating list of gauge key and values."""
    # create a set to populate
    val_set = set()

    # iterate the list of gauge ranges and add all
    for rng in gauge_ranges:

        # get tuples of the index and values for the gauge ranges
        min_lst = [rng.get("range_min"), rng.get("min")]
        max_lst = [rng.get("range_max"), rng.get("max")]

        # for each of the metrics retrieved
        for metric in (min_lst, max_lst):

            # if there is a value to use for comparison
            if metric[1] is not None:

                # ensure the value is numeric
                metric[1] = float(metric[1])

                # add the metric to the set
                val_set.add(metric)

    # sort the values and convert to list at the same time
    val_lst = list(val_set)

    return val_lst


def get_range_bias(gauge_keys: list[str]):
    """Helper to determine if ranges have more detail higher or lower in the scale, or are evenly balanced."""
    # get the index values without the prefix as numbers for comparison if not already integers
    if isinstance(gauge_keys[0], str):
        gauge_keys = [int(key.lstrip("R")) for key in gauge_keys]

    # determine if the bias is low, balanced or high based on index range from 0-9
    low_len = len([v for v in gauge_keys if v <= 4])
    high_len = len([v for v in gauge_keys if v >= 5])

    # determine if the range values are weighted higher or lower
    if low_len > high_len:
        range_bias = "low"
    elif low_len < high_len:
        range_bias = "high"
    else:
        range_bias = "balanced"

    return range_bias


def get_runnable(
    gauge_ranges: Union[dict, list[dict]], gauge_observation: Union[float, int]
) -> bool:
    """
    Returns whether the given gauge range is runnable.

    Args:
        gauge_ranges: A dictionary of gauge metrics from American Whitewater JSON.
        gauge_observation: The gauge observation.

    Returns:
        Whether the given gauge observation is runnable.
    """
    # ensure working with the right part of the AW JSON dict
    gauge_ranges = get_gauge_ranges(gauge_ranges)

    # get the values to evaluate
    range_idx_lst, val_lst = zip(*get_gauge_value_list(gauge_ranges))

    # get the index bias
    idx_bias = get_range_bias(range_idx_lst)

    # if at least two values, evaluate if between top and bottom value
    if len(val_lst) > 2 and val_lst[0] < gauge_observation < val_lst[-1]:
        runnable = True

    # if only one value, if above value
    elif len(val_lst) == 0 and idx_bias == "low" and gauge_observation > val_lst[0]:
        runnable = True

    else:
        runnable = False

    return runnable


def get_gauge_stage(
    gauge_ranges: Union[dict, list[dict]], gauge_observation: Union[float, int]
) -> str:
    """
    Get a human-readable gauge stage from the gauge metrics dictionary compared against the most recent gauge
    observation.

    Args:
        gauge_ranges: A dictionary of gauge metrics from American Whitewater JSON.
        gauge_observation: The gauge observation.

    Returns:
        The gauge stage description.
    """
    # if no observation provided, nothing to return
    if gauge_observation is None:
        return "no gauge reading"

    # ensure working with correct gauge ranges
    gauge_ranges = get_gauge_ranges(gauge_ranges)

    # get the ranges and metric indexes into non-repeating sorted list
    range_key_lst, metric_lst = zip(*get_gauge_value_list(gauge_ranges))

    # get range bias
    range_bias = get_range_bias(range_key_lst)

    # if high bias with only one value or between two values, is runnable
    if (
        (
            (range_bias == "high")
            and (len(metric_lst) == 1)
            and (gauge_observation < metric_lst[0])
        )
        # or (
        #     (range_bias == "low")
        #     and (len(metric_lst) == 1)
        #     and (gauge_observation > metric_lst[0])
        # )
        or (
            (len(metric_lst) == 2)
            and (metric_lst[0] < gauge_observation < metric_lst[1])
        )
    ):
        return "runnable"

    # if below the lowest value, is too low
    if gauge_observation < metric_lst[0]:
        return "too low"

    # if above the highest value, is too high
    if gauge_observation > metric_lst[-1]:
        return "too high"

    # if three metrics, bifurcates runnable into lower and higher
    if len(metric_lst) == 3:
        if metric_lst[0] < gauge_observation < metric_lst[1]:
            return "lower runnable"
        if metric_lst[1] < gauge_observation < metric_lst[2]:
            return "higher runnable"

    # if four metrics runnable becomes low, medium and high
    if len(metric_lst) == 4:
        if metric_lst[0] < gauge_observation < metric_lst[1]:
            return "low"
        if metric_lst[1] < gauge_observation < metric_lst[2]:
            return "medium"
        if metric_lst[2] < gauge_observation < metric_lst[3]:
            return "high"

    # if five metrics with more divisions below the middle of the ranges, stratify into two lows, medium and high
    if (len(metric_lst) == 5) and (range_bias == "low"):
        if metric_lst[0] < gauge_observation < metric_lst[1]:
            return "very low"
        if metric_lst[1] < gauge_observation < metric_lst[2]:
            return "medium low"
        if metric_lst[2] < gauge_observation < metric_lst[3]:
            return "medium"
        if metric_lst[3] < gauge_observation < metric_lst[4]:
            return "high"

    # if five metrics with more divisions above the middle of the ranges, stratify accordingly
    if (len(metric_lst) == 5) and (range_bias == "high"):
        if metric_lst[0] < gauge_observation < metric_lst[1]:
            return "low"
        if metric_lst[1] < gauge_observation < metric_lst[2]:
            return "medium"
        if metric_lst[2] < gauge_observation < metric_lst[3]:
            return "medium high"
        if metric_lst[3] < gauge_observation < metric_lst[4]:
            return "very high"

    # if six, stratify
    if len(metric_lst) == 6:
        if metric_lst[0] < gauge_observation < metric_lst[1]:
            return "low"
        if metric_lst[1] < gauge_observation < metric_lst[2]:
            return "medium low"
        if metric_lst[2] < gauge_observation < metric_lst[3]:
            return "medium"
        if metric_lst[3] < gauge_observation < metric_lst[4]:
            return "high medium"
        if metric_lst[4] < gauge_observation < metric_lst[5]:
            return "high"

    # if seven with low bias, stratify accordingly
    if (len(metric_lst) == 7) and (range_bias == "low"):
        if metric_lst[0] < gauge_observation < metric_lst[1]:
            return "very low"
        if metric_lst[1] < gauge_observation < metric_lst[2]:
            return "low"
        if metric_lst[2] < gauge_observation < metric_lst[3]:
            return "medium low"
        if metric_lst[3] < gauge_observation < metric_lst[4]:
            return "medium"
        if metric_lst[4] < gauge_observation < metric_lst[5]:
            return "high medium"
        if metric_lst[5] < gauge_observation < metric_lst[6]:
            return "high"

    # if seven and high bias, stratify accordingly
    if (len(metric_lst) == 7) and (range_bias == "high"):
        if metric_lst[0] < gauge_observation < metric_lst[1]:
            return "low"
        if metric_lst[1] < gauge_observation < metric_lst[2]:
            return "medium low"
        if metric_lst[2] < gauge_observation < metric_lst[3]:
            return "high medium"
        if metric_lst[3] < gauge_observation < metric_lst[4]:
            return "medium"
        if metric_lst[4] < gauge_observation < metric_lst[5]:
            return "high medium"
        if metric_lst[5] < gauge_observation < metric_lst[6]:
            return "high"

    # if eight, even numbers easy to stratify
    if len(metric_lst) == 8:
        if metric_lst[0] < gauge_observation < metric_lst[1]:
            return "very low"
        if metric_lst[1] < gauge_observation < metric_lst[2]:
            return "low"
        if metric_lst[2] < gauge_observation < metric_lst[3]:
            return "medium low"
        if metric_lst[3] < gauge_observation < metric_lst[4]:
            return "medium"
        if metric_lst[4] < gauge_observation < metric_lst[5]:
            return "medium high"
        if metric_lst[5] < gauge_observation < metric_lst[6]:
            return "high"
        if metric_lst[6] < gauge_observation < metric_lst[7]:
            return "very high"

    # at nine, stratify based on low bias
    if (len(metric_lst) == 9) and range_bias == "low":
        if metric_lst[0] < gauge_observation < metric_lst[1]:
            return "extremely low"
        if metric_lst[1] < gauge_observation < metric_lst[2]:
            return "very low"
        if metric_lst[2] < gauge_observation < metric_lst[3]:
            return "low"
        if metric_lst[3] < gauge_observation < metric_lst[4]:
            return "medium low"
        if metric_lst[4] < gauge_observation < metric_lst[5]:
            return "medium"
        if metric_lst[5] < gauge_observation < metric_lst[6]:
            return "medium high"
        if metric_lst[6] < gauge_observation < metric_lst[7]:
            return "high"
        if metric_lst[7] < gauge_observation < metric_lst[8]:
            return "very high"

    # again for nine, stratify accroding to high bias
    if len(metric_lst) == 9 and range_bias == "high":
        if metric_lst[0] < gauge_observation < metric_lst[1]:
            return "very low"
        if metric_lst[1] < gauge_observation < metric_lst[2]:
            return "low"
        if metric_lst[2] < gauge_observation < metric_lst[3]:
            return "medium low"
        if metric_lst[3] < gauge_observation < metric_lst[4]:
            return "medium"
        if metric_lst[4] < gauge_observation < metric_lst[5]:
            return "medium high"
        if metric_lst[5] < gauge_observation < metric_lst[6]:
            return "high"
        if metric_lst[6] < gauge_observation < metric_lst[7]:
            return "very high"
        if metric_lst[7] < gauge_observation < metric_lst[8]:
            return "extremely high"

    # even number ten is easy
    if len(metric_lst) == 10:
        if metric_lst[0] < gauge_observation < metric_lst[1]:
            return "extremely low"
        if metric_lst[1] < gauge_observation < metric_lst[2]:
            return "very low"
        if metric_lst[2] < gauge_observation < metric_lst[3]:
            return "low"
        if metric_lst[3] < gauge_observation < metric_lst[4]:
            return "medium low"
        if metric_lst[4] < gauge_observation < metric_lst[5]:
            return "medium"
        if metric_lst[5] < gauge_observation < metric_lst[6]:
            return "medium high"
        if metric_lst[6] < gauge_observation < metric_lst[7]:
            return "high"
        if metric_lst[7] < gauge_observation < metric_lst[8]:
            return "very high"
        if metric_lst[8] < gauge_observation < metric_lst[9]:
            return "extremely high"
