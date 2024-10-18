from typing import List
from ....io import EventBlock
from ....utils import raise_invalid_params
from ..base import Runnable
from ..embeddings import BaseEmbeddings

class VectorDB(Runnable):
    """
    向量数据库。
    """
    @classmethod
    def available_init_params(cls):
        return {
            "embeddings": "用于相似度计算的 embeddings 对象",
            "top_k": "返回结果的条数，默认 5",
            **Runnable.available_init_params()
        }

    def __init__(self, embeddings: BaseEmbeddings, top_k: int=None, **kwargs):
        raise_invalid_params(kwargs, self.__class__.available_init_params())

        if not isinstance(embeddings, BaseEmbeddings):
            raise ValueError(f"{embeddings} must be an instance of BaseEmbeddings")
        if embeddings.dim is None:
            raise ValueError(f"{embeddings} dim must be set")

        super().__init__(**kwargs)

        # 必须提供一个向量模型
        self.embeddings = embeddings
        self.dim = embeddings.dim
        self.top_k = top_k or 5

        # 向量数据库中备查的文档，包括了原始文档、元数据，以及由向量模型转换的向量索引
        self.documents = []

    def query(self, vector: List[List[float]], top_k: int=None, **kwargs):
        pass

    def add(self, text: str, *args, **kwargs):
        pass

    def call(self, text: str, top_k: int=None, **kwargs):
        self._last_output = self.query(text, top_k or self.top_k, **kwargs)
        yield EventBlock("info", f"查询到{len(self._last_output)}条结果")
