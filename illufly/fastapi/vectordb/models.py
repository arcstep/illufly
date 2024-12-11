from typing import List, Any, Optional, Dict
from datetime import datetime
from dataclasses import dataclass, field

@dataclass
class VectorDBConfig:
    """向量数据库配置信息"""
    name: str                                      # 向量库名称
    db_type: str                                   # 向量库类型(如 'faiss', 'milvus' 等)
    description: str = ""                          # 描述信息
    embeddings_config: Dict[str, Any] = field(default_factory=dict)  # embeddings模型配置
    db_config: Dict[str, Any] = field(default_factory=dict)         # 数据库特定配置
    
    # 基础配置
    top_k: int = 5                                # 默认返回结果数量
    knowledge_path: str = ""                      # 知识库存储路径
    
    # 运行时配置
    created_at: Optional[datetime] = None         # 创建时间
    last_used: Optional[datetime] = None          # 最后使用时间
    is_active: bool = True                        # 是否激活
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'name': self.name,
            'type': self.db_type,
            'description': self.description,
            'embeddings_config': self.embeddings_config,
            'db_config': self.db_config,
            'top_k': self.top_k,
            'knowledge_path': self.knowledge_path,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'is_active': self.is_active
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VectorDBConfig':
        """从字典创建实例"""
        return cls(
            name=data['name'],
            db_type=data['type'],
            description=data.get('description', ''),
            embeddings_config=data.get('embeddings_config', {}),
            db_config=data.get('db_config', {}),
            top_k=data.get('top_k', 5),
            knowledge_path=data.get('knowledge_path', ''),
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else None,
            last_used=datetime.fromisoformat(data['last_used']) if data.get('last_used') else None,
            is_active=data.get('is_active', True)
        ) 