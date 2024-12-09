"""
Knowledge Module Models

This module defines the knowledge-related data models.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import datetime

@dataclass
class Knowledge:
    """知识条目"""
    id: str
    content: str
    summary: str
    source: Optional[str]
    tags: List[str]
    created_at: datetime
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "id": self.id,
            "content": self.content,
            "summary": self.summary,
            "source": self.source,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Knowledge':
        """从字典创建知识对象"""
        return cls(
            id=data["id"],
            content=data["content"],
            summary=data["summary"],
            source=data.get("source"),
            tags=data.get("tags", []),
            created_at=datetime.fromisoformat(data["created_at"]) if isinstance(data["created_at"], str) else data["created_at"],
            updated_at=datetime.fromisoformat(data["updated_at"]) if isinstance(data.get("updated_at"), str) else data.get("updated_at")
        ) 