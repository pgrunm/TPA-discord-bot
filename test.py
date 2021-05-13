import asyncio
import json
import logging
import os
import sqlite3
import datetime

import aiohttp
from dotenv import load_dotenv
from ratelimit import limits, sleep_and_retry

from functions import create_database


async def retrieve_xp(cur, con):

    # Link to docs: https://tracker.gg/developers/docs/titles/division-2
    # https://public-api.tracker.gg/v2/division-2/standard/profile/uplay/{user}

    # Pass the API key to the header
    headers = {'TRN-Api-Key': os.getenv('TRN_API')}

    @sleep_and_retry
    @limits(calls=7, period=60)
    async def call_api(session, url, headers):
        html = await fetch(session=session, url=url, headers=headers)
        return html

    player_xp_statements = list()

    # Today's date
    date = f"{datetime.datetime.now():%d.%m.%Y}"

    # Call the TRN API
    async with aiohttp.ClientSession() as session:

        # Get all members from the database
        for row in cur.execute('SELECT player_name, player_id from players;'):

            player_name = row[0]
            player_id = row[1]

            url = f'https://public-api.tracker.gg/v2/division-2/standard/profile/uplay/{player_name}'

            # Parse the output, required attribute: xPClan
            raw_json = await call_api(session, url, headers)

            content = json.loads(raw_json)

            try:
                # Get the Clan XP
                value_clan_xp = content['data']['segments'][0]['stats']['xPClan']['value']
            # If no data is found -> log it
            except KeyError:
                logging.debug(f'No data found for player {player_name}')

            finally:
                # Check if there is a value, if not set it to 0
                if value_clan_xp == None:
                    logging.debug(
                        f'Clan XP for player xy was null, setting it to 0')
                    value_clan_xp = 0

                # Prepare the sql statement
                player_xp_statements.append((player_id, value_clan_xp, date,))

            logging.debug(
                f'Parsed Clan XP for player {player_name} value: {value_clan_xp}')

        logging.debug('Saving player xp data to database')

        # Insert the date
        cur.executemany(
            "INSERT INTO xp (player_id, player_xp, xp_date, xp_id) VALUES (?, ?, ?, NULL)", player_xp_statements)
        con.commit()


async def get_members(sql_cur, sql_con):
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

            # Save the output
            # Create the list for the SQL insert statements
            insert_statements = list()

            for user in json.loads(data):
                nickname = user['Ubisoft']['nickname']
                # Check if the user is already inside the database
                # https://stackoverflow.com/a/30042512
                c = sql_cur.execute(
                    f'SELECT EXISTS(SELECT 1 FROM players WHERE player_name = ?);', (nickname,)).fetchone()[0]

                # Check if c != 1 -> User is not inside the database
                if not c:
                    if user['isMember'] == True:
                        # Append the SQL Statement
                        insert_statements.append((nickname,))

            try:
                sql_cur.executemany(
                    "INSERT INTO players (player_name) VALUES (?)", insert_statements)
            except Exception as e:
                print(f'Error occured while saving rows: {e}')

            # Commit all changes made
            sql_con.commit()


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
        html = await fetch(session, url)
        logging.debug(f'Response erhalten für Number = {number}')


if __name__ == "__main__":
    # Load environmental variables
    load_dotenv()

    # Create the logging handler
    logging.basicConfig(filename='bot.log',
                        encoding='utf-8', level=os.getenv('log_level').upper(),
                        format='[%(levelname)s]%(asctime)s: %(message)s', datefmt='%d.%m.%Y %H:%M:%S')

    # Call the TRN Web service
    loop = asyncio.get_event_loop()

    # Get the Player data for me
    # loop.run_until_complete(main())

    # create_database()

    logging.debug('Creating connection to database...')
    con = sqlite3.connect('tpa.db')
    cur = con.cursor()

    # for i in range(0, 14):
    #     logging.debug(f'Aufruf test_ratelimit mit i = {i}')
    #     loop.run_until_complete(test_ratelimit(i))

    loop.run_until_complete(get_members(cur, con))

    # Get the XP
    loop.run_until_complete(retrieve_xp(cur, con))

    # Logging shutdown
    logging.debug('Closing connection to database.')
    con.close()

    logging.shutdown()
