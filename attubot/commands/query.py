"""
AttuBot - Query Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord import Permissions
from discord.ext import commands
from discord.utils import snowflake_time

from attubot.config import Config
from attubot.logging import get_logger
from attubot.markers import YearMarker, markers_get
from attubot.util import format_message_link, get_year_span, get_year_status, has_year_marker, is_authorized_guild
from attubot.wiki import AttuWiki

logger = get_logger(__name__)

# --- Year Commands ---

year_group = discord.SlashCommandGroup('year', description='Utlities related to current, past or future years')
