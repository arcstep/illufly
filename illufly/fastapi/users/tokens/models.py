from typing import List, Any, Dict, Union
from dataclasses import dataclass, field
from datetime import datetime
import uuid

@dataclass
class TokenClaims:
    """令牌信息"""
    user_id: str
    username: str = field(default="")
    device_id: str = field(default="")
    roles: List[str] = field(default_factory=list)
    exp: int = field(default=0)
    iat: int = field(default=0)
    token_type: str = field(default="refresh")

    def __post_init__(self):
        """初始化后处理"""
        if not self.username:
            self.username = self.user_id
        
        if not self.device_id:
            self.device_id = f"device_{uuid.uuid4().hex[:8]}"
        
        if isinstance(self.roles, str):
            self.roles = [self.roles]
        elif not self.roles:
            self.roles = ["user"]

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        from ..users.models import UserRole
        return {
            'user_id': self.user_id,
            'username': self.username,
            'device_id': self.device_id,
            'roles': [role.value if isinstance(role, UserRole) else role for role in self.roles],
            'exp': self.exp,
            'iat': self.iat,
            'token_type': self.token_type,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TokenClaims':
        """从字典创建实例
        
        Args:
            data: 包含令牌信息的字典
            
        Returns:
            TokenClaims: 令牌信息实例
            
        Examples:
            >>> data = {
            ...     'user_id': 'user123',
            ...     'username': 'john_doe',
            ...     'roles': ['admin', 'user']
            ... }
            >>> token = TokenClaims.from_dict(data)
        """
        from ..users.models import UserRole
        
        roles = data.get('roles', ['user'])
        if isinstance(roles, str):
            roles = [roles]
        
        device_id = data.get('device_id')
        if not device_id:
            device_id = f"device_{uuid.uuid4().hex[:8]}"

        return cls(
            user_id=data['user_id'],
            username=data.get('username', ''),
            device_id=device_id,
            roles=roles,
            exp=data.get('exp', 0),
            iat=data.get('iat', 0),
            token_type=data.get('token_type', 'refresh'),
        )

    @classmethod
    def create(cls, user_id: str, **kwargs) -> 'TokenClaims':
        """便捷创建方法
        
        Args:
            user_id: 用户ID
            **kwargs: 其他可选参数
            
        Returns:
            TokenClaims: 令牌信息实例
            
        Examples:
            >>> token = TokenClaims.create('user123', roles=['admin'])
        """
        return cls(user_id=user_id, **kwargs)