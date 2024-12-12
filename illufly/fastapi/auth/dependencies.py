from fastapi import Request, Response, HTTPException, status, Depends
from typing import List, Union
from jose import JWTError


class AuthDependencies:
    def __init__(self, auth_manager: "AuthManager"):
        self.auth_manager = auth_manager

    async def get_current_user(self, request: Request, response: Response) -> dict:
        """获取当前用户信息，包含令牌刷新逻辑"""
        access_token = request.cookies.get("access_token")
        refresh_token = request.cookies.get("refresh_token")

        # 1. 验证访问令牌
        if access_token:
            token_valid = self.auth_manager.is_token_valid(access_token, "access")
            if token_valid["success"]:
                try:
                    verify_result = self.auth_manager.verify_jwt(access_token)
                    if verify_result["success"]:
                        return verify_result["payload"]
                except JWTError:
                    # 移除无效的访问令牌
                    self.auth_manager.invalidate_token(access_token)

        # 2. 尝试使用刷新令牌
        if refresh_token:
            refresh_valid = self.auth_manager.is_token_valid(refresh_token, "refresh")
            if refresh_valid["success"]:
                try:
                    refresh_result = self.auth_manager.verify_jwt(refresh_token)
                    if refresh_result["success"]:
                        # 创建新的访问令牌
                        new_token_result = self.auth_manager.create_access_token(refresh_result["payload"])
                        if new_token_result["success"]:
                            # 如果旧的访问令牌存在，使其失效
                            if access_token:
                                self.auth_manager.invalidate_token(access_token)
                            
                            # 设置新的访问令牌
                            self.auth_manager.set_auth_cookies(response, access_token=new_token_result["token"])
                            
                            return refresh_result["payload"]
                except JWTError:
                    self.auth_manager.invalidate_token(refresh_token)

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证已过期，请重新登录"
        )

    def require_roles(self, roles: Union["UserRole", List["UserRole"]], require_all: bool = False):
        """角色验证装饰器"""
        from ..user import User, UserRole

        if isinstance(roles, UserRole):
            roles = [roles]

        async def role_checker(current_user: dict = Depends(self.get_current_user)):
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