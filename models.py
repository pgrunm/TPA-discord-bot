import asyncio
import datetime
import json
import logging
import os
import time
from json.decoder import JSONDecodeError

import aiohttp
import discord
from discord.ext.commands.bot import Bot
from peewee import (AutoField, DoesNotExist, IntegerField, Model,
                    SqliteDatabase, TextField, Value)

database = SqliteDatabase('tpa.db')


class Limit(object):
    def __init__(self, calls=5, period=1):
        self.calls = calls
        self.period = period
        self.clock = time.monotonic
        self.last_reset = 0
        self.num_calls = 0

    def __call__(self, func):
        async def wrapper(*args, **kwargs):
            if self.num_calls >= self.calls:
                await asyncio.sleep(self.__period_remaining())

            period_remaining = self.__period_remaining()

            if period_remaining <= 0:
                self.num_calls = 0
                self.last_reset = self.clock()

            self.num_calls += 1

            return await func(*args, **kwargs)

        return wrapper

    def __period_remaining(self):
        elapsed = self.clock() - self.last_reset
        return self.period - elapsed


class UnknownField(object):
    def __init__(self, *_, **__): pass


class BaseModel(Model):
    class Meta:
        database = database


class Player(BaseModel):
    player_id = AutoField(null=True)
    player_name = TextField(null=True, unique=True)
    player_xp = IntegerField(null=True)
    player_ubi_id = TextField(null=True, unique=True)
    player_weekly_xp = IntegerField(null=True)
    player_discord_id = IntegerField(null=True)

    class Meta:
        table_name = 'players'

    def __str__(self):
        return f'Player: {self.player_name}, ID {self.player_id}'

    @staticmethod
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

    @staticmethod
    @Limit(calls=20, period=60)
    async def call_api(session, url, headers):
        html = await Player.fetch(session=session, url=url, headers=headers)
        return html

    async def update_player_xp(self, session, update_weekly_xp=False):
        '''Retrieves the current amount of xp of a player'''

        # Pass the API key to the header
        headers = {'TRN-Api-Key': os.getenv('TRN_API')}

        url = f'https://public-api.tracker.gg/v2/division-2/standard/profile/uplay/{self.player_name}'

        # Parse the output, required attribute: xPClan
        raw_json = await Player.call_api(session, url, headers)
        try:
            content = json.loads(raw_json)
        except JSONDecodeError as json_decode_error:
            logging.error(
                f'Error while decoding content for player {self.player_name}. Error: {json_decode_error}')

        # Code will be run if there was no exception
        else:
            try:
                # Get the Clan XP
                if 'data' in content:
                    value_clan_xp = content['data']['segments'][0]['stats']['xPClan']['value']
                else:
                    value_clan_xp = 0
            # If no data is found -> log it
            except KeyError:
                logging.warning(
                    f'No data found for player {self.player_name}')

            finally:
                # Check if there is a value, if not set it to 0
                if value_clan_xp == None:
                    logging.debug(
                        f'Clan XP for player {self.player_name} was Null, setting it to 0')
                    value_clan_xp = 0

                # If this a totally new parsed player he does not have any xp inside the database. So save the current clan xp.
                if self.player_xp == 0:
                    self.player_xp = value_clan_xp

                # Calculate the XP difference and update the value inside the DB
                diff_xp = value_clan_xp - self.player_xp
                self.player_weekly_xp = diff_xp

                logging.debug(
                    f'Adding {diff_xp} xp for player {self.player_name} data to database')

                # Overwrite the weekly XP if update_weekly_xp = True
                if update_weekly_xp == True:
                    logging.debug(
                        f'Updating weekly xp for player {self.player_name}')

                    # Only Update the player's total xp if the value is > 0
                    if value_clan_xp > 0:
                        logging.debug(
                            f'Value for clan xp for player {self.player_name} is bigger than 0, actual value: {value_clan_xp} ')
                        self.player_xp = value_clan_xp

                # Write the XP to database
                self.save()

    @staticmethod
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
                    discord_id = user['Discord']['officialAccountId']

                    # Try to find the user inside the database
                    try:
                        player = Player.get(Player.player_name ==
                                            nickname or Player.player_ubi_id == ubi_id)

                        # Save the Ubisoft ID and if the name has changed also the name.
                        player.player_name = nickname
                        player.player_ubi_id = ubi_id

                        # Check if the Discord id is empty
                        if player.player_discord_id == None:
                            player.player_discord_id = discord_id

                    # If the player does not exists yet we have to create it
                    except DoesNotExist:
                        player = Player(player_name=nickname,
                                        player_xp=0, player_ubi_id=ubi_id, player_discord_id=discord_id)

                        logging.debug(
                            f"Spieler {nickname} does not exist, creating it with Ubisoft ID {ubi_id}...")

                    # Save the changes to the database
                    finally:
                        player.save()

    @Limit(calls=20, period=60)
    async def check_player_exit(self, session):
        url = 'http://bot.thepenguinarmy.de/BotRequest/Member'

        # Basic Auth from env file
        auth = aiohttp.BasicAuth(login=os.getenv('member_username'),
                                 password=os.getenv('member_pw'))

        # Create the JSON dict
        game_id = {'accountTypName': 'Ubisoft',
                   'officialAccountId': self.player_ubi_id}

        logging.debug(
            f'Trying to retrieve member stats for user {self.player_name} with ubi id {self.player_ubi_id}')

        # Send a POST request to the url and ask for members
        try:
            async with session.post(url, json=game_id, auth=auth) as resp:
                data = await resp.text()

                # Parse the raw json into an object
                content = json.loads(data)
                logging.debug(
                    f'Parsed json data for player {self.player_name}: {content}')

                if 'isMember' in content[0]:
                    is_member = content[0]['isMember']

                # Continue with the parsed value
                logging.debug(
                    f'Parsed value for player {self.player_name}: {is_member}')
        except aiohttp.client_exceptions.ServerDisconnectedError as server_disconnect:
            logging.error(
                f'Server disconnected session for player {self.player_name} with error: {server_disconnect}')
            is_member = True
        finally:
            return is_member

    @classmethod
    async def update_player_data(cls, update_weekly_xp=False):
        async with aiohttp.ClientSession() as session:
            for player in Player.select():

                # Check if the selected player is still member
                is_member = await player.check_player_exit(session=session)

                if is_member == True:
                    logging.debug(f'Updating player data for {player}')
                    await player.update_player_xp(session, update_weekly_xp=update_weekly_xp)
                    logging.debug(
                        f'Finished updating player data for player {player}')
                else:
                    logging.debug(
                        f'Deleting player {player.player_name} from database')

                    # Delete the player from database
                    Player.delete().where(Player.player_ubi_id == player.player_ubi_id)

    @classmethod
    async def get_player_weekly_xp_as_message(cls, player_limit=10):
        # Get current date and calculate the next thursday https://stackoverflow.com/a/8801197
        today = datetime.date.today()
        d = datetime.date.today()
        t = datetime.datetime.now()

        while d.weekday() != 3:
            d += datetime.timedelta(1)

        date_format = '%d.%m.%Y'
        counter = 1

        if today.weekday() > 3 or (today.weekday() == 3 and t.hour < 10):
            # After thursday / On Thursday before 10 o'clock
            date = f'{(d - datetime.timedelta(days=7)).strftime(date_format)} - {d.strftime(date_format)}'
        elif today.weekday() < 3 or (today.weekday() == 3 and t.hour >= 10):
            # Before / On thursday after 10 o'clock
            date = f'{d.strftime(date_format)} - {(d + datetime.timedelta(days=7)).strftime(date_format)}'

        # Create the embed, set the icon and fill it with content
        embed = discord.Embed(title="Wöchentliche Clan XP",
                              description=date, color=0x0066ff)
        embed.set_thumbnail(
            url="https://cdn.discordapp.com/icons/346339932647981057/98ee3738aa3e46b268677972637c4c7b.webp")

        # How many embed fields are necessary?
        if player_limit == -1:
            number_of_required_fields = round(
                Player.select().count(database=None) / 10)
            player_limit = 'Total'
        else:
            number_of_required_fields = round(
                player_limit / 10)

        for field_counter in range(1, number_of_required_fields + 1):

            field = ''
            # Get the xp of all the players, limit by the parameter player_limit
            for player in Player.select().where(Player.player_weekly_xp >= 0 | Player.player_discord_id != None).order_by(Player.player_weekly_xp.desc()).paginate(field_counter, paginate_by=10):

                # Added the player's xp to the message
                # Mention the player: https://stackoverflow.com/a/43991145
                # Formatting the XP: https://stackoverflow.com/a/48414649

                # Formatting the embed: https://cog-creators.github.io/discord-embed-sandbox/
                field += f"**{counter}.** <@{player.player_discord_id}> ({player.player_name})\n{'{:,}'.format(player.player_weekly_xp).replace(',', '.')}\n"

                counter += 1
            if field_counter == 1:
                embed.add_field(name=f'Top {player_limit}',
                                value="\n\u200b" + field, inline=False)
            else:
                embed.add_field(name=f'\u200b\n',
                                value=field, inline=False)
        embed.set_footer(text=f"Last Update: {t.strftime('%d.%m.%y %H:%M')}")
        return embed


class Message(BaseModel):
    message_id = AutoField(null=True)
    discord_message_id = IntegerField(null=True)
    description = TextField(null=True)
    discord_channel_id = IntegerField(null=True)

    class Meta:
        table_name = 'discord_messages'

    def __str__(self):
        return f'Discord Message ID: {self.discord_message_id}, Description {self.description}'
