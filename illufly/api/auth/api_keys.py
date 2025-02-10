import uuid
import secrets
import base64

from typing import List
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field

from ...rocksdb import IndexedRocksDB
from ..models import Result

__API_KEY_MODEL_NAME__ = "api_key"

class ApiKey(BaseModel):
    """API密钥"""

    @classmethod
    def get_prefix(cls, user_id: str) -> str:
        """获取 rocksdb key 的 前缀"""
        return f"api_key:{user_id}"

    @classmethod
    def get_db_key(cls, user_id: str, key: str) -> str:
        """获取 rocksdb key"""
        return f"{cls.get_prefix(user_id)}:{key}"

    @staticmethod
    def generate_key() -> str:
        """生成API密钥
        
        Returns:
            str: 格式为 "sk_xxx" 的API密钥
        """
        # 使用 secrets 模块生成安全的随机字节
        random_bytes = secrets.token_bytes(32)
        # 转换为 base64 并移除填充字符
        key = base64.urlsafe_b64encode(random_bytes).decode('utf-8').rstrip('=')
        # 添加前缀并返回
        return f"sk_{key}"

    key: str = Field(
        default_factory=lambda: ApiKey.generate_key(), 
        description="API密钥"
    )
    user_id: str = Field(..., description="用户ID")
    description: str = Field(
        default=None,
        description="描述"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="创建时间"
    )
    expires_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(days=90), 
        description="过期时间"
    )

class ApiKeysManager:
    def __init__(self, db: IndexedRocksDB):
        self._db = db
        self._db.register_model(__API_KEY_MODEL_NAME__, ApiKey)
        self._db.register_indexes(__API_KEY_MODEL_NAME__, ApiKey, "user_id")

    def create_api_key(self, user_id: str, description: str = None) -> Result[ApiKey]:
        """创建API密钥"""
        ak = ApiKey(user_id=user_id, description=description)
        db_key = ApiKey.get_db_key(user_id, ak.key)
        self._db.update_with_indexes(__API_KEY_MODEL_NAME__, db_key, ak)
        return Result.ok(data=ak.model_dump())
    
    def list_api_keys(self, user_id: str) -> Result[List[ApiKey]]:
        """列出API密钥"""
        keys = self._db.values(ApiKey.get_prefix(user_id))
        return Result.ok(data=[key.model_dump() for key in keys])
    
    def delete_api_key(self, user_id: str, key: str) -> Result[None]:
        """删除API密钥"""
        db_key = ApiKey.get_db_key(user_id, key)
        self._db.delete(db_key)
        return Result.ok()
