from fastapi import Request, Response, HTTPException, status, Depends
from fastapi.responses import Response
from jose import JWTError
from typing import List, Union
from .utils import verify_jwt, create_access_token, set_auth_cookies
from .whitelist import (
    is_access_token_in_whitelist,
    is_refresh_token_valid,
    remove_access_token_from_whitelist
)

async def get_current_user(request: Request, response: Response) -> dict:
    """
    获取当前用户信息，包含令牌刷新逻辑
    """
    access_token = request.cookies.get("access_token")
    refresh_token = request.cookies.get("refresh_token")

    # 1. 验证访问令牌
    if access_token:
        if is_access_token_in_whitelist(access_token):
            try:
                payload = verify_jwt(access_token)
                if payload:
                    return payload
            except JWTError:
                remove_access_token_from_whitelist(access_token)

    # 2. 尝试使用刷新令牌
    if refresh_token:
        if is_refresh_token_valid(refresh_token):
            try:
                refresh_payload = verify_jwt(refresh_token)
                if refresh_payload:
                    # 创建新的访问令牌
                    new_access_token = create_access_token(refresh_payload)
                    
                    # 如果旧的访问令牌存在，从白名单中移除
                    if access_token:
                        remove_access_token_from_whitelist(access_token)
                    
                    # 直接在传入的 response 对象上设置 cookie
                    set_auth_cookies(response, access_token=new_access_token)
                    
                    return refresh_payload
            except JWTError:
                pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="认证已过期，请重新登录"
    )

def require_roles(roles: Union["UserRole", List["UserRole"]], require_all: bool = False):
    """
    角色验证装饰器
    
    Args:
        roles: 单个角色或角色列表
        require_all: True 表示需要具有所有指定角色，False 表示具有任意一个角色即可
    """
    from ..user import User, UserRole

    if isinstance(roles, UserRole):
        roles = [roles]

    async def role_checker(current_user: dict = Depends(get_current_user)):
        user = User.from_dict(current_user)
        
        if require_all and not user.has_all_roles(roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. All specified roles required."
            )
        
        if not require_all and not user.has_any_role(roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. At least one of the specified roles required."
            )
        
        return current_user

    return role_checker