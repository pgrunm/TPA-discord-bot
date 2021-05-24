import asyncio
from datetime import datetime
import logging
import os

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord import Message
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


async def update_xp_messages():
    now = datetime.now().strftime('%d.%m.%Y %H:%M:%S')

    for msg in Message.select():
        channel = bot.get_channel(msg.discord_channel_id)

        try:
            xp_message = await channel.fetch_message(msg.discord_message_id)
        except:
            logging.error(f'Failed to parse the msg id')
        else:
            if msg.description == 'member_clan_xp':
                await xp_message.edit(content=f'New Content Clan Member XP Message at {now}')
            elif msg.description == 'admin_clan_xp':
                await xp_message.edit(content=f'New Content Admin Member XP Message at {now}')


async def new_xp_messages():
    for msg in Message.select():
        channel = bot.get_channel(msg.discord_channel_id)

        if msg.description == 'member_clan_xp':
            sent_message = await channel.send("Neue Clan Member XP Nachricht")

        elif msg.description == 'admin_clan_xp':
            sent_message = await channel.send("Neue Clan Admin XP Nachricht")

        if sent_message != None:
            # Save the message id to the database, so we can edit it later
            msg.discord_message_id = sent_message.id
            msg.save()


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
    # https://cron.help/
    scheduler = AsyncIOScheduler()
    # scheduler.add_job(Player.update_player_data, 'cron', minute='*/5')
    scheduler.add_job(new_xp_messages, 'cron', minute='*/10')
    scheduler.add_job(update_xp_messages, 'cron', minute='*/1')
    scheduler.start()

    # called_once_a_day.start()

    bot.run(os.getenv('discord_bot_key'))

    # Nachricht ändern: https://stackoverflow.com/a/55711759
