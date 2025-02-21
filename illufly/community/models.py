from typing import Optional, Dict, Any
import logging

from ..mq.models import StreamingBlock, BlockType
from ..mq.utils import serialize

logger = logging.getLogger(__name__)

@serialize
class TextChunk(StreamingBlock):
    """文本块"""
    block_type: BlockType = BlockType.TEXT_CHUNK
    text: str

    @property
    def content(self) -> str:
        return self.text

@serialize
class TextFinal(StreamingBlock):
    """文本结束块"""
    block_type: BlockType = BlockType.TEXT_FINAL
    text: str

    @property
    def content(self) -> str:
        return self.text

@serialize
class ToolCallChunk(StreamingBlock):
    """工具调用块"""
    block_type: BlockType = BlockType.TOOL_CALL_CHUNK
    tool_call_id: Optional[str] = None  # 工具调用ID
    tool_name: Optional[str] = None  # 工具名称
    arguments: str = ""  # 工具参数（逐步累积）

    @property
    def content(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "id": self.tool_call_id,
            "function": {
                "name": self.tool_name,
                "arguments": self.arguments
            }
        }

@serialize
class ToolCallFinal(ToolCallChunk):
    """工具调用结束块"""
    block_type: BlockType = BlockType.TOOL_CALL_FINAL

@serialize
class UsageBlock(StreamingBlock):
    """使用情况块"""
    block_type: BlockType = BlockType.USAGE
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    prompt_cache_hit_tokens: Optional[int] = None
    prompt_cache_miss_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    model: Optional[str] = None
    provider: Optional[str] = None

    @property
    def content(self) -> Dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "prompt_cache_hit_tokens": self.prompt_cache_hit_tokens,
            "prompt_cache_miss_tokens": self.prompt_cache_miss_tokens,
            "completion_tokens_details": {
                "reasoning_tokens": self.reasoning_tokens,
            }
        }
