"""
Auth Module Endpoints

This module defines the authentication-related API endpoints.
"""

from fastapi import Depends, HTTPException, status, Request, Response, Form
from typing import Dict, Any
from datetime import datetime
from .dependencies import get_current_user, require_roles
from .whitelist import (
    remove_user_access_tokens,
    remove_user_refresh_tokens
)
from .utils import (
    validate_password,
    validate_email,
    validate_username,
    create_access_token,
    create_refresh_token,
    set_auth_cookies,
    verify_password,
    verify_jwt,
    hash_password
)

def create_auth_endpoints(app, user_manager: "UserManager", prefix: str="/api"):
    """创建认证相关的端点
    
    Args:
        app: FastAPI应用实例
        user_manager: 用户管理器实例
        prefix: API路由前缀
    """

    from ..user import User, UserRole, UserManager

    @app.post(f"{prefix}/auth/register")
    async def register(
        username: str = Form(...),
        password: str = Form(...),
        email: str = Form(...),
        invite_code: str = Form(None),
        response: Response = None
    ):
        """用户注册接口
        
        Args:
            username: 用户名
            password: 密码
            email: 电子邮箱
            invite_code: 邀请码(可选)
            response: FastAPI响应对象
            
        Returns:
            JSONResponse: 包含用户信息的响应
            
        Raises:
            HTTPException: 
                - 400: 参数验证失败
                - 500: 服务器内部错误
        """
        if not response:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Response is required"
            )
        try:
            # 验证必填字段
            if not all([username, password, email]):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="缺少必填字段"
                )

            # 验证用户名格式
            username_valid, username_error = validate_username(username)
            if not username_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=username_error
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

            # 创建用户
            success, _ = user_manager.create_user(
                username=username,
                password=password,
                email=email,
                roles=[UserRole.USER, UserRole.GUEST],
                require_password_change=False
            )

            if not success:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="用户名或邮箱已存在"
                )

            # 获取用户信息用于生成令牌
            user_info = user_manager.get_user_info(username)
            if not user_info:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to retrieve user info"
                )

            # 自动登录
            token_data = {
                "username": username,
                "email": email,
                "roles": user_info["roles"]
            }
            access_token = create_access_token(data=token_data)
            refresh_token = create_refresh_token(data=token_data)
            set_auth_cookies(response, access_token, refresh_token)

            return user_info

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )

    @app.post(f"{prefix}/auth/login")
    async def login(
        username: str = Form(...),
        password: str = Form(...),
        response: Response = None
    ):
        """用户登录接口
        
        Args:
            username: 用户名
            password: 密码
            response: FastAPI响应对象
            
        Returns:
            JSONResponse: 包含用户信息和认证令牌的响应
            
        Raises:
            HTTPException:
                - 400: 缺少用户名或密码
                - 401: 用户名或密码错误
                - 500: 服务器内部错误
        """
        if not response:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Response is required"
            )
            
        # 验证密码
        is_valid, need_change = user_manager.verify_user_password(username, password)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )

        # 获取用户信息
        user_info = user_manager.get_user_info(username)
        if not user_info:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )

        # 检查账户状态
        if user_info.get("is_locked"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is locked"
            )
            
        if not user_info.get("is_active"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive"
            )

        # 提取JWT所需的关键信息
        token_data = {
            "username": user_info["username"],
            "email": user_info["email"],
            "roles": user_info["roles"],
            "need_password_change": need_change
        }

        # 创建令牌
        access_token = create_access_token(data=token_data)
        refresh_token = create_refresh_token(data=token_data)
        set_auth_cookies(response, access_token, refresh_token)

        # 返回必要的用户信息
        return {
            "username": user_info["username"],
            "email": user_info["email"],
            "roles": user_info["roles"],
            "is_locked": user_info["is_locked"],
            "is_active": user_info["is_active"],
            "need_password_change": need_change
        }

    @app.post(f"{prefix}/auth/change-password")
    async def change_password(
        current_password: str = Form(...),
        new_password: str = Form(...),
        current_user: dict = Depends(get_current_user)
    ):
        """修改密码接口
        
        Args:
            current_password: 当前密码
            new_password: 新密码
            current_user: 当前用户信息
            
        Returns:
            dict: 成功消息
            
        Raises:
            HTTPException:
                - 400: 密码验证失败
                - 500: 服务器内部错误
        """
        try:
            try:
                valid_pass, _ = user_manager.verify_user_password(current_user["username"], current_password)
                if not valid_pass:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Current password is incorrect"
                    )
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=str(e)
                )

            password_valid, password_error = validate_password(new_password)
            if not password_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=password_error
                )

            result = user_manager.change_password(current_user["username"], current_password, new_password)
            if not result:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to change password"
                )
            return {"message": "Password changed successfully"}

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )

    @app.post(f"{prefix}/auth/refresh-token")
    async def refresh_token(
        refresh_token: str = Form(...),
        response: Response = None,
        current_user: dict = Depends(get_current_user)
    ):
        """刷新Token接口
        
        Args:
            refresh_token: 刷新令牌
            response: FastAPI响应对象
            
        Returns:
            dict: 新的访问令牌
            
        Raises:
            HTTPException:
                - 401: 刷新令牌无效
                - 500: 服务器内部错误
        """
        if not response:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Response is required"
            )
        try:
            username = verify_jwt(refresh_token)
            if not username:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid refresh token"
                )

            user_info = user_manager.get_user_context(username)
            access_token = create_access_token(data=user_info)
            set_auth_cookies(response, access_token=access_token)

            return {"access_token": access_token}

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )

    @app.post(f"{prefix}/auth/logout")
    async def logout(
        response: Response = None,
        current_user: dict = Depends(get_current_user)
    ):
        """注销接口
        
        Args:
            response: FastAPI响应对象
            current_user: 当前用户信息
            
        Returns:
            dict: 成功消息
        """
        if not response:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Response is required"
            )
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token")
        return {"message": "Logged out successfully"}

    @app.post(f"{prefix}/auth/revoke-token")
    async def revoke_token(
        username: str = Form(...),
        current_user = Depends(require_roles([UserRole.ADMIN]))
    ):
        """撤销用户令牌接口
        
        Args:
            username: 要撤销令牌的用户名
            role_checker: 当前管理员角色（通过依赖注入）
            
        Returns:
            dict: 成功消息
            
        Raises:
            HTTPException:
                - 400: 用户不存在
                - 403: 权限不足
                - 500: 服务器内部错误
        """
        try:
            # 检查目标用户是否存在
            if not user_manager.get_user_info(username):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User not found"
                )

            # 移除所有访问令牌和刷新令牌
            remove_user_access_tokens(username)
            remove_user_refresh_tokens(username)
            
            return {
                "message": f"Successfully revoked all tokens for user {username}",
                "username": username
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )

    @app.post(f"{prefix}/auth/revoke-access-token")
    async def revoke_access_token(
        username: str = Form(...),
        current_user = Depends(require_roles([UserRole.ADMIN]))
    ):
        """撤销用户访问令牌接口
        
        Args:
            username: 要撤销令牌的用户名
            role_checker: 当前管理员角色（通过依赖注入）
            
        Returns:
            dict: 成功消息
            
        Raises:
            HTTPException:
                - 400: 用户不存在
                - 403: 权限不足
                - 500: 服务器内部错误
        """
        try:
            # 移除所有访问令牌
            remove_user_access_tokens(username)
            
            return {
                "message": f"Successfully revoked access tokens for user {username}",
                "username": username
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )