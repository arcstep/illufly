from typing import Dict, Optional, Any, List
from datetime import datetime, timedelta
from pathlib import Path

from ....config import get_env
from ....io import ConfigStoreProtocol, JiaoziCache
from .models import InviteCode

class InviteCodeManager:
    def __init__(self, storage: Optional[ConfigStoreProtocol] = None):
        """初始化邀请码管理器
        Args:
            storage: 存储实现，如果为None则使用默认的文件存储
        """
        if storage is None:
            storage = JiaoziCache(
                data_dir=Path(get_env("ILLUFLY_CONFIG_STORE_DIR")),
                filename="invite_codes.json",
                data_class=List[InviteCode],
            )
        self._storage = storage

    def generate_new_invite_codes(self, count: int, owner_id: str, expired_days: int = 30) -> List[InviteCode]:
        """生成新的邀请码"""
        existing_codes = self.get_invite_codes(owner_id)        
        invite_codes = [InviteCode(
            invite_from=owner_id,
            expired_at=datetime.now() + timedelta(days=expired_days)
        ) for _ in range(count)]
        self._storage.set(existing_codes + invite_codes, owner_id)
        return invite_codes

    def get_invite_codes(self, owner_id: str) -> List[InviteCode]:
        """获取邀请码"""
        return self._storage.get(owner_id) or []

    def use_invite_code(self, invite_code: str, owner_id: str=None):
        """使用邀请码"""
        invite_codes = self.get_invite_codes(owner_id or 'admin')
        for code in invite_codes:
            if code.invite_code == invite_code and code.is_valid():
                code.use()
                self._storage.set(invite_codes, owner_id)
                return True
        return False

    def invite_code_is_valid(self, invite_code: str, owner_id: str) -> bool:
        """检查邀请码是否可用"""
        invite_codes = self.get_invite_codes(owner_id)
        for code in invite_codes:
            if code.invite_code == invite_code and code.is_valid():
                return True
        return False

    def delete_invite_code(self, invite_code: str, owner_id: str) -> bool:
        """删除特定邀请码
        
        Args:
            invite_code: 要删除的邀请码
            owner_id: 邀请码所有者ID
            
        Returns:
            bool: 是否成功删除
        """
        invite_codes = self.get_invite_codes(owner_id)
        original_length = len(invite_codes)
        invite_codes = [code for code in invite_codes if code.invite_code != invite_code]
        
        if len(invite_codes) != original_length:
            self._storage.set(invite_codes, owner_id)
            return True
        return False

    def cleanup_expired_codes(self, owner_id: str) -> int:
        """清理过期的邀请码
        
        Args:
            owner_id: 邀请码所有者ID
            
        Returns:
            int: 清理的邀请码数量
        """
        invite_codes = self.get_invite_codes(owner_id)
        original_length = len(invite_codes)
        invite_codes = [code for code in invite_codes if not code.is_expired()]
        
        self._storage.set(invite_codes, owner_id)
        return original_length - len(invite_codes)

    def get_usage_statistics(self, owner_id: str) -> Dict[str, int]:
        """获取邀请码使用统计
        
        Args:
            owner_id: 邀请码所有者ID
            
        Returns:
            Dict[str, int]: 包含总数、已使用、已过期、可用数量的统计信息
        """
        invite_codes = self.get_invite_codes(owner_id)
        total = len(invite_codes)
        used = sum(1 for code in invite_codes if code.is_used())
        expired = sum(1 for code in invite_codes if code.is_expired())
        available = sum(1 for code in invite_codes if code.is_valid())
        
        return {
            "total": total,
            "used": used,
            "expired": expired,
            "available": available
        }
