# features/environment.py
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from unittest.mock import Mock
from illufly.fastapi.user.models import UserRole, User
from datetime import datetime
from illufly.fastapi.user.endpoints import create_user_endpoints
import json

class JSONEncoder(json.JSONEncoder):
    """自定义 JSON 编码器"""
    def default(self, obj):
        if isinstance(obj, bool):
            return str(obj).lower()  # 布尔值转小写
        if isinstance(obj, (UserRole, set)):
            return list(obj) if isinstance(obj, set) else obj.value
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def before_all(context):
    """在所有测试开始前运行"""
    print("启动测试环境...")

def before_scenario(context, scenario):
    """每个场景开始前运行"""
    # 创建 mock 对象
    context.auth_manager = Mock()
    context.user_manager = Mock()
    context.existing_users = set()  # 用于跟踪已存在的用户
    
    # 设置默认返回值
    context.auth_manager.validate_username.return_value = {"success": True}
    context.auth_manager.validate_password.return_value = {"success": True}
    context.auth_manager.validate_email.return_value = {"success": True}
    
    # 根据输入参数返回不同的验证结果
    def mock_validate_username(username):
        if len(username) < 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="用户名长度不足"
            )
        if not username.replace('_', '').isalnum():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="用户名包含非法字符"
            )
        return {"success": True}
    
    def mock_validate_password(password):
        if len(password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="密码不符合强度要求"
            )
        if not all([
            any(c.isupper() for c in password),
            any(c.islower() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password)
        ]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="密码不符合强度要求"
            )
        return {"success": True}
    
    def mock_validate_email(email):
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="邮箱格式无效"
            )
        return {"success": True}
    
    # 设置验证函数
    context.auth_manager.validate_username = mock_validate_username
    context.auth_manager.validate_password = mock_validate_password
    context.auth_manager.validate_email = mock_validate_email
    
    # 设置 mock_storage
    context.storage = Mock()
    context.storage.has_duplicate.return_value = False
    context.storage.set.return_value = True

    context.auth_manager.hash_password.return_value = {
        "success": True,
        "hash": "hashed_password_123"
    }
    context.auth_manager.create_access_token = lambda data: {
        "success": True,
        "token": "mock_access_token",
        "expires_in": 3600
    }
    context.auth_manager.create_refresh_token = lambda data: {
        "success": True,
        "token": "mock_refresh_token",
        "expires_in": 86400
    }
    context.auth_manager.set_auth_cookies = lambda response, access_token, refresh_token: None
    context.auth_manager.verify_jwt = lambda token: {
        "success": True,
        "data": {"user_id": "mock-user-001"}
    }

    # 设置 mock_user_manager
    context.user_manager = Mock()
    
    def mock_create_user(username, password, email, roles, **kwargs):
        if username in context.existing_users:
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
    
    context.user_manager.create_user = mock_create_user
    
    def mock_exists_username(username: str):
        """检查用户名是否存在"""
        return username in context.existing_users
        
    context.user_manager.exists_username = mock_exists_username
    
    def mock_get_user_info(user_id):
        """返回完整的用户信息字典"""
        return {
            "user_id": user_id,
            "username": "mockuser",
            "email": "mock@example.com",
            "roles": ["user", "guest"],
            "is_locked": False,
            "is_active": True,
            "require_password_change": False
        }
    
    context.user_manager.get_user_info = mock_get_user_info
    context.user_manager._storage = context.storage

    # 设置 FastAPI 应用并使用真实的API实现
    app = FastAPI()
    create_user_endpoints(
        app,
        user_manager=context.user_manager,
        auth_manager=context.auth_manager
    )
    context.client = TestClient(app)
    # 令牌相关的 mock
    context.auth_manager.create_access_token = lambda data: {
        "success": True,
        "token": "mock_access_token",
        "expires_in": 3600
    }
    
    context.auth_manager.create_refresh_token = lambda data: {
        "success": True,
        "token": "mock_refresh_token",
        "expires_in": 86400
    }
    
    # Cookie 设置
    def mock_set_auth_cookies(response, access_token, refresh_token):
        """模拟设置认证Cookie"""
        if response:
            response.set_cookie(
                key="access_token",
                value=access_token,
                httponly=True,
                secure=True,
                samesite="lax",
                max_age=3600  # 1小时
            )
            response.set_cookie(
                key="refresh_token",
                value=refresh_token,
                httponly=True,
                secure=True,
                samesite="lax",
                max_age=86400  # 24小时
            )
    
    context.auth_manager.set_auth_cookies = mock_set_auth_cookies

    def mock_verify_invite_code(invite_code: str) -> bool:
        """验证邀请码"""
        if not invite_code:
            return True
        
        # 模拟无效的邀请码
        if invite_code == "INVALID_CODE":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid invite code"
            )
            
        # 可以添加更多邀请码验证逻辑
        valid_codes = {"VALID_CODE_1", "VALID_CODE_2"}
        if invite_code not in valid_codes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid invite code"
            )
            
        return True
    
    # 设置邀请码验证函数
    context.user_manager.verify_invite_code = mock_verify_invite_code
