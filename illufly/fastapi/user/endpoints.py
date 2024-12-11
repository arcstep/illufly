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
        return user_manager.list_users(requester=current_user["user_id"])

    @app.post(f"{prefix}/users/roles")
    async def update_user_roles(
        user_id: str,
        roles: List[str],
        current_user: dict = Depends(require_roles(UserRole.ADMIN))
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
            return {"message": "User roles updated successfully"}
        
        # 如果更新失败，返回错误信息
        raise HTTPException(
            status_code=400,
            detail="Failed to update user roles"
        )

    @app.get(f"{prefix}/users/me")
    async def get_current_user_info(
        current_user: dict = Depends(get_current_user)
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
        current_user: dict = Depends(get_current_user)
    ):
        """更新用户设置"""
        user_id = current_user["user_id"]
        if user_manager.update_user(user_id, settings=settings):
            return {"message": "Settings updated successfully"}
        raise HTTPException(status_code=400, detail="Failed to update settings")

    @app.patch(f"{prefix}/users/me/password")
    async def change_password(
        password_data: dict,
        current_user: dict = Depends(get_current_user)
    ):
        """修改当前用户密码"""
        if user_manager.change_password(
            user_id=current_user["user_id"],
            old_password=password_data["old_password"],
            new_password=password_data["new_password"]
        ):
            return {"message": "Password changed successfully"}
        raise HTTPException(status_code=400, detail="Failed to change password")

    @app.post(f"{prefix}/users/{user_id}/reset-password")
    async def reset_user_password(
        user_id: str,
        password_data: dict,
        current_user: dict = Depends(require_roles(UserRole.ADMIN))
    ):
        """重置用户密码（管理员功能）"""
        if user_manager.reset_password(user_id, password_data["new_password"]):
            return {"message": "Password reset successfully"}
        raise HTTPException(status_code=400, detail="Failed to reset password")