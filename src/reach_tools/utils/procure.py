from typing import Union

import requests


def download_raw_json_from_aw(aw_reach_id: Union[int, str]) -> dict:
    """Download the raw JSON data from American Whitewater for a given reach ID."""

    # construct the URL to download reach data
    url = f"https://www.americanwhitewater.org/content/River/detail/id/{aw_reach_id}/.json"

    # tracking attempts to download the data
    attempts = 0

    # header dictionary with user agent for cloudflare
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.1.0.dev0 Safari/537.36 "
        "Edg/135.0.1.0.dev0"
    }

    # loop to retry the request if it fails...less likely now they are using cloudflare
    while attempts < 10:

        # make the request to the url
        resp = requests.get(url, headers=headers)

        # check the status code of the response
        if resp.status_code == 200 and len(resp.content):
            out_json = resp.json()
            break
        else:
            attempts = attempts + 1

    if attempts >= 10:
        raise Exception(f"Cannot download data for reach_id={aw_reach_id} from AW")

    return out_json