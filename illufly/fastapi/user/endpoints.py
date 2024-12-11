from fastapi import APIRouter, Depends, Response, HTTPException, status
from typing import Dict, Any, List
from ..auth import AuthManager
from .manager import UserManager
from .models import User, UserRole

def create_user_endpoints(
        app, 
        user_manager: UserManager, 
        auth_manager: AuthManager,
        prefix: str="/api"
    ):
    """用户相关的端点，主要处理用户信息和设置"""

    def _create_token_data(user_info: dict) -> dict:
        return {
            "user_id": user_info["user_id"],
            "username": user_info["username"],
            "email": user_info["email"],
            "roles": user_info["roles"],
            "is_locked": user_info["is_locked"],
            "is_active": user_info["is_active"],
            "need_password_change": user_info["need_password_change"],
        }

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
            username_valid, username_error = auth_manager.validate_username(username)
            if not username_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=username_error
                )

            # 验证邮箱
            email_valid, email_error = auth_manager.validate_email(email)
            if not email_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=email_error
                )

            # 验证密码强度
            password_valid, password_error = auth_manager.validate_password(password)
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
            success, _, user = user_manager.create_user(
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
            user_info = user_manager.get_user_info(user.user_id)
            if not user_info:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to retrieve user info"
                )

            # 自动登录
            token_data = _create_token_data(user_info)
            access_token = auth_manager.create_access_token(data=token_data)
            refresh_token = auth_manager.create_refresh_token(data=token_data)
            auth_manager.set_auth_cookies(response, access_token, refresh_token)

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
        user_info = user_manager.get_user_info(user_id)
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
        token_data = _create_token_data(user_info)

        # 创建令牌
        access_token = auth_manager.create_access_token(data=token_data)
        refresh_token = auth_manager.create_refresh_token(data=token_data)
        auth_manager.set_auth_cookies(response, access_token, refresh_token)

        # 返回必要的用户信息
        return {
            "user_id": user_info["user_id"],
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
        current_user: dict = Depends(auth_manager.get_current_user)
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

            password_valid, password_error = auth_manager.validate_password(new_password)
            if not password_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=password_error
                )

            result = user_manager.change_password(current_user["user_id"], current_password, new_password)
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
        current_user: dict = Depends(auth_manager.get_current_user)
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
            username = auth_manager.verify_jwt(refresh_token)
            if not username:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid refresh token"
                )

            user_info = user_manager.get_user_info(user_id, include_sensitive=False)
            access_token = auth_manager.create_access_token(data=user_info)
            auth_manager.set_auth_cookies(response, access_token=access_token)

            return {"access_token": access_token}

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )

    @app.post(f"{prefix}/auth/logout")
    async def logout(
        response: Response = None,
        current_user: dict = Depends(auth_manager.get_current_user)
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
        auth_manager.remove_user_tokens(current_user["username"])
        return {"message": "Logged out successfully"}

    @app.post(f"{prefix}/auth/revoke-token")
    async def revoke_token(
        username: str = Form(...),
        current_user = Depends(auth_manager.require_roles([UserRole.ADMIN]))
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
            if not user_manager.get_user_info(user_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User not found"
                )

            auth_manager.remove_user_tokens(username)
            
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
        current_user = Depends(auth_manager.require_roles([UserRole.ADMIN]))
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
            auth_manager.remove_user_tokens(username)
            
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

    return {
        "register": register,
        "login": login,
        "logout": logout,
        "refresh_token": refresh_token,
        "change_password": change_password,
        "revoke_token": revoke_token,
        "revoke_access_token": revoke_access_token
    }

    @app.get(f"{prefix}/users")
    async def list_users(
        current_user: dict = Depends(auth_manager.require_roles([UserRole.ADMIN, UserRole.OPERATOR]))
    ):
        """列出所有用户（需要管理员或运营角色）"""
        return user_manager.list_users(requester=current_user["user_id"])

    @app.post(f"{prefix}/users/roles")
    async def update_user_roles(
        user_id: str,
        roles: List[str],
        current_user: dict = Depends(auth_manager.require_roles(UserRole.ADMIN))
    ):
        """更新用户角色（仅管理员）"""
        # 检查用户是否存在
        user_info = user_manager.get_user_info(user_id)
        if not user_info:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )
        
        # 更新用户角色
        if user_manager.update_user_roles(user_id, roles):
            return {"message": "User roles updated successfully"}
        
        # 如果更新失败，返回错误信息
        raise HTTPException(
            status_code=400,
            detail="Failed to update user roles"
        )

    @app.get(f"{prefix}/users/me")
    async def get_current_user_info(
        current_user: dict = Depends(auth_manager.get_current_user)
    ):
        """获取当前用户信息"""
        user_id = current_user["user_id"]
        user_info = user_manager.get_user_info(user_id)
        if not user_info:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )
        return user_info

    @app.patch(f"{prefix}/users/me/settings")
    async def update_user_settings(
        settings: Dict[str, Any],
        current_user: dict = Depends(auth_manager.get_current_user)
    ):
        """更新用户设置"""
        user_id = current_user["user_id"]
        if user_manager.update_user(user_id, settings=settings):
            return {"message": "Settings updated successfully"}
        raise HTTPException(status_code=400, detail="Failed to update settings")

    @app.patch(f"{prefix}/users/me/password")
    async def change_password(
        password_data: dict,
        current_user: dict = Depends(auth_manager.get_current_user)
    ):
        """修改当前用户密码"""
        if user_manager.change_password(
            user_id=current_user["user_id"],
            old_password=password_data["old_password"],
            new_password=password_data["new_password"]
        ):
            return {"message": "Password changed successfully"}
        raise HTTPException(status_code=400, detail="Failed to change password")

    @app.post(f"{prefix}/users/{user_id}/reset-password")
    async def reset_user_password(
        user_id: str,
        password_data: dict,
        current_user: dict = Depends(auth_manager.require_roles(UserRole.ADMIN))
    ):
        """重置用户密码（管理员功能）"""
        if user_manager.reset_password(user_id, password_data["new_password"]):
            return {"message": "Password reset successfully"}
        raise HTTPException(status_code=400, detail="Failed to reset password")