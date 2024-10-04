from typing import List
from ..base import Runnable
from ..embeddings import BaseEmbeddings

class VectorDB(Runnable):
    """
    向量数据库。
    """

    def __init__(self, embeddings: BaseEmbeddings, top_k: int=None, **kwargs):
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
        yield from self.query(text, top_k or self.top_k)
