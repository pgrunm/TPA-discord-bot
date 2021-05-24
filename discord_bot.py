import asyncio
import logging
import os

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord.ext import commands, tasks
from dotenv import load_dotenv
from peewee import CharField  # Required permissions: Server Members Intent
from peewee import (DateField, DoesNotExist, ForeignKeyField, Model,
                    SqliteDatabase)

from models import Message, Player

intents = discord.Intents.default()
intents.members = True

# Bot command prefix
bot = commands.Bot(command_prefix='!', intents=intents)

# Database setting
db = SqliteDatabase('tpa.db')


@ bot.event
async def on_ready():
    '''Logs the currently logged in user.'''

    logging.info('Logged in as {0.user}'.format(bot))


@tasks.loop(minutes=30)
async def called_once_a_day():
    channel_id = 835946447097823262

    message_channel = bot.get_channel(channel_id)
    print(f"Got channel {message_channel}")
    await message_channel.send("Test Message")


@called_once_a_day.before_loop
async def before():
    # https://discordpy.readthedocs.io/en/latest/ext/tasks/index.html
    # https://stackoverflow.com/a/57634182
    await bot.wait_until_ready()


if __name__ == '__main__':

    # Load environmental variables
    load_dotenv()

    # Create the logging handler
    logging.basicConfig(filename='bot.log',
                        encoding='utf-8', level=os.getenv('log_level').upper(),
                        format='[%(levelname)s]%(asctime)s: %(message)s', datefmt='%d.%m.%Y %H:%M:%S')

    # Connect to the database and create missing tables
    logging.debug('Creating connection to database...')
    db.connect()
    logging.debug('Creating missing tables...')
    db.create_tables(models=[Player, Message])

    # Call the TRN Web service
    loop = asyncio.get_event_loop()

    # Scheduler for timing events
    # how to add jobs: https://apscheduler.readthedocs.io/en/stable/userguide.html#adding-jobs
    scheduler = AsyncIOScheduler()
    scheduler.start()

    called_once_a_day.start()
    bot.run(os.getenv('discord_bot_key'))

    # Nachricht ändern: https://stackoverflow.com/a/55711759
