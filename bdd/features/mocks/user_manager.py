from unittest.mock import Mock
from datetime import datetime
from fastapi import HTTPException, status
from illufly.fastapi.user.models import User

class UserManagerMockFactory:
    """用户管理器Mock工厂类"""
    
    @staticmethod
    def create() -> Mock:
        """创建UserManager的Mock实例"""
        user_manager = Mock()
        
        # 设置所有mock方法
        UserManagerMockFactory._setup_storage(user_manager)
        UserManagerMockFactory._setup_user_methods(user_manager)
        UserManagerMockFactory._setup_auth_methods(user_manager)
        UserManagerMockFactory._setup_validation_methods(user_manager)
        
        return user_manager

    @staticmethod
    def _setup_storage(mock: Mock) -> None:
        """设置存储相关的mock"""
        storage = Mock()
        storage.has_duplicate.return_value = False
        storage.set.return_value = True
        mock._storage = storage

    @staticmethod
    def _setup_user_methods(mock: Mock) -> None:
        """设置用户管理相关的mock方法"""
        def mock_create_user(username, password, email, roles, **kwargs):
            if username in getattr(mock, '_existing_users', set()):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="用户名已存在"
                )
            
            user = User(
                username=username,
                roles=set(roles),
                user_id="mock-user-001",
                email=email,
                password_hash=f"hashed_{password}",
                created_at=datetime.now(),
                is_active=True
            )
            return {"success": True, "user": user}
        mock.create_user = mock_create_user
        
        def mock_exists_username(username: str):
            return username in getattr(mock, '_existing_users', set())
        mock.exists_username = mock_exists_username
        
        def mock_get_user_info(user_id: str, include_sensitive: bool = False):
            # 基础用户信息
            user_info = {
                "user_id": user_id,
                "username": "mockuser",
                "email": "mock@example.com",
                "roles": ["user", "guest"],
                "is_locked": False,
                "is_active": True,
                "require_password_change": False,
                "created_at": datetime.now().isoformat()
            }
            
            # 如果需要包含敏感信息
            if include_sensitive:
                user_info.update({
                    "password_hash": "hashed_Test123!@#",
                    "last_password_change": None,
                    "failed_login_attempts": 0,
                    "last_failed_login": None
                })
                
            return user_info
        mock.get_user_info = mock_get_user_info
        
        # 初始化现有用户集合
        mock._existing_users = set()

    @staticmethod
    def _setup_auth_methods(mock: Mock) -> None:
        """设置认证相关的mock方法"""
        def mock_verify_user_password(username: str, password: str):
            if username == 'testuser' and password == 'Test123!@#':
                return {
                    "success": True,
                    "user": {
                        "user_id": "test-user-001",
                        "username": username,
                        "email": "test@example.com",
                        "roles": ["user", "guest"],
                        "is_locked": False,
                        "is_active": True,
                        "require_password_change": False
                    },
                    "require_password_change": False
                }
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )
        mock.verify_user_password.side_effect = mock_verify_user_password

    @staticmethod
    def _setup_validation_methods(mock: Mock) -> None:
        """设置验证相关的mock方法"""
        def mock_verify_invite_code(invite_code: str) -> bool:
            if not invite_code:
                return True
            
            if invite_code == "INVALID_CODE":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid invite code"
                )
                
            valid_codes = {"VALID_CODE_1", "VALID_CODE_2"}
            if invite_code not in valid_codes:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid invite code"
                )
                
            return True
        mock.verify_invite_code = mock_verify_invite_code