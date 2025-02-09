import pytest
import logging

from unittest.mock import MagicMock
from datetime import datetime, timedelta, timezone

from illufly.api.auth.tokens import TokensManager, TokenClaims, TokenType
from illufly.rocksdb import IndexedRocksDB

logger = logging.getLogger(__name__)

# Mock 数据
USER_ID = "user_1"
DEVICE_ID = "device_1"
USERNAME = "alice"
ROLES = ["admin"]

@pytest.fixture
def mock_db():
    """模拟 IndexedRocksDB 实例"""
    db = MagicMock(spec=IndexedRocksDB)
    return db

@pytest.fixture
def tokens_manager(mock_db):
    """创建 TokensManager 实例"""
    manager = TokensManager(db=mock_db)
    return manager

@pytest.fixture
def valid_refresh_token(tokens_manager):
    """生成有效的刷新令牌"""
    claims = tokens_manager.update_refresh_token(
        user_id=USER_ID,
        username=USERNAME,
        roles=ROLES,
        device_id=DEVICE_ID
    )
    return claims.jwt_encode()

@pytest.fixture
def valid_access_token(tokens_manager):
    """生成有效的访问令牌"""
    # 创建有效访问令牌
    claims = tokens_manager._update_access_token(
        user_id=USER_ID,
        username=USERNAME,
        roles=ROLES,
        device_id=DEVICE_ID
    )
    logger.info(f"生成有效的访问令牌: {claims}")
    access_token = claims.jwt_encode()
    return access_token

@pytest.fixture
def expired_access_token(tokens_manager, valid_refresh_token):
    """生成过期的访问令牌"""
    result = tokens_manager.refresh_access_token(
        user_id=USER_ID,
        username=USERNAME,
        roles=ROLES,
        device_id=DEVICE_ID
    )
    claims = result.data
    claims.exp = datetime.now(tz=timezone.utc) - timedelta(seconds=100)
    return claims.jwt_encode()

# 测试用例
class TestTokensManager:
    """测试令牌管理器

    原则是：
    - 访问令牌有效即可通过验证
    - 访问令牌过期时，如果刷新令牌有效，则自动刷新访问令牌
    - 访问令牌无效时，不予刷新，必须重新登录获取
    - 刷新令牌过期或者无效时，不予刷新，必须重新登录获取

    测试用例包括：
    | 刷新令牌 | 访问令牌 | 验证结果 |
    | 无效 | 有效 | 通过 |
    | 有效 | 有效 | 通过 |
    | 有效 | 过期 | 刷新 |
    | 有效 | 无效 | 失败 |
    | 无效 | 过期 | 失败 |
    | 过期 | 过期 | 失败 |

    其他用例：
    - 撤回刷新令牌
    - 撤回访问令牌
    """

    def update_refresh_token_to_expired(self, tokens_manager):
        """生成过期的刷新令牌"""
        claims = TokenClaims.create_refresh_token(USER_ID, USERNAME, ROLES, DEVICE_ID)
        claims.exp = datetime.now(tz=timezone.utc) - timedelta(seconds=100)
        # 保存刷新令牌到数据库
        token_key = TokenClaims.get_refresh_token_key(USER_ID, DEVICE_ID)
        tokens_manager._cache.put(token_key, claims)

    def update_refresh_token_to_invalid(self, tokens_manager):
        """生成无效的刷新令牌"""
        token_key = TokenClaims.get_refresh_token_key(USER_ID, DEVICE_ID)
        tokens_manager._cache.put(token_key, {"token": "invalid_refresh_token"})
        logger.info(f"更新后的刷新令牌: {tokens_manager._cache.get(token_key)}")

    def test_access_token_ok(self, tokens_manager, valid_refresh_token, valid_access_token):
        """测试有效的访问令牌鉴权
        | 刷新令牌 | 访问令牌 | 验证结果 |
        | 有效    | 有效     | 通过 |
        """
        # 验证访问令牌
        result = tokens_manager.verify_access_token(valid_access_token)
        assert result.is_ok()
        assert result.data.user_id == USER_ID
        assert result.data.username == USERNAME
        assert result.data.roles == ROLES
        assert result.data.device_id == DEVICE_ID

    def test_access_token_ok_but_refresh_token_invalid(self, tokens_manager, valid_refresh_token, valid_access_token):
        """测试有效的访问令牌鉴权，但刷新令牌无效
        | 刷新令牌 | 访问令牌 | 验证结果 |
        | 无效    | 有效     | 通过 |
        """
        # 第一次验证访问令牌
        result = tokens_manager.verify_access_token(valid_access_token)
        assert result.is_ok()

        # 验证访问令牌
        self.update_refresh_token_to_invalid(tokens_manager)

        # 第二次验证访问令牌
        result = tokens_manager.verify_access_token(valid_access_token)
        assert result.is_ok()

    def test_refresh_token_expired(self, tokens_manager, valid_refresh_token, expired_access_token):
        """测试过期的访问令牌，但因为刷新令牌有效，应当自动重新颁发可用的访问令牌
        | 刷新令牌 | 访问令牌 | 验证结果 |
        | 有效    | 过期     | 刷新 |
        """
        # 验证访问令牌
        result = tokens_manager.verify_access_token(expired_access_token)
        assert result.is_ok()
        assert result.data.user_id == USER_ID
        assert result.data.username == USERNAME
        assert result.data.roles == ROLES
        assert result.data.device_id == DEVICE_ID

    def test_access_token_invalid(self, tokens_manager, valid_refresh_token):
        """无效的访问令牌，不予刷新，必须重新登录获取
        | 刷新令牌 | 访问令牌 | 验证结果 |
        | 有效    | 无效     | 失败 |
        """
        # 验证访问令牌
        result = tokens_manager.verify_access_token("invalid_access_token")
        assert result.is_fail()

    def test_refresh_token_invalid(self, tokens_manager, expired_access_token):
        """无效的刷新令牌，不予刷新，必须重新登录获取
        | 刷新令牌 | 访问令牌 | 验证结果 |
        | 无效    | 过期     | 失败 |
        """
        # 验证访问令牌
        self.update_refresh_token_to_invalid(tokens_manager)
        # 验证访问令牌
        result = tokens_manager.verify_access_token(expired_access_token)
        assert result.is_fail()

    def test_refresh_token_expired(self, tokens_manager, expired_access_token):
        """过期的刷新令牌，不予刷新，必须重新登录获取
        | 刷新令牌 | 访问令牌 | 验证结果 |
        | 过期    | 过期     | 失败 |
        """
        # 验证访问令牌
        self.update_refresh_token_to_expired(tokens_manager)
        # 验证访问令牌
        result = tokens_manager.verify_access_token(expired_access_token)
        assert result.is_fail()

    def test_revoke_refresh_token(self, tokens_manager, mock_db):
        """测试撤销刷新令牌"""
        # 创建刷新令牌
        tokens_manager.update_refresh_token(
            user_id=USER_ID,
            username=USERNAME,
            roles=ROLES,
            device_id=DEVICE_ID
        )

        # 撤销刷新令牌
        tokens_manager.revoke_refresh_token(USER_ID, DEVICE_ID)

        # 验证结果
        refresh_token_key = TokenClaims.get_refresh_token_key(USER_ID, DEVICE_ID)
        token = tokens_manager._cache.get(refresh_token_key)
        assert token.exp < datetime.now().timestamp()

    def test_revoke_access_token(self, tokens_manager):
        """测试撤销访问令牌"""
        # 模拟内存中的访问令牌
        tokens_manager._access_tokens[USER_ID] = {DEVICE_ID: "mock_access_token"}

        # 撤销访问令牌
        tokens_manager.revoke_access_token(USER_ID, DEVICE_ID)

        # 验证结果
        assert DEVICE_ID not in tokens_manager._access_tokens[USER_ID] 