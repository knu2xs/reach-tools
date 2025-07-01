from typing import Union

import requests


def download_raw_json_from_aw(aw_reach_id: Union[int, str]) -> dict:
    """Download the raw JSON data from American Whitewater for a given reach ID."""

    # construct the URL to download reach data
    url = f"https://www.americanwhitewater.org/content/River/detail/id/{aw_reach_id}/.json"

    # tracking attempts to download the data
    attempts = 0
    max_attempts = 30

    header_dict = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "max-age=0",
        "priority": "u=0, i",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0"
    }

    # loop to retry the request if it fails...less likely now they are using cloudflare
    while attempts < max_attempts:

        # username = 'aw_reach_rJ8gg'
        # password = 'Tazsis_gipsas_duqbe2'

        # # Structure payload.
        # payload = {
        #     'source': 'universal',
        #     'url': url,
        #     'geo_location': 'United States',
        #     'user_agent_type': 'desktop',
        #     'context': [
        #         {'key': 'http_method', 'value': 'get'}
        #     ]
        # }

        # # Get response.
        # resp = requests.get(
        #     'https://realtime.oxylabs.io/v1/queries',
        #     auth=(username, password), #Your credentials go here
        #     json=payload,
        # )

        resp = resp = requests.get(url, headers=header_dict)

        # ensure the page is loaded, a 200 status
        if resp.status == 200 and len(resp.body()):
            out_json = resp.json()
            break
        else:
            attempts = attempts + 1

        out_json



    if attempts >= max_attempts:
        raise Exception(f"Cannot download data for reach_id={aw_reach_id} from AW")

    return out_json