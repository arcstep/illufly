from fastapi import Request, Response, HTTPException, status
from typing import List, Union
from jose import JWTError

class AuthDependencies:
    def __init__(self, tokens_manager: "TokensManager"):
        self.tokens_manager = tokens_manager

    async def get_current_user(self, request: Request, response: Response) -> dict:
        """获取当前用户信息，包含令牌刷新逻辑"""
        access_token = request.cookies.get("access_token")
        print(">>> access_token: ", access_token)

        # 当访问令牌过期时，会自动尝试重新颁发访问令牌
        if access_token:
            verify_result = self.tokens_manager.verify_jwt(access_token, token_type="access")
            print(">>> verify_result: ", verify_result)
            if verify_result["success"]:
                payload = verify_result["payload"]
                is_revoked = self.tokens_manager.is_access_token_revoked(access_token, payload['user_id'])
                if not is_revoked:
                    return payload

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证已过期，请重新登录"
        )

    def require_roles(self, roles: Union["UserRole", List["UserRole"]], require_all: bool = False):
        """角色验证装饰器"""
        from ..users import User, UserRole

        if isinstance(roles, UserRole):
            roles = [roles]

        async def role_checker(request: Request, response: Response):
            current_user = await self.get_current_user(request, response)
            user = User.from_dict(current_user)
            
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