from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from typing import List, Any

import logging

from .models import TextIndexing
from .base_embeddings import BaseEmbeddings

class BaseVectorDB(ABC):
    """向量索引基类
    根据文本查询文档所在的键
    """
    def __init__(self, embeddings: BaseEmbeddings):
        self.embeddings = embeddings
        self._logger = logging.getLogger(__name__)

    @abstractmethod
    def create_collection(self, name: str, **kwargs) -> Any:
        """创建集合"""
        pass

    @abstractmethod
    def delete_collection(self, name: str, **kwargs) -> Any:
        """删除集合"""
        pass

    @abstractmethod
    def add(self, texts: List[str], collection_name: str = None, **kwargs) -> None:
        """添加文本，如果存在就更新"""
        pass

    @abstractmethod
    def delete(self, texts: List[str], collection_name: str = None, **kwargs) -> None:
        """删除文本"""
        pass

    @abstractmethod
    def query(self,  texts: List[str], collection_name: str = None, **kwargs) -> List[str]:
        """查询"""
        pass
