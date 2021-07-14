from peewee import Model, SqliteDatabase


database = SqliteDatabase('tpa.db')


class BaseModel(Model):
    class Meta:
        database = database
