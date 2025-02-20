from pydantic import BaseModel, Field
from datetime import datetime
from typing import List

import uuid

from ...rocksdb import IndexedRocksDB
from ..memory.models import HistoryMessage

class Favorite(BaseModel):
    """收藏"""
    @classmethod
    def get_user_prefix(cls, user_id: str):
        return f"fav-{user_id}"

    @classmethod
    def get_key(cls, user_id: str, favorite_id: str):
        return f"{cls.get_user_prefix(user_id)}-{favorite_id}"
    
    @classmethod
    def get_messages(cls, db: IndexedRocksDB, favorite_id: str):
        """获取收藏的消息"""
        return db.items_with_index(HistoryMessage.__name__, "favorite_id", favorite_id)

    user_id: str = Field(..., description="用户ID")
    favorite_id: str = Field(default_factory=lambda: str(uuid.uuid4().hex[:8]), description="收藏ID")
    title: str = Field(default="", description="收藏标题")
    tags: List[str] = Field(default=[], description="收藏标签")
    created_at: datetime = Field(default_factory=datetime.now, description="收藏创建时间")
