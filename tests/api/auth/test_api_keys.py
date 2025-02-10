import pytest
import asyncio

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from illufly.api.auth.api_keys import ApiKey, ApiKeysManager
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
        key = ApiKey.generate_key()
        assert key.startswith("sk_")
        assert len(key) > 10  # 确保密钥长度合理

    def test_create_api_key(self):
        """测试创建 API 密钥对象"""
        user_id = "test_user"
        api_key = ApiKey(user_id=user_id)
        
        assert api_key.user_id == user_id
        assert api_key.key.startswith("sk_")
        assert isinstance(api_key.created_at, datetime)
        assert isinstance(api_key.expires_at, datetime)
        assert api_key.expires_at > api_key.created_at
        
    def test_api_key_with_description(self):
        """测试带描述的 API 密钥"""
        description = "Test API Key"
        api_key = ApiKey(user_id="test_user", description=description)
        assert api_key.description == description

    def test_get_prefix(self):
        """测试获取前缀"""
        user_id = "test_user"
        prefix = ApiKey.get_prefix(user_id)
        assert prefix == f"api_key:{user_id}"

    def test_get_db_key(self):
        """测试获取数据库键"""
        user_id = "test_user"
        key = "sk_test"
        db_key = ApiKey.get_db_key(user_id, key)
        assert db_key == f"api_key:{user_id}:{key}"

class TestApiKeysManager:
    def test_init(self, mock_db):
        """测试初始化"""
        manager = ApiKeysManager(mock_db)
        mock_db.register_model.assert_called_once()
        mock_db.register_indexes.assert_called_once()

    def test_create_api_key(self, api_keys_manager, mock_db):
        """测试创建 API 密钥"""
        user_id = "test_user"
        description = "Test Key"
        
        result = api_keys_manager.create_api_key(user_id, description)
        
        assert result.is_ok()
        api_key = result.data
        assert api_key.user_id == user_id
        assert api_key.description == description
        assert api_key.key.startswith("sk_")
        
        # 验证数据库调用
        mock_db.update_with_indexes.assert_called_once()

    def test_list_api_keys(self, api_keys_manager, mock_db):
        """测试列出 API 密钥"""
        user_id = "test_user"
        mock_keys = [
            ApiKey(user_id=user_id, description="Key 1"),
            ApiKey(user_id=user_id, description="Key 2")
        ]
        mock_db.values.return_value = mock_keys
        
        result = api_keys_manager.list_api_keys(user_id)
        
        assert result.is_ok()
        assert len(result.data) == 2
        assert all(isinstance(key, ApiKey) for key in result.data)
        mock_db.values.assert_called_once_with(ApiKey.get_prefix(user_id))

    def test_delete_api_key(self, api_keys_manager, mock_db):
        """测试删除 API 密钥"""
        user_id = "test_user"
        key = "sk_test"
        
        result = api_keys_manager.delete_api_key(user_id, key)
        
        assert result.is_ok()
        mock_db.delete.assert_called_once_with(ApiKey.get_db_key(user_id, key))

    @pytest.mark.asyncio
    async def test_api_key_expiration(self):
        """测试 API 密钥过期"""
        # 创建一个即将过期的 API 密钥
        now = datetime.now(timezone.utc)
        api_key = ApiKey(
            user_id="test_user",
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
            expires_at=custom_expiry
        )
        assert api_key.expires_at == custom_expiry 