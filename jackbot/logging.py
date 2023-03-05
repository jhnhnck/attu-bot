"""
JackBot - Wrapper for all the shit that is the python 'logging' library
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import sys

import logging
from os import getenv

log_formatter = logging.Formatter(fmt='{asctime} {name} > {levelname}. {message}', style='{')

# create console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(getenv('BOT_LOG_LVL', default='INFO'))
console_handler.setFormatter(log_formatter)

# TODO: something that formats better than the logging library
def get_logger(logger_name):
    # create logger
    logger = logging.getLogger(logger_name)
    logger.setLevel(getenv('BOT_LOG_LVL', default='INFO'))

    # Add console handler to logger
    logger.addHandler(console_handler)

    return logger
