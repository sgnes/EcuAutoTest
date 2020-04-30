from test_device import TestDevice
import sys
import os
from uds_proj_config import *
import logging
import json
from test_device import load_test_config

if len(sys.argv) >= 2:
    test_config_file = sys.argv[1]
else:
    test_config_file = "test_template.xlsx"


def setup_logging(default_path='logging.json', default_level=logging.INFO, env_key='LOG_CFG'):
    """Setup logging configuration

    """
    path = default_path
    value = os.getenv(env_key, None)
    if value:
        path = value
    if os.path.exists(path):
        with open(path, 'rt') as f:
            config = json.load(f)
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=default_level)


setup_logging()
test_cfg, test_cases = load_test_config(test_config_file)


with TestDevice(test_cfg) as test_dev:
    for case in test_cases:
        if hasattr(test_dev, case.Action):
            res = getattr(test_dev, case.Action)(case)

pass

