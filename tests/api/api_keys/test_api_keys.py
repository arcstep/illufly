import pytest
import asyncio

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from illufly.api.api_keys import ApiKey, ApiKeysManager
from illufly.rocksdb import IndexedRocksDB
from illufly.api.models import Result

@pytest.fixture
def mock_db():
    """创建模拟数据库"""
    db = MagicMock(spec=IndexedRocksDB)
    return db

@pytest.fixture
def api_keys_manager(mock_db):
    """创建 API 密钥管理器"""
    return ApiKeysManager(mock_db)

class TestApiKey:
    def test_generate_key(self):
        """测试生成 API 密钥"""
        key = ApiKey(user_id="test_user", imitator="QWEN").apikey
        assert key.startswith("sk-")
        assert len(key) > 10  # 确保密钥长度合理

    def test_create_api_key(self):
        """测试创建 API 密钥对象"""
        user_id = "test_user"
        api_key = ApiKey(user_id=user_id, imitator="QWEN")
        
        assert api_key.user_id == user_id
        assert api_key.apikey.startswith("sk-")
        assert isinstance(api_key.created_at, datetime)
        assert isinstance(api_key.expires_at, datetime)
        assert api_key.expires_at > api_key.created_at
        assert api_key.is_expired == False
        
    def test_api_key_with_description(self):
        """测试带描述的 API 密钥"""
        description = "Test API Key"
        api_key = ApiKey(user_id="test_user", imitator="QWEN", description=description)
        assert api_key.description == description

    def test_get_prefix(self):
        """测试获取前缀"""
        user_id = "test_user"
        prefix = ApiKey.get_prefix(user_id)
        assert prefix == f"ak:{user_id}:OPENAI"


    def test_get_db_key(self):
        """测试获取数据库键"""
        user_id = "test_user"
        key = "sk-test"
        db_key = ApiKey.get_db_key(key, user_id)
        assert db_key == f"ak:{user_id}:OPENAI:{key}"

class TestApiKeysManager:
    def test_init(self, mock_db):
        """测试初始化"""
        manager = ApiKeysManager(mock_db)
        mock_db.register_model.assert_called_once()
        mock_db.register_index.assert_called_once()

    def test_create_api_key(self, api_keys_manager, mock_db):
        """测试创建 API 密钥"""
        user_id = "test_user"
        description = "Test Key"
        imitator = "QWEN"
        
        result = api_keys_manager.create_api_key(user_id, imitator, description)
        
        assert result.is_ok()
        api_key_dict = result.data
        assert api_key_dict['user_id'] == user_id
        assert api_key_dict['description'] == description
        assert api_key_dict['apikey'].startswith(f"sk-")

        # 验证数据库调用
        mock_db.update_with_indexes.assert_called_once()

        # 验证
        mock_db.values_with_index.return_value = [ApiKey.model_validate(api_key_dict)]
        result = api_keys_manager.verify_api_key(api_key_dict['apikey'])
        assert result.is_ok()
        ak = ApiKey.model_validate(result.data)
        assert ak.is_expired == False

    def test_list_api_keys(self, api_keys_manager, mock_db):
        """测试列出 API 密钥"""
        user_id = "test_user"
        imitator = "QWEN"
        mock_keys = [
            ApiKey(user_id=user_id, imitator=imitator, description="Key 1"),
            ApiKey(user_id=user_id, imitator=imitator, description="Key 2")
        ]
        mock_db.values.return_value = mock_keys        
        result = api_keys_manager.list_api_keys(user_id, imitator)
        
        assert result.is_ok()
        assert len(result.data) == 2
        assert result.data[0]['user_id'] == user_id
        assert result.data[0]['imitator'] == imitator
        assert result.data[0]['description'] == "Key 1"
        assert result.data[1]['user_id'] == user_id
        assert result.data[1]['imitator'] == imitator
        assert result.data[1]['description'] == "Key 2"

    def test_revoke_api_key(self, api_keys_manager, mock_db):
        """测试删除 API 密钥"""
        user_id = "test_user"
        imitator = "QWEN"
        key = "sk-test"
        ak = ApiKey(user_id=user_id, imitator=imitator, apikey=key)

        mock_db.values_with_index.return_value = [ak]        
        result = api_keys_manager.verify_api_key(key)
        assert result.is_ok()
        
        mock_db.get.return_value = ak
        result = api_keys_manager.revoke_api_key(user_id, imitator, key)
        assert result.is_ok()

        ak.expires_at = ak.created_at
        mock_db.values_with_index.return_value = [ak]
        result = api_keys_manager.verify_api_key(key)
        assert result.is_fail()

    @pytest.mark.asyncio
    async def test_api_key_expiration(self):
        """测试 API 密钥过期"""
        # 创建一个即将过期的 API 密钥
        now = datetime.now(timezone.utc)
        api_key = ApiKey(
            user_id="test_user",
            imitator="QWEN",
            expires_at=now + timedelta(seconds=1)
        )
        
        # 验证未过期
        assert api_key.expires_at > now
        
        # 等待过期
        await asyncio.sleep(1.1)
        
        # 验证已过期
        assert api_key.expires_at < datetime.now(timezone.utc)

    def test_api_key_custom_expiration(self):
        """测试自定义过期时间"""
        custom_expiry = datetime.now(timezone.utc) + timedelta(days=180)
        api_key = ApiKey(
            user_id="test_user",
            imitator="QWEN",
            expires_at=custom_expiry
        )
        assert api_key.expires_at == custom_expiry 