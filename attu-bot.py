#!/usr/bin/env python3

"""
AttuBot - Command line entrypoint
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from dotenv import load_dotenv
from os import getenv, environ

load_dotenv()  # take environment variables from .env.

print(f'attubot.runner > info. Container Build Time: {getenv("BUILD_TIME")}')

if 'DEBUG' in environ:
    print('attubot.runner > info. Debug Mode: Enabled')
else:
    print('attubot.runner > info. Debug Mode: Disabled')

from attubot import core

if __name__ == '__main__':
    core.start_bot_loop()
