from typing import List, Any, Dict, Optional
from pydantic import BaseModel, Field, ConfigDict, model_validator, field_validator
import uuid
from datetime import datetime

class TokenClaims(BaseModel):
    """令牌信息"""
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        from_attributes=True
    )
    
    user_id: str
    username: str = Field(default="")
    device_id: str = Field(default_factory=lambda: f"device_{uuid.uuid4().hex[:8]}")
    roles: List[str] = Field(default_factory=lambda: ["user"])
    exp: int = Field(default=0)
    iat: int = Field(default_factory=lambda: int(datetime.utcnow().timestamp()))
    token_type: str = Field(default="refresh")

    @model_validator(mode='before')
    @classmethod
    def set_defaults(cls, values: dict) -> dict:
        """初始化后处理"""
        if isinstance(values, dict):
            # 设置默认用户名
            values["username"] = values.get("username") or values["user_id"]
            
            # 处理角色列表
            roles = values.get("roles", ["user"])
            values["roles"] = [roles] if isinstance(roles, str) else roles

        return values

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        from ..users.models import UserRole
        
        def convert_role(role: Any) -> str:
            return role.value if isinstance(role, UserRole) else str(role)
            
        return {
            "user_id": self.user_id,
            "username": self.username,
            "device_id": self.device_id,
            "roles": [convert_role(role) for role in self.roles],
            "exp": self.exp,
            "iat": self.iat,
            "token_type": self.token_type,
        }

    @classmethod
    def create(cls, user_id: str, **kwargs) -> "TokenClaims":
        """便捷创建方法
        
        Args:
            user_id: 用户ID
            **kwargs: 其他可选参数，如roles、exp等
            
        Returns:
            TokenClaims: 令牌信息实例
            
        Examples:
            >>> token = TokenClaims.create("user123", roles=["admin"])
            >>> token = TokenClaims.create("user456", exp=1735689600)
        """
        return cls(user_id=user_id, **kwargs)

    @property
    def payload(self) -> dict:
        """返回令牌的payload数据"""
        return self.model_dump()  # 使用 model_dump 替代旧的 model_dump() 方法