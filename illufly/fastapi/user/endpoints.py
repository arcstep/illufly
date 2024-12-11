from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List
from ..auth import get_current_user, require_roles
from .models import UserRole

def create_user_endpoints(app, user_manager: "UserManager", prefix: str="/api"):
    """用户相关的端点，主要处理用户信息和设置"""

    @app.get(f"{prefix}/users")
    async def list_users(
        current_user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.OPERATOR]))
    ):
        """列出所有用户（需要管理员或运营角色）"""
        return user_manager.list_users(requester=current_user["username"])

    @app.post(f"{prefix}/users/{{username}}/roles")
    async def update_user_roles(
        username: str,
        roles: List[str],
        current_user: dict = Depends(require_roles(UserRole.ADMIN))
    ):
        """更新用户角色（仅管理员）"""
        return user_manager.update_user_roles(username, roles)

    @app.get(f"{prefix}/users/me")
    async def get_current_user_info(
        current_user: dict = Depends(get_current_user)
    ):
        """获取当前用户信息"""
        username = current_user["username"]
        user_info = user_manager.get_user_info(username)
        if not user_info:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )
        return user_info

    @app.patch(f"{prefix}/users/me/settings")
    async def update_user_settings(
        settings: Dict[str, Any],
        current_user: dict = Depends(get_current_user)
    ):
        """更新用户设置"""
        username = current_user["username"]
        if user_manager.update_user(username, settings=settings):
            return {"message": "Settings updated successfully"}
        raise HTTPException(status_code=400, detail="Failed to update settings")