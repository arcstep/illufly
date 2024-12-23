from typing import List, Any, Optional, Dict
from datetime import datetime
from dataclasses import dataclass, field
import uuid
import time
import secrets
import string

@dataclass
class InviteCode:
    """邀请码信息"""
    invite_code: str = field(default_factory=lambda: ''.join(secrets.choice(string.digits) for _ in range(8)))
    invite_from: str = field(default='admin')
    created_at: Optional[datetime] = field(default_factory=lambda: datetime.now())
    expired_at: Optional[datetime] = field(default_factory=lambda: datetime.now() + timedelta(days=30))
    used_at: Optional[datetime] = None

    def is_used(self) -> bool:
        """是否已使用"""
        return self.used_at is not None
    
    def is_expired(self) -> bool:
        """是否已过期"""
        return self.expired_at < datetime.now()
    
    def use(self):
        """使用邀请码"""
        self.used_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'invite_code': self.invite_code,
            'invite_from': self.invite_from,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expired_at': self.expired_at.isoformat() if self.expired_at else None,
            'used_at': self.used_at.isoformat() if self.used_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'InviteCode':
        """从字典创建实例"""
        return cls(
            invite_code=data['invite_code'],
            invite_from=data['invite_from'],
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else None,
            expired_at=datetime.fromisoformat(data['expired_at']) if data.get('expired_at') else None,
            used_at=datetime.fromisoformat(data['used_at']) if data.get('used_at') else None,
        )
