"""
用户模块数据模型

定义用户相关的核心数据模型,包括用户角色和用户基础信息。
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Set, Union
from enum import Enum
from pydantic import BaseModel, Field, EmailStr, field_validator, constr, ConfigDict, model_validator, model_serializer
from ....utils import create_id_generator
import re

user_id_gen = create_id_generator()

class UserRole(str, Enum):
    """用户角色枚举"""
    ADMIN = "admin"          # 管理员
    OPERATOR = "operator"    # 运营人员
    USER = "user"           # 普通用户
    GUEST = "guest"         # 访客

    @classmethod
    def get_role_hierarchy(cls) -> Dict[str, List[str]]:
        """获取角色层级关系"""
        return {
            cls.ADMIN: [cls.OPERATOR, cls.USER, cls.GUEST],
            cls.OPERATOR: [cls.USER, cls.GUEST],
            cls.USER: [cls.GUEST],
            cls.GUEST: []
        }

class User(BaseModel):
    """用户基础信息模型"""
    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True
    )

    user_id: str = Field(..., description="用户唯一标识")
    username: constr(min_length=3, max_length=32) = Field(..., description="用户名")
    email: EmailStr = Field(..., description="电子邮箱")
    roles: Set[UserRole] = Field(
        default_factory=lambda: {UserRole.USER},
        description="用户角色集合"
    )
    password_hash: str = Field(..., description="密码哈希值")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    require_password_change: bool = Field(default=False, description="是否需要修改密码")
    last_password_change: Optional[datetime] = Field(default=None, description="最后密码修改时间")
    password_expires_days: int = Field(default=90, description="密码有效期(天)")
    last_login: Optional[datetime] = Field(default=None, description="最后登录时间")
    failed_login_attempts: int = Field(default=0, description="登录失败次数")
    last_failed_login: Optional[datetime] = Field(default=None, description="最后失败登录时间")
    is_locked: bool = Field(default=False, description="是否锁定")
    is_active: bool = Field(default=True, description="是否激活")

    def model_dump(
        self,
        *,
        mode: str = 'python',
        include: set[str] | None = None,
        exclude: set[str] | None = None,
        by_alias: bool = False,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
    ) -> dict[str, Any]:
        """自定义序列化方法"""
        data = {}
        for field_name, field_value in super().model_dump(
            mode=mode,
            include=include,
            exclude=exclude,
            by_alias=by_alias,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
        ).items():
            # 处理日期时间类型
            if isinstance(field_value, datetime):
                data[field_name] = field_value.isoformat()
            # 处理角色集合
            elif field_name == 'roles':
                data[field_name] = [role.value for role in field_value]
            else:
                data[field_name] = field_value
        return data

    @model_validator(mode='before')
    def set_defaults(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """初始化默认值"""
        values['user_id'] = values.get('user_id') or next(user_id_gen)
        values['username'] = values.get('username') or values['user_id']
        
        roles = values.get('roles', [UserRole.USER])
        if isinstance(roles, (str, UserRole)):
            roles = [roles]
        values['roles'] = {UserRole(r) if isinstance(r, str) else r for r in roles}

        return values

    def is_password_expired(self) -> bool:
        """检查密码是否过期"""
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
