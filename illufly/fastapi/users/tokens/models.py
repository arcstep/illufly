from typing import List, Any, Dict
from dataclasses import dataclass, field

@dataclass
class TokenClaims:
    """令牌信息"""

    user_id: str
    username: str = field(default_factory=lambda: "")
    device_id: str = field(default="default_device_id")
    device_name: str = field(default="Default-Device")
    roles: List[str] = field(default_factory=lambda: ["user"])
    exp: int = field(default=0)
    iat: int = field(default=0)
    token_type: str = field(default="refresh")

    def __post_init__(self):
        if not self.username:
            self.username = self.user_id

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        from ..users.models import UserRole
        return {
            'user_id': self.user_id,
            'username': self.username,
            'device_id': self.device_id,
            'device_name': self.device_name,
            'roles': [role.value if isinstance(role, UserRole) else role for role in self.roles],
            'exp': self.exp,
            'iat': self.iat,
            'token_type': self.token_type,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TokenClaims':
        """从字典创建实例"""
        from ..users.models import UserRole
        return cls(
            user_id=data['user_id'],
            username=data['username'],
            device_id=data['device_id'],
            device_name=data['device_name'],
            roles=[UserRole(role) if isinstance(role, str) else role for role in data['roles']],
            exp=data['exp'],
            iat=data['iat'],
            token_type=data['token_type'],
        )