#!/usr/bin/env python3

"""
AttuBot - Command line entrypoint
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from os import environ, getenv

from dotenv import load_dotenv
from termcolor import colored

load_dotenv()  # take environment variables from .env.

print(colored('attubot.runner[info]', 'cyan'), f'Container Build Time: {getenv("BUILD_TIME")}')

if 'DEBUG' in environ:
    print(colored('attubot.runner[info]', 'cyan'), 'Debug Mode: Enabled')
else:
    print(colored('attubot.runner[info]', 'cyan'), 'Debug Mode: Disabled')

from attubot import core  # noqa: E402

core.start_bot_loop()
