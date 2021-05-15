import asyncio
import datetime
import json
from json.decoder import JSONDecodeError
import logging
import os
import sqlite3
from datetime import date, datetime

import aiohttp
from dotenv import load_dotenv
from peewee import (CharField, DateField, DoesNotExist, ForeignKeyField, Model,
                    SqliteDatabase)
from ratelimit import limits, sleep_and_retry

from models import Player

db = SqliteDatabase('tpa.db')


async def retrieve_xp():

    # Link to docs: https://tracker.gg/developers/docs/titles/division-2
    # https://public-api.tracker.gg/v2/division-2/standard/profile/uplay/{user}

    # Pass the API key to the header
    headers = {'TRN-Api-Key': os.getenv('TRN_API')}

    @sleep_and_retry
    @limits(calls=10, period=60)
    async def call_api(session, url, headers):
        html = await fetch(session=session, url=url, headers=headers)
        return html

    # Call the TRN API
    async with aiohttp.ClientSession() as session:

        # Get all members from the database
        for player in Player.select():
            # Get the XP for the player
            url = f'https://public-api.tracker.gg/v2/division-2/standard/profile/uplay/{player.player_name}'

            # Parse the output, required attribute: xPClan
            raw_json = await call_api(session, url, headers)
            try:
                content = json.loads(raw_json)
            except JSONDecodeError as json_decode_error:
                logging.error(
                    f'Error while decoding content for player {player.player_name}. Error: {json_decode_error}')

            # Code will be run if there was no exception
            else:
                try:
                    # Get the Clan XP
                    value_clan_xp = content['data']['segments'][0]['stats']['xPClan']['value']
                # If no data is found -> log it
                except KeyError:
                    logging.warning(
                        f'No data found for player {player.player_name}')

                finally:
                    # Check if there is a value, if not set it to 0
                    if value_clan_xp == None:
                        logging.debug(
                            f'Clan XP for player {player.player_name} was Null, setting it to 0')
                        value_clan_xp = 0

                    # If this a totally new parsed player he does not have any xp inside the database. So save the current clan xp.
                    if player.player_xp == 0:
                        player.player_xp = value_clan_xp

                    # Calculate the XP difference and update the value inside the DB
                    diff_xp = value_clan_xp - player.player_xp
                    player.player_weekly_xp = diff_xp

                    logging.debug(
                        f'Adding {diff_xp} xp for player {player.player_name} data to database')
                    # Write the XP to database
                    player.save()


async def get_members():
    url = 'http://cv.thepenguinarmy.de/BotRequest/AllMember'

    # Basic Auth from env file
    auth = aiohttp.BasicAuth(login=os.getenv('member_username'),
                             password=os.getenv('member_pw'))

    # Post request with HTTP basic auth
    async with aiohttp.ClientSession(auth=auth) as session:
        # Game IDs:
        # gameId = 1: Division 2
        # gameID = 2: TemTem

        # Limit time:
        # lastModified = 0000-00-00 00:00:00 (YYYY-MM-DD)

        # Create the JSON dict
        game_id = {'gameId': 1}

        # Send a POST request to the url and ask for members
        async with session.post(url, json=game_id) as resp:
            data = await resp.text()

            for user in json.loads(data):
                nickname = user['Ubisoft']['nickname']
                ubi_id = user['Ubisoft']['officialAccountId']

                # Try to find the user inside the database
                try:
                    player = Player.get(Player.player_name ==
                                        nickname or Player.player_ubi_id == ubi_id)

                    # Save the Ubisoft ID and if the name has changed also the name.
                    player.player_name = nickname
                    player.player_ubi_id = ubi_id

                # If the player does not exists yet we have to create it
                except DoesNotExist:
                    player = Player()
                    player.player_name = nickname
                    player.player_xp = 0
                    player.player_ubi_id = ubi_id
                    logging.debug(
                        f"Spieler {nickname} does not exist, creating it with Ubisoft ID {ubi_id}...")

                # Save the changes to the database
                finally:
                    player.save()


async def fetch(session, url, headers=''):
    # https://docs.aiohttp.org/en/stable/http_request_lifecycle.html#how-to-use-the-clientsession
    '''Allows retrieval of a url with a session added
    '''
    async with session.get(url, headers=headers) as response:
        logging.debug(f"HTTP Status for {url}: {response.status}")
        if 'X-RateLimit-Remaining-minute' in response.headers:
            logging.debug(
                f"Remaining Requests per minute: {response.headers['X-RateLimit-Remaining-minute']}")

        # Return the response text
        return await response.text()


@sleep_and_retry
@limits(calls=7, period=60)
async def test_ratelimit(number):
    logging.debug(f'Starte Aufruf mit number = {number}')
    url = f'https://httpbin.org/anything/{number}'

    logging.debug(f'Starte Test aufruf zu {url}')
    async with aiohttp.ClientSession() as session:
        await fetch(session, url)
        logging.debug(f'Response erhalten für Number = {number}')


if __name__ == "__main__":
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
    db.create_tables(models=[Player])

    # Call the TRN Web service
    loop = asyncio.get_event_loop()

    # Get the Player data for me
    # loop.run_until_complete(main())

    # for i in range(0, 14):
    #     logging.debug(f'Aufruf test_ratelimit mit i = {i}')
    #     loop.run_until_complete(test_ratelimit(i))

    # Get all Members from the Administration
    loop.run_until_complete(get_members())

    # Get the XP for each user
    loop.run_until_complete(retrieve_xp())

    # Logging shutdown
    logging.debug('Closing connection to database.')
    db.close()

    logging.info('Shutting down.')
    logging.shutdown()
