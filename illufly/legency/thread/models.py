from pydantic import BaseModel, Field
from datetime import datetime
from typing import Union, Tuple, Dict, Any, List

import uuid

from ..mq.models import StreamingBlock, BlockType
from ..mq.utils import serialize

@serialize
class Thread(BaseModel):
    """连续对话跟踪"""
    @classmethod
    def get_user_prefix(cls, user_id: str):
        return f"thread-{user_id}"

    @classmethod
    def get_key(cls, user_id: str, thread_id: str):
        return f"{cls.get_user_prefix(user_id)}-{thread_id}"

    user_id: str = Field(..., description="用户ID")
    thread_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8], description="对话ID")
    title: str = Field(default="", description="连续对话标题")
    created_at: float = Field(default_factory=lambda: datetime.now().timestamp(), description="对话创建时间")

@serialize
class HistoryMessage(BaseModel):
    """持久化消息块"""
    @classmethod
    def get_thread_prefix(cls, user_id: str, thread_id: str):
        return f"msg-{user_id}-{thread_id}"

    @classmethod
    def get_key(cls, user_id: str, thread_id: str, request_id: str, message_id: str):
        return f"{cls.get_thread_prefix(user_id, thread_id)}-{request_id}-{message_id}"

    @classmethod
    def all_messages(cls, db: IndexedRocksDB, user_id: str, thread_id: str, limit: int = 100):
        values = [cls.model_validate(m) for m in db.values(prefix=cls.get_thread_prefix(user_id, thread_id), limit=limit)]
        return sorted(values, key=lambda x: x.completed_at, reverse=True)

    user_id: str = Field(default="default", description="用户ID")
    thread_id: str = Field(default="default", description="每次连续对话一个对话线程ID")
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8], description="每次请求一个唯一请求ID")
    response_id: str = Field(default="", description="每次LLM反馈一个唯一响应ID，一次请求可能反馈多个响应")
    message_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8], description="消息ID")
    message_type: str = Field(default="text", description="消息类型", pattern="^(text|mm)$")
    created_at: float = Field(default_factory=lambda: datetime.now().timestamp(), description="消息创建时间")
    service_name: str = Field(default="", description="模型名称、工具名称")
    completed_at: float = Field(default_factory=lambda: datetime.now().timestamp(), description="消息完成时间")
    role: str = Field(default="user", description="消息角色", pattern="^(user|assistant|system|tool)$")
    text: str = Field(default="", description="消息内容")
    images: List[str] = Field(default=[], description="图片列表")
    audios: List[str] = Field(default=[], description="音频列表")
    videos: List[str] = Field(default=[], description="视频列表")
    tool_calls: List[Any] = Field(default=[], description="工具调用列表")
    tool_call_id: str = Field(default="", description="工具ID")
    favorite_id: Union[str, None] = Field(default=None, description="收藏ID")

    @property
    def created_with_thread(self) -> str:
        return f'{self.user_id}-{self.thread_id}-{self.created_at}'

    def to_message(self) -> Dict[str, Any]:
        # 工具调用结果
        resp = {}
        if self.tool_calls:
            resp = {
                "role": self.role,
                "tool_calls": self.tool_calls,
                "content": self.text
            }
        # 文本消息
        elif self.message_type == "text":
            resp = {
                "role": self.role,
                "content": self.text
            }
        # 图片消息
        elif self.message_type == "mm":
            text = {
                "type": "text",
                "text": self.text
            } if self.text else {}
            images = [
                {
                    "type": "image",
                    "image_url": image
                }
                for image in self.images
            ]
            audios = [
                {
                    "type": "audio",
                    "audio_url": audio
                }
                for audio in self.audios
            ]
            videos = [
                {
                    "type": "video",
                    "video_url": video
                }
                for video in self.videos
            ]
            resp = {
                "role": self.role,
                "content": [*text, *images, *audios, *videos]
            }

        # 工具调用消息，补充 tool_call_id
        if self.role == "tool" and self.tool_call_id:
            resp.update({
                "tool_call_id": self.tool_call_id,
            })
        
        return resp

@serialize
class QuestionBlock(HistoryMessage):
    """查询块"""
    block_type: BlockType = BlockType.QUESTION

@serialize
class AnswerBlock(HistoryMessage):
    """回答块"""
    block_type: BlockType = BlockType.ANSWER

@serialize
class ToolBlock(HistoryMessage):
    """工具块"""
    block_type: BlockType = BlockType.TOOL
