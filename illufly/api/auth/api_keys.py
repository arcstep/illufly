import uuid

from pydantic import BaseModel, Field

from ...rocksdb import IndexedRocksDB
from ..models import ApiKey, Result

__API_KEY_MODEL_NAME__ = "api_key"

class ApiKey(BaseModel):
    """API密钥"""
    api_key: str = Field(..., description="API密钥")
    user_id: str = Field(..., description="用户ID")
    created_at: datetime = Field(..., description="创建时间")
    expires_at: datetime = Field(..., description="过期时间")

class ApiKeysManager:
    def __init__(self, db: IndexedRocksDB):
        self._db = db
        self._db.register_model(__API_KEY_MODEL_NAME__, ApiKey)

    def create_api_key(self, api_key: ApiKey) -> Result[ApiKey]:
        """创建API密钥"""
        return self._db.create_model(__API_KEY_MODEL_NAME__, api_key)
