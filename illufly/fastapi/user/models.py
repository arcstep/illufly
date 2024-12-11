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
    roles: Set[UserRole]
    email: str = None
    password_hash: str = None
    created_at: datetime = None
    require_password_change: bool = True
    last_password_change: Optional[datetime] = None  # 新增：最后修改密码时间
    password_expires_days: int = 90  # 新增：密码有效期（天数）
    last_login: Optional[datetime] = None
    failed_login_attempts: int = 0  # 新增：登录失败次数
    last_failed_login: Optional[datetime] = None  # 新增：最后一次登录失败时间
    is_locked: bool = False  # 新增：账户是否锁定
    is_active: bool = True

    def is_password_expired(self) -> bool:
        """检查密码是否过期"""
        if not self.last_password_change:
            return True
        days_since_change = (datetime.now() - self.last_password_change).days
        return days_since_change >= self.password_expires_days

    def record_login_attempt(self, success: bool):
        """记录登录尝试
        Args:
            success: 登录是否成功
        """
        if success:
            self.failed_login_attempts = 0
            self.last_login = datetime.now()
            self.last_failed_login = None
        else:
            self.failed_login_attempts += 1
            self.last_failed_login = datetime.now()
            if self.failed_login_attempts >= 5:  # 可配置的阈值
                self.is_locked = True

    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """转换为字典格式"""
        data = {
            "username": self.username,
            "email": self.email,
            "roles": [role.value for role in self.roles],
            "created_at": self.created_at.isoformat(),
            "require_password_change": self.require_password_change,
            "last_password_change": self.last_password_change.isoformat() if self.last_password_change else None,
            "password_expires_days": self.password_expires_days,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "failed_login_attempts": self.failed_login_attempts,
            "last_failed_login": self.last_failed_login.isoformat() if self.last_failed_login else None,
            "is_locked": self.is_locked,
            "is_active": self.is_active
        }
        
        if include_sensitive:
            data["password_hash"] = self.password_hash
            
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'User':
        """从字典创建用户对象"""
        return cls(
            username=data["username"],
            email=data.get("email", None),
            password_hash=data.get("password_hash", None),
            roles=set(UserRole(role) for role in data.get("roles", ["user"])),
            created_at=datetime.fromisoformat(data["created_at"]) if isinstance(data.get("created_at"), str) else data.get("created_at", None),
            require_password_change=data.get("require_password_change", True),
            last_password_change=datetime.fromisoformat(data["last_password_change"]) if data.get("last_password_change") else None,
            password_expires_days=data.get("password_expires_days", 90),
            last_login=datetime.fromisoformat(data["last_login"]) if data.get("last_login") else None,
            failed_login_attempts=data.get("failed_login_attempts", 0),
            last_failed_login=datetime.fromisoformat(data["last_failed_login"]) if data.get("last_failed_login") else None,
            is_locked=data.get("is_locked", False),
            is_active=data.get("is_active", True)
        )

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