from fastapi import Request, HTTPException, status, Depends
from jose import JWTError
from typing import List, Union
from functools import wraps
from .utils import verify_jwt
from .whitelist import is_access_token_in_whitelist

async def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    try:
        if not is_access_token_in_whitelist(token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access-Token not in whitelist"
            )

        token_data = verify_jwt(token)
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Access-Token"
            )
        print("token_data", token_data)
        return token_data

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
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
        print("current_user", current_user)
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

    return Depends(role_checker)