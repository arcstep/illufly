from fastapi import APIRouter, Form, Depends, Response, HTTPException, status, Request
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, EmailStr, Field
from jose import JWTError
import uuid
import logging

from ...rocksdict import IndexedRocksDB
from ..models import Result
from .models import User, UserRole
from .tokens import TokensManager
from .users import UsersManager

logger = logging.getLogger(__name__)


class RegisterRequest(BaseModel):
    """注册请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")
    email: EmailStr = Field(..., description="邮箱")
    invite_code: Optional[str] = Field(None, description="邀请码")
    invite_from: Optional[str] = Field(None, description="邀请人的 user_id")

class LoginRequest(BaseModel):
    """登录请求
    支持用户从多个设备使用自动生成的设备ID同时登录。
    """
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")
    device_id: Optional[str] = Field(None, description="设备ID")

class UpdateUserProfileRequest(BaseModel):
    """更新用户个人设置请求"""
    settings: Dict[str, Any] = Field(..., description="用户个人设置")

class UpdateUserRolesRequest(BaseModel):
    """更新用户角色请求"""
    roles: List[str] = Field(..., description="用户角色列表")

class ChangePasswordRequest(BaseModel):
    """修改密码请求"""
    current_password: str = Field(..., description="当前密码")
    new_password: str = Field(..., description="新密码")

def create_users_endpoints(app, db: IndexedRocksDB, prefix: str="/api"):
    """创建用户相关的API端点

    Args:
        app: FastAPI应用实例
        db: 数据库实例
        prefix: API前缀
    """
    tokens_manager = TokensManager(db)
    users_manager = UsersManager(db)

    def set_auth_cookies(response: Response, access_token: str = None, device_id: str = None) -> None:
        """设置认证Cookie"""
        try:
            if access_token:
                response.set_cookie(
                    key="access_token",
                    value=access_token,
                    httponly=True,
                    secure=True,
                    samesite="Lax"
                )
            
        except Exception as e:
            logger.error(f"设置 cookies 时发生错误: {str(e)}")
            raise

    async def get_current_user(request: Request, response: Response) -> Dict[str, Any]:
        """获取当前用户信息，包含令牌刷新逻辑"""

        # 获取当前用户的访问令牌
        access_token = request.cookies.get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="令牌不存在，您必须登录获取刷新令牌和访问令牌"
            )

        # 验证访问令牌
        verify_result = tokens_manager.verify_access_token(access_token)
        
        if not verify_result.success:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="认证已过期，请重新登录"
            )

        payload = verify_result.data.payload
        if tokens_manager.is_access_token_revoked(access_token, payload['user_id']):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="令牌已撤销，请重新登录"
            )

        # 如果有新的访问令牌，设置到cookie中
        if verify_result.data.new_token:
            tokens_manager.set_auth_cookies(
                response,
                access_token=verify_result.data.new_token
            )
        return payload

    def require_roles(self, roles: Union["UserRole", List["UserRole"]], require_all: bool = False):
        """
        角色验证装饰器
        :param roles: 单个角色或角色列表
        :param require_all: 是否需要具备所有指定角色
        """
        from ..users import User, UserRole

        if isinstance(roles, UserRole):
            roles = [roles]

        async def role_checker(request: Request, response: Response) -> Dict[str, Any]:
            current_user = await self.get_current_user(request, response)
            user = User.model_validate(current_user)
            
            if require_all and not user.has_all_roles(roles):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="权限不足。需要所有指定的角色。"
                )
            
            if not require_all and not user.has_any_role(roles):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="权限不足。至少需要一个指定的角色。"
                )
            
            return current_user

        return role_checker

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
    async def register(request: RegisterRequest, response: Response):
        """用户注册接口"""
        try:
            # 验证邀请码（如果需要）
            if request.invite_code:
                used_success = users_manager.invite_manager.use_invite_code(request.invite_code, request.invite_from)
                if not used_success:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="邀请码无效"
                    )
            # 创建用户
            result = users_manager.create_user(
                username=request.username,
                password=request.password,
                email=request.email,
                roles=[UserRole.USER, UserRole.GUEST],
                require_password_change=False
            )
            if result.success:
                return result
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
    async def login(request: LoginRequest, response: Response):
        """用户登录接口"""
        try:
            # 验证密码
            verify_result = users_manager.verify_user_password(request.username, request.password)
            
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
            device_id = request.device_id or _create_browser_device_id(request)

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
            })

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
        current_user: dict = Depends(get_current_user)
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

            return Result.ok(message="Token refreshed successfully")

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
        current_user: dict = Depends(get_current_user)
    ):
        """注销接口"""
        # 获取当前设备的访问令牌
        device_id = request.cookies.get("device_id")
        revoke_result = tokens_manager.revoke_device_tokens(current_user["user_id"], device_id)
        if revoke_result:
            return revoke_result
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=revoke_result.error
            )

    @app.post(f"{prefix}/auth/logout-all-devices")
    async def logout_all_devices(
        current_user: dict = Depends(get_current_user)
    ):
        """撤销指定用户的所有令牌（访问令牌和刷新令牌）"""
        try:
            revoke_result = tokens_manager.revoke_all_user_tokens(current_user["user_id"])
            if revoke_result.success:
                return revoke_result
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
                return revoke_result
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
            return Result.ok(data=user_info)
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

    @app.patch(f"{prefix}/auth/profile")
    async def update_user_profile(
        request: UpdateUserProfileRequest,
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """更新当前用户的个人设置"""
        update_result = users_manager.update_user(current_user["user_id"], **request.settings)
        if update_result.success:
            return update_result
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=update_result.error
            )

    @app.post(f"{prefix}/auth/change-password")
    async def change_password(
        request: ChangePasswordRequest,
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """修改密码接口"""
        try:
            user_id = current_user["user_id"]
            result = users_manager.change_password(user_id, request.current_password, request.new_password)
            if result.success:
                return result
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
            return result
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
        return Result.ok(data=all_users)

    @app.post(f"{prefix}/users/{{user_id}}/roles")
    async def update_user_roles(
        user_id: str,
        request: UpdateUserRolesRequest,
        current_user: dict = Depends(tokens_manager.require_roles([UserRole.ADMIN, UserRole.OPERATOR]))
    ):
        """更新用户角色（管理员）"""
        # 更新用户角色
        result = users_manager.update_user_roles(user_id, request.roles)
        if result.success:
            return result
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

