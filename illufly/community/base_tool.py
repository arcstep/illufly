from typing import AsyncGenerator, Dict, Any, List, Union
from pydantic import BaseModel, create_model, Field
import inspect
import json

from ..mq.models import StreamingBlock, BlockType

class ToolCallMessage(StreamingBlock):
    """工具调用消息模型"""
    block_type: BlockType = BlockType.TOOL_CALL_MESSAGE
    tool_call_id: str = Field(default="", description="工具调用ID")
    text: str = Field(..., description="工具调用返回结果")

    @property
    def content(self) -> Dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "content": self.text
        }

class BaseToolMeta(type):
    """元类用于校验子类实现"""
    def __new__(cls, name, bases, attrs):
        # 强制要求实现类方法异步生成器 call
        call_method = attrs.get('call', None)
        
        # 检查是否存在call方法
        if not call_method:
            raise TypeError(f"工具类 {name} 必须实现类方法 'call'")
            
        # 验证是否为类方法且是异步生成器
        is_valid = (
            isinstance(call_method, classmethod) and 
            inspect.isasyncgenfunction(call_method.__func__)
        )
        
        if not is_valid:
            raise TypeError(
                f"工具类 {name} 的 call 方法必须同时满足：\n"
                "1. 使用 @classmethod 装饰器\n"
                "2. 定义为 async generator 形式（包含 yield 语句）"
            )
            
        return super().__new__(cls, name, bases, attrs)

class BaseTool(metaclass=BaseToolMeta):
    """工具基类"""
    name: str = None
    description: str = None
    args_schema: BaseModel = None
    
    def __init_subclass__(cls, **kwargs):
        # 自动生成参数模型
        if cls.args_schema is None:
            cls.args_schema = create_model(
                f"{cls.name}Args",
                **cls.get_parameters()
            )
    
    @classmethod
    def get_parameters(cls) -> Dict[str, Any]:
        """获取参数结构（子类可覆盖）"""
        return {}
    
    @classmethod
    def to_openai_tool(cls) -> dict:
        """生成OpenAI工具描述"""
        if cls.name is None or cls.description is None:
            raise ValueError("Tool name and description must be set")
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": cls.description,
                "parameters": cls.args_schema.schema()
            }
        }
    
    @classmethod
    async def call(self, **kwargs) -> AsyncGenerator[ToolCallMessage, None]:
        """
        工具调用入口（必须实现为异步生成器）
        最后应返回最终结果字符串
        """
        yield NotImplementedError("Tool call method not implemented")
