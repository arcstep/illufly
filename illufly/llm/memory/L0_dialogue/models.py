from datetime import datetime
from typing import Dict, List, Union, Any
from pydantic import BaseModel, Field, computed_field

class Message(BaseModel):
    """原始消息

    用于格式化，在内存中交换。
    """
    user_id: str = Field(..., description="用户ID")
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
    dialogue_id: str = Field(default=None, description="对话ID，如果为None，则自动生成")
    user_id: str = Field(..., description="用户ID")
    thread_id: str = Field(..., description="对话ID")
    input_text: str = Field(..., description="用户输入消息")
    input_images: List[str] = Field(default_factory=list, description="用户输入图片")
    input_files: List[str] = Field(default_factory=list, description="用户输入文件")
    output_text: str = Field(..., description="AI输出消息")
    messages: List[Message] = Field(..., description="符合LLM标准的用户与AI的问答消息列表，包括系统提示语、用户输入、AI输出等")
    summary: str = Field(
        default="",  # 先设置空字符串作为默认值
        description="本轮对话摘要"
    )
    request_time: datetime = Field(default_factory=datetime.now)
    response_time: datetime = Field(default_factory=datetime.now)
    used_time: float = Field(
        default=0.0,  # 先设置默认值
        description="本轮对话耗时"
    )
    usage: Dict[str, float] = Field(
        default_factory=dict, 
        description="本轮对话的token使用情况"
    )

    def model_post_init(self, __context) -> None:
        """在模型初始化后执行"""
        # 如果没有提供摘要，则生成默认摘要
        if not self.summary:
            self.summary = f"human: {self.input_text}\nai: {self.output_text}"
        
        # 如果没有提供used_time，则计算默认值
        if self.used_time == 0.0:
            self.used_time = (self.response_time - self.request_time).total_seconds()

        if not self.dialogue_id:
            self.dialogue_id = f"dialogue.{self.thread_id}.{self.request_time.timestamp()}"
