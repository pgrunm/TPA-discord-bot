# TPA Discord Bot

## Features

- Clan Experience Points

## Installation

- Download requirements with:

```Bash
python -m venv venv
source ./venv/Scripts/activate
```

- Run the bot with `python3 discord_bot.py`

## Installation with Docker

You can also run the bot with docker, in my case a Raspberry Pi (see [Dockerfile](Dockerfile.armv7)).

**Recommended Settings**:

- Setting the timezone i. e. Europe/Berlin
- Mounting the bot to a folder inside the user's context
- Limiting the restarts (3 in my case)

## Links

- [Discord Library](https://discordpy.readthedocs.io/en/stable/intro.html)
- [Python Dotenv](https://pypi.org/project/python-dotenv/)
- [Fap Bot](https://github.com/Peter-Pwn/fap-bot)
- [Division 2 Tracker](https://tracker.gg/developers/docs/titles/division-2)
- [Asyncio tutorial](https://realpython.com/async-io-python/)
- [Peewee](https://docs.peewee-orm.com/en/latest/peewee/quickstart.html)
- [Advanced Python Scheduler](https://apscheduler.readthedocs.io/en/stable/)
