from peewee import AutoField, IntegerField, TextField
from models.BaseModel import BaseModel


class Message(BaseModel.BaseModel):
    message_id = AutoField(null=True)
    discord_message_id = IntegerField(null=True)
    description = TextField(null=True)
    discord_channel_id = IntegerField(null=True)

    class Meta:
        table_name = 'discord_messages'

    def __str__(self):
        return f'Discord Message ID: {self.discord_message_id}, Description {self.description}'
