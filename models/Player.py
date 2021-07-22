import datetime
import json
import logging
import os
from json.decoder import JSONDecodeError

import aiohttp
import discord
from peewee import SQL, AutoField, IntegerField, TextField

from models.BaseModel import BaseModel
from models.Limit.Limit import Limit
from models.Tools.Network import fetch


class Player(BaseModel.BaseModel):
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
    @Limit(calls=20, period=60)
    async def call_api(session, url, headers):
        try:
            html = await fetch(session=session, url=url, headers=headers)
            return html
        except LookupError as player_error:
            raise player_error

    async def update_player_xp(self, session, update_weekly_xp=False):
        '''Retrieves the current amount of xp of a player'''

        # Pass the API key to the header
        headers = {'TRN-Api-Key': os.getenv('TRN_API')}

        url = f'https://public-api.tracker.gg/v2/division-2/standard/profile/uplay/{self.player_name}'

        try:
            # Parse the output, required attribute: xPClan
            raw_json = await Player.call_api(session, url, headers)
            content = json.loads(raw_json)
        except JSONDecodeError as json_decode_error:
            logging.error(
                f'Error while decoding content for player {self.player_name}. Error: {json_decode_error}')

        except LookupError as player_error:
            raise player_error
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
                    logging.warning(
                        f'Clan XP for player {self.player_name} was Null, setting it to 0')
                    value_clan_xp = 0

                # If this a totally new parsed player he does not have any xp inside the database. So save the current clan xp.
                if self.player_xp == 0:
                    self.player_xp = value_clan_xp

                '''
                Database fields
                Weekly XP: Clan XP earned so far this
                Player XP: Total XP earned by a player
                '''
                # Calculate the XP difference and update the value inside the DB
                self.player_weekly_xp = value_clan_xp

                # Overwrite the weekly XP if update_weekly_xp = True -> this only occurs on Thursdays
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

    @Limit(calls=20, period=60)
    async def upload_player_weekly_xp(self, session, xp_value):
        '''
        Upload player's weekly XP data to TPA community site.
        '''
        # Requireded Configuration
        upload_url = "http://cv.thepenguinarmy.de/BotRequest/Activity"
        # Basic Auth from env file
        auth = aiohttp.BasicAuth(login=os.getenv('member_username'),
                                 password=os.getenv('member_pw'))
        t = datetime.datetime.now()

        # Create the JSON dict

        # Required Parameters:
        # Value: Weekly XP Value
        # GameID: 1
        # accountTypName: Ubisoft
        # officialAccountId: Account ID
        # Accountname: Name of the account, but not necessary

        if(xp_value > 0):
            json_upload_content = {
                'gameId': 1,
                'officialAccountId': self.player_ubi_id,
                'accountTypName': 'Ubisoft',
                'value': xp_value,
                'dateTime':  t.strftime("%Y-%m-%d %H:%M:%S")
            }

            logging.debug(
                f'Trying to upload weekly XP stats for user {self.player_name} with ubi id {self.player_ubi_id}. JSON Content: {json_upload_content}')

            # Try to submit data
            try:
                async with session.post(upload_url, json=json_upload_content, auth=auth) as resp:
                    # Await the reponse
                    return_msg = await resp.text()

                    # If the HTTP Status code is different from 200 log it
                    if resp.status != 200:
                        logging.error(return_msg)

            except aiohttp.client_exceptions.ServerDisconnectedError as server_disconnect:
                logging.error(
                    f'Server disconnected session for player {self.player_name} with error: {server_disconnect}')

    @classmethod
    async def upload_player_data(cls):
        async with aiohttp.ClientSession() as session:
            for player in Player.select():
                logging.debug(
                    f'Checking CV XP upload for player {player.player_name}...')

                # Calculate the player's xp. If it is negative it may not be uploaded so there is no need to call the method.
                xp_value = player.player_weekly_xp - player.player_xp
                logging.debug(
                    f'Calculated XP value for player {player.player_name}: {xp_value}')

                if(xp_value > 0):
                    logging.debug(
                        f'Uploading weekly XP data for player {player.player_name}')
                    await player.upload_player_weekly_xp(session, xp_value)
                    logging.debug(
                        f'Upload of xp data for player {player.player_name} finished.')
                else:
                    logging.debug(
                        f'XP value for player {player.player_name} is negative, so skipping')

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
                    player, created = Player.get_or_create(
                        player_ubi_id=ubi_id,
                        defaults={'player_name': nickname, 'player_xp': 0, 'player_discord_id': discord_id})

                    if created == False:
                        # Save the Ubisoft ID and if the name has changed also the name.
                        if player.player_name != nickname:
                            player.player_name = nickname

                        # Check if the ubi id is different
                        if player.player_ubi_id == None:
                            player.player_ubi_id = ubi_id

                        # Check if the Discord id is empty
                        if player.player_discord_id == None:
                            player.player_discord_id = discord_id

                    # Finally save the player to the database
                    player.save()

    @Limit(calls=20, period=60)
    async def check_player_exit(self, session):
        url = 'http://cv.thepenguinarmy.de/BotRequest/Member'

        # Basic Auth from env file
        auth = aiohttp.BasicAuth(login=os.getenv('member_username'),
                                 password=os.getenv('member_pw'))

        # Create the JSON dict
        game_id = {'accountTypName': 'Ubisoft',
                   'officialAccountId': self.player_ubi_id}
        is_member = True

        logging.debug(
            f'Trying to retrieve member stats for user {self.player_name} with ubi id {self.player_ubi_id}')

        # Send a POST request to the url and ask for members
        try:
            async with session.post(url, json=game_id, auth=auth) as resp:
                data = await resp.text()

                # Parse the raw json into an object
                try:
                    content = json.loads(data)
                except JSONDecodeError as json_err:
                    logging.debug(
                        f'{json_err} occured while checking player {self.player_name}')
                else:
                    logging.debug(
                        f'Parsed json data for player {self.player_name}: {content}')
                    if '1' in content[0]['Ubisoft']['games']:
                        # Check if there is a isMember flag inside and loop through the characters
                        char = list(content[0]['Ubisoft']['games']
                                    ['1']['characters'].keys())
                        if 'isMember' in content[0]['Ubisoft']['games']['1']['characters'][char[0]]:
                            is_member = content[0]['Ubisoft']['games']['1']['characters'][char[0]]['isMember']
                        else:
                            # Log an error if there is no isMember value inside
                            logging.error(
                                f"No isMember value for player {self.player_name}")

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
    async def update_player_data(cls, bot, update_weekly_xp=False):
        async with aiohttp.ClientSession() as session:
            for player in Player.select():

                # Check if the selected player is still member
                is_member = await player.check_player_exit(session=session)

                if is_member == True:
                    logging.debug(f'Updating player data for {player}')

                    try:
                        await player.update_player_xp(session, update_weekly_xp=update_weekly_xp)
                        logging.debug(
                            f'Finished updating player data for player {player}')
                    except LookupError as err:
                        # Log this error
                        logging.error(
                            f'Player {player.player_name} probably changed the name: {err}')

                        # Only send a warning if this is true
                        enable_name_warning = os.getenv('enable_name_warning')
                        if enable_name_warning == 'true':
                            # Send a message into the chat
                            channel = bot.get_channel(797970880089161758)
                            await channel.send(f'Warnung: Spieler <@{player.player_discord_id}> ({player.player_name}) hat den Namen geändert!')

                else:
                    logging.debug(
                        f'Deleting player {player.player_name} from database')

                    # Delete the player from database
                    player.delete_instance()

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
            for player in Player.select(Player.player_name, Player.player_discord_id, Player.player_id, (Player.player_weekly_xp - Player.player_xp).alias('sql_weekly_xp')
                                        ).where(Player.player_discord_id != None).order_by(SQL('sql_weekly_xp').desc()).paginate(field_counter, paginate_by=10):

                # Added the player's xp to the message
                # Mention the player: https://stackoverflow.com/a/43991145
                # Formatting the XP: https://stackoverflow.com/a/48414649

                # XP calculation is done by subtracting the columns player_weekly_xp and player_xp
                xp_to_display = player.sql_weekly_xp

                # Check the player name for underscores and escape them if necessary
                if r'_' in player.player_name:
                    player.player_name = player.player_name.replace('_', r'\_')

                # Check if the player's weekly XP is negative, as this can happen if the source server from tracker network
                # sends weird data.
                if xp_to_display == None:
                    xp_to_display = 0
                elif xp_to_display < 0:
                    xp_to_display = 0

                # Formatting the embed: https://cog-creators.github.io/discord-embed-sandbox/
                field += f"**{counter}.** <@{player.player_discord_id}> ({player.player_name})\n{'{:,}'.format(xp_to_display).replace(',', '.')}\n"

                counter += 1
            if field_counter == 1:
                embed.add_field(name=f'Top {player_limit}',
                                value="\n\u200b" + field, inline=False)
            else:
                # Only add the fields if its not empty
                if field != '':
                    embed.add_field(name=f'\u200b\n',
                                    value=field, inline=False)
        embed.set_footer(text=f"Last Update: {t.strftime('%d.%m.%y %H:%M')}")
        return embed
