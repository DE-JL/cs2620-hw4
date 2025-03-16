import uuid

from pydantic import BaseModel, Field


class User(BaseModel):
    username: str
    password: str
    message_ids: set[uuid.UUID] = Field(default_factory=set)

    def add_message(self, message_id: uuid.UUID):
        assert message_id not in self.message_ids
        self.message_ids.add(message_id)

    def delete_message(self, message_id: uuid.UUID):
        assert message_id in self.message_ids
        self.message_ids.remove(message_id)
