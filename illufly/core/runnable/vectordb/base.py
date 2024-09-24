from typing import List
from ..base import Runnable
from ..embeddings import BaseEmbeddings

class VectorDB(Runnable):
    """
    向量数据库。
    """

    def __init__(self, embeddings: BaseEmbeddings, top_k: int=None, **kwargs):
        super().__init__(**kwargs)
        self.embeddings = embeddings
        self.dim = self.embeddings.dim
        self.top_k = top_k or 5

    def query(self, vector: List[List[float]], top_k: int=None, **kwargs):
        pass

    def add(self, text: str, *args, **kwargs):
        pass

    def call(self, text: str, top_k: int=None, **kwargs):
        yield from self.query(text, top_k)
