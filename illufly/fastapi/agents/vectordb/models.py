from typing import Dict, Any, Optional, ClassVar
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, model_validator

class VectorDBConfig(BaseModel):
    """向量数据库配置信息"""
    db_name: str
    vdb_config: Dict[str, Any] = Field(default_factory=dict)
    knowledge_config: Dict[str, Any] = Field(default_factory=dict)
    embeddings_config: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None

    # 默认配置
    DEFAULT_VDB_CONFIG: ClassVar[Dict[str, Any]] = {
        "vdb": "FaissDB",
        "params": {
            "top_k": 5,
            "device": "cpu",
            "batch_size": 1024
        }
    }
    
    DEFAULT_KNOWLEDGE_CONFIG: ClassVar[Dict[str, Any]] = {
        "knowledge": "LocalFileKnowledgeDB",
        "params": {}
    }
    
    DEFAULT_EMBEDDINGS_CONFIG: ClassVar[Dict[str, Any]] = {
        "embeddings": "TextEmbeddings",
        "params": {}
    }

    @model_validator(mode='before')
    def apply_defaults_and_validate(cls, values):
        """应用默认值和验证配置"""
        if 'created_at' not in values or values['created_at'] is None:
            values['created_at'] = datetime.now()

        def deep_update(d1: Dict, d2: Dict):
            """递归更新字典，保留已有值"""
            for k, v in d2.items():
                if k not in d1:
                    d1[k] = v
                elif isinstance(v, dict) and isinstance(d1[k], dict):
                    deep_update(d1[k], v)

        deep_update(values.get('vdb_config', {}), cls.DEFAULT_VDB_CONFIG)
        deep_update(values.get('knowledge_config', {}), cls.DEFAULT_KNOWLEDGE_CONFIG)
        deep_update(values.get('embeddings_config', {}), cls.DEFAULT_EMBEDDINGS_CONFIG)

        required_keys = {
            "vdb": ["vdb", "params"],
            "knowledge": ["knowledge", "params"],
            "embeddings": ["embeddings", "params"]
        }

        for config_name, keys in required_keys.items():
            config = values.get(f"{config_name}_config", {})
            for key in keys:
                if key not in config:
                    raise ValueError(f"Missing required key '{key}' in {config_name} configuration")

        return values

    model_config = ConfigDict(from_attributes=True)
