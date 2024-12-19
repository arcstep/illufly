# illufly/bdd/features/mocks/auth.py

from datetime import datetime, timedelta
from unittest.mock import Mock
import re
from fastapi import Response, HTTPException, Depends, Request, status

class AuthManagerMockFactory:
    """认证管理器Mock工厂类"""
    
    @staticmethod
    def create(storage: dict) -> Mock:
        """创建AuthManager的Mock实例"""
        auth_manager = Mock()
        
        # 设置基础配置
        AuthManagerMockFactory._setup_base_config(auth_manager, storage)
        
        # 设置所有mock方法
        AuthManagerMockFactory._setup_jwt_methods(auth_manager, storage)
        AuthManagerMockFactory._setup_token_methods(auth_manager, storage)
        AuthManagerMockFactory._setup_password_methods(auth_manager, storage)
        AuthManagerMockFactory._setup_session_methods(auth_manager, storage)
        AuthManagerMockFactory._setup_device_methods(auth_manager, storage)
        AuthManagerMockFactory._setup_cookie_methods(auth_manager, storage)
        AuthManagerMockFactory._setup_user_methods(auth_manager, storage)
        
        return auth_manager
    
    @staticmethod
    def _setup_base_config(mock: Mock, storage: dict) -> None:
        """设置基础配置"""
        mock.secret_key = "test-secret-key"
        mock.algorithm = "HS256"
    
    @staticmethod
    def _setup_cookie_methods(mock: Mock, storage: dict) -> None:
        """设置Cookie相关的mock方法"""
        def mock_set_auth_cookies(response, access_token, refresh_token):
            if response:
                response.set_cookie(
                    key="access_token",
                    value=access_token,
                    httponly=True,
                    secure=True,
                    samesite="lax",
                    max_age=3600
                )
                response.set_cookie(
                    key="refresh_token",
                    value=refresh_token,
                    httponly=True,
                    secure=True,
                    samesite="lax",
                    max_age=86400
                )
                response.set_cookie(
                    key="device_id",
                    value="mock_device_id",
                    httponly=True,
                    secure=True,
                    samesite="lax",
                    max_age=86400 * 30
                )
                storage['tokens'].add_token(
                    access_token=access_token,
                    refresh_token=refresh_token,
                    device_id="mock_device_id"
                )
        mock.set_auth_cookies.side_effect = mock_set_auth_cookies
        
        def mock_clear_auth_cookies(response):
            if response:
                response.delete_cookie('access_token')
                response.delete_cookie('refresh_token')
                response.delete_cookie('device_id')
                storage['tokens'].remove_token(
                    access_token=access_token,
                    refresh_token=refresh_token,
                    device_id="mock_device_id"
                )
        mock.clear_auth_cookies.side_effect = mock_clear_auth_cookies
    
    @staticmethod
    def _setup_jwt_methods(mock: Mock, storage: dict) -> None:
        """设置JWT相关的mock方法"""
        def mock_verify_jwt(token: str, verify_exp: bool = True):
            if token == "invalid_token":
                return {
                    "success": False,
                    "error": "Invalid token"
                }
            return {
                "success": True,
                "data": {
                    "user_id": "test-user-001",
                    "username": "testuser",
                    "roles": ["user"],
                    "device_id": "test-device",
                    "exp": (datetime.utcnow() + timedelta(hours=1)).timestamp()
                }
            }
        mock.verify_jwt.side_effect = mock_verify_jwt
    
    @staticmethod
    def _setup_token_methods(mock: Mock, storage: dict) -> None:
        """设置令牌相关的mock方法"""
        # 存储令牌的字典
        def mock_create_access_token(data: dict):
            token = "mock_access_token"
            # 存储令牌
            mock._access_tokens[token] = {
                "user_id": data.get("user_id", "test-user-001"),
                "exp": datetime.utcnow() + timedelta(hours=1)
            }
            return {
                "success": True,
                "token": token,
                "expires_in": 3600
            }
        mock.create_access_token.side_effect = mock_create_access_token
        
        def mock_invalidate_access_token(token: str):
            """模拟令牌失效逻辑"""
            # 验证令牌
            if token not in mock._access_tokens:
                return {
                    "success": False,
                    "error": "Access token not found"
                }
            
            # 从存储中移除令牌
            storage['tokens'].remove_token(access_token=token)
            return {
                "success": True,
                "message": "Access token invalidated successfully"
            }
        mock.invalidate_access_token.side_effect = mock_invalidate_access_token
        
        def mock_create_refresh_token(data: dict):
            return {
                "success": True,
                "token": "mock_refresh_token",
                "expires_in": 86400
            }
        mock.create_refresh_token.side_effect = mock_create_refresh_token
        
        mock.invalidate_refresh_token.return_value = {
            "success": True,
            "message": "刷新令牌已成功撤销"
        }
        
        def mock_is_token_valid(token: str, token_type: str = "access"):
            """模拟令牌有效性验证"""
            # 验证令牌格式
            if not token or len(token.split(".")) != 3:
                return {
                    "success": False,
                    "error": "无效的令牌格式"
                }
            
            # 对于测试用的模拟令牌，始终返回有效
            if token in ["mock.refresh.token", "mock.access.token"]:
                return {"success": True}
            
            return {
                "success": False,
                "error": f"无效的{token_type}令牌"
            }
        
        mock.is_token_valid = Mock(side_effect=mock_is_token_valid)
        
        def mock_invalidate_token(token: str):
            """模拟令牌失效处理"""
            if not token or len(token.split(".")) != 3:
                return {
                    "success": False,
                    "error": "无效的令牌格式"
                }
            
            # 模拟令牌失效逻辑
            return {
                "success": True,
                "message": "令牌已成功失效"
            }
        
        mock.invalidate_token = Mock(side_effect=mock_invalidate_token)
        
        def mock_is_token_in_other_device(token: str, token_type: str = "refresh"):
            """模拟令牌设备验证"""
            return {
                "success": True  # 表示令牌未在其他设备使用
            }
        
        mock.is_token_in_other_device = Mock(side_effect=mock_is_token_in_other_device)
    
    @staticmethod
    def _setup_password_methods(mock: Mock, storage: dict) -> None:
        """设置密码相关的mock方法"""
        def mock_hash_password(password: str):
            return {
                "success": True,
                "hash": f"hashed_{password}"
            }
        mock.hash_password.side_effect = mock_hash_password
        
        def mock_verify_password(plain_password: str, hashed_password: str):
            expected_hash = f"hashed_{plain_password}"
            return {
                "success": expected_hash == hashed_password,
                "error": None if expected_hash == hashed_password else "密码错误"
            }
        mock.verify_password.side_effect = mock_verify_password
    
    @staticmethod
    def _setup_session_methods(mock: Mock, storage: dict) -> None:
        """设置会话相关的mock方法"""
        def mock_create_session(user_id: str, device_id: str = None):
            return {
                "success": True,
                "session_id": f"session_{user_id}_{device_id or 'default'}",
                "token_data": {
                    "access_token": "mock_access_token",
                    "refresh_token": "mock_refresh_token",
                    "token_type": "bearer",
                    "expires_in": 3600
                }
            }
        mock.create_session.side_effect = mock_create_session
        
        mock.invalidate_session.return_value = {
            "success": True,
            "message": "Session invalidated successfully"
        }
    
    @staticmethod
    def _setup_device_methods(mock: Mock, storage: dict) -> None:
        """设置设备相关的mock方法"""

        def mock_login(user_dict, password, password_hash, device_id, device_name, response: Response):
            """模拟登录验证
            
            Args:
                user_dict: 用户信息字典
                password: 用户提供的密码
                password_hash: 存储的密码哈希
                device_id: 设备ID
                device_name: 设备名称
                response: FastAPI响应对象
            
            Returns:
                dict: 登录结果
            """
            # 验证密码
            if password == "wrongpassword":
                return {
                    "success": False,
                    "error": "认证失败：用户名或密码错误"
                }
            
            # 验证密码哈希
            if f"hashed_{password}" != password_hash:
                return {
                    "success": False,
                    "error": "认证失败：密码错误"
                }
            
            # 成功登录的处理逻辑...
            access_token = f"mock.access.token_{device_id}"
            refresh_token = f"mock.refresh.token_{device_id}"
            mock.set_auth_cookies(response, access_token, refresh_token)
            
            return {
                "success": True,
                "message": "登录成功",
                "access_token": access_token,
                "refresh_token": refresh_token
            }
        mock.login.side_effect = mock_login
        
        def mock_logout_device(token: str, response):
            # 模拟设备登出
            for device_id, tokens in mock._device_tokens.items():
                if tokens["access_token"] == token or tokens["refresh_token"] == token:
                    mock.clear_auth_cookies(response)
                    return {
                        "success": True,
                        "message": "设备成功登出"
                    }
            return {
                "success": False,
                "message": "设备登出失败"
            }
        mock.logout_device.side_effect = mock_logout_device

        def mock_list_user_devices(user_id: str):
            # 返回所有设备信息
            devices = [
                {
                    "device_id": device_id,
                    "device_name": f"Device {device_id}",
                    "last_active": datetime.utcnow().isoformat(),
                    "is_current": tokens["access_token"] == token
                }
                for device_id, tokens in mock._device_tokens.items()
            ]
            return {
                "success": True,
                "devices": devices
            }
        mock.list_user_devices.side_effect = mock_list_user_devices

    @staticmethod
    def _setup_user_methods(mock: Mock, storage: dict) -> None:
        """设置用户相关的mock方法"""
        def mock_get_current_user(request: Request = None, response: Response = None):
            """简化的 get_current_user mock 实现"""
            # 不再尝试验证 token，直接返回模拟的用户数据
            return {
                "user_id": "test-user-001",
                "username": "testuser",
                "roles": ["user"],
                "device_id": "test-device"
            }
        
        mock.get_current_user = mock_get_current_user
        
        def mock_require_roles(required_roles):
            """模拟角色要求检查"""
            def check_user(request: Request = None):
                return {
                    "user_id": "test-user-001",
                    "username": "testuser",
                    "roles": ["admin"],
                    "device_id": "test-device"
                }
            return check_user
