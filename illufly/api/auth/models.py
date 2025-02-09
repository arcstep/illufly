"""
用户模块数据模型

定义用户相关的核心数据模型,包括用户角色和用户基础信息。
"""

from pydantic import BaseModel, Field, EmailStr, field_validator, constr, ConfigDict, model_validator, model_serializer
from argon2 import PasswordHasher
from typing import Optional, Dict, Any, List, Set, Union
from datetime import datetime, timedelta
from enum import Enum

import re
import uuid

from ...envir import get_env

class UserRole(str, Enum):
    """用户角色枚举"""
    @classmethod
    def get_role_hierarchy(cls) -> Dict[str, List[str]]:
        """获取角色层级关系"""
        return {
            cls.ADMIN: [cls.OPERATOR, cls.USER, cls.GUEST],
            cls.OPERATOR: [cls.USER, cls.GUEST],
            cls.USER: [cls.GUEST],
            cls.GUEST: []
        }

    ADMIN = "admin"          # 管理员
    OPERATOR = "operator"    # 运营人员
    USER = "user"           # 普通用户
    GUEST = "guest"         # 访客

class User(BaseModel):
    """用户基础信息模型"""
    @classmethod
    def can_update_field(cls, fields: List[str]) -> bool:
        """检查是否可以更新字段"""
        return all(field in ["username", "email", "mobile"] for field in fields)

    @staticmethod
    def generate_random_password(length: int = 12) -> str:
        """生成随机密码"""
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        password = ''.join(secrets.choice(alphabet) for _ in range(length-2))
        password += secrets.choice(string.digits)
        password += secrets.choice("!@#$%^&*")
        password_list = list(password)
        secrets.SystemRandom().shuffle(password_list)
        return ''.join(password_list)

    @classmethod
    def hash_password(cls, password: str) -> str:
        """密码加密"""
        ph = PasswordHasher()
        return ph.hash(password)

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True
    )

    # 用户必要信息
    username: constr(min_length=3, max_length=32) = Field(..., description="用户名")
    password_hash: str = Field(..., description="密码哈希值")

    # 用户ID
    user_id: str = Field(
        default_factory=lambda: f"u_{str(uuid.uuid4().hex)}",
        description="用户唯一标识"
    )

    # 用户联系方式
    email: EmailStr = Field(default="", description="电子邮箱")
    email_verified: bool = Field(default=False, description="邮箱是否验证")
    mobile: str = Field(default="", description="手机号")
    mobile_verified: bool = Field(default=False, description="手机号是否验证")

    # 用户角色
    roles: Set[UserRole] = Field(
        default_factory=lambda: {UserRole.USER},
        description="用户角色集合"
    )

    # 用户状态
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    require_password_change: bool = Field(default=False, description="是否需要修改密码")
    last_password_change: datetime = Field(default_factory=datetime.now, description="最后密码修改时间")
    password_expires_days: float = Field(default=90.0, description="密码有效期(天)")
    last_login: Optional[datetime] = Field(default=None, description="最后登录时间")
    failed_login_attempts: int = Field(default=0, description="登录失败次数")
    last_failed_login: Optional[datetime] = Field(default=None, description="最后失败登录时间")
    is_locked: bool = Field(default=False, description="是否锁定")
    is_active: bool = Field(default=True, description="是否激活")

    @field_validator('username')
    def validate_username(cls, v: str) -> str:
        """验证用户名格式"""
        if not v[0].isalpha():
            raise ValueError("用户名必须以字母开头")
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', v):
            raise ValueError("用户名只能包含字母、数字和下划线")
        return v

    @field_validator('roles', mode='before')
    def validate_roles(cls, v: Union[str, UserRole]) -> UserRole:
        """验证并转换角色值"""
        if isinstance(v, str):
            return UserRole(v)
        return v

    def verify_password(self, to_verify_password: str) -> bool:
        """密码验证"""
        if not to_verify_password:
            return False
        
        ph = PasswordHasher()
        ph.verify(self.password_hash, to_verify_password)

        if ph.check_needs_rehash(self.password_hash):
            self.password_hash = ph.hash(to_verify_password)
            return {"rehash": True}
        return {"rehash": False}
    
    def is_password_expired(self) -> bool:
        """检查密码是否过期

        使用 password_expires_days 设置密码过期时间，可以强制要求用户定期修改密码。
        """
        if not self.last_password_change:
            return True
        expiry_date = self.last_password_change + timedelta(days=self.password_expires_days)
        return datetime.now() >= expiry_date

    def record_login_attempt(self, success: bool) -> None:
        """记录登录尝试"""
        current_time = datetime.now()
        if success:
            self.failed_login_attempts = 0
            self.last_login = current_time
            self.last_failed_login = None
            self.is_locked = False
        else:
            self.failed_login_attempts += 1
            self.last_failed_login = current_time
            if self.failed_login_attempts >= 5:
                self.is_locked = True

    def has_role(self, role: Union[UserRole, str]) -> bool:
        """检查用户是否具有指定角色(包含继承的角色)"""
        role_obj = UserRole(role) if isinstance(role, str) else role
        if role_obj in self.roles:
            return True

        hierarchy = UserRole.get_role_hierarchy()
        return any(
            role_obj in hierarchy.get(user_role, [])
            for user_role in self.roles
        )

    def has_any_role(self, roles: List[Union[UserRole, str]]) -> bool:
        """检查用户是否具有任意一个指定角色"""
        return any(self.has_role(role) for role in roles)

    def has_all_roles(self, roles: List[Union[UserRole, str]]) -> bool:
        """检查用户是否具有所有指定角色"""
        return all(self.has_role(role) for role in roles)
