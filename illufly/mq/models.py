from typing import List, Union, Dict, Any, Optional, AsyncGenerator, Generator
from enum import Enum
from pydantic import BaseModel, Field, model_validator
import time
import json

class BlockType(str, Enum):
    START = "start"           
    CHUNK = "chunk"          
    END = "end"             
    USAGE = "usage"          
    ERROR = "error"         
    PROGRESS = "progress"     
    TOOLS_CALL = "tools_call"  

class ProgressContent(BaseModel):
    """进度信息"""
    percentage: float = Field(default=0.0)
    message: str = Field(default="")
    step: int = Field(default=0)
    total_steps: int = Field(default=0)

class ToolsCallContent(BaseModel):
    """工具调用信息"""
    tool_name: str
    parameters: Dict[str, Any]
    call_id: str = Field(default="")

class StreamingBlock(BaseModel):
    """流式处理块"""
    block_type: BlockType = Field(default=BlockType.CHUNK)
    content: Union[str, dict] = Field(default="")
    topic: str = Field(default="")
    created_at: float = Field(default_factory=time.time)
    thread_id: str = Field(default="")

    @model_validator(mode='before')
    @classmethod
    def validate_content(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """验证并处理content字段"""
        if not isinstance(data, dict):
            return data
            
        content = data.get('content')
        block_type = data.get('block_type')

        # 如果content是字符串形式的JSON，尝试解析
        if isinstance(content, str) and block_type:
            try:
                if block_type in ('progress', BlockType.PROGRESS):
                    content = json.loads(content)
                    ProgressContent.model_validate(content)
                elif block_type in ('tools_call', BlockType.TOOLS_CALL):
                    content = json.loads(content)
                    ToolsCallContent.model_validate(content)
            except (json.JSONDecodeError, ValueError):
                pass  # 如果解析失败，保持原始字符串
            data['content'] = content
            
        return data

    def get_structured_content(self) -> Optional[BaseModel]:
        """获取结构化内容"""
        if isinstance(self.content, dict):
            try:
                if self.block_type == BlockType.PROGRESS:
                    return ProgressContent.model_validate(self.content)
                elif self.block_type == BlockType.TOOLS_CALL:
                    return ToolsCallContent.model_validate(self.content)
            except ValueError:
                pass
        return None

    def model_dump(self, **kwargs) -> Dict[str, Any]:
        """重写model_dump以处理content的序列化"""
        data = super().model_dump(**kwargs)
        if isinstance(data['content'], dict):
            # 确保字典内容被序列化为JSON字符串
            data['content'] = json.dumps(data['content'])
        return data

    @classmethod
    def create_progress(cls, percentage: float, message: str = "", step: int = 0, total_steps: int = 0, **kwargs) -> "StreamingBlock":
        """创建进度块"""
        content = ProgressContent(
            percentage=percentage,
            message=message,
            step=step,
            total_steps=total_steps
        )
        return cls(
            block_type=BlockType.PROGRESS,
            content=content.model_dump(),
            **kwargs
        )

    @classmethod
    def create_tools_call(cls, tool_name: str, parameters: Dict[str, Any], call_id: str = "", **kwargs) -> "StreamingBlock":
        """创建工具调用块"""
        content = ToolsCallContent(
            tool_name=tool_name,
            parameters=parameters,
            call_id=call_id
        )
        return cls(
            block_type=BlockType.TOOLS_CALL,
            content=content.model_dump(),
            **kwargs
        )
