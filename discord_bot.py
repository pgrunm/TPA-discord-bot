import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord import Message
from discord import message
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
    # Edit message: https://stackoverflow.com/a/55711759
    for msg in Message.select():
        channel = bot.get_channel(msg.discord_channel_id)

        try:
            xp_message = await channel.fetch_message(msg.discord_message_id)
        except:
            logging.error(f'Failed to parse the msg id')
        else:
            if msg.description == 'member_clan_xp':
                xp_msg = await Player.get_player_weekly_xp_as_message()
                await xp_message.edit(embed=xp_msg, content=None)
            elif msg.description == 'admin_clan_xp':
                xp_msg = await Player.get_player_weekly_xp_as_message(player_limit=-1)
                await xp_message.edit(embed=xp_msg, content=None)


async def new_xp_messages():
    for msg in Message.select():
        channel = bot.get_channel(msg.discord_channel_id)
        if msg.description == 'member_clan_xp':
            xp_msg = await Player.get_player_weekly_xp_as_message()
            sent_message = await channel.send(embed=xp_msg)

        elif msg.description == 'admin_clan_xp':
            xp_msg = await Player.get_player_weekly_xp_as_message(player_limit=-1)
            sent_message = await channel.send(embed=xp_msg)

        if sent_message != None:
            # Save the message id to the database, so we can edit it later
            msg.discord_message_id = sent_message.id
            msg.save()


@bot.command()
async def xpmessage(ctx, *args):

    if log_level.upper() == 'DEBUG':
        await new_xp_messages()
    else:
        message = "Currently not in debugging mode, command not available!"
        await ctx.author.send(message)


@bot.event
async def on_message(message):
    # Just in case there are any commands they need to be processed.
    await bot.process_commands(message)

    # If the bot receives a private message answer it.
    if not message.guild:
        if message.author.id != bot.user.id:
            await message.author.send(f"Hallo {message.author}! Ich bin leider nur ein Bot, wenn du Fragen hast, wende dich an einen unserer Pinguine aus Fleisch und Blut. Danke! :-)")
        else:
            # If the message is from the bot we have to ignore it
            return


if __name__ == '__main__':

    # Load environmental variables
    load_dotenv(override=True)
    log_level = os.getenv('log_level').upper()
    enable_crons = os.getenv('enable_crons')

    # Logging configuration
    log_file = 'bot.log'
    log_encoding = 'utf-8'

    # Create the logging handler
    my_handler = RotatingFileHandler(log_file, mode='a',
                                     # 5 -> 5 MiB
                                     maxBytes=5*1024*1024,
                                     backupCount=2, encoding=log_encoding, delay=0)

    # Set the logging level
    my_handler.setLevel(log_level)

    # Create the config with the file handler from above
    logging.basicConfig(level=log_level,
                        handlers=[my_handler],
                        format='[%(levelname)s]%(asctime)s: %(message)s', datefmt='%d.%m.%Y %H:%M:%S')

    # Connect to the database and create missing tables
    logging.debug('Creating connection to database...')
    db.connect()
    logging.debug('Creating missing tables...')
    db.create_tables(models=[Player, Message])

    # Scheduler for timing events
    # how to add jobs: https://apscheduler.readthedocs.io/en/stable/userguide.html#adding-jobs
    # https://cron.help/
    scheduler = AsyncIOScheduler()
    # https://cron.help/#15_10_*_*_4

    # Feature toggle disable_crons: Disables all cronjobs to better test settings and dont get into problems
    # with production.
    if enable_crons == 'true':
        logging.info('Enabling cronjobs...')

        scheduler.add_job(new_xp_messages, 'cron',
                          day_of_week='thu', minute=15, hour=10)

        # https://cron.help/#*/30_*_*_*_*
        scheduler.add_job(update_xp_messages, 'cron', minute='*/30')

        # Update player data, https://cron.help/#15/30_*_*_*_*
        scheduler.add_job(Player.update_player_data, 'cron', minute='15/30')

        # Retrieve new members
        scheduler.add_job(Player.get_members, 'cron', minute=55)

        # Update weekly xp
        scheduler.add_job(Player.update_player_data, kwargs={
            'update_weekly_xp': True}, trigger='cron',  day_of_week='thu', hour=10)
    else:
        logging.info('Starting with disabled cronjobs...')

    scheduler.start()

    bot.run(os.getenv('discord_bot_key'))
