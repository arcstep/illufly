from pydantic import BaseModel

class EventBlock(BaseModel):
    block_type: str
    content: str