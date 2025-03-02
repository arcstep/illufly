import secrets
import logging

from typing import List
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field

from ...rocksdb import IndexedRocksDB
from ..models import Result

__API_KEY_MODEL_NAME__ = "api_key"

def generate_apikey() -> str:
    """生成API密钥
    
    Returns:
        str: 格式为 "sk-xxx" 的API密钥
    """
    # 使用 secrets 生成指定长度的随机字母数字组合
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    random_str = ''.join(secrets.choice(alphabet) for _ in range(32))
    return f"sk-{random_str}"

class ApiKey(BaseModel):
    """用于服务端的OpenAI兼容的APIKEY管理"""

    @classmethod
    def get_prefix(cls, user_id: str = None, imitator: str = None) -> str:
        """获取 rocksdb key 的 前缀"""
        user_id = user_id or "default"
        imitator = imitator or "OPENAI"
        return f"ak:{user_id}:{imitator}"

    @classmethod
    def get_db_key(cls, apikey: str, user_id: str = None, imitator: str = None) -> str:
        """获取 rocksdb key"""
        user_id = user_id or "default"
        imitator = imitator or "OPENAI"
        return f"{cls.get_prefix(user_id, imitator)}:{apikey}"

    apikey: str = Field(
        default=generate_apikey(), 
        description="OpenAI兼容的APIKEY管理"
    )
    user_id: str = Field(..., description="用户ID")
    imitator: str = Field(..., description="OpenAI兼容接口的模仿来源")
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

    @property
    def is_expired(self) -> bool:
        """判断是否过期"""
        return self.expires_at < datetime.now(timezone.utc)

class ApiKeysManager:
    def __init__(self, db: IndexedRocksDB, logger: logging.Logger = None):
        self._db = db
        self._logger = logger or logging.getLogger(__name__)
        self._db.register_model(__API_KEY_MODEL_NAME__, ApiKey)
        self._db.register_index(__API_KEY_MODEL_NAME__, ApiKey, "apikey")

    def create_api_key(self, user_id: str, imitator: str, description: str = None) -> Result[ApiKey]:
        """创建APIKEY"""
        ak = ApiKey(user_id=user_id, imitator=imitator, description=description)
        db_key = ApiKey.get_db_key(ak.apikey, user_id, imitator)
        self._db.update_with_indexes(__API_KEY_MODEL_NAME__, db_key, ak)
        return Result.ok(data=ak.model_dump())
    
    def list_api_keys(self, user_id: str) -> Result[List[ApiKey]]:
        """列出APIKEY"""
        keys = self._db.values(prefix=ApiKey.get_prefix(user_id))
        return Result.ok(data=[{**ak.model_dump(), "is_expired": ak.is_expired} for ak in keys])

    def verify_api_key(self, user_id: str, api_key: str) -> Result[ApiKey]:
        """验证APIKEY"""
        keys = self._db.values_with_index(__API_KEY_MODEL_NAME__, "apikey", api_key)
        if len(keys) == 0:
            return Result.fail(error="API密钥不存在")
        ak = keys[0]
        if ak.is_expired:
            return Result.fail(error="API密钥已过期")
        if ak.user_id != user_id:
            return Result.fail(error="API密钥不属于当前用户")

        return Result.ok(data=ak.model_dump())

    def revoke_api_key(self, user_id: str, apikey: str) -> Result[None]:
        """撤销APIKEY"""
        keys = self._db.values_with_index(__API_KEY_MODEL_NAME__, "apikey", apikey)
        if len(keys) == 0:
            return Result.fail(error="API密钥不存在")
        ak = keys[0]
        if ak.is_expired:
            return Result.fail(error="API密钥已过期")
        if ak.user_id != user_id:
            return Result.fail(error="API密钥不属于当前用户")

        ak.expires_at = ak.created_at
        self._db.update_with_indexes(__API_KEY_MODEL_NAME__, ApiKey.get_db_key(ak.apikey, user_id), ak)
        return Result.ok()
