import pytest
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional, Dict, Any
from illufly.fastapi.auth import AuthManager, Token, TokenStorage
from illufly.config import get_env
from freezegun import freeze_time
import jwt

__ACCESS_TOKEN_EXPIRE_MINUTES__ = get_env("ACCESS_TOKEN_EXPIRE_MINUTES")
__REFRESH_TOKEN_EXPIRE_DAYS__ = get_env("REFRESH_TOKEN_EXPIRE_DAYS")

@dataclass(frozen=True)
class MockUser:
    """测试用户数据模型"""
    user_id: str
    username: str
    password_hash: str
    email: str
    roles: list[str] = None
    
    def to_dict(self, include_sensitive: bool = True) -> Dict[str, Any]:
        """模拟用户数据字典化"""
        data = {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "roles": self.roles or []
        }
        if include_sensitive:
            data["password_hash"] = self.password_hash
        return data

class MockUserManager:
    """模拟用户管理器"""
    def __init__(self):
        self.users: Dict[str, MockUser] = {}
        
    def get_user_by_username(self, username: str) -> Optional[MockUser]:
        return self.users.get(username)

@pytest.fixture
def mock_user_manager():
    return MockUserManager()

@pytest.fixture
def auth_config():
    """测试用的认证配置"""
    return {
        "secret_key": "test-secret-key-for-testing-only",
        "algorithm": "HS256",
        "hash_method": "pbkdf2_sha256",
        "access_token_expire_minutes": "30",
        "refresh_token_expire_days": "7"
    }

@pytest.fixture
def auth_manager(setup_env):
    """创建测试用的认证管理器"""
    from illufly.fastapi.common import FileConfigStore
    from illufly.fastapi.auth import Token, TokenStorage
    
    # 创建临时目录
    import tempfile
    from pathlib import Path
    temp_dir = Path(tempfile.mkdtemp())
    
    # 创建令牌存储
    token_storage = FileConfigStore[TokenStorage](
        data_dir=temp_dir,
        filename="test_tokens.json",
        serializer=lambda x: x.to_dict() if x else {"tokens": []},
        deserializer=TokenStorage.from_dict
    )
    
    manager = AuthManager(storage=token_storage)
    yield manager
    
    # 清理临时目录
    import shutil
    shutil.rmtree(temp_dir)

def test_auth_manager_initialization(auth_manager, auth_config):
    """测试认证管理器初始化"""
    assert auth_manager.secret_key == auth_config["secret_key"]
    assert auth_manager.algorithm == auth_config["algorithm"]
    assert auth_manager.hash_method == auth_config["hash_method"]
    assert auth_manager.pwd_context is not None

@pytest.fixture
def test_user():
    """创建测试用户数据"""
    return {
        "user_id": "test123",
        "username": "testuser",
        "password": "TestPass123",
        "roles": ["user"]
    }

@pytest.fixture
def device_info():
    """设备信息fixture"""
    return {
        "device_id": "test_device_123",
        "device_name": "Test Device"
    }

class TestTokenManagement:
    """令牌管理相关测试"""
    
    @pytest.fixture
    def access_token(self, auth_manager, test_user, device_info):
        """创建测试用的访问令牌"""
        user = test_user
        token_data = {
            "user_id": user["user_id"],
            "username": user["username"],
            "roles": user["roles"],
            **device_info
        }
        result = auth_manager.create_access_token(token_data)
        assert result["success"] is True
        return result["token"]
    
    @pytest.fixture
    def refresh_token(self, auth_manager, test_user):
        """创建测试用的刷新令牌"""
        user = test_user
        token_data = {
            "user_id": user["user_id"],
            "username": user["username"],
            "roles": user["roles"]
        }
        result = auth_manager.create_refresh_token(token_data)
        assert result["success"] is True
        return result["token"]

    def test_create_access_token(self, auth_manager, test_user, frozen_time):
        """测试创建访问令牌"""
        token_data = {
            "user_id": test_user["user_id"],
            "username": test_user["username"],
            "roles": test_user["roles"],
            "token_type": "access"
        }
        result = auth_manager.create_access_token(token_data)
        print(f"Create access token result: {result}")
        
        assert result["success"] is True, f"Failed to create access token: {result.get('error')}"
        assert "token" in result, "Token not found in result"
        
        verify_result = auth_manager.is_token_valid(result["token"], "access")
        print(f"Verify access token result: {verify_result}")
        
        if not verify_result["success"]:
            import jwt
            try:
                decoded = jwt.decode(result["token"], options={"verify_signature": False})
                print(f"Token payload: {decoded}")
            except Exception as e:
                print(f"Failed to decode token: {e}")
            
        assert verify_result["success"] is True, f"Failed to verify token: {verify_result.get('error')}"

    def test_create_refresh_token(self, auth_manager, test_user):
        """测试创建刷新令牌"""
        token_data = {
            "user_id": test_user["user_id"],
            "username": test_user["username"],
            "roles": test_user["roles"],
            "token_type": "refresh"  # 添加令牌类型
        }
        result = auth_manager.create_refresh_token(token_data)
        print(f"Create refresh token result: {result}")  # 调试信息
        
        assert result["success"] is True, f"Failed to create refresh token: {result.get('error')}"

    def test_token_expiration(self, auth_manager, test_user):
        """测试令牌过期"""
        user = test_user
        token_data = {
            "user_id": user["user_id"],
            "username": user["username"],
            "roles": user["roles"],
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
            "user_id": test_user["user_id"],
            "username": test_user["username"],
            "roles": test_user["roles"],
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
            username=test_user["username"],
            user_id=test_user["user_id"],
            expire=datetime.fromtimestamp(payload["exp"]),
            token_type="refresh",
            device_id="test_device",
            device_name="Test Device"
        )
        
        storage.tokens.append(token_obj)
        
        # 存储令牌
        auth_manager._storage.set(value=storage, owner_id=test_user["user_id"])
        
        # 2. 验证令牌初始有效
        stored_token = auth_manager._storage.get(owner_id=test_user["user_id"])
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
                "user_id": test_user["user_id"],
                "username": test_user["username"],
                "roles": test_user["roles"],
                "device": device
            }
            result = auth_manager.create_access_token(token_data)
            assert result["success"] is True
            tokens.append(result["token"])
        
        # 使用 user_id 撤销令牌
        result = auth_manager.invalidate_user_access_tokens(test_user["user_id"])
        assert result["success"] is True
        assert f"Removed {len(tokens)} access tokens" in result["message"]

    def test_invalidate_user_refresh_tokens(self, auth_manager, test_user):
        """测试撤销用户所有刷新令牌"""
        tokens = []
        for device in ["mobile", "desktop", "tablet"]:
            token_data = {
                "user_id": test_user["user_id"],
                "username": test_user["username"],
                "roles": test_user["roles"],
                "device": device
            }
            result = auth_manager.create_refresh_token(token_data)
            tokens.append(result["token"])
        
        result = auth_manager.invalidate_user_refresh_tokens(test_user["user_id"])
        assert result["success"] is True

    def test_invalidate_all_user_tokens(self, auth_manager, test_user):
        """测试撤销用户所有令牌"""
        access_tokens = []
        refresh_tokens = []
        storage = TokenStorage()
        
        # 1. 创建多个令牌
        for device in ["mobile", "desktop"]:
            token_data = {
                "user_id": test_user["user_id"],
                "username": test_user["username"],
                "roles": test_user["roles"],
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
                username=test_user["username"],
                user_id=test_user["user_id"],
                expire=datetime.utcnow() + timedelta(days=7),
                token_type="refresh",
                device_id=device,
                device_name=f"{device.title()} Device"
            ))
        
        # 存储所有令牌
        auth_manager._storage.set(value=storage, owner_id=test_user["user_id"])
        
        # 2. 撤销所有令牌
        result = auth_manager.invalidate_all_user_tokens(test_user["user_id"])
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

class TestAuthentication:
    """认证相关测试"""
    
    def test_login_success(self, auth_manager, test_user, device_info, frozen_time):
        """测试登录成功"""
        # 1. 准备用户数据
        password = test_user["password"]
        hash_result = auth_manager.hash_password(password)
        assert hash_result["success"] is True, "Failed to hash password"
        
        user_dict = {
            "user_id": test_user["user_id"],
            "username": test_user["username"],
            "password_hash": hash_result["hash"],
            "roles": test_user["roles"]
        }
        
        # 2. 尝试登录
        result = auth_manager.login(
            user_dict=user_dict,
            password=password,
            password_hash=hash_result["hash"],
            device_id=device_info["device_id"],
            device_name=device_info["device_name"]
        )
        print(f"Login result: {result}")
        
        # 3. 验证登录结果
        assert result["success"] is True, f"Login failed: {result.get('error')}"
        assert "access_token" in result, "Access token not found in result"
        assert "refresh_token" in result, "Refresh token not found in result"
        assert result["token_type"] == "bearer", "Incorrect token type"

    def test_login_wrong_password(self, auth_manager, test_user, device_info):
        """测试密码错误"""
        # 1. 准备用户数据
        hash_result = auth_manager.hash_password("correct_password")
        assert hash_result["success"] is True
        
        user_dict = {
            "user_id": test_user["user_id"],
            "username": test_user["username"],
            "roles": test_user["roles"]
        }
        
        # 2. 尝试使用错误密码登录
        result = auth_manager.login(
            user_dict=user_dict,
            password="wrong_password",  # 使用错误的密码
            password_hash=hash_result["hash"],  # 正确的密码哈希
            device_id=device_info["device_id"],
            device_name=device_info["device_name"]
        )
        
        # 3. 验证结果
        assert result["success"] is False
        assert "error" in result
        assert "Password Not Correct" in result["error"]

    def test_login_missing_required_fields(self, auth_manager):
        """测试缺少必要字段的登录请求"""
        print("\n=== 测试缺少必要字段的登录 ===")
        
        # 1. 准备测试数据
        incomplete_user = {
            "username": "testuser"  # 故意缺少 user_id
        }
        print(f">>> 测试数据: {incomplete_user}")
        
        # 2. 验证测试数据确实缺少必要字段
        assert "user_id" not in incomplete_user, "测试数据应该缺少 user_id 字段"
        
        # 3. 执行登录
        result = auth_manager.login(
            user_dict=incomplete_user,
            password="TestPass123",
            password_hash="hashed_password",
            device_id="test_device",
            device_name="Test Device"
        )
        print(f">>> 登录结果: {result}")
        
        # 4. 详细验证结果
        assert isinstance(result, dict), f"返回值应该是字典，但得到了 {type(result)}"
        assert "success" in result, "返回值应该包含 success 字段"
        assert "error" in result, "返回值应该包含 error 字段"
        assert result["success"] is False, "缺少必要字段时登录应该失败"
        assert isinstance(result["error"], str), "错误信息应该是字符串"
        assert "Missing required field" in result["error"], f"错误信息应该提示缺少字段，但得到了: {result['error']}"

class TestValidation:
    """验证相关测试"""
    
    @pytest.mark.parametrize("password,is_valid", [
        ("Short1", False),  # 太短
        ("nouppercase1", False),  # 没有大写字母
        ("NOLOWERCASE1", False),  # 没有小写字母
        ("NoNumbers", False),  # 没有数字
        ("ValidPass123", True),  # 有效密码
    ])
    def test_password_validation(self, auth_manager, password, is_valid):
        """测试密码验证"""
        result = auth_manager.validate_password(password)
        assert result["success"] is is_valid

    @pytest.mark.parametrize("email,is_valid", [
        ("invalid", False),
        ("no@domain", False),
        ("valid@example.com", True),
        ("user.name+tag@example.co.uk", True),
    ])
    def test_email_validation(self, auth_manager, email, is_valid):
        """测试邮箱验证"""
        result = auth_manager.validate_email(email)
        assert result["success"] is is_valid

    @pytest.mark.parametrize("username,is_valid", [
        ("ab", False),  # 太短
        ("123user", False),  # 不能以数字开头
        ("valid_user123", True),
        ("very_long_username_that_exceeds_32_chars", False),
    ])
    def test_username_validation(self, auth_manager, username, is_valid):
        """测试用户���验证"""
        result = auth_manager.validate_username(username)
        assert result["success"] is is_valid 

@pytest.fixture
def multi_device_tokens(auth_manager):
    """创建多设备的测试令牌"""
    print("\n=== 创建多设备测试令牌 ===")
    
    with freeze_time("2024-01-01 12:00:00"):  # 冻结时间
        # 1. 准备测试用户
        test_user = {
            "user_id": "test123",
            "username": "testuser",
            "roles": ["user"]
        }
        
        # 2. 准备测试设备
        devices = [
            {"id": "mobile", "name": "Mobile Phone"},
            {"id": "desktop", "name": "Desktop PC"}
        ]
        
        # 3. 为每个设备创建令牌
        tokens = []
        for device in devices:
            print(f"\n>>> 为设备创建令牌: {device}")
            token_data = {
                **test_user,
                "device_id": device["id"],
                "device_name": device["name"]
            }
            
            access_result = auth_manager.create_access_token(token_data)
            refresh_result = auth_manager.create_refresh_token(token_data)
            
            print(f">>> 访问令牌结果: {access_result}")
            print(f">>> 刷新令牌结果: {refresh_result}")
            
            assert access_result["success"], f"创建访问令牌失败: {access_result.get('error')}"
            assert refresh_result["success"], f"创建刷新令牌失败: {refresh_result.get('error')}"
            
            tokens.append({
                "access_token": access_result["token"],
                "refresh_token": refresh_result["token"],
                "device": device
            })
        
        return tokens, test_user

class TestMultiDeviceTokenManagement:
    """多终端令牌管理测试"""
    
    def test_list_user_devices(self, auth_manager, test_user):
        """测试列出用户设备"""
        print("\n=== 测试列出用户设备 ===")
        
        # 1. 准备测试数据：创建多个设备的令牌
        devices = [
            {"id": "device1", "name": "Device 1"},
            {"id": "device2", "name": "Device 2"}
        ]
        
        tokens = []
        for device in devices:
            print(f"\n>>> 为设备创建令牌: {device}")
            # 设置合适的过期时间
            token_data = {
                "user_id": test_user["user_id"],
                "username": test_user["username"],
                "device_id": device["id"],
                "device_name": device["name"],
                # 移除手动设置的过期时间，让 create_refresh_token 来处理
            }
            
            # 创建并存储令牌
            result = auth_manager.create_refresh_token(token_data)
            print(f">>> 创建令牌结果: {result}")
            assert result["success"], f"创建令牌失败: {result.get('error')}"
            tokens.append(result["token"])
            print(f">>> 令牌创建成功: {result['token'][:30]}...")
            
            # 验证新创建的令牌
            verify_result = auth_manager.verify_jwt(result["token"])
            print(f">>> 新令牌验证结果: {verify_result}")
            assert verify_result["success"], "新创建的令牌应该有效"
        
        # 2. 验证令牌存储
        storage = auth_manager._storage.get(owner_id=test_user["user_id"])
        print(f"\n>>> 存储的令牌: {storage}")
        assert storage is not None, "令牌存储不应为空"
        assert len(storage.tokens) == len(devices), f"期望 {len(devices)} 个令牌，实际有 {len(storage.tokens)} 个"
        
        # 3. 使用其中一个令牌列出设备
        test_token = tokens[0]
        print(f"\n>>> 使用令牌列出设备: {test_token[:30]}...")
        
        # 再次验证令牌
        verify_result = auth_manager.verify_jwt(test_token)
        print(f">>> 令牌验证结果: {verify_result}")
        assert verify_result["success"], f"令牌验证失败: {verify_result.get('error')}"
        
        # 列出设备
        result = auth_manager.list_user_devices(test_token)
        print(f">>> 列出设备结果: {result}")
        
        # 4. 详细验证结果
        assert isinstance(result, dict), f"返回值应该是字典，但得到了 {type(result)}"
        assert "success" in result, "返回值应该包含 success 字段"
        assert result["success"] is True, f"列出设备应该成功，但失败了: {result.get('error')}"
        assert "devices" in result, "返回值应该包含 devices 字段"
        assert isinstance(result["devices"], list), "devices 应该是列表"
        assert len(result["devices"]) == len(devices), f"设备数量不匹配: 期望 {len(devices)}，实际 {len(result['devices'])}"

    @freeze_time("2024-01-01 12:00:00")
    def test_single_device_logout(self, auth_manager, multi_device_tokens):
        """测试单个终端登出"""
        tokens, user = multi_device_tokens
        
        # 模拟第一个终端登出
        mobile_tokens = tokens[0]
        with freeze_time("2024-01-01 12:00:00"):  # 确保时间一致
            logout_result = auth_manager.logout_device(
                token=mobile_tokens["access_token"]
            )
            assert logout_result["success"] is True
            
            # 验证已登出终端的令牌无效
            mobile_access_valid = auth_manager.is_token_valid(
                mobile_tokens["access_token"], 
                "access"
            )
            assert mobile_access_valid["success"] is False
            
            # 验证其他终端的令牌仍然有效
            for device_tokens in tokens[1:]:
                access_valid = auth_manager.is_token_valid(
                    device_tokens["access_token"], 
                    "access"
                )
                assert access_valid["success"] is True

    def test_expired_tokens_cleanup(self, auth_manager, multi_device_tokens):
        """测试过期令牌自动理"""
        tokens, user = multi_device_tokens
        
        # 模一令牌过期
        expired_token = auth_manager._access_tokens[tokens[0]["access_token"]]
        expired_token.expire = datetime.utcnow() - timedelta(minutes=1)
        
        # 创建新的令牌应该触发过期令牌清理
        new_token_data = {
            "user_id": user["user_id"],
            "username": user["username"],
            "roles": user["roles"],
            "device": "new_device"
        }
        new_access_result = auth_manager.create_access_token(new_token_data)
        assert new_access_result["success"] is True
        
        # 验证过期令牌已被清理
        expired_valid = auth_manager.is_token_valid(
            tokens[0]["access_token"], 
            "access"
        )
        assert expired_valid["success"] is False

@pytest.fixture
def frozen_time():
    """固定测试时间"""
    test_time = datetime(2024, 1, 1, 12, 0, 0)  # 2024-01-01 12:00:00
    with freeze_time(test_time) as frozen:
        yield frozen

def test_basic_token_creation(auth_manager, frozen_time):
    """测试基本的令牌创建功能"""
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

@pytest.fixture(autouse=True)
def setup_env():
    """设置测试环境变量"""
    import os
    env_vars = {
        "FASTAPI_SECRET_KEY": "test-secret-key-for-testing-only",
        "FASTAPI_ALGORITHM": "HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
        "REFRESH_TOKEN_EXPIRE_DAYS": "7",
        "HASH_METHOD": "pbkdf2_sha256"
    }
    
    # 保存原始环境变量
    original_vars = {key: os.environ.get(key) for key in env_vars}
    
    # 设置测试环境变量
    os.environ.update(env_vars)
    
    yield
    
    # 恢复原始环境变量
    for key in env_vars:
        if key in original_vars and original_vars[key] is not None:
            os.environ[key] = original_vars[key]
        else:
            os.environ.pop(key, None)
