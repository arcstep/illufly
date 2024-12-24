from fastapi import APIRouter, Form, Depends, Response, HTTPException, status, Request
from typing import Dict, Any, List
from jose import JWTError
import uuid

from ..result import Result
from ..users import TokensManager, UsersManager, User, UserRole

def create_users_endpoints(
        app, 
        users_manager: UsersManager, 
        prefix: str="/api"
    ):
    """创建用户相关的API端点"""
    tokens_manager = users_manager.tokens_manager

    def _create_token_data(user_info: dict, device_id: str = "DEFAULT_DEVICE") -> dict:
        """从用户信息中提取JWT令牌所需的数据"""
        return {
            "device_id": device_id,
            "user_id": user_info["user_id"],
            "username": user_info["username"],
            "email": user_info["email"],
            "roles": user_info["roles"],
            "is_locked": user_info.get("is_locked", False),
            "is_active": user_info.get("is_active", True),
            "require_password_change": user_info.get("require_password_change", False)
        }

    def _create_refresh_token_and_access_token(user_id: str, token_data: dict) -> tuple[str, str]:
        """创建刷新令牌和访问令牌"""
        refresh_result = tokens_manager.create_refresh_token(data=token_data)
        if not refresh_result.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=refresh_result.error
            )
        
        refresh_token = refresh_result.data
        
        access_result = tokens_manager.refresh_access_token(refresh_token, user_id)
        if not access_result.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=access_result.error
            )
        
        access_token = access_result.data
        
        return refresh_token, access_token

    def _create_browser_device_id(request: Request) -> str:
        """为浏览器创建或获取设备ID
        
        优先从cookie中获取，如果没有则创建新的
        """
        existing_device_id = request.cookies.get("device_id")
        if existing_device_id:
            return existing_device_id
        
        user_agent = request.headers.get("user-agent", "unknown")
        os_info = "unknown_os"
        browser_info = "unknown_browser"
        
        if "Windows" in user_agent:
            os_info = "Windows"
        elif "Macintosh" in user_agent:
            os_info = "Mac"
        elif "Linux" in user_agent:
            os_info = "Linux"
        
        if "Chrome" in user_agent:
            browser_info = "Chrome"
        elif "Firefox" in user_agent:
            browser_info = "Firefox"
        elif "Safari" in user_agent and "Chrome" not in user_agent:
            browser_info = "Safari"
        
        return f"{os_info}_{browser_info}_{uuid.uuid4().hex[:8]}"

    @app.post(f"{prefix}/auth/register")
    async def register(
        username: str = Form(...),
        password: str = Form(...),
        email: str = Form(...),
        invite_code: str = Form(None),
        invite_from: str = Form(None),
        response: Response = None
    ):
        """用户注册接口"""
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
            if result.success:
                return result.to_dict()
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=result.error
                )

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
        device_id: str = Form(None),
    ):
        """用户登录接口"""
        try:
            # 验证密码
            verify_result = users_manager.verify_user_password(username, password)
            print(">>> verify_result: ", verify_result.to_dict())
            
            if not verify_result.success:
                if verify_result.data:
                    if verify_result.data.get("is_locked", False):
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="账户已锁定"
                        )
                    elif not verify_result.data.get("is_active", True):
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN, 
                            detail="账户未激活"
                        )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=verify_result.error or "认证失败"
                )
            
            user_info = verify_result.data["user"]
            require_password_change = verify_result.data["require_password_change"]
            
            # 获取或创建设备ID
            device_id = device_id or request.cookies.get("device_id") or _create_browser_device_id(request)

            token_data = _create_token_data(user_info, device_id)
            refresh_token, access_token = _create_refresh_token_and_access_token(
                user_info["user_id"], 
                token_data
            )
            
            tokens_manager.set_auth_cookies(
                response, 
                access_token=access_token, 
                refresh_token=refresh_token,
                device_id=device_id
            )

            return Result.ok({
                "user_info": user_info,
                "require_password_change": require_password_change
            }).to_dict()

        except HTTPException:
            raise
        except Exception as e:
            print(">>> Exception: ", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="登录过程发生错误"  # 模糊化具体错误
            )

    @app.post(f"{prefix}/auth/refresh-token")
    async def refresh_token(
        request: Request, 
        response: Response = None,
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """刷新Token接口"""
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

            return Result.ok(message="Token refreshed successfully").to_dict()

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"刷新令牌时发生错误: {str(e)}"
            )

    @app.post(f"{prefix}/auth/logout-device")
    async def logout_device(
        request: Request,
        response: Response,
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """注销接口"""
        # 获取当前设备的访问令牌
        device_id = request.cookies.get("device_id")
        revoke_result = tokens_manager.revoke_device_tokens(current_user["user_id"], device_id)
        if revoke_result:
            return revoke_result.to_dict()
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=revoke_result.error
            )

    @app.post(f"{prefix}/auth/logout-all-devices")
    async def logout_all_devices(
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """撤销指定用户的所有令牌（访问令牌和刷新令牌）"""
        try:
            revoke_result = tokens_manager.revoke_all_user_tokens(current_user["user_id"])
            if revoke_result.success:
                return revoke_result.to_dict()
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=revoke_result.error
                )

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )

    @app.post(f"{prefix}/auth/revoke-access-token")
    async def revoke_access_token(
        current_user = Depends(tokens_manager.require_roles([UserRole.ADMIN]))
    ):
        """撤销用户访问令牌接口（管理员）"""
        try:
            revoke_result = tokens_manager.revoke_user_access_tokens(current_user["user_id"])
            if revoke_result.success:
                return revoke_result.to_dict()
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=revoke_result.error
                )

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )

    @app.get(f"{prefix}/auth/profile")
    async def get_user_profile(
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """获取当前用户信息"""
        user_id = current_user["user_id"]
        user_info = users_manager.get_user_info(user_id)
        if user_info:
            return Result.ok(data=user_info).to_dict()
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

    @app.patch(f"{prefix}/auth/profile")
    async def update_user_profile(
        settings: Dict[str, Any],
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """更新当前用户的个人设置"""
        update_result = users_manager.update_user(current_user["user_id"], settings=settings)
        if update_result.success:
            return update_result.to_dict()
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=update_result.error
            )

    @app.post(f"{prefix}/auth/change-password")
    async def change_password(
        current_password: str = Form(...),
        new_password: str = Form(...),
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """修改密码接口"""
        try:
            user_id = current_user["user_id"]
            result = users_manager.change_password(user_id, current_password, new_password)
            if result.success:
                return result.to_dict()
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=result.error
                )

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )

    @app.get(f"{prefix}/auth/devices")
    async def list_devices(
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """列出用户的所有登录设备"""
        result = tokens_manager.list_user_devices(current_user["user_id"])
        if result.success:
            return result.to_dict()
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.error
            )

    @app.get(f"{prefix}/users")
    async def list_users(
        current_user: dict = Depends(tokens_manager.require_roles([UserRole.ADMIN, UserRole.OPERATOR]))
    ):
        """获取系统中所用户的列表（管理员或运营角色）"""
        all_users = users_manager.list_users()
        return Result.ok(data=all_users).to_dict()

    @app.post(f"{prefix}/users/{{user_id}}/roles")
    async def update_user_roles(
        user_id: str,
        roles: List[str] = Form(...),
        current_user: dict = Depends(tokens_manager.require_roles([UserRole.ADMIN, UserRole.OPERATOR]))
    ):
        """更新用户角色（管理员）"""
        # 更新用户角色
        result = users_manager.update_user_roles(user_id, roles)
        if result.success:
            return result.to_dict()
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.error
            )

    return {
        "register": register,
        "login": login,
        "refresh_token": refresh_token,
        "logout_device": logout_device,
        "logout_all_devices": logout_all_devices,
        "revoke_access_token": revoke_access_token,
        "list_users": list_users,
        "update_user_roles": update_user_roles,
        "update_user_profile": update_user_profile,
        "change_password": change_password,
        "get_user_profile": get_user_profile,
        "list_devices": list_devices,
    }

