from typing import List, Any, Optional, Dict
from datetime import datetime
from dataclasses import dataclass, field

@dataclass
class VectorDBConfig:
    """向量数据库配置信息"""
    db_name: str                                  # 向量库名称
    vdb_config: Dict[str, Any] = field(default_factory=lambda: {})        # 数据库特定配置
    knowledge_config: Dict[str, Any] = field(default_factory=lambda: {})  # 知识库配置
    embeddings_config: Dict[str, Any] = field(default_factory=lambda: {}) # 向量模型配置
    created_at: Optional[datetime] = None         # 创建时间

    # 默认配置
    DEFAULT_VDB_CONFIG = {
        "vdb": "FaissDB",
        "params": {
            "top_k": 5,
            "device": "cpu",
            "batch_size": 1024
        }
    }
    
    DEFAULT_KNOWLEDGE_CONFIG = {
        "knowledge": "LocalFileKnowledgeDB",
        "params": {}
    }
    
    DEFAULT_EMBEDDINGS_CONFIG = {
        "embeddings": "TextEmbeddings",
        "params": {}
    }

    def __post_init__(self):
        """初始化后设置默认值和验证配置"""
        self.created_at = datetime.now()
        
        # 应用默认配置
        self._apply_defaults()
        
        # 验证配置
        self._validate_config(self.vdb_config, "vdb", ["vdb", "params"])
        self._validate_config(self.knowledge_config, "knowledge", ["knowledge", "params"])
        self._validate_config(self.embeddings_config, "embeddings", ["embeddings", "params"])

    def _apply_defaults(self):
        """应用默认配置"""
        def deep_update(d1: Dict, d2: Dict):
            """递归更新字典，保留已有值"""
            for k, v in d2.items():
                if k not in d1:
                    d1[k] = v
                elif isinstance(v, dict) and isinstance(d1[k], dict):
                    deep_update(d1[k], v)
        
        deep_update(self.vdb_config, self.DEFAULT_VDB_CONFIG)
        deep_update(self.knowledge_config, self.DEFAULT_KNOWLEDGE_CONFIG)
        deep_update(self.embeddings_config, self.DEFAULT_EMBEDDINGS_CONFIG)

    def _validate_config(self, config: Dict[str, Any], config_name: str, required_keys: List[str]):
        """验证配置是否包含必要的键"""
        for key in required_keys:
            if key not in config:
                raise ValueError(f"Missing required key '{key}' in {config_name} configuration")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'db_name': self.db_name,
            'vdb_config': self.vdb_config,
            'knowledge_config': self.knowledge_config,
            'embeddings_config': self.embeddings_config,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VectorDBConfig':
        """从字典创建实例"""
        return cls(
            db_name=data['db_name'],
            vdb_config=data.get('vdb_config', {}),
            knowledge_config=data.get('knowledge_config', {}),
            embeddings_config=data.get('embeddings_config', {}),
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else None,
        ) 
