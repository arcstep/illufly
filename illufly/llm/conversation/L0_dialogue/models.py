from datetime import datetime
from typing import Dict, List, Union, Any
from pydantic import BaseModel, Field

class Message(BaseModel):
    """原始消息

    用于格式化，在内存中交换。
    """
    thread_id: str = Field(..., description="对话ID")
    request_id: str = Field(..., description="调用ID")
    role: str = Field(
        ..., 
        description="消息角色：user/assistant/system/tool",
        pattern="^(user|assistant|system|tool)$"
    )
    content: Union[str, Dict[str, Any]] = Field(..., description="消息内容")
    timestamp: datetime = Field(default_factory=datetime.now)

class Dialogue(BaseModel):
    """L0: 单次对话

    持久化保存。
    每次对话中，都通过 messages 向AI发送了完整的上下文信息；
    但用户看到的UI中，一般只包含 input_text 和 output_text。

    通常情况下，我们都需要对本轮对话做摘要处理，以便于后续提取事实和概念。
    """
    thread_id: str = Field(..., description="对话ID")
    input_text: str = Field(..., description="用户输入消息")
    input_images: List[str] = Field(..., description="用户输入图片")
    input_files: List[str] = Field(..., description="用户输入文件")
    output_text: str = Field(..., description="AI输出消息")
    messages: List[Message] = Field(..., description="符合LLM标准的用户与AI的问答消息列表，包括系统提示语、用户输入、AI输出等")
    summary: str = Field(..., description="本轮对话摘要")
    request_time: datetime = Field(default_factory=datetime.now)
    response_time: datetime = Field(default_factory=datetime.now)
    used_time: float = Field(..., description="本轮对话耗时")
    usage: Dict[str, float] = Field(..., description="本轮对话的token使用情况")

