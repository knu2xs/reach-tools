# coding: utf-8

import datetime
import json
import logging
from pathlib import Path
import re

from reach_tools.utils.procure import download_raw_json_from_aw

# file name without extension
file_name = Path(__file__).stem

# path for saving data
dir_prj = Path(__file__).parent.parent
dir_raw_aw = dir_prj / 'data' / 'raw' / 'american_whitewater' / 'reach_json'
dir_logs = dir_prj / 'reports' / 'logs' / file_name

# ensure needed directories exist
if not dir_raw_aw.exists():
    dir_raw_aw.mkdir(parents=True)

if not dir_logs.exists():
    dir_logs.mkdir(parents=True)

# timestamp for logging
dt_str = datetime.datetime.now().strftime('%Y%m%dT%H%M%S')

# create logger for this file and set the level
logger = logging.getLogger(file_name)
logger.setLevel(logging.DEBUG)

# create and configure a file handler for progress tracking
lfh = logging.FileHandler(dir_logs / f'{file_name}_{dt_str}.log')
lfh.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s', datefmt='%Y-%m-%dT%H:%M:%S'))

# add the handler to the logger
logger.addHandler(lfh)

# variables for tracking progress
start_id = 1
fail_count = 0
max_fail = 5000
max_range = 10000000

# get a list of reaches already downloaded
existing_reach_id_lst = [int(re.search(r"aw_(\d+)\.json", pth.name).group(1)) for pth in dir_raw_aw.glob('aw_*.json')]

if len(existing_reach_id_lst):
    logger.info(f"{len(existing_reach_id_lst):,} reaches have already been downloaded to {dir_raw_aw}.")

    # sort the reaches sequentially
    existing_reach_id_lst.sort()

    # start at the last retrieved reach id
    start_id = existing_reach_id_lst[-1]

for reach_id in range(start_id, max_range):

    # location for saving the reach json
    file_pth = dir_raw_aw / f'aw_{reach_id:08d}.json'

    # handle if file already exists
    if reach_id in existing_reach_id_lst:
        logger.debug(f"reach_id={reach_id} already exists at {file_pth}")

    else:        
        logger.debug(f"Attempting to download reach_id={reach_id}")
        
        try:
            # download the data from AW
            aw_json = download_raw_json_from_aw(reach_id)
    
            # if the file exists, clean it out
            if file_pth.exists():
                file_pth.unlink()
    
            # save to a local file
            with open(file_pth, 'x') as fp:
                json.dump(aw_json, fp, indent=2)
    
            logger.info(f'Downloaded reach_id={reach_id} and saved to {file_pth}')

            # reset fail count
            fail_count = 0
    
        except:
            logger.debug(f'Could not retrieve data for reach_id={reach_id} (fail_count: {fail_count})')
            fail_count += 1
