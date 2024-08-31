import uuid

from pydantic import BaseModel

class Token(BaseModel):
    token: uuid.UUID