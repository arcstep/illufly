import secrets
import logging
import uuid

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
    return f"sk-{uuid.uuid4().hex}"

class ApiKey(BaseModel):
    """用于服务端的OpenAI兼容的APIKEY管理"""

    @classmethod
    def get_prefix(cls, user_id: str = None, imitator: str = None) -> str:
        """获取 rocksdb key 的 前缀"""
        user_id = user_id or "default"
        imitator = imitator or "OPENAI"
        return f"ak:{user_id}:{imitator}"

    @classmethod
    def get_db_key(cls, api_key: str, user_id: str = None, imitator: str = None) -> str:
        """获取 rocksdb key"""
        user_id = user_id or "default"
        imitator = imitator or "OPENAI"
        return f"{cls.get_prefix(user_id, imitator)}:{api_key}"

    api_key: str = Field(
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
        self._db.register_index(__API_KEY_MODEL_NAME__, ApiKey, "api_key")

    def create_api_key(self, user_id: str, imitator: str, description: str = None) -> Result[ApiKey]:
        """创建APIKEY"""
        ak = ApiKey(user_id=user_id, imitator=imitator, api_key=generate_apikey(), description=description)
        db_key = ApiKey.get_db_key(ak.api_key, user_id, imitator)
        self._db.update_with_indexes(__API_KEY_MODEL_NAME__, db_key, ak)
        return Result.ok(data=ak.model_dump())
    
    def list_api_keys(self, user_id: str, base_url: str = None) -> Result[List[ApiKey]]:
        """列出APIKEY"""
        base_url = base_url or "/api"
        keys = self._db.values(prefix=ApiKey.get_prefix(user_id))
        self._logger.debug(f"keys: {keys}")
        return Result.ok(
            data=[
                {
                    **ak.model_dump(),
                    "is_expired": ak.is_expired,
                    "base_url": f"{base_url}/imitator/{ak.imitator.lower()}"
                }
                for ak
                in keys
                if getattr(ak, "api_key", None) and getattr(ak, "imitator", None)
            ])

    def verify_api_key(self, user_id: str, api_key: str) -> Result[ApiKey]:
        """验证APIKEY"""
        keys = self._db.values_with_index(__API_KEY_MODEL_NAME__, "api_key", api_key)
        if len(keys) == 0:
            return Result.fail(error="API密钥不存在")
        ak = keys[0]
        if ak.is_expired:
            return Result.fail(error="API密钥已过期")
        if ak.user_id != user_id:
            return Result.fail(error="API密钥不属于当前用户")

        return Result.ok(data=ak.model_dump())

    def revoke_api_key(self, user_id: str, api_key: str) -> Result[None]:
        """撤销APIKEY"""
        keys = self._db.values_with_index(__API_KEY_MODEL_NAME__, "api_key", api_key)
        if len(keys) == 0:
            return Result.fail(error="API密钥不存在")
        ak = keys[0]
        if ak.is_expired:
            return Result.fail(error="API密钥已过期")
        if ak.user_id != user_id:
            return Result.fail(error="API密钥不属于当前用户")

        ak.expires_at = ak.created_at
        self._db.update_with_indexes(__API_KEY_MODEL_NAME__, ApiKey.get_db_key(ak.api_key, user_id), ak)
        return Result.ok()
