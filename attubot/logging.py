"""
AttuBot - Logging wrapper
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import sys
from os import environ

from termcolor import colored

class Logger:
    class_name: str

    def __init__(self, class_name):
        self.class_name = class_name or 'attubot.???'

    def _stdout(self, level, message):
        print(colored(f'{self.class_name}[{level}]', 'cyan'), message)

    def _stderr(self, level, message):
        print(colored(f'{self.class_name}[{level}]', 'light_red'), message, file=sys.stderr)

    def trace(self, message):
        if 'DEBUG' in environ:
            self._stdout('trace', message)

    def debug(self, message):
        if 'DEBUG' in environ:
            self._stdout('debug', message)

    def info(self, message):
        self._stdout('info', message)

    def warn(self, message):
        self._stderr('warn', message)

    def error(self, message):
        self._stderr('error', message)

    def fatal(self, message):
        self._stderr('fatal', message)

def get_logger(class_name):
    return Logger(class_name)
