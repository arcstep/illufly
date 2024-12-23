from datetime import datetime
from typing import List
from unittest.mock import Mock
from illufly.fastapi.user.models import UserRole, User
from illufly.fastapi.user.endpoints import UsersManager
from .auth_manager import AuthManagerMockFactory
import re

class UserManagerMockFactory:
    """用户管理器Mock工厂类"""
    
    @staticmethod
    def create(storage: dict) -> Mock:
        """创建UserManager的Mock实例"""
        users_manager = Mock()
        
        # 设置基础配置
        UserManagerMockFactory._setup_base_config(users_manager, storage)
        
        # 设置所有mock方法
        UserManagerMockFactory._setup_auth_methods(users_manager, storage)
        UserManagerMockFactory._setup_user_methods(users_manager, storage)
        UserManagerMockFactory._setup_validation_methods(users_manager)
        
        return users_manager

    @staticmethod
    def _setup_auth_methods(mock: Mock, storage: dict) -> None:
        """设置认证相关的mock方法"""
        # 在 mock 对象上存储状态
        mock._test_state = {
            'is_locked': False,
            'is_active': True
        }
        
        def mock_verify_user_password(username: str, password: str):
            print(f"DEBUG: Current test state: {mock._test_state}")
            
            # 构建用户信息
            user_info = {
                "user_id": "mock-user-001",
                "username": username,
                "email": f"{username}@example.com",
                "roles": ["user", "guest"],
                "is_locked": mock._test_state['is_locked'],
                "is_active": mock._test_state['is_active'],
                "require_password_change": False,
                "created_at": datetime.now().isoformat()
            }
            
            print(f"DEBUG: User info: {user_info}")
                
            # 检查账户状态
            if mock._test_state['is_locked']:
                print("DEBUG: Account is locked")
                return {
                    "success": False,
                    "error": "账户无法访问：账户已被锁定",
                    "is_locked": True,
                    "user": user_info
                }
                
            if not mock._test_state['is_active']:
                print("DEBUG: Account is inactive")
                return {
                    "success": False,
                    "error": "账户无法访问：账户未激活",
                    "is_active": False,
                    "user": user_info
                }
                
            # 再检查密码
            if password != 'Test123!@#':
                print("DEBUG: Password verification failed")
                return {
                    "success": False,
                    "error": "认证失败"
                }
                
            print("DEBUG: Login successful")
            # 正常登录
            return {
                "success": True,
                "user": user_info,
                "require_password_change": False
            }
            
        mock.verify_user_password.side_effect = mock_verify_user_password

    @staticmethod
    def _setup_validation_methods(mock: Mock) -> None:
        """设置验证相关的mock方法"""
        def mock_validate_username(username: str):
            """验证用户名
            - 长度在3-32个字符之间
            - 只能包含字母、数字和下划线
            """
            if len(username) < 3 or len(username) > 32:
                return {
                    "success": False,
                    "error": "用户名长度必须在3到32个字符之间"
                }
            
            if not re.match(r'^[a-zA-Z0-9_]+$', username):
                return {
                    "success": False,
                    "error": "用户名只能包含字母、数字和下划线"
                }

            if username.startswith("duplicate_"):
                return {
                    "success": False,
                    "error": "用户名已存在"
                }
            
            return {"success": True, "error": None}
        mock.validate_username.side_effect = mock_validate_username
        
        def mock_validate_password(password: str):
            """验证密码
            - 长度至少8个字符
            - 必须包含至少一个大写字母
            """
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
            return {"success": True, "error": None}
        mock.validate_password.side_effect = mock_validate_password
        
        def mock_validate_email(email: str):
            """验证邮箱格式
            - 必须符合标准邮箱格式
            """
            pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(pattern, email):
                return {
                    "success": False,
                    "error": "邮箱格式无效"
                }
            return {"success": True, "error": None}
        mock.validate_email.side_effect = mock_validate_email
        
        def mock_verify_invite_code(invite_code: str):
            """验证邀请码"""
            if invite_code.startswith("INVALID_"):
                return {
                    "success": False,
                    "error": "邀请码无效"
                }            
            return {
                "success": True,
                "error": None
            }

    @staticmethod
    def _setup_user_methods(mock: Mock, storage: dict) -> None:
        """设置用户相关的mock方法"""
        def mock_create_user(
            email: str,
            username: str = None,
            user_id: str = None,
            roles: List[str] = None,
            password: str = None,
            require_password_change: bool = True,
            password_expires_days: int = 90
        ):
            """模拟创建用户"""
            # 生成随机密码（如果没提供）
            generated_password = None
            if password:
                generated_password = "generated_password"
                password = generated_password

            user = User(
                user_id=user_id or "mock-user-001",
                username=username or email,
                email=email,
                password_hash=f"hashed_{password}",
                roles=set(roles or [UserRole.USER, UserRole.GUEST]),
                created_at=datetime.now(),
                require_password_change=require_password_change,
                password_expires_days=password_expires_days
            )
            storage['users'].append(user)

            return {
                "success": True,
                "generated_password": generated_password,
                "user": user,
                "error": None
            }
        mock.create_user.side_effect = mock_create_user

        def mock_get_user_info(user_id: str, include_sensitive: bool = False):
            """模拟获取用户信息"""
            print(">>> 获取用户信息", storage['users'])
            for user in storage['users']:
                if user.user_id == user_id:
                    return user.to_dict(include_sensitive=include_sensitive)
            return None
        mock.get_user_info.side_effect = mock_get_user_info

    @staticmethod
    def _setup_base_config(mock: Mock, storage: dict) -> None:
        """设置基础配置"""
        mock._storage = Mock()
        mock._storage.has_duplicate.return_value = False
        mock.auth_manager = AuthManagerMockFactory.create(storage)