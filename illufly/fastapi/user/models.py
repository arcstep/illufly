"""
User Module Models

This module defines the core user-related data models.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, List, Set, Union
from enum import Enum

class UserRole(str, Enum):
    """用户角色枚举"""
    ADMIN = "admin"          # 管理员
    OPERATOR = "operator"    # 运营人员
    USER = "user"           # 普通用户
    GUEST = "guest"         # 访客

@dataclass
class User:
    """用户基础信息"""
    username: str
    email: str
    roles: Set[UserRole]    # 用户可以有多个角色
    created_at: datetime
    last_login: Optional[datetime] = None
    is_active: bool = True

    def __post_init__(self):
        # 确保 roles 是 set 类型且元素是 UserRole
        if isinstance(self.roles, (list, str)):
            self.roles = {UserRole(r) for r in self.roles}
        elif isinstance(self.roles, set):
            self.roles = {UserRole(r) for r in self.roles}
        
    def has_role(self, role: Union[UserRole, str]) -> bool:
        """检查用户是否具有指定角色"""
        if isinstance(role, str):
            role = UserRole(role)
        return role in self.roles

    def has_any_role(self, roles: List[Union[UserRole, str]]) -> bool:
        """检查用户是否具有任意一个指定角色"""
        return any(self.has_role(role) for role in roles)

    def has_all_roles(self, roles: List[Union[UserRole, str]]) -> bool:
        """检查用户是否具有所有指定角色"""
        return all(self.has_role(role) for role in roles)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "username": self.username,
            "email": self.email,
            "roles": [role.value for role in self.roles],
            "created_at": self.created_at.isoformat(),
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "is_active": self.is_active
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'User':
        """从字典创建用户对象"""
        return cls(
            username=data["username"],
            email=data["email"],
            roles=set(data.get("roles", ["user"])),  # 默认为普通用户
            created_at=datetime.fromisoformat(data["created_at"]) if isinstance(data["created_at"], str) else data["created_at"],
            last_login=datetime.fromisoformat(data["last_login"]) if isinstance(data.get("last_login"), str) else data.get("last_login"),
            is_active=data.get("is_active", True)
        )