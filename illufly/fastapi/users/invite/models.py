from typing import List, Any, Optional, Dict
from datetime import datetime, timedelta
from pydantic import BaseModel, Field, field_validator, ConfigDict, ValidationInfo
import secrets
import string

class InviteCode(BaseModel):
    """邀请码信息"""
    invite_code: str = Field(
        default_factory=lambda: ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8)),
        description="8位邀请码,由大写字母和数字组成"
    )
    invite_from: str = Field(default='admin', description="邀请人")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    expired_at: datetime = Field(
        default_factory=lambda: datetime.now() + timedelta(days=30),
        description="过期时间,默认30天"
    )
    used_at: Optional[datetime] = Field(default=None, description="使用时间")
    
    @field_validator('expired_at')
    def validate_expired_at(cls, v, info: ValidationInfo) -> datetime:
        """验证过期时间必须大于创建时间"""
        data = info.data  # 使用 ValidationInfo 对象获取数据
        if 'created_at' in data and v <= data['created_at']:
            raise ValueError('过期时间必须大于创建时间')
        return v

    def is_used(self) -> bool:
        """是否已使用"""
        return self.used_at is not None
    
    def is_expired(self, current_time: Optional[datetime] = None) -> bool:
        """是否已过期"""
        if current_time is None:
            current_time = datetime.now()
        return current_time > self.expired_at
    
    def is_valid(self, current_time: Optional[datetime] = None) -> bool:
        """是否有效(未使用且未过期)"""
        return not self.is_used() and not self.is_expired(current_time)
    
    def use(self, current_time: Optional[datetime] = None) -> bool:
        """使用邀请码,返回是否使用成功"""
        if self.is_valid(current_time):
            self.used_at = current_time or datetime.now()
            return True
        return False
