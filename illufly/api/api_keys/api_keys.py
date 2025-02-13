import secrets
import logging

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
            str: 格式为 "sk-xxx" 的API密钥
        """
        # 使用 secrets 生成指定长度的随机字母数字组合
        alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
        random_str = ''.join(secrets.choice(alphabet) for _ in range(32))
        return f"sk-{random_str}"

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

    def is_expired(self) -> bool:
        """判断是否过期"""
        return self.expires_at < datetime.now(timezone.utc)

class ApiKeysManager:
    def __init__(self, db: IndexedRocksDB, logger: logging.Logger = None):
        self._db = db
        self._logger = logger or logging.getLogger(__name__)
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
        keys = self._db.values(prefix=ApiKey.get_prefix(user_id))
        return Result.ok(data=[key.model_dump() for key in keys])

    def verify_api_key(self, user_id: str, key: str) -> Result[ApiKey]:
        """验证API密钥"""
        db_key = ApiKey.get_db_key(user_id, key)
        ak = self._db.get(db_key)
        if ak is None:
            return Result.fail(error="API密钥不存在")
        if ak.is_expired():
            return Result.fail(error="API密钥已过期")
        return Result.ok(data=ak.model_dump())

    def revoke_api_key(self, user_id: str, key: str) -> Result[None]:
        """删除API密钥"""
        db_key = ApiKey.get_db_key(user_id, key)
        ak = self._db.get(db_key)
        if ak is None:
            return Result.fail(error="API密钥不存在")
        if ak.is_expired():
            return Result.fail(error="API密钥已过期")

        ak.expires_at = ak.created_at
        self._db.put(db_key, ak)
        return Result.ok()
