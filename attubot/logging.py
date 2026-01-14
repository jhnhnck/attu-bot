"""
AttuBot - Logging Utility
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""
#ruff: noqa: PLC0415

import sys
from os import environ

from termcolor import colored

class Logger:
    """
    Logger supports the following logging levels: trace, debug, info, warn, error, fatal

    Args:
      class_name (str): Name of the class or module using the logger

    Example:
      ```
      from attubot.logging import get_logger
      logger = get_logger(__name__)
      ````
    """

    class_name: str

    def __init__(self, class_name: str):
        self.class_name = class_name or 'attubot.???'
        self.debug_mode = 'DEBUG' in environ
        nop = lambda *a, **k: None  # noqa: E731

        self.alert = self._generate('alert', sys.stdout, 'yellow') if self.debug_mode else nop
        self.trace = self._generate('trace', sys.stdout, 'light_green') if self.debug_mode else nop
        self.debug = self._generate('debug', sys.stdout, 'blue') if self.debug_mode else nop

        self.info = self._generate('info', sys.stdout, 'cyan')
        self.warn = self._generate('warn', sys.stderr, 'light_red')
        self.error = self._generate('error', sys.stderr, 'light_red')
        self.fatal = self._generate('fatal', sys.stderr, 'red')

    def _generate(self, level, file, color):
        def printer(*obj: object, sep: str = ' ', end: str = '\n', flush: bool = False) -> None:
            """
            Prints formatted log messages with severity and origin indicators, mirrors print builtin interface and behavior

            Args:
              sep (str): string inserted between values, default a space
              end (str): string appended after the last value, default a newline
              flush (bool): whether to forcibly flush the stream (idk either)
            """
            print(colored(f'{self.class_name}[{level}] ', color), end='', flush=flush, file=file)
            print(*obj, sep=sep, end=end, flush=flush, file=file)

        return printer

    async def send_to_webhook(self, error: Exception, location: str = ''):
        import traceback

        tb_str = ''.join(traceback.format_exception(error))

        self.error(f'{error!s}\n{tb_str}')

        try:
            import aiohttp
            from discord import Webhook

            from attubot.config import NovaConfig
            from attubot.util import break_at_newline

            async with aiohttp.ClientSession() as session:
                webhook = Webhook.from_url(NovaConfig.error_hook, session=session)
                await webhook.send(f'**{error}**\n', username='DoomBot')

                # this removes the useless bits and trims the number of lines to fit
                padding = len('``````')
                tb_str = break_at_newline(tb_str.split('The above exception')[0], 2000 - padding)

                await webhook.send(f'```{tb_str}```', username='DoomBot')

                end_msg = location if len(location) > 0 else f'(location not set; called from {self.class_name})'
                await webhook.send(end_msg, username='DoomBot')

        except Exception as err:
            self.error(f'Issue logging error to configured webhook: {err}')


def get_logger(class_name: str) -> Logger:
    return Logger(class_name)
