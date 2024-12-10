"""
Auth Module Endpoints

This module defines the authentication-related API endpoints.
"""

from fastapi import Depends, HTTPException, status, Request, Response
from typing import Dict, Any
from datetime import datetime
from .utils import (
    hash_password,
    validate_password,
    validate_email,
    validate_username,
    create_access_token,
    create_refresh_token,
    set_auth_cookies
)

def create_auth_endpoints(app, user_manager: "UserManager", prefix: str="/api"):
    """创建认证相关的端点"""

    from ..user import User, UserRole, UserManager

    @app.post(f"{prefix}/auth/register")
    async def register(request: Request, response: Response):
        """
        用户注册
        
        请求体格式:
        {
            "username": str,
            "password": str,
            "email": str,
            "invite_code": str (optional)
        }
        """
        try:
            data = await request.json()
            username = data.get("username")
            password = data.get("password")
            email = data.get("email")
            invite_code = data.get("invite_code")

            # 验证必填字段
            if not all([username, password, email]):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Missing required fields"
                )

            # 验证用户名格式
            username_valid, username_error = validate_username(username)
            if not username_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=username_error
                )

            # 验证用户名是否已存在
            if user_manager.get_user_context(username):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username already registered"
                )

            # 验证邮箱
            email_valid, email_error = validate_email(email)
            if not email_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=email_error
                )

            # 验证密码强度
            password_valid, password_error = validate_password(password)
            if not password_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=password_error
                )

            # 验证邀请码（如果需要）
            if invite_code and not user_manager.verify_invite_code(invite_code):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid invite code"
                )

            # 创建用户（默认为普通用户角色）
            now = datetime.now()
            user = User(
                username=username,
                email=email,
                roles={UserRole.USER},  # 默认角色
                created_at=now,
                last_login=now
            )

            # 保存用户
            success = user_manager.create_user(
                user=user,
                password_hash=hash_password(password)
            )

            if not success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create user"
                )

            # 自动登录
            user_info = {
                "username": username,
                "email": email
            }
            access_token = create_access_token(data=user_info)
            refresh_token = create_refresh_token(data=user_info)
            set_auth_cookies(response, access_token, refresh_token)

            return user.to_dict()

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )

    @app.post(f"{prefix}/auth/login")
    async def login(request: Request, response: Response):
        """用户登录"""
        try:
            data = await request.json()
            username = data.get("username")
            password = data.get("password")

            if not all([username, password]):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Missing username or password"
                )

            user = user_manager.verify_user_password(username, password)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid username or password"
                )

            user_info = {
                "username": user.username,
                "email": user.email
            }
            access_token = create_access_token(data=user_info)
            refresh_token = create_refresh_token(data=user_info)
            set_auth_cookies(response, access_token, refresh_token)

            return user.to_dict()

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )
