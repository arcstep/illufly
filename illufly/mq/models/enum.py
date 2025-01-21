from enum import Enum
from typing import Literal

class BlockType(str, Enum):
    REQUEST = "request"
    REPLY = "reply"
    START = "start"
    TEXT_CHUNK = "text_chunk"
    TEXT_FINAL = "text_final"
    TOOL_CALL_CHUNK = "tool_call_chunk"
    TOOL_CALL_FINAL = "tool_call_final"
    USAGE = "usage"
    PROGRESS = "progress"
    IMAGE = "image"
    VISION = "vision"
    ERROR = "error"
    END = "end"
    CONTENT = "content"

class ReplyState(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
