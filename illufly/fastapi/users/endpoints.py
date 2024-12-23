from fastapi import APIRouter, Form, Depends, Response, HTTPException, status, Request
from typing import Dict, Any, List
from jose import JWTError
import uuid

from ..users import TokensManager, UsersManager, User, UserRole

def create_users_endpoints(
        app, 
        users_manager: UsersManager, 
        tokens_manager: TokensManager,
        prefix: str="/api"
    ):
    """创建用户相关的API端点

    Args:
        app: FastAPI应用实例
        users_manager (UsersManager): 用户管理器实例
        tokens_manager (TokensManager): 认证管理器实例
        prefix (str, optional): API路由前缀. 默认为 "/api"

    Returns:
        dict: 包含所有注册的端点函数的字典
    """

    def _create_token_data(user_info: dict, device_id: str = "DEFAULT_DEVICE", device_name: str = "Default Device") -> dict:
        """从用户信息中提取JWT令牌所需的数据

        Args:
            user_info (dict): 用户信息字典

        Returns:
            dict: 包含令牌所需字段的字典，包括:
                - device_id: 设备ID
                - device_name: 设备名称
                - user_id: 用户ID
                - username: 用户名
                - email: 电子邮箱
                - roles: 用户角色列表
                - is_locked: 账户是否锁定
                - is_active: 账户是否激活
                - require_password_change: 是否需要修改密码
        """
        return {
            "device_id": device_id,
            "device_name": device_name,
            "user_id": user_info["user_id"],
            "username": user_info["username"],
            "email": user_info["email"],
            "roles": user_info["roles"],
            "is_locked": user_info.get("is_locked", False),
            "is_active": user_info.get("is_active", True),
            "require_password_change": user_info.get("require_password_change", False)
        }

    def _create_refresh_token_and_access_token(user_id: str, token_data: dict) -> dict:
        refresh_token = tokens_manager.create_refresh_token(data=token_data)
        if not refresh_token["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=refresh_token["error"]
            )
        
        access_token_result = tokens_manager.refresh_access_token(refresh_token, user_id)
        if not access_token_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=access_token_result["error"]
            )
        return refresh_token, access_token_result["token"]

    def _create_browser_device_id(request: Request) -> str:
        """为浏览器创建或获取设备ID
        
        优先从cookie中获取，如果没有则创建新的
        """
        existing_device_id = request.cookies.get("device_id")
        if existing_device_id:
            return existing_device_id
        
        return f"browser_{uuid.uuid4().hex[:8]}"

    @app.post(f"{prefix}/auth/register")
    async def register(
        username: str = Form(...),
        password: str = Form(...),
        email: str = Form(...),
        invite_code: str = Form(None),
        invite_from: str = Form(None),
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
        try:
            # 验证必填字段
            if not all([username, password, email]):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="缺少必填字段"
                )

            # 验证邀请码（如果需要）
            if invite_code:
                used_success = users_manager.invite_manager.use_invite_code(invite_code, invite_from)
                if not used_success:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="邀请码无效"
                    )

            # 创建用户
            result = users_manager.create_user(
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
            
            return {
                "success": True,
                "message": "User registered successfully"
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
        request: Request,
        response: Response,
        username: str = Form(...),
        password: str = Form(...),
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
                - 401: 认证失败
                - 403: 账户被锁定或未激活
                - 500: 服务器内部错误
        """

        # 获取或创建设备ID
        device_id = request.cookies.get("device_id") or _create_browser_device_id(request)
        
        # 设置设备cookie（http_only=False 允许前端读取设备ID）
        response.set_cookie(
            "device_id",
            device_id,
            httponly=False,
            secure=True,
            samesite="Lax"
        )
        
        # 创建令牌时使用固定的设备ID
        token_data = {
            "user_id": user_info["user_id"],
            "username": user_info["username"],
            "device_id": device_id,
            "device_name": device_name or f"Browser on {request.headers.get('User-Agent', 'Unknown')}"
        }

        try:
            # 验证密码
            verify_result = users_manager.verify_user_password(username, password)
            
            if not verify_result["success"]:
                if verify_result.get("is_locked"):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="账户已锁定"
                    )
                elif not verify_result.get("is_active", True):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN, 
                        detail="账户未激活"
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="认证失败"
                    )

            user_info = verify_result["user"]
            token_data = _create_token_data(user_info, device_id, device_name)
            if not token_data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to retrieve user info"
                )
            require_password_change = verify_result["require_password_change"]
            
            refresh_token, access_token = _create_refresh_token_and_access_token(user_info["user_id"], token_data)
            tokens_manager.set_auth_cookies(response, access_token["token"], refresh_token["token"])

            return {
                "success": True,
                "user_info": user_info,
                "require_password_change": require_password_change
            }
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="登录过程发生错误"  # 模糊化具体错误
            )

    @app.post(f"{prefix}/auth/change-password")
    async def change_password(
        current_password: str = Form(...),
        new_password: str = Form(...),
        current_user: dict = Depends(tokens_manager.get_current_user)
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
            user_id = current_user["user_id"]
            result = users_manager.change_password(user_id, current_password, new_password)
            if not result["success"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=result["error"]
                )
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
        request: Request, 
        response: Response = None,
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """刷新Token接口
        
        从 http_only cookie 中获取 Refresh-Token 并重新颁发新的 Access-Token
        
        Args:
            request: FastAPI请求对象，用于获取cookie
            response: FastAPI响应对象，用于设置新cookie
            
        Returns:
            dict: 包含新的令牌对
                - success: bool, 操作是否成功
                - access_token: str, 新的访问令牌
                - refresh_token: str, 新的刷新令牌
                
        Raises:
            HTTPException:
                - 400: 请求格式错误
                    - 缺少刷新令牌
                    - 无效的刷新令牌格式
                - 401: 认证失败
                    - 令牌已过期
                    - 令牌已被使用
                - 500: 服务器内部错误
                    - 获取用户信息失败
                    - 创建新令牌失败
                    - 使令牌失效失败
        """
        try:
            new_access_token = tokens_manager.refresh_access_token(
                refresh_token=request.cookies.get("refresh_token"),
                user_id=current_user["user_id"]
            )
            # 设置新的令牌cookie
            tokens_manager.set_auth_cookies(
                response,
                access_token=new_access_token["token"]
            )

            return {
                "success": True,
                "message": "Token refreshed successfully"
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"刷新令牌时发生错误: {str(e)}"
            )

    @app.post(f"{prefix}/auth/logout")
    async def logout(
        request: Request,
        response: Response,
        device_id: str = Form(...),
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """注销接口
        
        实现按设备退出的功能：
        1. 获取当前设备的访问令牌
        2. 使该令牌失效
        3. 清除当前设备的 Cookie
        
        Args:
            request: FastAPI请求对象
            response: FastAPI响应对象
            current_user: 当前用户信息
            
        Returns:
            dict: 成功消息
        """
        # 获取当前设备的访问令牌
        access_token = request.cookies.get("access_token")
        refresh_token = request.cookies.get("refresh_token")

        revoke_result = tokens_manager.revoke_device_tokens(current_user["user_id"], device_id)
        if not revoke_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=revoke_result["error"]
            )

        return {
            "success": True,
            "message": "Logged out successfully"
        }

    @app.post(f"{prefix}/auth/revoke-token")
    async def revoke_token(
        username: str = Form(...),
        current_user = Depends(tokens_manager.require_roles([UserRole.ADMIN]))
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
            if not users_manager.get_user_info(user_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User not found"
                )

            tokens_manager.remove_user_tokens(username)
            
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
        current_user = Depends(tokens_manager.require_roles([UserRole.ADMIN]))
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
            tokens_manager.remove_user_tokens(username)
            
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
        current_user: dict = Depends(tokens_manager.require_roles([UserRole.ADMIN, UserRole.OPERATOR]))
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
        return users_manager.list_users(requester=current_user["user_id"])

    @app.post(f"{prefix}/users/roles")
    async def update_user_roles(
        user_id: str = Form(...),
        roles: List[str] = Form(...),
        current_user: dict = Depends(tokens_manager.require_roles(UserRole.ADMIN))
    ):
        """更新用户角色（管理员）"""
        # 检查用户是否存在
        user_info = users_manager.get_user_info(user_id)
        if not user_info:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )
        
        # 更新用户角色
        if users_manager.update_user_roles(user_id, roles):
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
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """获取当前用户信息"""
        user_id = current_user["user_id"]
        user_info = users_manager.get_user_info(user_id)
        if not user_info:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )
        return user_info

    @app.patch(f"{prefix}/users/me/settings")
    async def update_user_settings(
        settings: Dict[str, Any],
        current_user: dict = Depends(tokens_manager.get_current_user)
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
        if users_manager.update_user(user_id, settings=settings):
            return {
                "success": True,
                "message": "Settings updated successfully"
            }
        raise HTTPException(status_code=400, detail="Failed to update settings")

    @app.patch(f"{prefix}/users/me/password")
    async def change_password(
        password_data: dict,
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """修改当前用户密码"""
        if users_manager.change_password(
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
        current_user: dict = Depends(tokens_manager.require_roles([UserRole.ADMIN]))
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
        result = tokens_manager.validate_password(new_password)
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["error"]
            )

        # 重置密码
        result = users_manager.reset_password(user_id, new_password)
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
        current_user: dict = Depends(tokens_manager.require_roles([UserRole.ADMIN]))
    ):
        result = users_manager.update_user_roles(user_id, roles)
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
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        result = users_manager.update_user(current_user["user_id"], **settings)
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["error"]
            )

        return {
            "success": True,
            "message": "Settings updated successfully"
        }

    @app.get(f"{prefix}/auth/devices")
    async def list_devices(current_user: dict = Depends(tokens_manager.get_current_user)):
        """列出用户的所有登录设备"""
        devices = tokens_manager.list_user_devices(current_user["user_id"])
        return {
            "devices": [
                {
                    "device_id": device_id,
                    "device_name": device_info["claims"].device_name,
                    "last_active": device_info["claims"].iat,
                    "is_current": device_id == current_user["device_id"]
                }
                for device_id, device_info in devices.items()
            ]
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
        "reset_user_password": reset_user_password,
        "list_devices": list_devices
    }
