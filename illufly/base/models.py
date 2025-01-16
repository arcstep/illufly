from pydantic import BaseModel

class StreamingBlock(BaseModel):
    """流式处理块"""
    block_type: str
    content: str
