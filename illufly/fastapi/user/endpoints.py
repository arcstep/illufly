from fastapi import APIRouter, Form, Depends, Response, HTTPException, status
from typing import Dict, Any, List
from ..auth import AuthManager
from .manager import UserManager
from .models import User, UserRole
from jose import JWTError

def create_user_endpoints(
        app, 
        user_manager: UserManager, 
        auth_manager: AuthManager,
        prefix: str="/api"
    ):
    """创建用户相关的API端点

    Args:
        app: FastAPI应用实例
        user_manager (UserManager): 用户管理器实例
        auth_manager (AuthManager): 认证管理器实例
        prefix (str, optional): API路由前缀. 默认为 "/api"

    Returns:
        dict: 包含所有注册的端点函数的字典
    """

    def _create_token_data(user_info: dict) -> dict:
        """从用户信息中提取JWT令牌所需的数据

        Args:
            user_info (dict): 用户信息字典

        Returns:
            dict: 包含令牌所需字段的字典，包括:
                - user_id: 用户ID
                - username: 用户名
                - email: 电子邮箱
                - roles: 用户角色列表
                - is_locked: 账户是否锁定
                - is_active: 账户是否激活
                - require_password_change: 是否需要修改密码
        """
        return {
            "user_id": user_info["user_id"],
            "username": user_info["username"],
            "email": user_info["email"],
            "roles": user_info["roles"],
            "is_locked": user_info.get("is_locked", False),
            "is_active": user_info.get("is_active", True),
            "require_password_change": user_info.get("require_password_change", False)
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
            result = auth_manager.validate_username(username)
            if not result["success"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=result["error"]
                )

            # 验证邮箱
            result = auth_manager.validate_email(email)
            if not result["success"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=result["error"]
                )

            # 验证密码强度
            result = auth_manager.validate_password(password)
            if not result["success"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=result["error"]
                )

            # 验证邀请码（如果需要）
            if invite_code and not user_manager.verify_invite_code(invite_code):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid invite code"
                )

            # 创建用户
            print(">>> username", username)
            result = user_manager.create_user(
                username=username,
                password=password,
                email=email,
                roles=[UserRole.USER, UserRole.GUEST],
                require_password_change=False
            )

            if not result["success"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=result["error"]
                )

            user = result["user"]
            # 获取用户信息用于生成令牌
            print(">>> user", user)
            user_info = user_manager.get_user_info(user.user_id)
            if not user_info:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to retrieve user info"
                )

            # 自动登录
            print(">>> user_info", user_info)
            token_data = _create_token_data(user_info)
            print(">>> token_data", token_data)
            access_token = auth_manager.create_access_token(data=token_data)
            refresh_token = auth_manager.create_refresh_token(data=token_data)
            auth_manager.set_auth_cookies(response, access_token["token"], refresh_token["token"])

            return {
                "success": True,
                "user_info": user_info
            }

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
        verify_result = user_manager.verify_user_password(username, password)
        if not verify_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=verify_result["error"]
            )

        user_info = verify_result["user"]
        require_password_change = verify_result["require_password_change"]

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

        token_data = _create_token_data(user_info)
        access_token = auth_manager.create_access_token(data=token_data)
        refresh_token = auth_manager.create_refresh_token(data=token_data)
        auth_manager.set_auth_cookies(response, access_token["token"], refresh_token["token"])

        return {
            "success": True,
            "token_data": token_data,
            "require_password_change": require_password_change
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
                verify_old_result = user_manager.verify_user_password(
                    username=current_user["username"],
                    password=current_password
                )
                if not verify_old_result["success"]:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=verify_old_result["error"]
                    )
                print(">>> verify_old_result", verify_old_result)
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=str(e)
                )

            validate_result = auth_manager.validate_password(new_password)
            if not validate_result["success"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=validate_result["error"]
                )
            print(">>> validate_result", validate_result)

            change_result = user_manager.change_password(
                user_id=current_user["user_id"],
                old_password=current_password,
                new_password=new_password
            )
            if not change_result["success"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=change_result["error"]
                )
            print(">>> change_result", change_result)

            return {
                "success": True,
                "message": "Password changed successfully"
            }

        except HTTPException:
            raise
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
            # 验证令牌格式
            if not refresh_token or len(refresh_token.split(".")) != 3:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="无效的刷新令牌格式"
                )

            # 首先验证刷新令牌是否有效
            valid_result = auth_manager.is_token_valid(refresh_token, "refresh")
            if not valid_result["success"]:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=valid_result.get("error", "刷新令牌无效")
                )

            # 验证并解码刷新令牌
            verify_result = auth_manager.verify_jwt(refresh_token)
            if not verify_result["success"]:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=verify_result.get("error", "刷新令牌验证失败")
                )

            # 获取最新的用户信息
            user_info = user_manager.get_user_info(current_user["user_id"])
            if not user_info:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="获取用户信息失败"
                )

            # 使旧的刷新令牌失效
            invalidate_result = auth_manager.invalidate_token(refresh_token)
            if not invalidate_result["success"]:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=invalidate_result.get("error", "使令牌失效失败")
                )

            # 创建新的令牌
            token_data = _create_token_data(user_info)
            access_token_result = auth_manager.create_access_token(data=token_data)
            if not access_token_result["success"]:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=access_token_result.get("error", "创建新访问令牌失败")
                )

            refresh_token_result = auth_manager.create_refresh_token(data=token_data)
            if not refresh_token_result["success"]:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=refresh_token_result.get("error", "创建新刷新令牌失败")
                )

            # 设置新的令牌cookie
            auth_manager.set_auth_cookies(
                response, 
                access_token_result["token"],
                refresh_token_result["token"]
            )

            return {
                "success": True,
                "access_token": access_token_result["token"],
                "refresh_token": refresh_token_result["token"]
            }

        except HTTPException:
            raise
        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"令牌验证失败: {str(e)}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"刷新令牌时发生错误: {str(e)}"
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

        return {
            "success": True,
            "message": "Logged out successfully"
        }

    @app.post(f"{prefix}/auth/revoke-token")
    async def revoke_token(
        username: str = Form(...),
        current_user = Depends(auth_manager.require_roles([UserRole.ADMIN]))
    ):
        """撤销指定用户的所有令牌（访问令牌和刷新令牌）

        Args:
            username (str): 要撤销令牌的用户名
            current_user (dict): 当前管理员用户信息（通过依赖注入）

        Returns:
            dict: 包含操作结果的字典:
                - success (bool): 操作是否成功
                - message (str): 操作结果消息
                - username (str): 被操作的用户名

        Raises:
            HTTPException:
                - 400: 用户不存在
                - 403: 当前用户权限不足
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
                "success": True,
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
                "success": True,
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

    @app.get(f"{prefix}/users")
    async def list_users(
        current_user: dict = Depends(auth_manager.require_roles([UserRole.ADMIN, UserRole.OPERATOR]))
    ):
        """获取系统中所用户的列表

        Args:
            current_user (dict): 当前用户信息（必须是管理员或运营角色）

        Returns:
            List[dict]: 用户信息列表，每个用户包含基本信息

        Raises:
            HTTPException:
                - 403: 权限不足
                - 500: 服务器内部错误
        """
        return user_manager.list_users(requester=current_user["user_id"])

    @app.post(f"{prefix}/users/roles")
    async def update_user_roles(
        user_id: str = Form(...),
        roles: List[str] = Form(...),
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
            return {
                "success": True,
                "message": "User roles updated successfully"
            }
        
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
        """更新当前用户的个人设置

        Args:
            settings (Dict[str, Any]): 要更新的设置键值对
            current_user (dict): 当前用户信息

        Returns:
            dict: 包含操作结果的字典:
                - success (bool): 操作是否成功
                - message (str): 操作结果消息

        Raises:
            HTTPException:
                - 400: 设置更新失败
                - 500: 服务器内部错误
        """
        user_id = current_user["user_id"]
        if user_manager.update_user(user_id, settings=settings):
            return {
                "success": True,
                "message": "Settings updated successfully"
            }
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
            return {
                "success": True,
                "message": "Password changed successfully"
            }
        raise HTTPException(status_code=400, detail="Failed to change password")

    @app.post(f"{prefix}/users/{{user_id}}/reset-password")
    async def reset_user_password(
        user_id: str,
        new_password: str = Form(...),
        current_user: dict = Depends(auth_manager.require_roles([UserRole.ADMIN]))
    ):
        """管理员重置指定用户的密码

        Args:
            user_id (str): 目标用户ID
            new_password: 新的密码
            current_user (dict): 当前管理员用户信息

        Returns:
            dict: 包含操作结果的字典:
                - success (bool): 操作是否成功
                - message (str): 操作结果消息

        Raises:
            HTTPException:
                - 400: 密码重置失败
                - 403: 权限不足
                - 500: 服务器内部错误
        """
        # 验证新密码强度
        result = auth_manager.validate_password(new_password)
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["error"]
            )

        # 重置密码
        result = user_manager.reset_password(user_id, new_password)
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["error"]
            )

        return {
            "success": True,
            "message": "Password reset successfully"
        }

    @app.patch(f"{prefix}/users/{{user_id}}/roles")
    async def update_user_roles(
        user_id: str,
        roles: List[str],
        current_user: dict = Depends(auth_manager.require_roles([UserRole.ADMIN]))
    ):
        result = user_manager.update_user_roles(user_id, roles)
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["error"]
            )

        return {
            "success": True,
            "message": "User roles updated successfully"
        }

    @app.patch(f"{prefix}/users/me/settings")
    async def update_user_settings(
        settings: Dict[str, Any],
        current_user: dict = Depends(auth_manager.get_current_user)
    ):
        result = user_manager.update_user(current_user["user_id"], **settings)
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["error"]
            )

        return {
            "success": True,
            "message": "Settings updated successfully"
        }

    return {
        "register": register,
        "login": login,
        "logout": logout,
        "refresh_token": refresh_token,
        "change_password": change_password,
        "revoke_token": revoke_token,
        "revoke_access_token": revoke_access_token,
        "list_users": list_users,
        "update_user_roles": update_user_roles,
        "get_current_user_info": get_current_user_info,
        "update_user_settings": update_user_settings,
        "reset_user_password": reset_user_password
    }
