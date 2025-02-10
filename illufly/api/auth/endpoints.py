from fastapi import FastAPI, Depends, Response, HTTPException, status, Request
from typing import Dict, Any, List, Optional, Callable, Union
from pydantic import BaseModel, EmailStr, Field
import uuid
import logging
from datetime import datetime, timedelta

from ...rocksdb import IndexedRocksDB
from ..models import Result
from .models import User, UserRole
from .tokens import TokensManager, TokenClaims
from .users import UsersManager

logger = logging.getLogger(__name__)


class RegisterRequest(BaseModel):
    """注册请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")
    email: EmailStr = Field(..., description="邮箱")

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

def _set_auth_cookies(response: Response, access_token: str = None) -> None:
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

def require_user(
    tokens_manager: TokensManager,
    users_manager: UsersManager,
    require_roles: Union[UserRole, List[UserRole]] = None,
    update_access_token: bool = True,
) -> Callable[[Request, Response], Dict[str, Any]]:
    """验证用户信息

    Args:
        tokens_manager: 令牌管理器
        users_manager: 用户管理器
        require_roles: 要求的角色
    """
    async def verified_user(
        request: Request,
        response: Response,
    ) -> Dict[str, Any]:
        """验证用户信息

        如果要求角色，则需要用户具备所有指定的角色。
        """

        # 获取当前用户的访问令牌
        access_token = request.cookies.get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="令牌不存在，您必须登录获取刷新令牌和访问令牌"
            )

        # 验证访问令牌
        verify_result = tokens_manager.verify_access_token(access_token)        
        if not verify_result.is_ok():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail=f"令牌验证失败: {verify_result.error}"
            )

        token_claims = verify_result.data
        logger.info(f"验证用户信息: {token_claims}")

        # 更新令牌到 response 的 cookie
        # JWT 的 encode 和 decode 通常基于对 CPU 可以忽略不计的 HMAC 计算
        if update_access_token:
            access_token = TokenClaims.create_access_token(**token_claims).jwt_encode()
            _set_auth_cookies(response, access_token)
            logger.info(f"设置令牌到 Cookie: {access_token}")

        # 如果要求所有角色，则需要用户具备指定的角色
        if require_roles and not UserRole.has_role(require_roles, token_claims['roles']):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足。需要指定的角色。"
            )

        return token_claims

    return verified_user

def create_auth_endpoints(
    app: FastAPI,
    tokens_manager: TokensManager,
    users_manager: UsersManager,
    prefix: str="/api"
):
    """创建认证相关的API端点

    Args:
        app: FastAPI应用实例
        tokens_manager: 令牌管理器
        users_manager: 用户管理器
        prefix: API前缀
    """

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
        register_data: RegisterRequest,
        response: Response,
    ):
        """用户注册接口"""
        try:
            # 创建用户
            user = User(
                username=register_data.username,
                email=register_data.email,
                password_hash=User.hash_password(register_data.password),
            )
            result = users_manager.create_user(user)
            if result.is_ok():
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
    async def login(
        login_data: LoginRequest,
        request: Request,
        response: Response,
    ):
        """登录接口"""
        try:
            # 验证用户密码
            verify_result = users_manager.verify_password(
                username=login_data.username,
                password=login_data.password
            )
            
            if verify_result.is_fail():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=verify_result.error or "认证失败"
                )
            
            user_info = verify_result.data
            logger.info(f"登录结果: {user_info}")

            # 检查用户状态
            if user_info['is_locked']:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="账户已锁定"
                )                
            if not user_info['is_active']:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="账户未激活"
                )
                
            # 获取或创建设备ID
            device_id = login_data.device_id or _create_browser_device_id(request)

            # 更新设备刷新令牌
            tokens_manager.update_refresh_token(
                user_id=user_info['user_id'],
                username=user_info['username'],
                roles=user_info['roles'],
                device_id=device_id
            )
            logger.info(f"更新设备刷新令牌: {device_id}")

            # 创建设备访问令牌
            result = tokens_manager.refresh_access_token(
                user_id=user_info['user_id'],
                device_id=device_id,
                username=user_info['username'],
                roles=user_info['roles']
            )
            logger.info(f"创建设备访问令牌: {result}")
            if result.is_ok():
                access_token = TokenClaims.create_access_token(**result.data).jwt_encode()
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=result.error
                )

            # 设置 http_only 的 cookie
            _set_auth_cookies(response, access_token=access_token)

            return Result.ok(
                data=result.data,
                message="登录成功"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"登录过程发生错误: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="登录过程发生错误"
            )

    @app.post(f"{prefix}/auth/logout")
    async def logout_device(
        request: Request,
        response: Response,
        token_claims: TokenClaims = Depends(require_user(tokens_manager, users_manager, update_access_token=False))
    ):
        """注销接口"""
        try:
            logger.info(f"要注销的用户信息: {token_claims}")

            # 撤销当前设备的访问令牌
            tokens_manager.revoke_refresh_token(
                user_id=token_claims['user_id'],
                device_id=token_claims['device_id']
            )
            logger.info(f"撤销当前设备的刷新令牌: {token_claims['user_id']}, {token_claims['device_id']}")

            # 撤销当前设备的访问令牌
            tokens_manager.revoke_access_token(
                user_id=token_claims['user_id'],
                device_id=token_claims['device_id']
            )
            logger.info(f"撤销当前设备的访问令牌: {token_claims['user_id']}, {token_claims['device_id']}")

            # 删除当前设备的cookie
            response.delete_cookie("access_token")
            logger.info(f"删除当前设备的cookie: {token_claims['user_id']}, {token_claims['device_id']}")

            return Result.ok(message="注销成功")

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )

    @app.get(f"{prefix}/auth/profile")
    async def get_user_profile(
        request: Request,
        response: Response,
        token_claims: TokenClaims = Depends(require_user(tokens_manager, users_manager))
    ):
        """获取当前用户信息"""
        return Result.ok(data=token_claims)

    @app.patch(f"{prefix}/auth/profile")
    async def update_user_profile(
        request: UpdateUserProfileRequest,
        response: Response,
        token_claims: TokenClaims = Depends(require_user(tokens_manager, users_manager))
    ):
        """更新当前用户的个人设置"""
        try:
            result = users_manager.update_user(token_claims.user_id, **request.settings)
            if result.is_ok():
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

    @app.post(f"{prefix}/auth/change-password")
    async def change_password(
        request: ChangePasswordRequest,
        response: Response,
        token_claims: TokenClaims = Depends(require_user(tokens_manager, users_manager))
    ):
        """修改密码接口"""
        try:
            result = users_manager.change_password(
                user_id=token_claims.user_id,
                current_password=request.current_password,
                new_password=request.new_password
            )
            if result.is_ok():
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

    return {
        "register": register,
        "login": login,
        "logout_device": logout_device,
        "change_password": change_password,
        "update_user_profile": update_user_profile,
        "get_user_profile": get_user_profile,
    }

