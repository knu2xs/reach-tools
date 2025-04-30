"""Tools and utilities unique to working with American Whitewater data."""

from typing import Union

__all__ = ["get_gauge_stage"]

# keys for gauge metrics
metric_keys = [
    "gauge_r0",
    "gauge_r1",
    "gauge_r2",
    "gauge_r3",
    "gauge_r4",
    "gauge_r5",
    "gauge_r6",
    "gauge_r7",
    "gauge_r8",
    "gauge_r9",
]


def get_gauge_metrics(metrics: dict, metric_keys: list[str]) -> list[Union[float, int]]:
    """
    Get gauge metrics from a metric
    """
    # get a list of the values corresponding to the keys provided
    metrics = [getattr(self, key) for key in metric_keys]
    metrics = list(set(val for val in metrics if val is not None))
    metrics.sort()
    return metrics


def get_gauge_metric(gauge_info: dict, metric: str) -> float:
    """Get a metric as a float."""
    val = gauge_info.get(metric)
    if val is not None:
        val = float(gauge_info[metric])
    return val


def get_gauge_stage(
    gauge_ranges: Union[dict, list[dict]], gauge_observation: Union[float, int]
) -> str:
    """
    Get a human-readable gauge stage from the gauge metrics dictionary compared against the most recent gauge
    observation.

    Args:
        gauge_ranges (dict): A dictionary of gauge metrics.
        gauge_observation (Union[float, int]): The gauge observation.
    """
    # if no observation provided, nothing to return
    if gauge_observation is None:
        return "no gauge reading"

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

    # get the ranges and metric indexes into non-repeating sorted list
    metric_set = set()
    range_idx_set = set()

    for rng in gauge_ranges:

        metric_min = rng.get("min")
        metric_max = rng.get("max")

        for metric in (metric_min, metric_max):
            if metric is not None:
                metric_set.add(float(metric))

        min_idx = rng["range_min"]
        max_idx = rng["range_max"]

        for idx in (min_idx, max_idx):
            if idx is not None:
                range_idx_set.add(int(idx.lstrip("R")))

    metric_lst = sorted(metric_set)
    range_idx_lst = sorted(range_idx_set)

    # determine if the bias is low, balanced or high
    low_len = len([v for v in range_idx_lst if v < 5])
    high_len = len([v for v in range_idx_lst if v > 5])

    if low_len > high_len:
        range_bias = "low"
    elif low_len < high_len:
        range_bias = "high"
    else:
        range_bias = "balanced"

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

    # if five metrics stratify into two lows, medium and high
    if (len(metric_lst) == 5) & (range_bias == "low"):
        if metric_lst[0] < gauge_observation < metric_lst[1]:
    ):
        stage = "very low"

    elif ((len(metric_lst) == 5) & (range_bias == "low")) & (
        metric_lst[1] < gauge_observation < metric_lst[2]
    ):
        stage = "medium low"

    elif ((len(metric_lst) == 5) & (range_bias == "low")) & (
        metric_lst[2] < gauge_observation < metric_lst[3]
    ):
        stage = "medium"

    elif ((len(metric_lst) == 5) & (range_bias == "low")) & (
        metric_lst[3] < gauge_observation < metric_lst[4]
    ):
        stage = "high"

    elif ((len(metric_lst) == 5) & (range_bias == "high")) & (
        metric_lst[0] < gauge_observation < metric_lst[1]
    ):
        stage = "low"

    elif ((len(metric_lst) == 5) & (range_bias == "high")) & (
        metric_lst[1] < gauge_observation < metric_lst[2]
    ):
        stage = "medium"

    elif ((len(metric_lst) == 5) & (range_bias == "high")) & (
        metric_lst[2] < gauge_observation < metric_lst[3]
    ):
        stage = "medium high"

    elif ((len(metric_lst) == 5) & (range_bias == "high")) & (
        metric_lst[3] < gauge_observation < metric_lst[4]
    ):
        stage = "very high"

    # if six, stratify
    elif len(metric_lst) == 6 & (metric_lst[0] < gauge_observation < metric_lst[1]):
        stage = "low"

    elif len(metric_lst) == 6 & (metric_lst[1] < gauge_observation < metric_lst[2]):
        stage = "medium low"

    elif len(metric_lst) == 6 & (metric_lst[2] < gauge_observation < metric_lst[3]):
        stage = "medium"

    elif len(metric_lst) == 6 & (metric_lst[3] < gauge_observation < metric_lst[4]):
        stage = "high medium"

    elif len(metric_lst) == 6 & (metric_lst[4] < gauge_observation < metric_lst[5]):
        stage = "high"

    # if seven, stratify with consideration to high or low bias
    elif ((len(metric_lst) == 7) & (range_bias == "low")) & (
        metric_lst[0] < gauge_observation < metric_lst[1]
    ):
        stage = "very low"

    elif ((len(metric_lst) == 7) & (range_bias == "low")) & (
        metric_lst[1] < gauge_observation < metric_lst[2]
    ):
        stage = "low"

    elif ((len(metric_lst) == 7) & (range_bias == "low")) & (
        metric_lst[2] < gauge_observation < metric_lst[3]
    ):
        stage = "medium low"

    elif ((len(metric_lst) == 7) & (range_bias == "low")) & (
        metric_lst[3] < gauge_observation < metric_lst[4]
    ):
        stage = "medium"

    elif ((len(metric_lst) == 7) & (range_bias == "low")) & (
        metric_lst[4] < gauge_observation < metric_lst[5]
    ):
        stage = "high medium"

    elif ((len(metric_lst) == 7) & (range_bias == "low")) & (
        metric_lst[5] < gauge_observation < metric_lst[6]
    ):
        stage = "high"

    elif ((len(metric_lst) == 7) & (range_bias == "high")) & (
        metric_lst[0] < gauge_observation < metric_lst[1]
    ):
        stage = "low"

    elif ((len(metric_lst) == 7) & (range_bias == "high")) & (
        metric_lst[1] < gauge_observation < metric_lst[2]
    ):
        stage = "medium low"

    elif ((len(metric_lst) == 7) & (range_bias == "low")) & (
        metric_lst[2] < gauge_observation < metric_lst[3]
    ):
        stage = "high medium"

    elif ((len(metric_lst) == 7) & (range_bias == "low")) & (
        metric_lst[3] < gauge_observation < metric_lst[4]
    ):
        stage = "medium"

    elif ((len(metric_lst) == 7) & (range_bias == "low")) & (
        metric_lst[4] < gauge_observation < metric_lst[5]
    ):
        stage = "high medium"

    elif ((len(metric_lst) == 7) & (range_bias == "low")) & (
        metric_lst[5] < gauge_observation < metric_lst[6]
    ):
        stage = "high"
