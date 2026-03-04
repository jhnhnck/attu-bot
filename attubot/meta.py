"""
AttuBot - Package Metadata Constants
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

# leaf module - no attubot imports; keeps metadata accessible without touching __init__.py

__all__ = [
    '__author__',
    '__build_time__',
    '__copyright__',
    '__description__',
    '__email__',
    '__license__',
    '__schema__',
    '__title__',
    '__version__',
]

__title__ = 'AttuBot'
__author__ = 'jhnhnck'
__license__ = 'Apache License, Version 2.0'
__copyright__ = 'Copyright (c) 2026 John Hancock, The Attu Project'
__schema__ = '2.5.1'  # previously __version__
__email__ = 'doom@attuproject.org'
__description__ = 'A discord bot designed for automating tasks for the Attu Project'

__version__ = '26.2.22'
__build_time__ = 'Thu Aug 11 02:23:20 UTC 2022'  # stamped during docker build
