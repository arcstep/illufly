# illufly/bdd/features/mocks/auth.py

from datetime import datetime, timedelta
from unittest.mock import Mock
import re
from typing import Dict, Any

class AuthManagerMockFactory:
    """认证管理器Mock工厂类"""
    
    @staticmethod
    def create() -> Mock:
        """创建AuthManager的Mock实例"""
        auth_manager = Mock()
        
        # 设置基础配置
        AuthManagerMockFactory._setup_base_config(auth_manager)
        
        # 设置所有mock方法
        AuthManagerMockFactory._setup_jwt_methods(auth_manager)
        AuthManagerMockFactory._setup_token_methods(auth_manager)
        AuthManagerMockFactory._setup_password_methods(auth_manager)
        AuthManagerMockFactory._setup_validation_methods(auth_manager)
        AuthManagerMockFactory._setup_session_methods(auth_manager)
        AuthManagerMockFactory._setup_device_methods(auth_manager)
        AuthManagerMockFactory._setup_cookie_methods(auth_manager)
        
        return auth_manager
    
    @staticmethod
    def _setup_base_config(mock: Mock) -> None:
        """设置基础配置"""
        mock.secret_key = "test-secret-key"
        mock.algorithm = "HS256"
        mock._access_tokens = {}
        mock._session_storage = Mock()
        mock._session_storage.get.return_value = {
            "user_id": "test-user-001",
            "device_id": "mock_device_id",
            "is_active": True
        }
        mock._session_storage.set.return_value = True
        mock._session_storage.delete.return_value = True
    
    @staticmethod
    def _setup_cookie_methods(mock: Mock) -> None:
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
        mock.set_auth_cookies.side_effect = mock_set_auth_cookies
        
        def mock_clear_auth_cookies(response):
            if response:
                response.delete_cookie('access_token')
                response.delete_cookie('refresh_token')
                response.delete_cookie('device_id')
        mock.clear_auth_cookies.side_effect = mock_clear_auth_cookies
    
    @staticmethod
    def _setup_jwt_methods(mock: Mock) -> None:
        """设置JWT相关的mock方法"""
        def mock_verify_jwt(token: str, verify_exp: bool = True):
            if token == "invalid_token":
                return {
                    "success": False,
                    "error": "Invalid token"
                }
            return {
                "success": True,
                "payload": {
                    "user_id": "test-user-001",
                    "username": "testuser",
                    "roles": ["user"],
                    "device_id": "test-device",
                    "exp": (datetime.utcnow() + timedelta(hours=1)).timestamp()
                }
            }
        mock.verify_jwt.side_effect = mock_verify_jwt
    
    @staticmethod
    def _setup_token_methods(mock: Mock) -> None:
        """设置令牌相关的mock方法"""
        def mock_create_access_token(data: dict):
            return {
                "success": True,
                "token": "mock_access_token",
                "expires_in": 3600
            }
        mock.create_access_token.side_effect = mock_create_access_token
        
        def mock_create_refresh_token(data: dict):
            return {
                "success": True,
                "token": "mock_refresh_token",
                "expires_in": 86400
            }
        mock.create_refresh_token.side_effect = mock_create_refresh_token
        
        # 令牌撤销相关方法
        mock.invalidate_access_token.return_value = {
            "success": True,
            "message": "访问令牌已成功撤销"
        }
        
        mock.invalidate_refresh_token.return_value = {
            "success": True,
            "message": "刷新令牌已成功撤销"
        }
    
    @staticmethod
    def _setup_password_methods(mock: Mock) -> None:
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
    def _setup_validation_methods(mock: Mock) -> None:
        """设置验证相关的mock方法"""
        # 添加用户名验证方法
        def mock_validate_username(username: str) -> Dict[str, Any]:
            if not username:
                return {
                    "success": False,
                    "error": "用户名不能为空"
                }
            
            if len(username) < 3 or len(username) > 32:
                return {
                    "success": False,
                    "error": "用户名长度必须在3到32个字符之间"
                }
            
            if not username[0].isalpha():
                return {
                    "success": False,
                    "error": "用户名必须以字母开头"
                }
            
            if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', username):
                return {
                    "success": False,
                    "error": "用户名只能包含字母、数字和下划线"
                }
            
            return {
                "success": True,
                "error": None
            }
        mock.validate_username = mock_validate_username

        # 添加邮箱验证方法
        def mock_validate_email(email: str) -> Dict[str, Any]:
            pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(pattern, email):
                return {
                    "success": False,
                    "error": "邮箱格式无效"
                }
            return {
                "success": True,
                "error": None
            }
        mock.validate_email = mock_validate_email

        # 添加密码验证方法
        def mock_validate_password(password: str) -> Dict[str, Any]:
            if len(password) < 8:
                return {
                    "success": False,
                    "error": "密码长度必须至少为8个字符"
                }
            
            if not re.search(r"[A-Z]", password):
                return {
                    "success": False,
                    "error": "密码必须包含至少一个大写字母"
                }
            
            if not re.search(r"[a-z]", password):
                return {
                    "success": False,
                    "error": "密码必须包含至少一个小写字母"
                }
            
            if not re.search(r"\d", password):
                return {
                    "success": False,
                    "error": "密码必须包含至少一个数字"
                }
            
            if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
                return {
                    "success": False,
                    "error": "密码必须包含至少一个特殊字符"
                }
            
            return {
                "success": True,
                "error": None
            }
        mock.validate_password = mock_validate_password
    
    @staticmethod
    def _setup_session_methods(mock: Mock) -> None:
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
    def _setup_device_methods(mock: Mock) -> None:
        """设置设备相关的mock方法"""
        def mock_list_user_devices(token: str):
            return {
                "success": True,
                "devices": [
                    {
                        "device_id": "test-device",
                        "device_name": "Test Device",
                        "last_active": datetime.utcnow().isoformat(),
                        "is_current": True
                    }
                ]
            }
        mock.list_user_devices.side_effect = mock_list_user_devices
        
        def mock_login(user_dict, password, password_hash, device_id, device_name):
            if password == "wrong_password":
                return {
                    "success": False,
                    "error": "密码错误"
                }
            return {
                "success": True,
                "access_token": "mock_access_token",
                "refresh_token": "mock_refresh_token",
                "token_type": "bearer"
            }
        mock.login.side_effect = mock_login
        
        def mock_logout_device(token: str):
            return {
                "success": True,
                "message": "设备已成功登出"
            }
        mock.logout_device.side_effect = mock_logout_device