import logging
import os
import sys
from pathlib import Path

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord.ext import commands
from dotenv import load_dotenv
from gcsa.google_calendar import GoogleCalendar
from peewee import SqliteDatabase
from dateutil import parser

import models.Message
import models.Player

intents = discord.Intents.default()
intents.members = True

# Bot command prefix
bot = commands.Bot(command_prefix='!', intents=intents)

# Database setting
db = SqliteDatabase('tpa.db')


@bot.event
async def on_ready():
    '''Logs the currently logged in user.'''

    logging.info('Logged in as {0.user}'.format(bot))


@bot.event
async def on_member_join(member):
    if os.getenv('enable_member_join_messages') == 'true':
        # Get the discord channel id from local environment
        channel_id = os.getenv('log_channel_id')
        discord_log_channel = bot.get_channel(int(channel_id))

        if discord_log_channel != None:
            logging.debug(f'Logging channel id {channel_id} found.')

            message = f':new:<@{member.id}> `{member.name}#{member.discriminator}` ist dem Server beigetreten.'

            await discord_log_channel.send(message)
        else:
            logging.error(f'Logging channel id {channel_id} NOT found.')


@bot.event
async def on_member_remove(member):
    if os.getenv('enable_member_join_messages') == 'true':
        # Get the discord channel id from local environment
        channel_id = os.getenv('log_channel_id')
        discord_log_channel = bot.get_channel(int(channel_id))

        if discord_log_channel != None:
            logging.debug(f'Logging channel id {channel_id} found.')

            message = f':door:<@{member.id}> `{member.name}#{member.discriminator}` hat den Server verlassen.'

            await discord_log_channel.send(message)
        else:
            logging.error(f'Logging channel id {channel_id} NOT found.')


'''
# https://stackoverflow.com/a/62496039
@client.event
async def on_member_update(before, after):
    if len(before.roles) < len(after.roles):
        # The user has gained a new role, so lets find out which one
        newRole = next(
            role for role in after.roles if role not in before.roles)

        if newRole.name == "Respected":
            # This uses the name but you could always use newRole.id == Roleid here
            # Now, simply put the code you want to run whenever someone gets the "Respected" role here
'''


async def update_xp_messages():
    # Edit message: https://stackoverflow.com/a/55711759
    for msg in models.Message.Message.select():
        channel = bot.get_channel(msg.discord_channel_id)

        try:
            xp_message = await channel.fetch_message(msg.discord_message_id)
        except:
            logging.error(f'Failed to parse the msg id')
        else:
            if msg.description == 'member_clan_xp':
                xp_msg = await models.Player.Player.get_player_weekly_xp_as_message()
                await xp_message.edit(embed=xp_msg, content=None)
            elif msg.description == 'admin_clan_xp':
                xp_msg = await models.Player.Player.get_player_weekly_xp_as_message(player_limit=-1)
                await xp_message.edit(embed=xp_msg, content=None)


async def new_xp_messages():
    for msg in models.Message.Message.select():
        channel = bot.get_channel(msg.discord_channel_id)
        if msg.description == 'member_clan_xp':
            xp_msg = await models.Player.Player.get_player_weekly_xp_as_message()
            sent_message = await channel.send(embed=xp_msg)

        elif msg.description == 'admin_clan_xp':
            xp_msg = await models.Player.Player.get_player_weekly_xp_as_message(player_limit=-1)
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


@bot.command()
async def termine(ctx, *args):
    # Retrieve the calender settings
    logging.debug(
        f"Parsing calender credentials from {Path(os.getenv('calendar_credentials_path'))}")

    calendar = GoogleCalendar(
        calendar=os.getenv('kalender_mail'),
        credentials_path=Path(os.getenv('calendar_credentials_path')),
        token_path=Path(os.getenv('calendar_token_path')))

    # Parse the channel id and convert it to integer
    channel_id = os.getenv('calender_channel_id')
    discord_channel = bot.get_channel(int(channel_id))

    if discord_channel != None:
        logging.debug(f'Calender channel id {channel_id} found.')

        logging.debug('Preparing the download of the calendar events...')

        for event in calendar:
            # New Embed formatting
            embed = discord.Embed(title=f":calendar_spiral: {event.summary}\n")

            # Prepare datetime formatting
            time_format = "%d.%m.%Y %H:%M"
            dt = event.start  # Contains the start time of the event

            # Add beginning time as field
            embed.add_field(name="Beginn",
                            value=dt.strftime(time_format), inline=False)

            # Add a description
            embed.add_field(name="Beschreibung",
                            value=event.description, inline=False)

            # Send the embed
            embed_msg = await discord_channel.send(embed=embed)

            # Add reactions for yes and maybe.
            await embed_msg.add_reaction('✅')
            await embed_msg.add_reaction('🤷')


@ bot.event
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
    my_handler = logging.StreamHandler(sys.stdout)

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
    db.create_tables(models=[models.Player.Player, models.Message.Message])

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

        # https://cron.help/#*/30_0-9,11_*_*_*
        scheduler.add_job(update_xp_messages, 'cron',
                          minute='*/30', hour='0-9,11-23')

        # Update player data, https://cron.help/#15/30_*_*_*_*
        scheduler.add_job(models.Player.Player.update_player_data, kwargs={
            'bot': bot}, trigger='cron', minute='15/30')

        # Retrieve new members
        scheduler.add_job(models.Player.Player.get_members, 'cron', minute=55)

        # Update weekly xp
        scheduler.add_job(models.Player.Player.update_player_data, kwargs={
            'update_weekly_xp': True, 'bot': bot}, trigger='cron',  day_of_week='thu', hour=10)

        # Upload weekly xp to CV
        scheduler.add_job(models.Player.Player.upload_player_data,
                          trigger='cron',  day_of_week='thu', hour=9, minute='40')

    else:
        logging.info('Starting with disabled cronjobs...')

    scheduler.start()

    bot.run(os.getenv('discord_bot_key'))
