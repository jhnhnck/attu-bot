"""
JackBot - Main file
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from os import getenv

import discord
from discord.utils import escape_mentions

from jackbot.config import Config
from jackbot.logging import get_logger
logger = get_logger(__name__)

# --- Initialization ---

logger.info('Initializing...')

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

bot = discord.Bot(intents=intents)
config = Config(getenv('BOT_CONFIG_FILE'))

# --- Slash Commands ---

@bot.slash_command(guilds_only=True)
async def gametime(ctx, message: str=None):
    if message != None and len(message) > 0:
        await ctx.respond(f"<@&1082043670620024924> from {ctx.author.mention}: `{escape_mentions(message)}`")
    else:
        await ctx.respond(f"<@&1082043670620024924> from {ctx.author.mention}!")

# --- Reactions ---

@bot.event
async def on_raw_reaction_add(payload):
    """
    <RawReactionActionEvent
        message_id=1082050030925512765
        user_id=263116922793623555
        channel_id=1082050009010282546
        guild_id=572148465870700544
        emoji=<PartialEmoji animated=False name='jh_green' id=619258364094054440>
        event_type='REACTION_ADD'
        member=<Member id=263116922793623555 name='jhnhnckjr' discriminator='6220' bot=False nick=None
            guild=<Guild id=572148465870700544 name='PIVOT Playground' shard_id=0 chunked=False member_count=5>
        >>
    """
    user = payload.user_id
    reaction = payload.emoji
    message_id = payload.message_id
    logger.info(f'Added {reaction} on {message_id}: {user}')

@bot.event
async def on_raw_reaction_remove(payload):
    """
    <RawReactionActionEvent
        message_id=1082050030925512765
        user_id=263116922793623555
        channel_id=1082050009010282546
        guild_id=572148465870700544
        emoji=<PartialEmoji animated=False name='jh_green' id=619258364094054440>
        event_type='REACTION_ADD'
        member=<Member id=263116922793623555 name='jhnhnckjr' discriminator='6220' bot=False nick=None
            guild=<Guild id=572148465870700544 name='PIVOT Playground' shard_id=0 chunked=False member_count=5>
        >>
    """
    user = payload.user_id
    reaction = payload.emoji
    message_id = payload.message_id
    logger.info(f'Removed {reaction} on {message_id}: {user}')

# --- Events ---

@bot.event
async def on_ready():
    perms = '1512634297568'

    logger.info(f'Logged in as {bot.user} (ID: {bot.user.id})!')
    logger.info(f'Add to a server:\n\thttps://discordapp.com/oauth2/authorize?client_id={bot.application_id}&scope=bot&permissions={perms}')

    # await load_role_menu()

@bot.event
async def on_message(message):
    logger.info(f'Message from {message.author}: {message.content}')

# --- Trigger Function ---

def start_bot_loop():
    global bot, config

    config.load_from_file()

    logger.info('Starting bot...')
    bot.run(config.bot_token)
