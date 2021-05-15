from peewee import SqliteDatabase, Model, AutoField, TextField, ForeignKeyField, IntegerField, DateTimeField

database = SqliteDatabase('tpa.db')


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

    class Meta:
        table_name = 'players'
