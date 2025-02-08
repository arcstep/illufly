import uuid

from ...rocksdict import IndexedRocksDB
from ..models import ApiKey, Result

__API_KEY_MODEL_NAME__ = "api_key"

class ApiKeysManager:
    def __init__(self, db: IndexedRocksDB):
        self._db = db
        self._db.register_model(__API_KEY_MODEL_NAME__, ApiKey)

    def create_api_key(self, api_key: ApiKey) -> Result[ApiKey]:
        """创建API密钥"""
        return self._db.create_model(__API_KEY_MODEL_NAME__, api_key)
