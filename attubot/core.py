"""
AttuBot - Main file
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import traceback

import discord
from discord.errors import CheckFailure

from attubot.config import Config
from attubot.logging import get_logger

# --- Initialization ---

logger = get_logger(__name__)
logger.info('Initializing...')

intents = discord.Intents.default()
intents.message_content = True

bot = discord.Bot(intents=intents)

# --- Error Handling ---

async def send_to_error_log(error):
    guild = bot.get_guild(Config.jhn_guild)
    error_log = guild.get_channel(Config.error_log_channel)

    tb_str = ''.join(traceback.format_tb(error.__traceback__))

    await error_log.send(f'**{error}**\n```\n{tb_str}```')

    logger.error(str(error) + '\n' + tb_str)

# --- Events ---

@bot.event
async def on_ready():
    perms = '207952'

    logger.info(f'Logged in as {bot.user} (ID: {bot.user.id})!')
    logger.info(f'Add to a server:\n\thttps://discordapp.com/oauth2/authorize?client_id={bot.application_id}&scope=bot&permissions={perms}')

    logger.info('Pushing commands to Discord')
    await bot.sync_commands()

@bot.event
async def on_message(message):
    if message.channel.id == Config.activity_channel and message.content.startswith(f'[{Config.wiki_user.split('@')[0]}]'):  # TODO: verify correct part of wiki bot username
        if 'blocked' in message.content:
            await message.add_reaction('<:tieteran_wave:1308636215930654801>')
        else:
            await message.add_reaction('💖')

@bot.before_invoke
async def on_command(ctx):
    logger.info(f'Command executed: user={ctx.user.global_name} command={ctx.command} channel={ctx.channel.name} data={ctx.interaction.data}')

@bot.event
async def on_application_command_error(ctx, error):
    logger.error(f'Error sent to `on_application_command_error()` vars={vars(ctx)}')

    if isinstance(error, CheckFailure):
        await ctx.respond("You're not my real dad!")
    else:
        await ctx.respond('An unexpected error occurred! <:rockball_player:1308977543034048552>')
        await send_to_error_log(error)


# --- Trigger Function ---

def start_bot_loop():
    Config.init()

    logger.info('Loading Extensions')
    bot.load_extension('attubot.tasks')
    bot.load_extension('attubot.admin')
    bot.load_extension('attubot.commands')

    logger.info('Starting Bot')
    bot.run(Config.bot_token)
