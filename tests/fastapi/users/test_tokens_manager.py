from datetime import datetime, timedelta
import pytest
from illufly.fastapi.users import TokensManager, TokenClaims

class TestTokensManagerInit:
    """测试TokensManager的初始化功能"""
    
    def test_init_with_default_settings(self, tokens_manager, temp_dir):
        """测试使用默认配置初始化
        验证点:
        - 验证默认存储是否正确创建
        - 验证必要的环境变量是否被正确加载
        - 验证密码上下文是否正确配置
        """
        # 1. 验证默认存储是否正确创建
        assert tokens_manager._refresh_tokens is not None
        assert tokens_manager._refresh_tokens._data_dir == temp_dir
        assert tokens_manager._refresh_tokens._filename == "tokens.json"
        
        # 2. 验证环境变量是否被正确加载
        assert tokens_manager.secret_key is not None
        assert tokens_manager.algorithm == "HS256"
        assert tokens_manager.hash_method == "pbkdf2_sha256"
        assert tokens_manager.access_token_expire_minutes == 15
        assert tokens_manager.refresh_token_expire_days == 30
        
        # 3. 验证密码上下文是否正确配置
        assert "bcrypt" in tokens_manager.pwd_context.schemes()
        assert "argon2" in tokens_manager.pwd_context.schemes()
        assert "pbkdf2_sha256" in tokens_manager.pwd_context.schemes()
        
        # 4. 验证访问令牌存储初始化
        assert isinstance(tokens_manager._access_tokens, dict)
        assert len(tokens_manager._access_tokens) == 0
        
        # 5. 验证依赖管理器初始化
        assert tokens_manager.dependencies is not None
        assert hasattr(tokens_manager.dependencies, "get_current_user")
        assert hasattr(tokens_manager.dependencies, "require_roles")


class TestTokenCreation:
    """测试令牌创建相关功能"""
    
    def test_create_access_token(self, tokens_manager, test_user):
        """测试创建访问令牌
        验证点:
        - 验证令牌格式是否正确
        - 验证令牌声明是否完整
        - 验证过期时间是否正确设置
        - 验证令牌是否被正确存储
        """
        # 创建访问令牌
        data = {
            k: v for k, v in test_user.to_dict().items() if k in ["user_id", "username", "device_id", "device_name", "roles"]
        }
        result = tokens_manager.create_access_token(data=data)
        print(">>> result: ", result)
        assert result["success"] is True
        access_token = result["token"]

        # 验证令牌格式是否正确
        assert isinstance(access_token, str)
        assert access_token.count('.') == 2  # JWT 令牌应包含两个点

        # 解码令牌以验证声明
        verified = tokens_manager.verify_jwt(access_token, token_type="access")
        assert verified["success"] is True
        payload = verified["payload"]
        assert payload["user_id"] == test_user.user_id
        assert payload["exp"] is not None
        assert payload["iat"] is not None
        assert payload["token_type"] == "access"

        # 验证过期时间是否正确设置
        expire_time = datetime.utcfromtimestamp(payload["exp"])
        expected_expire_time = datetime.utcnow() + timedelta(minutes=tokens_manager.access_token_expire_minutes)
        assert abs((expire_time - expected_expire_time).total_seconds()) < 60  # 允许一分钟的误差

        # 验证令牌是否被正确存储
        assert tokens_manager._access_tokens.get(test_user.user_id, None) is not None

    def test_create_refresh_token(self, tokens_manager, test_user):
        """测试创建刷新令牌
        验证点:
        - 验证令牌格式是否正确
        - 验证令牌声明是否完整
        - 验证过期时间是否正确设置
        - 验证令牌是否被正确存储到持久化存储中
        """
        # 创建刷新令牌
        data = {
            k: v for k, v in test_user.to_dict().items() if k in ["user_id", "username", "device_id", "device_name", "roles"]
        }
        result = tokens_manager.create_refresh_token(data=data)
        print(">>> result: ", result)
        assert result["success"] is True
        refresh_token = result["token"]

        # 验证令牌格式是否正确
        assert isinstance(refresh_token, str)
        assert refresh_token.count('.') == 2  # JWT 令牌应包含两个点

        # 解码令牌以验证声明
        verified = tokens_manager.verify_jwt(refresh_token, token_type="refresh")
        assert verified["success"] is True
        payload = verified["payload"]
        assert payload["user_id"] == test_user.user_id
        assert payload["exp"] is not None
        assert payload["iat"] is not None
        assert payload["token_type"] == "refresh"

        # 验证令牌是否被正确存储
        assert tokens_manager._refresh_tokens.get(test_user.user_id) is not None

class TestTokenVerification:
    """测试令牌验证相关功能"""
    
    def test_verify_valid_access_token(self, tokens_manager, test_user):
        """测试验证有效的访问令牌
        验证点:
        - 验证正确令牌的验证结果
        - 验证返回的payload内容
        """
        # 准备测试数据
        test_data = {
            "user_id": test_user.user_id,
            "username": test_user.username,
            "roles": test_user.roles,
            "device_id": test_user.device_id,
            "device_name": test_user.device_name
        }
        
        # 创建访问令牌
        token_result = tokens_manager.create_access_token(test_data)
        assert token_result["success"]
        access_token = token_result["token"]
        
        # 验证令牌
        verify_result = tokens_manager.verify_jwt(
            access_token,
            verify_exp=True,
            token_type="access"
        )
        
        # 验证结果
        assert verify_result["success"]
        payload = verify_result["payload"]
        assert payload["user_id"] == test_user.user_id
        assert payload["username"] == test_user.username
        assert payload["roles"] == [role.value for role in test_user.roles]
        assert payload["device_id"] == test_user.device_id
        assert payload["device_name"] == test_user.device_name
        assert "exp" in payload
        assert "iat" in payload
        assert payload["token_type"] == "access"


class TestTokenRefresh:
    """测试令牌刷新相关功能"""
    
    def test_refresh_with_valid_token(self, tokens_manager, test_user):
        """测试使用有效的刷新令牌
        验证点:
        - 验证新访问令牌的创建
        - 验证新令牌的有效性
        - 验证用户信息的保持
        """

        # 准备测试数据
        test_data = {
            "user_id": test_user.user_id,
            "username": test_user.username,
            "roles": test_user.roles,
            "device_id": test_user.device_id,
            "device_name": test_user.device_name
        }
        
        # 创建刷新令牌
        refresh_result = tokens_manager.create_refresh_token(test_data)
        assert refresh_result["success"]
        refresh_token = refresh_result["token"]
        
        # 使用刷新令牌获取新的访问令牌
        refresh_access_result = tokens_manager.refresh_access_token(
            refresh_token=refresh_token,
            user_id=test_user.user_id
        )
        
        # 验证刷新结果
        assert refresh_access_result["success"]
        assert "token" in refresh_access_result
        
        # 验证新令牌的有效性
        new_token = refresh_access_result["token"]
        verify_result = tokens_manager.verify_jwt(
            new_token,
            verify_exp=True,
            token_type="access"
        )
        
        # 验证新令牌的payload
        assert verify_result["success"]
        payload = verify_result["payload"]
        assert payload["user_id"] == test_user.user_id
        assert payload["username"] == test_user.username
        assert set(payload["roles"]) == {role.value for role in test_user.roles}
        assert payload["device_id"] == test_user.device_id
        assert payload["device_name"] == test_user.device_name
        assert payload["token_type"] == "access"

class TestTokenRevocation:
    """测试令牌撤销相关功能"""
    
    def test_revoke_device_tokens(self, tokens_manager, test_user):
        """测试撤销特定设备的令牌
        验证点:
        - 验证设备的访问令牌是否被撤销
        - 验证设备的刷新令牌是否被撤销
        - 验证其他设备的令牌是否保持不变
        """
        # 准备测试数据
        test_data = {
            "user_id": test_user.user_id,
            "username": test_user.username,
            "roles": [role.value for role in test_user.roles],
            "device_id": test_user.device_id,
            "device_name": test_user.device_name
        }
        
        # 创建另一个设备的令牌
        other_device_data = {
            **test_data,
            "device_id": "other_device",
            "device_name": "Other Device"
        }
        
        # 创建两个设备的令牌
        device1_access = tokens_manager.create_access_token(test_data)
        device1_refresh = tokens_manager.create_refresh_token(test_data)
        device2_access = tokens_manager.create_access_token(other_device_data)
        device2_refresh = tokens_manager.create_refresh_token(other_device_data)
        
        # 验证令牌创建成功且存储在管理器中
        assert device1_access["success"] and device1_refresh["success"]
        assert device2_access["success"] and device2_refresh["success"]
        assert test_user.user_id in tokens_manager._access_tokens
        assert tokens_manager._refresh_tokens.get(test_user.user_id) is not None
        
        # 撤销第一个设备的令牌
        revoke_result = tokens_manager.revoke_device_tokens(
            test_user.user_id,
            test_user.device_id
        )
        assert revoke_result["success"]
        
        # 验证第一个设备的令牌已被撤销
        device1_tokens = tokens_manager._access_tokens.get(test_user.user_id, {})
        assert test_user.device_id not in device1_tokens
        device1_refresh_tokens = tokens_manager._refresh_tokens.get(test_user.user_id)
        assert test_user.device_id not in device1_refresh_tokens
        
        # 验证第二个设备的令牌仍然存在
        assert "other_device" in tokens_manager._access_tokens.get(test_user.user_id, {})
        assert "other_device" in tokens_manager._refresh_tokens.get(test_user.user_id)

    def test_revoke_all_user_tokens(self, tokens_manager, test_user):
        """测试撤销用户的所有令牌
        验证点:
        - 验证所有设备的令牌是否被撤销
        - 验证存储状态的更新
        """

        # 准备多个设备的测试数据
        devices = [
            {"device_id": "device1", "device_name": "Device 1"},
            {"device_id": "device2", "device_name": "Device 2"},
            {"device_id": "device3", "device_name": "Device 3"}
        ]
        
        # 为每个设备创建令牌
        for device in devices:
            test_data = {
                "user_id": test_user.user_id,
                "username": test_user.username,
                "roles": [role.value for role in test_user.roles],
                **device
            }
            access_result = tokens_manager.create_access_token(test_data)
            refresh_result = tokens_manager.create_refresh_token(test_data)
            assert access_result["success"] and refresh_result["success"]
        
        # 验证令牌已存储
        assert test_user.user_id in tokens_manager._access_tokens
        assert len(tokens_manager._access_tokens[test_user.user_id]) == 3
        assert len(tokens_manager._refresh_tokens.get(test_user.user_id)) == 3
        
        # 撤销所有令牌
        revoke_result = tokens_manager.revoke_all_user_tokens(test_user.user_id)
        assert revoke_result["success"]
        
        # 验证所有令牌已被撤销
        assert len(tokens_manager._access_tokens.get(test_user.user_id, {})) == 0
        all_devices = tokens_manager.list_user_devices(test_user.user_id)
        assert all_devices["success"] is True
        assert len(all_devices["devices"]) == 0

    def test_revoke_access_tokens_only(self, tokens_manager, test_user):
        """测试仅撤销用户所有设备上的访问令牌
        验证点:
        - 验证访问令牌的撤销
        - 验证刷新令牌的保留
        """

        # 准备测试数据
        test_data = {
            "user_id": test_user.user_id,
            "username": test_user.username,
            "roles": [role.value for role in test_user.roles],
            "device_id": test_user.device_id,
            "device_name": test_user.device_name
        }
        
        # 创建令牌
        access_result = tokens_manager.create_access_token(test_data)
        refresh_result = tokens_manager.create_refresh_token(test_data)
        assert access_result["success"] and refresh_result["success"]
        
        # 验证令牌已存储
        assert test_user.user_id in tokens_manager._access_tokens
        assert test_user.device_id in tokens_manager._access_tokens[test_user.user_id]
        assert tokens_manager._refresh_tokens.get(test_user.user_id) is not None
        assert test_user.device_id in tokens_manager._refresh_tokens.get(test_user.user_id)
        
        # 仅撤销访问令牌
        revoke_result = tokens_manager.revoke_user_access_tokens(
            test_user.user_id
        )
        assert revoke_result["success"]
        
        # 验证访问令牌已被撤销，但刷新令牌仍然存在
        assert test_user.device_id not in tokens_manager._access_tokens.get(test_user.user_id, {})
        assert tokens_manager._refresh_tokens.get(test_user.user_id) is not None
        assert test_user.device_id in tokens_manager._refresh_tokens.get(test_user.user_id)

    def test_verify_revoked_tokens(self, tokens_manager, test_user):
        """测试验证已撤销的令牌
        验证点:
        - 验证撤销后的访问令牌验证
        - 验证撤销后的刷新令牌验证
        """
        # 准备测试数据
        test_data = {
            "user_id": test_user.user_id,
            "username": test_user.username,
            "roles": test_user.roles,
            "device_id": test_user.device_id,
            "device_name": test_user.device_name
        }
        
        # 创建令牌
        access_result = tokens_manager.create_access_token(test_data)
        refresh_result = tokens_manager.create_refresh_token(test_data)
        assert access_result["success"] and refresh_result["success"]
        
        access_token = access_result["token"]
        refresh_token = refresh_result["token"]
        
        # 撤销令牌
        revoke_result = tokens_manager.revoke_device_tokens(
            test_user.user_id,
            test_data["device_id"]
        )
        assert revoke_result["success"]
        
        # 验证已撤销的访问令牌
        access_verify = tokens_manager.verify_jwt(
            access_token,
            verify_exp=True,
            token_type="access"
        )
        assert not access_verify["success"]
        assert "Token has been revoked" in access_verify["error"]
        
        # 验证已撤销的刷新令牌
        refresh_verify = tokens_manager.verify_jwt(
            refresh_token,
            verify_exp=True,
            token_type="refresh"
        )
        assert not refresh_verify["success"]
        assert "Token has been revoked" in refresh_verify["error"]

