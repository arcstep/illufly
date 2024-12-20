from datetime import datetime, timedelta
from freezegun import freeze_time
from illufly.fastapi.auth import TokenStorage, Token
import pytest

class TestTokenManagement:
    """令牌管理相关测试"""
    @pytest.fixture
    def frozen_time(self):
        """冻结时间"""
        return freeze_time("2024-01-01 12:00:00")
    
    def test_create_access_token(self, auth_manager):
        """测试基本的访问令牌创建功能"""
        token_data = {
            "user_id": "test123",
            "username": "testuser",
            "device_id": "test_device",
            "device_name": "Test Device"
        }
        
        # 创建访问令牌
        access_result = auth_manager.create_access_token(token_data)
        assert access_result["success"] is True, f"Failed to create access token: {access_result.get('error')}"
        access_token = access_result["token"]
        
        # 验证访问令牌
        verify_result = auth_manager.verify_jwt(access_token)
        assert verify_result["success"] is True, f"Failed to verify access token: {verify_result.get('error')}"
        payload = verify_result["payload"]
        
        # 验证令牌内容
        assert payload["user_id"] == token_data["user_id"]
        assert payload["username"] == token_data["username"]
        assert payload["device_id"] == token_data["device_id"]
        assert "exp" in payload
        assert "iat" in payload

    def test_create_refresh_token(self, auth_manager, test_user):
        """测试创建刷新令牌"""
        token_data = {
            "user_id": test_user.user_id,
            "username": test_user.username,
            "roles": test_user.roles,
            "token_type": "refresh"  # 添加令牌类型
        }
        result = auth_manager.create_refresh_token(token_data)
        print(f"Create refresh token result: {result}")  # 调试信息
        
        assert result["success"] is True, f"Failed to create refresh token: {result.get('error')}"

    def test_token_expiration(self, auth_manager, test_user):
        """测试令牌过期"""
        user = test_user
        token_data = {
            "user_id": user.user_id,
            "username": user.username,
            "roles": user.roles,
            "exp": datetime.utcnow() - timedelta(minutes=1)
        }
        
        result = auth_manager.create_access_token(token_data)
        assert result["success"] is True
        verify_result = auth_manager.is_token_valid(result["token"], "access")
        assert verify_result["success"] is False
        assert "expired" in verify_result["error"].lower()

    @freeze_time("2024-01-01 12:00:00")
    def test_invalidate_access_token(self, auth_manager):
        """测试撤销访问令牌"""
        print("\n=== 测试撤销访问令牌 ===")
        
        # 创建测试令牌
        token_data = {
            "user_id": "test123",
            "username": "testuser",
            "roles": ["user"]
        }
        
        with freeze_time("2024-01-01 12:00:00"):
            # 创建令牌
            result = auth_manager.create_access_token(token_data)
            print(f"Create token result: {result}")
            assert result["success"]
            token = result["token"]
            
            # 验证初始状态
            verify_result = auth_manager.is_token_valid(token, "access")
            print(f"Initial verify result: {verify_result}")
            assert verify_result["success"], f"Token should be valid initially: {verify_result.get('error')}"
            
            # 撤销令牌
            invalidate_result = auth_manager.invalidate_access_token(token)
            print(f"Invalidate result: {invalidate_result}")
            assert invalidate_result["success"]
            
            # 验证令牌已失效
            verify_result = auth_manager.is_token_valid(token, "access")
            print(f"Final verify result: {verify_result}")
            assert verify_result["success"] is False, "Token should be invalid after invalidation"

    def test_invalidate_refresh_token(self, auth_manager, test_user):
        """测试撤销刷新令牌"""
        # 1. 创建一个刷新令牌
        token_data = {
            "user_id": test_user.user_id,
            "username": test_user.username,
            "roles": test_user.roles,
            "token_type": "refresh",
            "device_id": "test_device",
            "device_name": "Test Device",
            "exp": int((datetime.utcnow() + timedelta(days=7)).timestamp())  # 添加过期时间
        }
        
        # 创建并存储令牌
        result = auth_manager.create_refresh_token(token_data)
        assert result["success"] is True, "Failed to create refresh token"
        refresh_token = result["token"]
        
        # 添加调试信息
        print(f"Created refresh token: {refresh_token}")
        
        # 解码令牌以获取过期时间
        decoded = auth_manager.verify_jwt(refresh_token)
        print(f"Decode result: {decoded}")  # 添加调试输出
        assert decoded["success"] is True, f"Failed to decode token: {decoded.get('error')}"
        payload = decoded["payload"]
        
        # 初始化存储
        storage = TokenStorage()
        token_obj = Token(
            token=refresh_token,
            username=test_user.username,
            user_id=test_user.user_id,
            expire=datetime.fromtimestamp(payload["exp"]),
            token_type="refresh",
            device_id="test_device",
            device_name="Test Device"
        )
        
        storage.tokens.append(token_obj)
        
        # 存储令牌
        auth_manager._storage.set(value=storage, owner_id=test_user.user_id)
        
        # 2. 验证令牌初始有效
        stored_token = auth_manager._storage.get(owner_id=test_user.user_id)
        print(f"Stored token: {stored_token}")
        
        verify_result = auth_manager.verify_jwt(refresh_token)
        print(f"JWT verify result: {verify_result}")
        
        verify_result = auth_manager.is_token_valid(refresh_token, "refresh")
        print(f"Initial verify result: {verify_result}")
        assert verify_result["success"] is True, f"Token should be valid initially: {verify_result.get('error')}"
        
        # 3. 撤销令牌
        invalidate_result = auth_manager.invalidate_refresh_token(refresh_token)
        print(f"Invalidate result: {invalidate_result}")
        assert invalidate_result["success"] is True, f"Failed to invalidate token: {invalidate_result.get('error')}"
        
        # 4. 验证令牌已失效
        verify_result = auth_manager.is_token_valid(refresh_token, "refresh")
        print(f"Final verify result: {verify_result}")
        assert verify_result["success"] is False, "Token should be invalid after invalidation"

    def test_invalidate_user_access_tokens(self, auth_manager, test_user):
        """测试撤销用户所有访问令牌"""
        # 创建多个访问令牌
        tokens = []
        for device in ["mobile", "desktop", "tablet"]:
            token_data = {
                "user_id": test_user.user_id,
                "username": test_user.username,
                "roles": test_user.roles,
                "device": device
            }
            result = auth_manager.create_access_token(token_data)
            assert result["success"] is True
            tokens.append(result["token"])
        
        # 使用 user_id 撤销令牌
        result = auth_manager.invalidate_user_access_tokens(test_user.user_id)
        assert result["success"] is True
        assert f"Removed {len(tokens)} access tokens" in result["message"]

    def test_invalidate_user_refresh_tokens(self, auth_manager, test_user):
        """测试撤销用户所有刷新令牌"""
        tokens = []
        for device in ["mobile", "desktop", "tablet"]:
            token_data = {
                "user_id": test_user.user_id,
                "username": test_user.username,
                "roles": test_user.roles,
                "device": device
            }
            result = auth_manager.create_refresh_token(token_data)
            tokens.append(result["token"])
        
        result = auth_manager.invalidate_user_refresh_tokens(test_user.user_id)
        assert result["success"] is True

    def test_invalidate_all_user_tokens(self, auth_manager, test_user):
        """测试撤销用户所有令牌"""
        access_tokens = []
        refresh_tokens = []
        storage = TokenStorage()
        
        # 1. 创建多个令牌
        for device in ["mobile", "desktop"]:
            token_data = {
                "user_id": test_user.user_id,
                "username": test_user.username,
                "roles": test_user.roles,
                "device_id": device,
                "device_name": f"{device.title()} Device"
            }
            
            # 创建访问令牌
            access_result = auth_manager.create_access_token(token_data)
            assert access_result["success"] is True
            access_tokens.append(access_result["token"])
            
            # 创建刷新令牌
            refresh_result = auth_manager.create_refresh_token(token_data)
            assert refresh_result["success"] is True
            refresh_tokens.append(refresh_result["token"])
            
            # 添加到存储中
            storage.tokens.append(Token(
                token=refresh_result["token"],
                username=test_user.username,
                user_id=test_user.user_id,
                expire=datetime.utcnow() + timedelta(days=7),
                token_type="refresh",
                device_id=device,
                device_name=f"{device.title()} Device"
            ))
        
        # 存储所有令牌
        auth_manager._storage.set(value=storage, owner_id=test_user.user_id)
        
        # 2. 撤销所有令牌
        result = auth_manager.invalidate_all_user_tokens(test_user.user_id)
        assert result["success"] is True
        tokens_count = len(refresh_tokens)
        expected_message = f"Removed {tokens_count} access tokens, {tokens_count} refresh tokens"
        assert result["message"] == expected_message

    def test_invalidate_nonexistent_tokens(self, auth_manager):
        """测试撤销不存在的令牌"""
        invalid_token = "invalid.token.string"
        
        # 测试撤销不存在的访问令牌
        result = auth_manager.invalidate_access_token(invalid_token)
        assert result["success"] is False
        assert "Invalid token" in result["error"]
        
        # 测试撤销不存在的刷新令牌
        result = auth_manager.invalidate_refresh_token(invalid_token)
        assert result["success"] is False
        assert "Invalid token" in result["error"]
