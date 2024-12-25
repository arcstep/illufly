from abc import ABC, abstractmethod
from typing import Optional, Type
from pathlib import Path
from datetime import datetime
import importlib

from ....config import get_env
from ....core.runnable.vectordb import VectorDB
from ....community.dashscope import TextEmbeddings
from ....community.faiss import FaissDB
from ....io import LocalFileKnowledgeDB
from .models import VectorDBConfig

class BaseVectorDBFactory(ABC):
    """向量库工厂基类"""

    @abstractmethod
    def create_db_instance(
        self,
        user_id: str,
        db_name: str,        
        config: VectorDBConfig,
    ) -> Optional[VectorDB]:
        """创建向量库实例"""
        pass

class DefaultVectorDBFactory(BaseVectorDBFactory):
    """默认向量库工厂实现"""

    def create_db_instance(
        self,
        user_id: str,
        db_name: str,
        config: VectorDBConfig,
    ) -> Optional[VectorDB]:
        """创建向量库实例"""
        base_store_path = Path(get_env("ILLUFLY_CONFIG_STORE_DIR")) / user_id / "store"
        knowledge_db_path = str(base_store_path / db_name)
        Path(knowledge_db_path).mkdir(parents=True, exist_ok=True)

        # 配置已经在 VectorDBConfig 中验证过，可以直接使用
        embeddings = TextEmbeddings(**config.embeddings_config["params"])
        knowledge = LocalFileKnowledgeDB(knowledge_db_path)
        return FaissDB(
            name=db_name,
            embeddings=embeddings,
            knowledge=knowledge,
            **config.vdb_config["params"]
        )
